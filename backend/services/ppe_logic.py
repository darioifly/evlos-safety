"""
Pure decision logic for PPE (helmet/vest) violation evaluation.

No torch / cv2 / DB imports: everything here operates on plain Python
structures so it can be unit-tested without the runtime stack and reused
by any worker implementation.

A "detection" is a dict:
    {'cls_name': str, 'conf': float, 'xyxy': (x1, y1, x2, y2)}
where cls_name is a CANONICAL class (see canonical_class) and xyxy can be
any indexable sequence (list, tuple, numpy array).

Design goals (fixes for the false-alert problems observed in production):
  * A violation box (novest/nohat) only counts if it is ASSOCIATED with a
    detected person — spurious boxes on background clutter are ignored.
    Association accepts persons down to a LOWER confidence floor than the
    person count does, so a truncated/occluded person (conf 0.35-0.5) can
    still own a confident violation box.
  * Persons that are too small in the frame (too far from the camera) are
    NOT judged for PPE: at that distance the model cannot resolve a vest,
    so any verdict would be noise.
  * Per-class confidence thresholds: violation classes need much stronger
    evidence (default 0.80) than compliance classes (default 0.45), because
    a false violation costs an alarm while a false compliance only delays it.
  * Vest-veto: if a person ALSO has an associated vest detection, novest
    boxes on that person are suppressed (YOLO NMS is per-class, so both can
    coexist on one torso; the tie goes to compliance).
  * Temporal N-of-M voting (TemporalViolationFilter): a violation must be
    seen in at least N of the last M analyzed frames — AND those votes must
    be recent (time-based expiry) — before it can alert.
"""
import time as _time
from collections import deque

# Classes that are irrelevant for helmet/vest compliance.
# (construction_safety.pt extras + SH17 body parts / other PPE)
IGNORED_CLASSES = {
    'machinery', 'vehicle', 'safety cone',
    'mask', 'no-mask',
    'ear', 'ear-mufs', 'face', 'face-guard', 'face-mask',
    'foot', 'hands', 'head', 'tool', 'glasses', 'gloves',
    'shoes', 'safety-suit', 'medical-suit',
}

# Violation classes need much stronger evidence than compliance classes.
# novest is the historical false-positive source (0.80); nohat proved
# reliable on real footage (true helmet violations landed at 0.77-0.81),
# so it gets a lower bar (0.70).
DEFAULT_CLASS_CONFIDENCE = {
    'person': 0.50,
    'vest': 0.45,
    'hat': 0.45,
    'novest': 0.80,
    'nohat': 0.70,
}

# Persons above this floor can OWN violation/compliance boxes even if they
# are below the 'person' counting threshold (truncated/occluded persons).
DEFAULT_ASSOCIATION_PERSON_CONFIDENCE = 0.35

# Person boxes shorter than this fraction of the frame height are too far
# away for a reliable vest/helmet verdict and are skipped. For a 16:9 frame
# this is roughly resolution-independent in model-input space.
DEFAULT_MIN_PERSON_HEIGHT_RATIO = 0.06

# Association: an item belongs to a person if its center falls inside the
# person box (expanded upward for helmets) or overlaps it substantially.
# The IoU disjunct is a fallback for odd geometry, so it is deliberately
# stricter than the old 0.10 (which let person-sized background boxes
# attach to nearby workers).
ASSOCIATION_IOU = 0.25
ASSOCIATION_TOP_EXPAND = 0.15


def canonical_class(cls_name):
    """Map a raw model class name to a canonical one.

    Returns one of 'person', 'hat', 'nohat', 'vest', 'novest', or None for
    classes that are irrelevant to helmet/vest compliance.

    Handles the naming of all models used so far:
      * wesjos helmet_vest.pt: person, hat, nohat, vest, novest
      * construction_safety.pt: Person, Hardhat, NO-Hardhat, Safety Vest,
        NO-Safety Vest (+ ignored: Mask, machinery, vehicle, Safety Cone...)
      * workspace_safety.pt: head_helmet, head_nohelmet, vest
      * SH17: safety-vest (+ many ignored body parts / other PPE)
    """
    n = cls_name.strip().lower()
    if n in IGNORED_CLASSES:
        return None
    if n == 'person':
        return 'person'
    if 'vest' in n:
        return 'novest' if 'no' in n.split('vest')[0] else 'vest'
    if 'helmet' in n or 'hat' in n:
        head = n.split('helmet')[0] if 'helmet' in n else n.split('hat')[0]
        return 'nohat' if 'no' in head else 'hat'
    return None


def iou(box_a, box_b):
    """Intersection over Union between two xyxy boxes."""
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_a = max(0.0, box_a[2] - box_a[0]) * max(0.0, box_a[3] - box_a[1])
    area_b = max(0.0, box_b[2] - box_b[0]) * max(0.0, box_b[3] - box_b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def is_associated(person_box, item_box,
                  top_expand=ASSOCIATION_TOP_EXPAND,
                  iou_threshold=ASSOCIATION_IOU):
    """True if item_box belongs to the person in person_box.

    The person box is expanded upward by top_expand * height so that a
    helmet sitting right on the box's top edge still associates.
    """
    person_h = person_box[3] - person_box[1]
    py1 = person_box[1] - top_expand * person_h
    cx = (item_box[0] + item_box[2]) / 2.0
    cy = (item_box[1] + item_box[3]) / 2.0
    center_in = (person_box[0] <= cx <= person_box[2] and
                 py1 <= cy <= person_box[3])
    return center_in or iou(person_box, item_box) > iou_threshold


def evaluate_ppe(detections, frame_height, *,
                 class_confidence=None,
                 min_person_height_ratio=DEFAULT_MIN_PERSON_HEIGHT_RATIO,
                 association_person_confidence=DEFAULT_ASSOCIATION_PERSON_CONFIDENCE,
                 require_helmet=True,
                 require_vest=True,
                 model_class_names=()):
    """Evaluate one frame's detections for PPE violations.

    Args:
        detections: list of canonical detection dicts (see module docstring).
        frame_height: height in pixels of the frame the boxes refer to.
        class_confidence: optional per-class threshold overrides.
        min_person_height_ratio: persons shorter than this fraction of the
            frame are not judged for PPE.
        association_person_confidence: floor for persons to OWN items.
        require_helmet / require_vest: which rules are active.
        model_class_names: raw class names of the loaded model, used to know
            whether it has explicit novest/nohat classes (fallback logic).

    Returns a dict:
        person_count        persons above the person threshold
        eligible_count      persons large enough for a PPE verdict
        violations          set among {'vest_missing', 'helmet_missing'}
        boxes               filtered detections (with flags) for annotation
        ignored_violations  violation boxes dropped as background/too-far
    """
    thresholds = dict(DEFAULT_CLASS_CONFIDENCE)
    if class_confidence:
        thresholds.update(class_confidence)
    person_threshold = thresholds.get('person', 0.50)
    association_floor = min(association_person_confidence, person_threshold)

    # Per-class confidence filter. Persons survive down to the association
    # floor (flagged 'counted' only above the person threshold).
    kept = []
    for d in detections:
        if d['cls_name'] == 'person':
            if d['conf'] >= association_floor:
                d['counted'] = d['conf'] >= person_threshold
                kept.append(d)
        elif d['conf'] >= thresholds.get(d['cls_name'], 1.0):
            kept.append(d)

    persons = [d for d in kept if d['cls_name'] == 'person']
    items = [d for d in kept if d['cls_name'] != 'person']

    # Size gate: PPE is only judged on persons close enough to resolve it.
    min_h = min_person_height_ratio * float(frame_height)
    for p in persons:
        box = p['xyxy']
        p['ppe_eligible'] = (box[3] - box[1]) >= min_h

    # Does the model have explicit violation classes? A person class?
    canon_names = {canonical_class(c) for c in model_class_names}
    has_explicit_novest = 'novest' in canon_names
    has_explicit_nohat = 'nohat' in canon_names
    has_person_class = 'person' in canon_names if model_class_names else True

    # A model WITHOUT a person class can never satisfy person association:
    # judge its explicit violation boxes directly (threshold still applies),
    # like the legacy behavior — otherwise the pipeline goes silent.
    if not has_person_class:
        violations = set()
        for item in items:
            if item['cls_name'] == 'novest' and require_vest:
                violations.add('vest_missing')
            elif item['cls_name'] == 'nohat' and require_helmet:
                violations.add('helmet_missing')
        return {
            'person_count': 0,
            'eligible_count': 0,
            'violations': violations,
            'boxes': kept,
            'ignored_violations': 0,
        }

    # Pass 1 — attach compliance items (vest/hat) to their owners.
    violation_items = []
    for item in items:
        owners = [p for p in persons if is_associated(p['xyxy'], item['xyxy'])]
        item['associated'] = bool(owners)
        if item['cls_name'] in ('vest', 'hat'):
            for p in owners:
                p.setdefault('items', set()).add(item['cls_name'])
        else:
            violation_items.append((item, owners))

    # Pass 2 — judge violation items now that worn items are known.
    violations = set()
    ignored_violations = 0
    for item, owners in violation_items:
        eligible_owners = [p for p in owners if p['ppe_eligible']]
        if not eligible_owners:
            # Background clutter or a person too far away to judge.
            ignored_violations += 1
            continue
        if item['cls_name'] == 'novest':
            # Vest-veto: if every eligible owner also has an associated
            # vest, the tie goes to compliance (NMS is per-class; both
            # boxes routinely coexist on one torso).
            if all('vest' in p.get('items', set()) for p in eligible_owners):
                item['vetoed_by_vest'] = True
                continue
            if require_vest:
                violations.add('vest_missing')
        elif item['cls_name'] == 'nohat':
            if all('hat' in p.get('items', set()) for p in eligible_owners):
                item['vetoed_by_hat'] = True
                continue
            if require_helmet:
                violations.add('helmet_missing')

    # Fallback for models WITHOUT explicit violation classes: an eligible,
    # fully-counted person with no associated compliance item is a
    # violation. (Kept at the stricter person threshold on purpose —
    # absence of evidence is weaker than an explicit violation box.)
    for p in persons:
        if not p['ppe_eligible'] or not p.get('counted', False):
            continue
        worn = p.get('items', set())
        if require_vest and not has_explicit_novest and 'vest' not in worn:
            violations.add('vest_missing')
        if require_helmet and not has_explicit_nohat and 'hat' not in worn:
            violations.add('helmet_missing')

    return {
        'person_count': sum(1 for p in persons if p.get('counted', False)),
        'eligible_count': sum(1 for p in persons if p['ppe_eligible']),
        'violations': violations,
        'boxes': kept,
        'ignored_violations': ignored_violations,
    }


class TemporalViolationFilter:
    """N-of-M temporal voting over per-frame violation sets.

    A violation type is CONFIRMED only when it appears in at least
    `min_hits` of the last `window` analyzed frames AND those votes are
    younger than `max_age_seconds`. Single-frame flicker never confirms;
    stale votes from before a stream drop, a mode switch or an overnight
    gap expire instead of combining with fresh noise.
    """

    def __init__(self, window=5, min_hits=3, max_age_seconds=90.0):
        self.window = max(1, int(window))
        self.min_hits = max(1, min(int(min_hits), self.window))
        self.max_age_seconds = float(max_age_seconds)
        self.history = deque(maxlen=self.window)  # (timestamp, frozenset)

    def update(self, violation_types, now=None):
        """Record one frame's violations; return the confirmed set."""
        if now is None:
            now = _time.time()
        self.history.append((now, frozenset(violation_types)))
        # Drop expired votes.
        cutoff = now - self.max_age_seconds
        while self.history and self.history[0][0] < cutoff:
            self.history.popleft()
        counts = {}
        for _, frame_set in self.history:
            for t in frame_set:
                counts[t] = counts.get(t, 0) + 1
        return {t for t, c in counts.items() if c >= self.min_hits}

    def reset(self):
        self.history.clear()

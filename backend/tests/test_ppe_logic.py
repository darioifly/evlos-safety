"""Unit tests for the pure PPE decision logic (services/ppe_logic.py).

These run without torch/cv2/DB — plain dicts in, verdicts out.
"""
import pytest

from services.ppe_logic import (
    TemporalViolationFilter,
    canonical_class,
    evaluate_ppe,
    iou,
    is_associated,
)

# Frame 1080p; a person >= 6% of height (65 px) is eligible for PPE.
FRAME_H = 1080

WESJOS_CLASSES = ['person', 'hat', 'nohat', 'vest', 'novest']
# A model WITH person but WITHOUT explicit novest (fallback vest logic).
FALLBACK_CLASSES = ['person', 'hat', 'nohat', 'vest']
# workspace_safety.pt: NO person class at all.
PERSONLESS_CLASSES = ['head_helmet', 'head_nohelmet', 'vest']


def det(cls_name, conf, x1, y1, x2, y2):
    return {'cls_name': cls_name, 'conf': conf, 'xyxy': (x1, y1, x2, y2)}


def person(x1=100, y1=100, x2=200, y2=400, conf=0.9):
    """A large, clearly eligible person (300 px tall)."""
    return det('person', conf, x1, y1, x2, y2)


def evaluate(dets, **kwargs):
    kwargs.setdefault('model_class_names', WESJOS_CLASSES)
    return evaluate_ppe(dets, FRAME_H, **kwargs)


# ---------------------------------------------------------------- canonical

@pytest.mark.parametrize('raw,expected', [
    # wesjos helmet_vest.pt
    ('person', 'person'), ('hat', 'hat'), ('nohat', 'nohat'),
    ('vest', 'vest'), ('novest', 'novest'),
    # construction_safety.pt
    ('Person', 'person'), ('Hardhat', 'hat'), ('NO-Hardhat', 'nohat'),
    ('Safety Vest', 'vest'), ('NO-Safety Vest', 'novest'),
    ('Mask', None), ('NO-Mask', None), ('machinery', None),
    ('vehicle', None), ('Safety Cone', None),
    # workspace_safety.pt
    ('head_helmet', 'hat'), ('head_nohelmet', 'nohat'),
    # SH17
    ('safety-vest', 'vest'), ('head', None), ('gloves', None),
    ('glasses', None), ('tool', None),
])
def test_canonical_class(raw, expected):
    assert canonical_class(raw) == expected


# ------------------------------------------------------------- association

def test_iou_disjoint_and_identical():
    assert iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == pytest.approx(1.0)


def test_association_center_inside():
    assert is_associated((100, 100, 200, 400), (130, 200, 170, 260))


def test_association_helmet_above_top_edge():
    # Helmet center slightly ABOVE the person box top: still associated
    # thanks to the upward expansion.
    assert is_associated((100, 100, 200, 400), (130, 70, 170, 105))


def test_association_far_box_rejected():
    assert not is_associated((100, 100, 200, 400), (500, 500, 540, 560))


# ------------------------------------------------- background false alarms

def test_novest_without_person_is_ignored():
    """The Velletri failure mode: novest on background clutter, no person."""
    result = evaluate([det('novest', 0.85, 500, 500, 540, 560)])
    assert result['violations'] == set()
    assert result['ignored_violations'] == 1


def test_novest_on_distant_person_is_ignored():
    """Person too small in frame (< 8% height): no PPE verdict."""
    tiny = det('person', 0.8, 100, 100, 115, 140)  # 40 px tall
    novest = det('novest', 0.85, 100, 110, 114, 130)
    result = evaluate([tiny, novest])
    assert result['violations'] == set()
    assert result['eligible_count'] == 0
    assert result['person_count'] == 1
    assert result['ignored_violations'] == 1


def test_novest_on_eligible_person_alerts():
    result = evaluate([person(), det('novest', 0.85, 120, 180, 180, 280)])
    assert result['violations'] == {'vest_missing'}
    assert result['ignored_violations'] == 0


def test_nohat_on_eligible_person_alerts():
    result = evaluate([person(), det('nohat', 0.85, 130, 90, 170, 130)])
    assert result['violations'] == {'helmet_missing'}


# ------------------------------------------------------ per-class thresholds

def test_low_confidence_novest_is_dropped():
    result = evaluate([person(), det('novest', 0.6, 120, 180, 180, 280)])
    assert result['violations'] == set()


def test_low_confidence_person_is_dropped():
    result = evaluate([det('person', 0.3, 100, 100, 200, 400)])
    assert result['person_count'] == 0


def test_custom_class_confidence_override():
    result = evaluate(
        [person(), det('novest', 0.6, 120, 180, 180, 280)],
        class_confidence={'novest': 0.5},
    )
    assert result['violations'] == {'vest_missing'}


# ---------------------------------------------------------------- rule flags

def test_require_vest_false_suppresses_vest_violation():
    result = evaluate(
        [person(), det('novest', 0.9, 120, 180, 180, 280)],
        require_vest=False,
    )
    assert result['violations'] == set()


def test_require_helmet_false_suppresses_helmet_violation():
    result = evaluate(
        [person(), det('nohat', 0.9, 130, 90, 170, 130)],
        require_helmet=False,
    )
    assert result['violations'] == set()


# --------------------------------------- explicit vs fallback model handling

def test_explicit_model_person_without_vest_class_no_violation():
    """wesjos has an explicit novest class: a person with NO vest verdict at
    all gets the benefit of the doubt (no alert)."""
    result = evaluate([person()])
    assert result['violations'] == set()


def test_fallback_model_person_without_vest_is_violation():
    result = evaluate(
        [person()],
        model_class_names=FALLBACK_CLASSES,
        require_helmet=False,
    )
    assert result['violations'] == {'vest_missing'}


def test_fallback_model_person_with_vest_ok():
    result = evaluate(
        [person(), det('vest', 0.7, 120, 180, 180, 280)],
        model_class_names=FALLBACK_CLASSES,
        require_helmet=False,
    )
    assert result['violations'] == set()


def test_fallback_model_distant_person_not_judged():
    tiny = det('person', 0.8, 100, 100, 115, 140)
    result = evaluate(
        [tiny],
        model_class_names=FALLBACK_CLASSES,
        require_helmet=False,
    )
    assert result['violations'] == set()


# ---------------------------------------------- person-less model handling

def test_personless_model_explicit_nohat_still_alerts():
    """workspace_safety.pt has no person class: association is impossible,
    explicit violation boxes must be judged directly (legacy behavior)."""
    result = evaluate(
        [det('nohat', 0.85, 130, 90, 170, 130)],
        model_class_names=PERSONLESS_CLASSES,
    )
    assert result['violations'] == {'helmet_missing'}
    assert result['person_count'] == 0


def test_personless_model_low_conf_violation_still_dropped():
    result = evaluate(
        [det('nohat', 0.6, 130, 90, 170, 130)],
        model_class_names=PERSONLESS_CLASSES,
    )
    assert result['violations'] == set()


def test_personless_model_respects_rule_flags():
    result = evaluate(
        [det('nohat', 0.9, 130, 90, 170, 130)],
        model_class_names=PERSONLESS_CLASSES,
        require_helmet=False,
    )
    assert result['violations'] == set()


# ------------------------------------------------------------ vest-veto

def test_vest_veto_suppresses_coexisting_novest():
    """NMS is per-class: vest and novest can coexist on one torso.
    The tie goes to compliance."""
    result = evaluate([
        person(),
        det('vest', 0.60, 120, 180, 180, 280),
        det('novest', 0.82, 118, 178, 182, 282),
    ])
    assert result['violations'] == set()


def test_novest_without_coexisting_vest_still_alerts():
    result = evaluate([person(), det('novest', 0.82, 120, 180, 180, 280)])
    assert result['violations'] == {'vest_missing'}


def test_hat_veto_suppresses_coexisting_nohat():
    result = evaluate([
        person(),
        det('hat', 0.60, 130, 90, 170, 130),
        det('nohat', 0.85, 132, 92, 168, 128),
    ])
    assert result['violations'] == set()


# --------------------------------------------- association confidence floor

def test_truncated_person_at_association_floor_owns_novest():
    """A torso-only person at conf 0.40 (below the 0.50 counting threshold)
    can still own a confident novest box."""
    p = det('person', 0.40, 100, 100, 200, 400)
    result = evaluate([p, det('novest', 0.85, 120, 180, 180, 280)])
    assert result['violations'] == {'vest_missing'}
    assert result['person_count'] == 0  # not counted, but owns the item


def test_person_below_association_floor_is_dropped():
    p = det('person', 0.30, 100, 100, 200, 400)
    result = evaluate([p, det('novest', 0.85, 120, 180, 180, 280)])
    assert result['violations'] == set()
    assert result['ignored_violations'] == 1


def test_fallback_ignores_uncounted_persons():
    """Fallback (absence-of-vest) evidence is weak: it only applies to
    persons above the full counting threshold."""
    p = det('person', 0.40, 100, 100, 200, 400)
    result = evaluate(
        [p],
        model_class_names=FALLBACK_CLASSES,
        require_helmet=False,
    )
    assert result['violations'] == set()


# ------------------------------------------------------------ temporal filter

def test_temporal_single_flicker_never_confirms():
    f = TemporalViolationFilter(window=5, min_hits=3)
    assert f.update({'vest_missing'}, now=0) == set()
    assert f.update(set(), now=1) == set()
    assert f.update(set(), now=2) == set()


def test_temporal_confirms_after_min_hits():
    f = TemporalViolationFilter(window=5, min_hits=3)
    assert f.update({'vest_missing'}, now=0) == set()
    assert f.update({'vest_missing'}, now=1) == set()
    assert f.update({'vest_missing'}, now=2) == {'vest_missing'}


def test_temporal_nonconsecutive_hits_confirm():
    f = TemporalViolationFilter(window=5, min_hits=3)
    f.update({'vest_missing'}, now=0)
    f.update(set(), now=1)
    f.update({'vest_missing'}, now=2)
    f.update(set(), now=3)
    assert f.update({'vest_missing'}, now=4) == {'vest_missing'}


def test_temporal_expires_out_of_window():
    f = TemporalViolationFilter(window=3, min_hits=2)
    f.update({'vest_missing'}, now=0)
    f.update(set(), now=1)
    f.update(set(), now=2)
    # First hit has rolled out of the window: one new hit isn't enough.
    assert f.update({'vest_missing'}, now=3) == set()


def test_temporal_tracks_types_independently():
    f = TemporalViolationFilter(window=5, min_hits=2)
    f.update({'vest_missing'}, now=0)
    confirmed = f.update({'vest_missing', 'helmet_missing'}, now=1)
    assert confirmed == {'vest_missing'}


def test_temporal_min_hits_clamped_to_window():
    f = TemporalViolationFilter(window=2, min_hits=10)
    f.update({'vest_missing'}, now=0)
    assert f.update({'vest_missing'}, now=1) == {'vest_missing'}


def test_temporal_stale_votes_expire_by_age():
    """Votes older than max_age_seconds must not combine with fresh noise
    (overnight dual-mode gap, stream drop)."""
    f = TemporalViolationFilter(window=5, min_hits=3, max_age_seconds=90)
    f.update({'vest_missing'}, now=0)
    f.update({'vest_missing'}, now=1)
    # 12 hours later a single flicker arrives: old votes are expired.
    assert f.update({'vest_missing'}, now=43200) == set()


def test_temporal_fresh_votes_within_age_confirm():
    f = TemporalViolationFilter(window=5, min_hits=3, max_age_seconds=90)
    f.update({'vest_missing'}, now=0)
    f.update({'vest_missing'}, now=30)
    assert f.update({'vest_missing'}, now=60) == {'vest_missing'}


def test_temporal_reset_clears_history():
    f = TemporalViolationFilter(window=5, min_hits=2)
    f.update({'vest_missing'}, now=0)
    f.reset()
    assert f.update({'vest_missing'}, now=1) == set()

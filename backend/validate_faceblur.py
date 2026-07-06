"""E2E check of face blur on real alert frames with the real YuNet model.
Writes *_faceblur.jpg next to each input so we can eyeball 'only the face'."""
import sys
import cv2
from ultralytics import YOLO
from services.face_blur import FaceBlurrer
from services import ppe_logic

fb = FaceBlurrer()
print("FaceBlurrer enabled:", fb.enabled)
model = YOLO('models/ppe/helmet_vest.pt')

for path in sys.argv[1:]:
    frame = cv2.imread(path)
    if frame is None:
        print(f"{path}: cannot read"); continue
    # person boxes from the real detector (device cpu to avoid GPU dependency)
    res = model(frame, conf=0.45, imgsz=1280, device='cpu', verbose=False)
    persons = []
    for b in res[0].boxes:
        if ppe_logic.canonical_class(model.names[int(b.cls[0])]) == 'person':
            persons.append(list(map(float, b.xyxy[0].cpu().numpy())))
    n = fb.blur_faces(frame, person_boxes=persons)
    out = path.replace('.jpg', '_faceblur.jpg')
    cv2.imwrite(out, frame)
    name = path.split('\\')[-1].split('/')[-1]
    print(f"{name}: persons={len(persons)} faces_blurred={n} -> {out.split(chr(92))[-1].split('/')[-1]}")

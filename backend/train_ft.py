"""Fine-tune helmet_vest.pt on the ensemble-labelled site dataset.

Conservative (nudging, not rebuilding): start from the deployed model, LOW
hue augmentation (keep the teal-vest colour signal), modest lr, early stop,
imgsz 1280 to match inference. val mAP measures agreement with AUTO-labels,
not truth — the real test is ft_accept_gate.py on human-judged frames.

Windows: everything under __main__ (dataloader spawns worker processes).
"""
import sys


def main():
    import torch
    from ultralytics import YOLO

    free, total = torch.cuda.mem_get_info()
    print(f"VRAM free {free/1e9:.1f}/{total/1e9:.1f} GB before train", flush=True)

    imgsz = int(sys.argv[1]) if len(sys.argv) > 1 else 1280
    batch = int(sys.argv[2]) if len(sys.argv) > 2 else 8

    model = YOLO('models/ppe/helmet_vest.pt')
    try:
        model.train(
            data='datasets/ppe_ft_clean/data.yaml',
            epochs=60, patience=15, imgsz=imgsz, batch=batch, device=0,
            project='runs_ft', name='ppe_site', exist_ok=True,
            workers=0,
            lr0=0.005, warmup_epochs=3.0,
            hsv_h=0.01, hsv_s=0.5, hsv_v=0.4,   # keep vest COLOURS stable
            fliplr=0.5, mosaic=0.6, degrees=0.0, translate=0.05, scale=0.3,
            close_mosaic=10, verbose=True, plots=True,
        )
        print("BEST:", model.trainer.best, flush=True)
    except torch.cuda.OutOfMemoryError:
        print("CUDA OOM — retry: python train_ft.py 960 4", flush=True)
        sys.exit(2)


if __name__ == '__main__':
    main()

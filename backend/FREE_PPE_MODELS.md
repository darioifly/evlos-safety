# Modelli PPE Detection COMPLETAMENTE GRATUITI

## 🆓 Soluzioni 100% Gratuite (No Limiti)

---

## ✅ OPZIONE 1: Roboflow Download + Uso Offline (RACCOMANDATO)

### Come funziona:
1. **Download UNA VOLTA** (gratis con account Roboflow)
2. **Usa OFFLINE per sempre** (nessun limite, nessun costo)

### Passi:
```bash
# 1. Crea account Roboflow (gratis)
# https://roboflow.com/

# 2. Vai al dataset
# https://universe.roboflow.com/roboflow-100/construction-safety-gsnvb

# 3. Click "Download Dataset"
# Scegli formato: YOLOv8
# Scarica ZIP

# 4. Estrai e usa
unzip construction-safety.zip -d models/ppe/
```

### Uso nel codice:
```python
from ultralytics import YOLO

# Carica modello OFFLINE (nessun costo, nessun limite)
model = YOLO("models/ppe/weights/best.pt")

# Usa per sempre, gratis
results = model(frame, conf=0.5)  # Sulla tua GPU, gratis!
```

**✅ PRO:**
- Completamente gratis
- Nessun limite di inferenze
- Tutto locale sulla tua GPU
- Alta qualità (Roboflow-100)
- Nessuna dipendenza da API esterne

**❌ CONTRO:**
- Devi scaricare una volta (richiede account)

---

## ✅ OPZIONE 2: GitHub - Modelli Open Source

### A) keremberke/yolov8m-hard-hat-detection (Hugging Face)

**URL:** https://huggingface.co/keremberke/yolov8m-hard-hat-detection

**Download:**
```python
from huggingface_hub import hf_hub_download

# Download automatico (gratis, no account richiesto)
model_path = hf_hub_download(
    repo_id="keremberke/yolov8m-hard-hat-detection",
    filename="best.pt"
)

# Usa il modello
from ultralytics import YOLO
model = YOLO(model_path)
```

**Classi:**
- `helmet`
- `head`
- `person`

**PRO:**
- ✅ Completamente gratis
- ✅ No account richiesto
- ✅ Download automatico
- ✅ YOLOv8m (più accurato)

**CONTRO:**
- ⚠️ Solo 3 classi (no "no-helmet", "vest")
- ⚠️ Meno specifico per cantieri

---

### B) RizwanMunawar/yolov8-object-tracking (PPE variant)

**URL:** https://github.com/RizwanMunawar/yolov8-object-tracking

**Include:**
- PPE Detection
- Person Tracking
- Safety monitoring

**Download diretto:**
```bash
git clone https://github.com/RizwanMunawar/yolov8-object-tracking
cd yolov8-object-tracking
# Modelli inclusi nella repo
```

---

### C) ultralytics/assets - Sample Models

**URL:** https://github.com/ultralytics/assets/releases

**Download:**
```bash
# Hard hat detection model
wget https://github.com/ultralytics/assets/releases/download/v0.0.0/hard-hat.pt
```

---

## ✅ OPZIONE 3: Train Your Own (Completamente Gratis)

### Usa dataset pubblici gratuiti:

#### Dataset Gratuiti:
1. **Kaggle - Hard Hat Workers**
   - URL: https://www.kaggle.com/datasets/andrewmvd/hard-hat-detection
   - 5,000+ immagini
   - Gratis con account Kaggle

2. **Open Images - PPE Subset**
   - URL: https://storage.googleapis.com/openimages/web/index.html
   - Filtra per "helmet", "vest", "construction"

3. **COCO Dataset - Person Class**
   - Combina con manual annotation

### Training (gratis su Google Colab GPU):
```python
from ultralytics import YOLO

# Carica base model
model = YOLO('yolov8n.pt')

# Train (gratis su Colab GPU)
model.train(
    data='ppe-dataset.yaml',
    epochs=100,
    imgsz=640,
    device=0  # Google Colab GPU gratis
)
```

---

## 📊 Comparazione Opzioni Gratuite

| Opzione | Difficoltà | Qualità | Tempo Setup | Classi |
|---------|-----------|---------|-------------|--------|
| **Roboflow Download + Offline** | ⭐ Facile | ⭐⭐⭐⭐⭐ | 10 min | 10 classi |
| **Hugging Face** | ⭐⭐ Media | ⭐⭐⭐⭐ | 5 min | 3 classi |
| **GitHub Repos** | ⭐⭐ Media | ⭐⭐⭐ | 15 min | Varia |
| **Train Your Own** | ⭐⭐⭐⭐⭐ Difficile | ⭐⭐⭐⭐⭐ | 2+ giorni | Custom |

---

## 🎯 LA MIA RACCOMANDAZIONE:

### **Usa Roboflow Download + Offline Usage**

**Perché:**
1. ✅ **Gratis al 100%** - Download una volta, usa per sempre
2. ✅ **Miglior qualità** - Roboflow-100 è top tier
3. ✅ **Più classi** - helmet, vest, no-helmet, no-vest
4. ✅ **Nessun limite** - Tutto sulla tua GPU
5. ✅ **Setup rapido** - 10 minuti

**Come:**
```bash
# 1. Crea account Roboflow (1 min)
# 2. Download dataset (5 min)
# 3. Usa offline per sempre (gratis!)
```

---

## 🚀 Alternative se Roboflow non funziona:

### **Fallback 1: Hugging Face**
```bash
pip install huggingface_hub
python download_huggingface_model.py
```

### **Fallback 2: GitHub Direct**
```bash
wget https://github.com/.../ppe-model.pt
```

### **Fallback 3: Train Custom**
- Usa Google Colab (GPU gratis)
- Dataset Kaggle (gratis)
- Ultralytics YOLO (gratis, open source)

---

## ⚠️ IMPORTANTE: Licensing

### Tutti questi modelli sono:
- ✅ **Open Source** (MIT, Apache 2.0, GPL-3.0)
- ✅ **Uso commerciale OK**
- ✅ **No royalties**
- ✅ **No limiti di inferenze**

### Ma verifica sempre la licenza:
- Roboflow datasets: Tipicamente CC BY 4.0 (uso commerciale OK)
- Hugging Face: Vedi pagina del modello
- GitHub: Vedi LICENSE file

---

## 💡 TL;DR - Cosa fare ORA:

1. **Prova Roboflow Download** (raccomandato)
   - Crea account → Download → Usa offline

2. **Se Roboflow non va, usa Hugging Face**
   - No account, download automatico

3. **Entrambi falliscono? Train custom**
   - Kaggle dataset + Google Colab

**Tutti 100% GRATIS, nessun limite!**

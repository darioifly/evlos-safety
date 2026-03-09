# Guida Classi Rilevabili - Sistema Detection

## Modello YOLOv8n - 80 Classi COCO

Il modello person detection attuale (`yolov8n.pt`) può rilevare **80 classi** diverse.

---

## 🏗️ CLASSI UTILI PER CANTIERE

### 👥 **Persone e Sicurezza:**
```
0: person        ⭐ ESSENZIALE - Sempre abilitato
```

### 🚗 **Veicoli e Mezzi:**
```
2: car           🚙 Auto
3: motorcycle    🏍️ Moto
5: bus           🚌 Bus
7: truck         🚛 Camion/Mezzi pesanti ⭐ UTILE
```

### 🛠️ **Attrezzature e Oggetti:**
```
24: backpack     🎒 Zaini
28: suitcase     💼 Valigie/Casse
```

### 🚦 **Segnaletica (se vicino a strada):**
```
9: traffic light  🚦 Semafori
11: stop sign     🛑 Stop
```

---

## 💡 SCENARI DI UTILIZZO

### **Scenario 1: Solo Persone (Attuale)**
```json
{
  "detectionClasses": [0],
  "classNames": ["person"]
}
```
**Uso:** Intrusione, controllo presenza

---

### **Scenario 2: Persone + Veicoli** ⭐ CONSIGLIATO
```json
{
  "detectionClasses": [0, 2, 7],
  "classNames": ["person", "car", "truck"]
}
```
**Uso:** Cantiere con traffico veicolare
**Vantaggi:**
- Rileva persone
- Rileva camion/mezzi pesanti
- Rileva auto non autorizzate

---

### **Scenario 3: Monitoraggio Completo Cantiere**
```json
{
  "detectionClasses": [0, 1, 2, 3, 7],
  "classNames": ["person", "bicycle", "car", "motorcycle", "truck"]
}
```
**Uso:** Cantiere urbano con molto traffico

---

### **Scenario 4: Sicurezza Perimetrale**
```json
{
  "detectionClasses": [0, 2, 3, 7],
  "classNames": ["person", "car", "motorcycle", "truck"]
}
```
**Uso:** Rilevare intrusioni di persone E veicoli

---

## 🎨 ANNOTAZIONI COLORI (Proposta)

Quando rilevi più classi, usa colori diversi:

```python
COLORS = {
    'person': (0, 255, 0),      # Verde
    'car': (255, 255, 0),        # Giallo
    'truck': (255, 165, 0),      # Arancione
    'motorcycle': (255, 0, 255), # Magenta
    'bicycle': (0, 255, 255),    # Cyan
}
```

---

## 📊 ALERT CONFIGURABILI PER CLASSE

### **Alert per Persone:**
```json
{
  "person": {
    "enabled": true,
    "minCount": 1,
    "cooldown": 5,
    "severity": "CRITICAL"
  }
}
```

### **Alert per Veicoli:**
```json
{
  "truck": {
    "enabled": true,
    "minCount": 1,
    "cooldown": 30,
    "severity": "WARNING",
    "message": "Camion rilevato in cantiere"
  }
}
```

---

## 🔧 IMPLEMENTAZIONE

### **Config.json Extended:**

```json
{
  "model": "yolov8n.pt",
  "confidence": 0.65,
  "device": "cuda:0",

  "detectionClasses": {
    "enabled": [0, 2, 7],
    "names": {
      "0": "person",
      "2": "car",
      "7": "truck"
    }
  },

  "alerts": {
    "person": {
      "enabled": true,
      "minCount": 1,
      "cooldown": 5
    },
    "truck": {
      "enabled": true,
      "minCount": 1,
      "cooldown": 60,
      "message": "Veicolo pesante rilevato"
    }
  }
}
```

### **Worker Modificato:**

```python
# Invece di:
results = self.model(frame, conf=confidence, classes=[0])

# Usa:
enabled_classes = CONFIG.get("detectionClasses", {}).get("enabled", [0])
results = self.model(frame, conf=confidence, classes=enabled_classes)
```

---

## 📈 DATABASE UPDATES

```sql
-- Nuova tabella per detections multi-classe
CREATE TABLE IF NOT EXISTS detections_by_class (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id TEXT NOT NULL,
    class_id INTEGER NOT NULL,
    class_name TEXT NOT NULL,
    count INTEGER DEFAULT 0,
    avg_confidence REAL DEFAULT 0.0,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 🎯 PRIORITÀ IMPLEMENTAZIONE

### **Phase 1 (Ora):**
- ✅ Solo persone (class 0)
- ✅ Annotazioni base

### **Phase 2 (PPE System):**
- Helmet + Vest detection
- Annotazioni colorate per violazioni

### **Phase 3 (Multi-Class):**
- Aggiungi veicoli (car, truck)
- Alert separati per classe
- Database multi-classe

---

## 💡 ALTRE POSSIBILITÀ FUTURE

### **Rilevamento Oggetti Pericolosi:**
```
39: bottle       (bottiglie abbandonate)
76: scissors     (attrezzi taglienti)
```

### **Controllo Ordine Cantiere:**
```
56: chair        (sedie fuori posto)
60: dining table (tavoli)
```

### **Animali (se cantiere rurale):**
```
15: cat
16: dog
17: horse
```

---

## ❓ DOMANDE PER TE

Vorresti:

1. **Abilitare rilevamento veicoli?** (car, truck)
   - Utile se hai traffico nel cantiere
   - Alert quando entra un camion

2. **Configurazione tramite UI?**
   - Checkbox per ogni classe
   - Abilita/disabilita classi dinamicamente

3. **Alert separati per classe?**
   - Alert diversi per person vs truck
   - Cooldown diversi

Fammi sapere cosa ti interessa! 🎯

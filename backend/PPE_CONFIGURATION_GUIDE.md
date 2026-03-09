# Guida Configurazione Sistema PPE Detection

## Panoramica Configurazioni Necessarie

### 📋 **CONFIGURAZIONI PRINCIPALI**

---

## 1. 🎯 **SELEZIONE MODELLO**

### Modelli Disponibili:

```json
"models": {
  "person": {
    "path": "yolov8n.pt",
    "description": "Solo rilevamento persone (modalità intrusione)",
    "use_case": "Notte - Rilevamento intrusioni"
  },
  "ppe": {
    "path": "models/ppe/helmet_vest.pt",
    "description": "Rilevamento PPE (elmetto + giubbotto)",
    "use_case": "Giorno - Controllo sicurezza cantiere"
  },
  "helmet_only": {
    "path": "models/ppe/ppe_detection.pt",
    "description": "Solo elmetti",
    "use_case": "Se serve solo controllo elmetti"
  }
}
```

**Configurazione UI:**
- Dropdown/Select con i 3 modelli
- Descrizione per ogni modello
- Indicatore modello attualmente in uso

---

## 2. 🔄 **MODALITÀ RILEVAMENTO**

### Opzioni:

1. **"person"** - Sempre modalità intrusione
   - Usa modello person detection
   - Alert per QUALSIASI persona rilevata
   - Utile per: Zone vietate 24/7

2. **"ppe"** - Sempre modalità PPE
   - Usa modello PPE
   - Alert per violazioni DPI
   - Utile per: Aree lavoro attive 24/7

3. **"dual"** - Auto-switch giorno/notte ⭐ CONSIGLIATO
   - Giorno (6:00-18:00): Modalità PPE
   - Notte (18:00-6:00): Modalità intrusione
   - Utile per: Cantieri normali

**Configurazione UI:**
- Radio buttons o Toggle per le 3 modalità
- Spiegazione di ogni modalità
- Se "dual" selezionato, mostrare configurazione orari

---

## 3. ⏰ **ORARI GIORNO/NOTTE** (se detectionMode = "dual")

```json
"schedule": {
  "dayStartHour": 6,    // Ora inizio giorno (0-23)
  "dayEndHour": 18,     // Ora fine giorno (0-23)
  "dayMode": "ppe",     // Modalità diurna
  "nightMode": "person" // Modalità notturna
}
```

**Configurazione UI:**
- Time picker per "Ora inizio giorno"
- Time picker per "Ora fine giorno"
- Preview: "Giorno: 06:00-18:00 (PPE) | Notte: 18:00-06:00 (Intrusione)"

---

## 4. 🦺 **REGOLE DPI** (se usa modello PPE)

```json
"ppeRules": {
  "requireHelmet": true,  // Elmetto obbligatorio
  "requireVest": true,    // Giubbotto obbligatorio
  "requireBoth": true,    // ENTRAMBI obbligatori
  "allowPartialCompliance": false
}
```

**Configurazione UI:**
- Checkbox: "Richiedi elmetto"
- Checkbox: "Richiedi giubbotto"
- Checkbox: "Richiedi entrambi" (se entrambi checked sopra)

**Logica:**
```
requireBoth = true:
  Alert se manca elmetto OR giubbotto

requireBoth = false:
  Alert solo se mancano ENTRAMBI
  (uno solo ok)
```

---

## 5. 🚨 **CONFIGURAZIONE ALERT**

### Alert per tipo:

```json
"alerts": {
  "intrusion": {
    "enabled": true,        // Abilita alert intrusione
    "minPersons": 1,        // Min persone per alert
    "cooldown": 5,          // Secondi tra alert
    "severity": "CRITICAL"  // Livello gravità
  },
  "noPPE": {
    "enabled": true,
    "cooldown": 10,
    "severity": "CRITICAL"  // Mancano elmetto E giubbotto
  },
  "noHelmet": {
    "enabled": true,
    "cooldown": 15,
    "severity": "WARNING"   // Manca solo elmetto
  },
  "noVest": {
    "enabled": true,
    "cooldown": 15,
    "severity": "WARNING"   // Manca solo giubbotto
  }
}
```

**Configurazione UI per ogni tipo di alert:**

```
┌─────────────────────────────────────┐
│ Alert: Intrusione (Notte)          │
│ ☑ Abilitato                         │
│ Cooldown: [5] secondi              │
│ Min persone: [1]                    │
│ Gravità: [CRITICAL ▼]              │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ Alert: Persona senza DPI completo  │
│ ☑ Abilitato                         │
│ Cooldown: [10] secondi             │
│ Gravità: [CRITICAL ▼]              │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ Alert: Persona senza elmetto       │
│ ☑ Abilitato                         │
│ Cooldown: [15] secondi             │
│ Gravità: [WARNING ▼]               │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ Alert: Persona senza giubbotto     │
│ ☑ Abilitato                         │
│ Cooldown: [15] secondi             │
│ Gravità: [WARNING ▼]               │
└─────────────────────────────────────┘
```

---

## 6. ⚙️ **IMPOSTAZIONI GENERALI**

```json
{
  "device": "cuda:0",          // GPU da usare
  "confidence": 0.65,          // Soglia confidenza (0-1)
  "streamWidth": 640,          // Larghezza stream
  "streamHeight": 480,         // Altezza stream
  "frameSampling": 10          // Processa 1 frame ogni N
}
```

**Configurazione UI:**
- Device: Dropdown (cuda:0, cpu, auto)
- Confidence: Slider 0-100% (default 65%)
- Resolution: Dropdown presets (640x480, 1280x720, etc.)
- Frame Sampling: Slider 1-30 (default 10)

---

## 7. 🎨 **OPZIONI VISUALIZZAZIONE** (opzionale)

```json
"ui": {
  "showBoundingBoxes": true,    // Mostra box rilevamenti
  "showConfidence": true,       // Mostra % confidenza
  "showLabels": true,           // Mostra etichette classi
  "highlightViolations": true   // Evidenzia violazioni DPI
}
```

---

## 📊 **INTERFACCIA PROPOSTA**

### Pagina Settings - Sezione "Detection & Alerts"

```
╔════════════════════════════════════════════════════════════╗
║  DETECTION SETTINGS                                        ║
╠════════════════════════════════════════════════════════════╣
║                                                            ║
║  Detection Mode                                            ║
║  ○ Person Only (Intrusion detection 24/7)                 ║
║  ○ PPE Only (Safety compliance 24/7)                      ║
║  ● Dual Mode (Auto-switch day/night) ← RECOMMENDED        ║
║                                                            ║
║  ┌──────────────────────────────────────────────────────┐ ║
║  │ Day/Night Schedule                                   │ ║
║  │ Day starts: [06:00] → Day ends: [18:00]            │ ║
║  │ • Day (06:00-18:00): PPE Detection                  │ ║
║  │ • Night (18:00-06:00): Intrusion Detection          │ ║
║  └──────────────────────────────────────────────────────┘ ║
║                                                            ║
║  Model Selection                                           ║
║  Person Detection:  [yolov8n.pt ▼]                        ║
║  PPE Detection:     [helmet_vest.pt ▼] (Helmet + Vest)   ║
║                                                            ║
╠════════════════════════════════════════════════════════════╣
║  PPE COMPLIANCE RULES                                      ║
╠════════════════════════════════════════════════════════════╣
║                                                            ║
║  Required Equipment:                                       ║
║  ☑ Safety Helmet (Hard Hat)                               ║
║  ☑ High-Visibility Vest                                   ║
║  ☑ Both Required (alert if ANY missing)                   ║
║                                                            ║
╠════════════════════════════════════════════════════════════╣
║  ALERT CONFIGURATION                                       ║
╠════════════════════════════════════════════════════════════╣
║                                                            ║
║  Intrusion (Night Mode)                                    ║
║  ☑ Enabled   Cooldown: [5]s   Severity: [CRITICAL ▼]     ║
║                                                            ║
║  Missing Both PPE (Day Mode)                               ║
║  ☑ Enabled   Cooldown: [10]s  Severity: [CRITICAL ▼]     ║
║                                                            ║
║  Missing Helmet Only (Day Mode)                            ║
║  ☑ Enabled   Cooldown: [15]s  Severity: [WARNING ▼]      ║
║                                                            ║
║  Missing Vest Only (Day Mode)                              ║
║  ☑ Enabled   Cooldown: [15]s  Severity: [WARNING ▼]      ║
║                                                            ║
╠════════════════════════════════════════════════════════════╣
║  GENERAL SETTINGS                                          ║
╠════════════════════════════════════════════════════════════╣
║                                                            ║
║  Confidence Threshold: [━━━━━━●───] 65%                   ║
║  Frame Sampling: Process 1 frame every [10] frames        ║
║  Device: [cuda:0 ▼] (GPU)                                 ║
║                                                            ║
║  [Save Configuration]  [Reset to Defaults]                ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
```

---

## 🔧 **BACKEND - Endpoint Necessari**

```javascript
// GET - Ottieni configurazione corrente
GET /api/detection/config

// POST - Aggiorna configurazione
POST /api/detection/config
Body: { /* config completo */ }

// GET - Ottieni modelli disponibili
GET /api/detection/models

// GET - Ottieni stato modalità corrente (day/night)
GET /api/detection/current-mode
Response: {
  "currentMode": "ppe",  // o "person"
  "isDaytime": true,
  "nextSwitch": "2025-10-23T18:00:00"
}
```

---

## 📝 **VALIDAZIONE CONFIGURAZIONE**

### Regole di validazione:

1. **detectionMode = "dual"** → Richiede `schedule` configurato
2. **dayMode = "ppe"** → Richiede `ppeRules` configurato
3. **requireBoth = true** → Richiede `requireHelmet` E `requireVest` true
4. **Orari validi**: dayStartHour < dayEndHour (o gestire overnight)
5. **Cooldown minimo**: >= 1 secondo
6. **Confidence**: 0.0 - 1.0

---

## 💾 **DATABASE UPDATES NECESSARI**

```sql
-- Nuove colonne per detections
ALTER TABLE detections ADD COLUMN helmet_count INTEGER DEFAULT 0;
ALTER TABLE detections ADD COLUMN no_helmet_count INTEGER DEFAULT 0;
ALTER TABLE detections ADD COLUMN vest_count INTEGER DEFAULT 0;
ALTER TABLE detections ADD COLUMN no_vest_count INTEGER DEFAULT 0;
ALTER TABLE detections ADD COLUMN detection_mode TEXT DEFAULT 'person';

-- Nuove colonne per alerts
ALTER TABLE alerts ADD COLUMN alert_type TEXT DEFAULT 'intrusion';
-- Tipi: 'intrusion', 'no_helmet', 'no_vest', 'no_ppe'
ALTER TABLE alerts ADD COLUMN severity TEXT DEFAULT 'INFO';
-- Severità: 'CRITICAL', 'WARNING', 'INFO'
ALTER TABLE alerts ADD COLUMN missing_equipment TEXT;
-- JSON array: ["helmet", "vest"]
```

---

## 🎯 **PRIORITY IMPLEMENTATION**

### Phase 1 (Essential):
1. ✅ Selezione modello (person / ppe)
2. ✅ Detection mode (person / ppe / dual)
3. ✅ Schedule giorno/notte
4. ✅ PPE rules base (requireHelmet, requireVest)
5. ✅ Alert configuration base

### Phase 2 (Nice to have):
6. ⚪ Advanced settings (tracking, NMS, etc.)
7. ⚪ UI display options
8. ⚪ Multi-language support
9. ⚪ Alert email/webhook configuration

---

## 🚀 **NEXT STEPS**

1. Aggiornare `config.json` con nuova struttura
2. Modificare backend endpoints per nuove config
3. Aggiornare database schema
4. Modificare `video_worker.py` per dual-mode
5. Creare UI configurazione nel frontend
6. Testing completo

---

**Domande?** Fammi sapere se serve chiarire qualche configurazione!

# EVLOS Safety - Documentazione Tecnica

## Panoramica

**evlos-safety** è un modulo di AI detection che si integra con la piattaforma EVLOS (iFly) per generare alert di sicurezza nei cantieri edili. Il sistema analizza in tempo reale i flussi video provenienti da telecamere NxWitness VMS, rileva persone e violazioni DPI (Dispositivi di Protezione Individuale), e invia alert alla piattaforma EVLOS.

### Ruolo nell'ecosistema EVLOS
EVLOS è la piattaforma principale iFly per la gestione dei cantieri, che offre:
- Visualizzazione telecamere
- Gestione alert di sicurezza
- Ortomosaici e mappature
- Video e documentazione
- Dati meteo

Il modulo **evlos-safety** si occupa specificamente del rilevamento automatico di:
- **Intrusioni**: Persone in aree ristrette (es. cantiere di notte)
- **Violazioni DPI**: Assenza di casco o gilet di sicurezza

---

## Stack Tecnologico

### Backend (Python)
| Componente | Tecnologia | Versione |
|------------|------------|----------|
| Framework API | FastAPI | 0.109.0 |
| Server ASGI | Uvicorn | - |
| Detection AI | YOLOv8 (Ultralytics) | 8.1.11 |
| Deep Learning | PyTorch + CUDA | 2.5.1 / 12.1 |
| Video Processing | OpenCV (headless) | - |
| Database | SQLite | - |
| WebSocket | websockets | 12.0 |
| Validazione | Pydantic | 2.5.3 |

### Frontend (React)
| Componente | Tecnologia | Versione |
|------------|------------|----------|
| Framework UI | React | 18.2.0 |
| Build Tool | Vite | 5.0.11 |
| Styling | Tailwind CSS | 3.4.1 |
| State Management | TanStack React Query | 5.17.0 |
| Grafici | Recharts | 2.10.3 |
| HTTP Client | Axios | 1.6.5 |
| Icone | Lucide React | 0.303.0 |

### Modelli ML

#### Person Detection (Intrusion Mode)
| Modello | File | Classi |
|---------|------|--------|
| YOLOv8 Nano | `yolov8n.pt` | person (COCO class 0) |

#### PPE Detection
I modelli vengono caricati in ordine di priorità (il primo trovato viene usato):

| Priorità | File | Classi | Note |
|----------|------|--------|------|
| 1 | `models/ppe/helmet_vest.pt` | hat, nohat, vest, novest, person | **Raccomandato** - Supporta sia casco che gilet |
| 2 | `models/ppe/ppe_detection.pt` | Hardhat, NO-Hardhat | Solo casco, no gilet |
| 3 | `models/ppe/ppe_combined.pt` | helmet, no_helmet, glove, no_glove, etc. | Modello multi-PPE alternativo |

#### Face Detection (Privacy)
| Modello | File | Scopo |
|---------|------|-------|
| YOLOv8 Face | `models/face/yolov8n-face.pt` | Blur volti per privacy (GDPR) |

---

## Architettura Sistema

### Diagramma High-Level

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   NxWitness     │     │   evlos-safety  │     │   EVLOS Cloud   │
│   VMS Server    │────►│   Backend       │────►│   Platform      │
│   (Telecamere)  │     │   (FastAPI)     │     │   (Alert API)   │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                                 │ WebSocket + REST API
                                 ▼
                        ┌─────────────────┐
                        │   React         │
                        │   Frontend      │
                        │   (Dashboard)   │
                        └─────────────────┘
```

### Struttura Directory

```
evlos-safety/
├── backend/
│   ├── main.py                    # Entry point FastAPI
│   ├── config.py                  # Configurazione (Pydantic Settings)
│   ├── routers/                   # API endpoints
│   │   ├── cameras.py             # Gestione telecamere
│   │   ├── detection.py           # Configurazione detection
│   │   ├── alerts.py              # Storico alert
│   │   ├── presets.py             # Preset detection
│   │   └── evlos.py               # Integrazione EVLOS
│   ├── services/                  # Business logic
│   │   ├── stream_manager.py      # Gestione stream multi-camera
│   │   ├── detection_worker.py    # Worker YOLO (processo separato)
│   │   ├── alert_manager.py       # Logica alert e cooldown
│   │   ├── nx_witness.py          # Client NxWitness API
│   │   ├── ptz_tracker.py         # Tracking PTZ cameras
│   │   └── worker_pool.py         # Pool processi YOLO
│   ├── database/
│   │   ├── db_manager.py          # Operazioni SQLite
│   │   ├── schema.sql             # Schema database
│   │   └── surveillance.db        # Database SQLite
│   ├── integrations/
│   │   └── evlos_client.py        # Client EVLOS API
│   ├── models/                    # Modelli ML pre-trained
│   │   ├── face/
│   │   └── ppe/
│   └── utils/
│       ├── logger.py              # Configurazione logging
│       ├── metrics.py             # Metriche performance
│       └── screenshot.py          # Generazione screenshot alert
├── frontend/
│   ├── src/
│   │   ├── main.jsx               # Entry point React
│   │   ├── App.jsx                # Root component (tab navigation)
│   │   ├── components/
│   │   │   ├── CameraGrid.jsx     # Griglia telecamere
│   │   │   ├── ConfigPanel.jsx    # Pannello configurazione
│   │   │   ├── Presets.jsx        # Gestione preset
│   │   │   ├── AlertLog.jsx       # Log alert
│   │   │   └── Dashboard.jsx      # Dashboard metriche
│   │   ├── hooks/
│   │   │   └── useWebSocket.js    # Hook WebSocket
│   │   └── lib/
│   │       └── api.js             # Client API Axios
│   └── vite.config.js             # Configurazione Vite + proxy
├── data/
│   ├── alert_screenshots/         # Screenshot degli alert
│   └── evlos_failed_alerts/       # Alert falliti (retry)
├── logs/                          # Log applicazione
└── .env                           # Variabili ambiente
```

---

## Flusso Dati - Pipeline Detection

### Diagramma Pipeline

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           PIPELINE DETECTION                              │
└──────────────────────────────────────────────────────────────────────────┘

    ┌─────────────┐         ┌─────────────┐         ┌─────────────┐
    │  NxWitness  │  MJPEG  │   Stream    │  Frame  │    Frame    │
    │   Camera    │────────►│  Producer   │────────►│    Queue    │
    │   Stream    │         │   Thread    │         │  (shared)   │
    └─────────────┘         └─────────────┘         └─────────────┘
                                                           │
                                                           ▼
    ┌─────────────┐         ┌─────────────┐         ┌─────────────┐
    │  WebSocket  │◄────────│   Result    │◄────────│    Batch    │
    │  Broadcast  │         │   Handler   │         │  Collector  │
    └─────────────┘         └─────────────┘         └─────────────┘
                                   │                       │
                                   ▼                       ▼
                            ┌─────────────┐         ┌─────────────┐
                            │   Alert     │         │   Worker    │
                            │   Manager   │         │    Pool     │
                            └─────────────┘         │   (YOLO)    │
                                   │                └─────────────┘
                 ┌─────────────────┼─────────────────┐
                 ▼                 ▼                 ▼
          ┌───────────┐     ┌───────────┐     ┌───────────┐
          │ NxWitness │     │  SQLite   │     │   EVLOS   │
          │   Event   │     │ Database  │     │   Cloud   │
          └───────────┘     └───────────┘     └───────────┘
```

### Fasi del Processing

1. **Stream Acquisition** (`StreamProducer`)
   - Connessione a stream MJPEG via NxWitness API
   - Decodifica frame JPEG dal flusso HTTP
   - Frame sampling configurabile (default: 1 ogni 30 frame)
   - Retry automatico con exponential backoff

2. **Batch Collection** (`BatchCollector`)
   - Raccolta frame da coda condivisa
   - Raggruppamento in batch per efficienza GPU (default: 4 frame)
   - Associazione metadata camera a ogni frame

3. **YOLO Inference** (`WorkerPool` + `DetectionWorker`)
   - Esecuzione in processo separato (evita GIL Python)
   - Inferenza batch su GPU CUDA
   - Due modalità:
     - **Intrusion**: Classe "person" (class 0)
     - **PPE**: Classi "nohat", "novest" da modello custom

4. **Result Processing** (`ResultHandler`)
   - Valutazione risultati contro preset camera
   - Calcolo confidence media e conteggio persone
   - Trigger alert se soglie superate

5. **Alert Generation** (`AlertManager`)
   - Verifica cooldown per camera
   - Screenshot con bounding box
   - Inserimento in database SQLite
   - Invio evento a NxWitness (bookmark + generic event)
   - Upload async a EVLOS (con retry)

6. **Real-time Broadcast** (`WebSocket`)
   - Notifica frontend via WebSocket
   - Update stato telecamere
   - Metriche sistema

---

## Modalità di Rilevamento

### Intrusion Detection
Rileva la presenza di persone in aree ristrette.

**Parametri configurabili:**
| Parametro | Descrizione | Default |
|-----------|-------------|---------|
| `intrusion_min_persons` | Numero minimo persone per alert | 1 |
| `intrusion_confidence` | Confidence minima detection | 0.5 |
| `cooldown_seconds` | Secondi tra alert successivi | 5 |

**Preset default:**
- **High Sensitivity**: 1+ persona, confidence 50%, cooldown 5s
- **Medium Sensitivity**: 1+ persona, confidence 70%, cooldown 10s
- **Low Sensitivity**: 2+ persone, confidence 80%, cooldown 15s

### PPE Detection (DPI)
Rileva l'assenza di dispositivi di protezione individuale.

**Parametri configurabili:**
| Parametro | Descrizione | Default |
|-----------|-------------|---------|
| `ppe_require_helmet` | Richiede casco | true |
| `ppe_require_vest` | Richiede gilet | true |
| `ppe_confidence` | Confidence minima | 0.6 |
| `cooldown_seconds` | Secondi tra alert | 5 |

**Preset default:**
- **Helmet Required**: Solo casco richiesto
- **Vest Required**: Solo gilet richiesto
- **Full (Helmet + Vest)**: Entrambi richiesti

### Sistema Preset

I preset sono configurazioni di detection salvate nel database che possono essere assegnate a singole telecamere.

**Tabella `detection_presets`:**
```sql
CREATE TABLE detection_presets (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    mode TEXT NOT NULL,              -- 'intrusion' o 'ppe'
    intrusion_min_persons INTEGER,
    intrusion_confidence REAL,
    ppe_require_helmet BOOLEAN,
    ppe_require_vest BOOLEAN,
    ppe_confidence REAL,
    cooldown_seconds INTEGER,
    face_blur_enabled BOOLEAN        -- Privacy: blur volti
);
```

---

## Database Schema

### Tabelle Principali

#### `camera_status`
Stato real-time delle telecamere.

```sql
CREATE TABLE camera_status (
    camera_id TEXT PRIMARY KEY,
    camera_name TEXT NOT NULL,
    online BOOLEAN DEFAULT 0,
    stream_connected BOOLEAN DEFAULT 0,
    person_count INTEGER DEFAULT 0,
    fps REAL DEFAULT 0.0,
    enabled BOOLEAN DEFAULT 1,
    is_ptz BOOLEAN DEFAULT 0,
    home_preset_id TEXT NULL,
    ptz_state TEXT DEFAULT 'IDLE',
    detection_mode TEXT DEFAULT 'intrusion',
    detection_preset_id INTEGER NULL,
    last_update TIMESTAMP,
    last_detection TIMESTAMP
);
```

#### `alerts`
Storico degli alert generati.

```sql
CREATE TABLE alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id TEXT NOT NULL,
    camera_name TEXT NOT NULL,
    person_count INTEGER NOT NULL,
    avg_confidence REAL NOT NULL,
    full_image_path TEXT,
    cropped_image_path TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notified BOOLEAN DEFAULT 0
);
```

#### `detections`
Log dettagliato di tutte le detection (anche non-alert).

```sql
CREATE TABLE detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id TEXT NOT NULL,
    person_count INTEGER NOT NULL,
    avg_confidence REAL NOT NULL,
    boxes TEXT,  -- JSON con coordinate bounding box
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notified BOOLEAN DEFAULT 0
);
```

### Indici
```sql
CREATE INDEX idx_detections_camera ON detections(camera_id);
CREATE INDEX idx_detections_timestamp ON detections(timestamp);
CREATE INDEX idx_alerts_timestamp ON alerts(timestamp);
```

---

## Integrazioni

### NxWitness VMS

**Autenticazione:** HTTP Basic Auth

**Endpoint utilizzati:**
| Endpoint | Metodo | Scopo |
|----------|--------|-------|
| `/rest/v1/devices` | GET | Lista telecamere |
| `/ec2/getCamerasEx` | GET | Lista telecamere (fallback) |
| `/media/{id}.mpjpeg` | GET | Stream MJPEG |
| `/api/createEvent` | POST | Creazione evento alert |
| `/ec2/bookmarks/add` | POST | Creazione bookmark timeline |

**Configurazione** (file `.env`):
```env
NX_SERVER_URL=http://192.168.1.31:7001
NX_STREAM_SERVER_URL=http://192.168.1.31:7001
NX_ADMIN_USERNAME=admin
NX_ADMIN_PASSWORD=***
```

### EVLOS Platform

**Endpoint:** `POST https://evlos.ifly.it/api/v1/alerts/upload`

**Formato:** `multipart/form-data`

**Campi:**
| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `file` | File | Screenshot JPEG dell'alert |
| `camera_id` | String | UUID telecamera |
| `alert_type` | String | `intrusion`, `crowd`, `no_ppe` |
| `timestamp` | ISO8601 | Timestamp dell'evento |
| `severity` | String | `low`, `medium`, `high`, `critical` |
| `confidence` | Float | Confidence media detection |

**Logica Retry:**
- 3 tentativi con exponential backoff (2s, 4s, 8s)
- Alert falliti salvati in `data/evlos_failed_alerts/`
- Possibilità di retry manuale via API

**Configurazione:**
```env
EVLOS_ENABLED=true
EVLOS_API_URL=https://evlos.ifly.it/api/v1/alerts/upload
EVLOS_TIMEOUT=10
EVLOS_MAX_RETRIES=3
```

---

## Configurazione

### Variabili Ambiente (`.env`)

```env
# NxWitness
NX_SERVER_URL=http://192.168.1.31:7001
NX_STREAM_SERVER_URL=http://192.168.1.31:7001
NX_ADMIN_USERNAME=admin
NX_ADMIN_PASSWORD=***

# Detection
YOLO_MODEL=yolov8n.pt
CONFIDENCE_THRESHOLD=0.5
DEVICE=cuda:0
MIN_PERSONS_FOR_ALERT=1
ALERT_COOLDOWN_SECONDS=5

# Stream
STREAM_WIDTH=640
STREAM_HEIGHT=480
FRAME_SAMPLING=30
BATCH_SIZE=4

# Threading
MAX_CAMERAS=20
PRODUCER_THREADS=20
CONSUMER_THREADS=1
FRAME_QUEUE_SIZE=50
IGNORE_CAMERA_STATUS=true

# EVLOS
EVLOS_ENABLED=true
EVLOS_API_URL=https://evlos.ifly.it/api/v1/alerts/upload
EVLOS_TIMEOUT=10
EVLOS_MAX_RETRIES=3

# Server
HOST=0.0.0.0
PORT=7002
LOG_LEVEL=INFO
```

### Parametri Chiave

| Parametro | Valore | Descrizione |
|-----------|--------|-------------|
| `FRAME_SAMPLING` | 30 | Processa 1 frame ogni 30 (riduce carico) |
| `BATCH_SIZE` | 4 | Frame per batch (efficienza GPU) |
| `CONSUMER_THREADS` | 1 | 1 thread evita contention GIL |
| `IGNORE_CAMERA_STATUS` | true | Connetti a tutte le camere |

---

## API Reference

### Endpoint REST

#### Cameras
| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| GET | `/api/cameras` | Lista tutte le telecamere |
| GET | `/api/cameras/status` | Stato real-time telecamere |
| POST | `/api/cameras/{id}/toggle` | Abilita/disabilita worker |
| POST | `/api/cameras/{id}/restart` | Restart stream telecamera |

#### Alerts
| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| GET | `/api/alerts` | Lista alert (con filtri) |
| GET | `/api/alerts/export` | Export CSV |
| GET | `/api/alerts/stats` | Statistiche alert |
| DELETE | `/api/alerts/{id}` | Elimina alert |
| DELETE | `/api/alerts` | Elimina tutti gli alert |

#### Presets
| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| GET | `/api/presets` | Lista preset |
| POST | `/api/presets` | Crea preset |
| PUT | `/api/presets/{id}` | Modifica preset |
| DELETE | `/api/presets/{id}` | Elimina preset |
| POST | `/api/presets/camera/{id}/set-preset` | Assegna preset a camera |

#### Detection
| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| GET | `/api/detection/config` | Configurazione corrente |
| POST | `/api/detection/config` | Aggiorna configurazione |

#### EVLOS
| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| GET | `/api/evlos/config` | Stato integrazione |
| POST | `/api/evlos/test` | Test connessione |
| POST | `/api/evlos/enable` | Abilita integrazione |
| POST | `/api/evlos/disable` | Disabilita integrazione |
| GET | `/api/evlos/failed-alerts` | Alert falliti |

#### Sistema
| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/api/metrics` | Metriche sistema |
| POST | `/api/worker/restart` | Restart tutti i worker |

### WebSocket

**Endpoint:** `ws://localhost:7002/ws`

**Messaggi:**

```json
// Stato iniziale (on connect)
{"type": "initial_status", "data": {...}}

// Update singola camera
{"type": "camera_status", "data": {...}}

// Update tutte le camere
{"type": "camera_status_update", "data": {...}}

// Nuovo alert
{"type": "alert", "data": {...}}

// Metriche sistema
{"type": "metrics_update", "data": {...}}

// Ping/Pong
{"type": "pong", "data": "..."}
```

---

## Frontend - Componenti

### App.jsx
Root component con navigazione a tab:
- **Cameras**: Griglia telecamere con stato
- **Presets**: Gestione preset detection
- **Configuration**: Impostazioni sistema
- **Alerts**: Log alert
- **Dashboard**: Metriche e grafici

### CameraGrid.jsx
Tabella telecamere con:
- Stato online/offline
- Stream connected
- Person count real-time
- FPS
- Preset assegnato
- Toggle enable/disable

### ConfigPanel.jsx
Configurazione:
- Modello YOLO
- Confidence threshold
- Device (GPU/CPU)
- Face blur (privacy)
- PTZ tracking
- EVLOS integration toggle

### Presets.jsx
CRUD preset detection:
- Creazione preset intrusion/PPE
- Modifica parametri
- Assegnazione a telecamere

### AlertLog.jsx
Storico alert:
- Filtro per camera
- Export CSV
- Link a screenshot
- Eliminazione

### Dashboard.jsx
Metriche real-time:
- FPS per camera (Recharts)
- GPU usage
- Alert count
- Processing time

---

## Avvio Sistema

### Requisiti
- Python 3.9+
- Node.js 18+
- NVIDIA GPU con CUDA 11.8+
- NxWitness VMS configurato

### Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
python main.py
```

### Frontend (development)
```bash
cd frontend
npm install
npm run dev
```

### Frontend (production)
```bash
cd frontend
npm run build
# I file statici vengono serviti da FastAPI
```

### URL di accesso
- **Backend API**: http://localhost:7002
- **Frontend dev**: http://localhost:5173
- **Frontend prod**: http://localhost:7002 (servito da FastAPI)

---

## Logging

**Directory:** `logs/`

**Formato file:** `detection_YYYYMMDD.log`

**Rotazione:** Giornaliera, retention 30 giorni

**Livelli:**
- `DEBUG`: Dettagli frame-by-frame (solo troubleshooting)
- `INFO`: Operazioni normali
- `WARNING`: Problemi non bloccanti
- `ERROR`: Errori che richiedono attenzione

---

## Note Tecniche

### Performance
- Il worker YOLO gira in processo separato per evitare il GIL Python
- Il frame sampling riduce il carico (1 su 30 frame processati)
- Il batch processing ottimizza l'uso della GPU
- Il cooldown previene flood di alert

### Sicurezza
- Le credenziali NxWitness sono in `.env` (non committare)
- Il face blur può essere abilitato per privacy (GDPR)
- Gli screenshot vengono eliminati automaticamente dopo 7 giorni

### Limitazioni
- Max 20 telecamere simultanee (configurabile)
- Richiede GPU NVIDIA per performance ottimali
- NxWitness è un requisito (no supporto altri VMS)

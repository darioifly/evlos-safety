# Person Detection System - SQLite Architecture

## Architettura della Soluzione

Il sistema è ora diviso in **2 processi separati** per evitare problemi di GIL blocking:

```
┌──────────────────┐         ┌──────────────┐         ┌────────────────┐
│   FastAPI        │         │  SQLite DB   │         │ Video Worker   │
│ (main_sqlite.py) │◄───────►│(surveillance.│◄───────►│(video_worker.py│
│  Port 7002       │  READ   │     db)      │  WRITE  │                │
│                  │         │              │         │                │
│ - HTTP/WebSocket │         │- camera_     │         │- YOLO          │
│ - Frontend       │         │  status      │         │- Detection     │
│ - API            │         │- detections  │         │- Alerts        │
│ - Real-time      │         │- alerts      │         │- GPU           │
│   alerts (0.1s)  │         │              │         │                │
└──────────────────┘         └──────────────┘         └────────────────┘
```

## Vantaggi

✅ **FastAPI mai bloccato** - gestisce solo HTTP/WebSocket, legge da database
✅ **Video Worker indipendente** - processa video senza impattare FastAPI
✅ **Alert in tempo reale** - WebSocket controlla DB ogni 0.1 secondi (~100ms latency)
✅ **Nessuna dipendenza esterna** - usa solo SQLite (già incluso in Python)
✅ **Persistenza dati** - tutte le detection salvate nel database
✅ **Scalabile** - facile aggiungere più worker per più telecamere

## File Principali

```
Safety/
├── backend/
│   ├── main_sqlite.py          ← FastAPI server (solo HTTP/WebSocket)
│   ├── video_worker.py          ← Video processing separato
│   ├── database/
│   │   ├── schema.sql           ← Schema database
│   │   ├── db_manager.py        ← Gestione database condiviso
│   │   └── surveillance.db      ← Database SQLite (creato automaticamente)
│   └── ...
├── start_fastapi.bat            ← Avvia FastAPI
├── start_video_worker.bat       ← Avvia Video Worker
└── README_SQLITE.md             ← Questo file
```

## Come Avviare il Sistema

### Metodo 1: Script Batch (Consigliato)

**Terminal 1 - FastAPI:**
```bash
# Doppio click su:
start_fastapi.bat
```

**Terminal 2 - Video Worker:**
```bash
# Doppio click su:
start_video_worker.bat
```

### Metodo 2: Manuale

**Terminal 1 - FastAPI:**
```bash
cd C:\Users\iflys\Desktop\Safety\backend
venv\Scripts\python.exe main_sqlite.py
```

**Terminal 2 - Video Worker:**
```bash
cd C:\Users\iflys\Desktop\Safety\backend
venv\Scripts\python.exe video_worker.py
```

## Verifica Funzionamento

### 1. Test FastAPI (deve rispondere immediatamente)

```bash
curl http://localhost:7002/health
# Risposta: {"status":"ok","mode":"sqlite"}

curl http://localhost:7002/api/cameras/status
# Risposta: {...status telecamere...}
```

### 2. Test Video Worker

Guarda i logs del Video Worker - dovresti vedere:
```
[Pontinia 1] ✓ Connected to stream
🚨 [Pontinia 1] ALERT: 2 person(s) detected!
```

### 3. Test WebSocket Real-Time

Apri il frontend e verifica che ricevi alert in tempo reale quando YOLO rileva persone.

## Database SQLite

### Posizione
```
backend/database/surveillance.db
```

### Tabelle Principali

**camera_status** - Status telecamere aggiornato da Video Worker
```sql
camera_id | camera_name | online | person_count | fps | last_update
```

**detections** - Tutte le detection di persone
```sql
id | camera_id | person_count | avg_confidence | timestamp | notified
```

**alerts** - Alert generati (con cooldown di 5 secondi)
```sql
id | camera_id | camera_name | person_count | timestamp | notified
```

### Query Utili

```bash
# Vedere database con SQLite command-line
cd backend/database
sqlite3 surveillance.db

# Query utili:
sqlite> SELECT * FROM camera_status;
sqlite> SELECT * FROM detections WHERE person_count > 0 ORDER BY timestamp DESC LIMIT 10;
sqlite> SELECT * FROM alerts ORDER BY timestamp DESC LIMIT 10;
sqlite> .quit
```

## Configurazione

### Video Worker

Modifica `backend/video_worker.py`:
```python
FRAME_SAMPLING = 10  # Processa 1 frame ogni 10 (più veloce = più detection)
ALERT_COOLDOWN = 5   # Secondi tra alert per stessa telecamera
```

### FastAPI WebSocket

Modifica `backend/main_sqlite.py`:
```python
WEBSOCKET_CHECK_INTERVAL = 0.1  # Controlla DB ogni 0.1s per alert in tempo reale
```

### YOLO Settings

Modifica `backend/config.py`:
```python
DEVICE = "cuda:0"                 # GPU device
CONFIDENCE_THRESHOLD = 0.5        # Soglia confidence (0.0-1.0)
MIN_PERSONS_FOR_ALERT = 1         # Minimo persone per alert
```

## Troubleshooting

### FastAPI non risponde
- ✅ Controlla che nessun altro processo usa porta 7002
- ✅ Killa vecchi processi: `taskkill /F /IM python.exe`

### Video Worker non rileva persone
- ✅ Verifica che la telecamera sia effettivamente nel campo visivo di persone
- ✅ Abbassa `CONFIDENCE_THRESHOLD` in config.py (es. 0.3)
- ✅ Riduci `FRAME_SAMPLING` per processare più frames (es. 5)

### Database locked error
- ✅ SQLite gestisce concurrent access automaticamente
- ✅ Se persiste, chiudi entrambi i processi e riavvia

### GPU non utilizzata
- ✅ Verifica con: `nvidia-smi`
- ✅ Controlla che PyTorch sia versione CUDA:
  ```bash
  venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available())"
  ```

## Performance Attese

- **FastAPI Response Time**: < 10ms (mai bloccato!)
- **WebSocket Alert Latency**: ~100ms dalla detection
- **YOLO FPS su GPU**: 20-30 FPS per camera
- **Database Query Time**: < 1ms

## Prossimi Miglioramenti

- [ ] Processare multiple telecamere in parallelo (threading nel Video Worker)
- [ ] Dashboard con statistiche detection
- [ ] Export detection history to CSV
- [ ] Configurazione camera dinamica (start/stop singole telecamere)
- [ ] Notifiche email/Telegram per alert critici

## Support

Per problemi o domande, controlla i logs:
- FastAPI logs: output di `start_fastapi.bat`
- Video Worker logs: output di `start_video_worker.bat`

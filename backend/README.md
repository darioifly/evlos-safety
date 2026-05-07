# Backend — Person Detection System

FastAPI service that ingests MJPEG streams from NxWitness, runs YOLOv8 detection
in-process, persists results to SQLite, and forwards alerts to NxWitness and
EVLOS.

## Architecture

Single Python process. No separate workers, no IPC.

```
backend/main_sqlite.py                ← entry point
  └── services/video_worker_manager.py
        ├── one CameraWorker thread per enabled camera
        ├── shared YOLO model + threading.Lock for inference
        └── per-frame: MJPEG decode → resize → YOLO → SQLite update
                       → (on alert) NxWitness Generic Event + bookmark
                       → (on alert) integrations/evlos_client async POST
```

- The FastAPI WebSocket loop polls SQLite for new alerts and pushes them to all
  connected clients.
- `services/nx_witness.py` is the HTTP client for NxWitness REST + MJPEG.
- `integrations/evlos_client.py` wraps a `ThreadPoolExecutor` (4 workers) for
  fire-and-forget alert uploads to the EVLOS platform.
- SQLite (`database/surveillance.db`) is the single source of truth for camera
  state, detections, alerts, and per-camera detection presets.

## Layout

```
backend/
├── main_sqlite.py            # FastAPI app, WebSocket, lifespan, inline endpoints
├── config.py                 # pydantic-settings (.env loader)
├── config.json               # Hot-reloaded JSON config (model, PPE rules, schedule)
├── routers/
│   ├── evlos.py              # /api/evlos/*  (config, test, enable/disable, failed-alerts)
│   └── presets.py            # /api/presets/* (CRUD detection presets, set-camera-preset)
├── services/
│   ├── video_worker_manager.py  # CameraWorker threads + YOLO model lifecycle
│   └── nx_witness.py            # NxWitness REST + MJPEG client
├── integrations/
│   └── evlos_client.py       # EVLOS HTTP client + thread pool + failed-alert spool
├── database/
│   ├── db_manager.py         # SQLite access (camera_status, detections, alerts, presets)
│   ├── schema.sql            # Self-applying CREATE TABLE IF NOT EXISTS
│   └── migrations_legacy/    # Archived one-shot ALTER TABLE scripts (do not run)
├── utils/
│   ├── logger.py             # Rotating file + console logger
│   ├── metrics.py            # In-memory FPS / detection counters
│   └── screenshot.py         # Box-drawing helpers, retention cleanup helper
└── requirements.txt
```

## Running

```bash
# Windows
venv\Scripts\activate
python main_sqlite.py
```

The repo-root scripts `start_fastapi.bat` and `backend/restart_backend.bat`
invoke this entry point.

The server listens on `HOST:PORT` from `.env` / `config.py` (default
`0.0.0.0:7002`). The frontend dev server (Vite, port 5173) proxies `/api` and
`/ws` to this backend.

## Configuration

See [`.env.example`](.env.example) for environment variables. A subset can be
hot-reloaded via `POST /api/detection/config` (which writes to `config.json`
and tells `VideoWorkerManager.reload_config()` to re-read it).

Per-camera detection mode (intrusion / PPE) and preset are stored in the
`camera_status` and `detection_presets` tables.

## API surface (registered routes)

- `GET  /health` — liveness probe.
- `GET  /api/cameras`, `/api/cameras/status`, `/api/cameras/{id}` — camera state.
- `POST /api/cameras/{id}/toggle` — enable/disable a per-camera worker.
- `GET  /api/detections/recent`, `/api/alerts/recent`, `/api/alerts/stats` — read paths.
- `DELETE /api/alerts/{id}`, `/api/alerts` — alert management.
- `GET  /api/metrics`, `/api/system/memory` — observability.
- `GET/POST /api/detection/config` — read / hot-reload `config.json`.
- `POST /api/system/reload-presets` — re-read detection presets for all running workers.
- `/api/evlos/*`, `/api/presets/*` — see router files.
- `WS   /ws` — alert + camera-status broadcast.

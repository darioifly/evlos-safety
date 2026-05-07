# Person Detection System

YOLOv8-based person detection system for NxWitness cameras with real-time monitoring and alerts.

## Features

- **Real-time Person Detection** - YOLOv8 nano/small models with GPU acceleration
- **Multi-Camera Support** - Process up to 20 camera streams simultaneously
- **NxWitness Integration** - Direct integration with NxWitness VMS
- **Alert System** - Configurable alerts with cooldown and retry logic
- **Web Dashboard** - Modern React-based interface with real-time updates
- **Performance Monitoring** - Track FPS, GPU usage, and system metrics
- **WebSocket Updates** - Live camera status and alert notifications

## System Requirements

### Hardware
- **GPU**: NVIDIA RTX 3090 (or any CUDA-compatible GPU)
- **RAM**: 16GB minimum (32GB recommended)
- **CPU**: Multi-core processor (8+ cores recommended)

### Software
- **OS**: Windows 10/11, Linux (Ubuntu 20.04+)
- **Python**: 3.9 or higher
- **Node.js**: 18.x or higher
- **CUDA**: 11.8 or higher (for GPU acceleration)

## Installation

### 1. Clone Repository

```bash
git clone <repository-url>
cd Safety
```

### 2. Backend Setup

```bash
# Navigate to backend
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Frontend Setup

```bash
# Navigate to frontend
cd frontend

# Install dependencies
npm install
```

### 4. Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```env
# NxWitness Configuration
NX_SERVER_URL=https://your-nxwitness-server/cameras
NX_ADMIN_USERNAME=your-username
NX_ADMIN_PASSWORD=your-password

# Detection Configuration
YOLO_MODEL=yolov8n.pt
CONFIDENCE_THRESHOLD=0.5
DEVICE=cuda:0
MIN_PERSONS_FOR_ALERT=1
ALERT_COOLDOWN_SECONDS=5
```

## Running the Application

The backend listens on port **7002** (configurable via `PORT` in `.env`). The
frontend dev server runs on **5173** and proxies `/api` and `/ws` to the
backend.

### Development Mode

**Terminal 1 — Backend:**
```bash
cd backend
venv\Scripts\activate
python main_sqlite.py
```
Or run `start_fastapi.bat` from the repo root.

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```

Or run `start_dev.bat` from the repo root to launch both at once.

Access the application:
- Frontend: http://localhost:5173 (development server)
- Backend API: http://localhost:7002/docs (Swagger UI)

### Production Mode

**Build Frontend:**
```bash
cd frontend
npm run build
```

**Run Backend (serves the built frontend):**
```bash
cd backend
venv\Scripts\activate
python main_sqlite.py
```

Access the application: http://localhost:7002

## Usage

### 1. Camera Grid
View all cameras with real-time status:
- Online/offline indicator
- Person count
- FPS
- Last alert timestamp

### 2. Configuration Panel
Configure detection parameters:
- **YOLO Model**: Choose between YOLOv8n (faster) or YOLOv8s (more accurate)
- **Confidence**: Detection confidence threshold (0.1 - 0.9)
- **Device**: CUDA GPU or CPU processing
- **Min Persons**: Minimum persons to trigger alert
- **Cooldown**: Seconds between alerts per camera
- **Batch Size**: Frames processed together

### 3. Alert Log
Monitor all detection alerts:
- Real-time alert updates via WebSocket
- Filter by camera
- Export to CSV
- Timestamp, camera, person count, confidence

### 4. Dashboard
System performance metrics:
- Average FPS
- GPU usage and memory
- Alerts today/total
- System uptime
- Performance charts
- Alerts per camera

## Architecture

Single Python process. FastAPI serves HTTP and WebSocket; YOLO inference
runs on threads inside the same process (one `CameraWorker` thread per enabled
camera). SQLite is the single source of truth for camera state, detections,
and alerts. EVLOS uploads happen through a 4-worker thread pool.

### Backend (FastAPI, in-process YOLO)
```
backend/
├── main_sqlite.py             # FastAPI app + WebSocket + lifespan + inline endpoints
├── config.py                  # pydantic-settings (.env loader)
├── config.json                # Hot-reloaded JSON config (model, PPE rules, schedule)
├── routers/
│   ├── evlos.py              # /api/evlos/* (config, test, failed-alerts)
│   └── presets.py            # /api/presets/* (CRUD detection presets)
├── services/
│   ├── video_worker_manager.py  # CameraWorker threads + YOLO model lifecycle
│   └── nx_witness.py         # NxWitness REST + MJPEG client
├── integrations/
│   └── evlos_client.py       # EVLOS HTTP client + ThreadPoolExecutor + spool
├── database/
│   ├── db_manager.py         # SQLite access layer
│   ├── schema.sql            # Self-applying CREATE TABLE IF NOT EXISTS
│   └── migrations_legacy/    # Archived one-shot migration scripts
└── utils/
    ├── logger.py             # Rotating file + console logger
    ├── metrics.py            # In-memory FPS / detection counters
    └── screenshot.py         # Box-drawing helpers, retention cleanup
```

### Frontend (React + Vite)
```
frontend/
├── src/
│   ├── App.jsx               # Main app component
│   ├── main.jsx              # Entry point
│   ├── components/
│   │   ├── CameraGrid.jsx    # Camera status grid
│   │   ├── ConfigPanel.jsx   # Configuration form
│   │   ├── AlertLog.jsx      # Alert table
│   │   └── Dashboard.jsx     # Metrics dashboard
│   ├── hooks/
│   │   └── useWebSocket.js   # WebSocket hook
│   └── styles/
│       └── index.css         # TailwindCSS
└── dist/                     # Production build
```

## API Endpoints

### Cameras
- `GET  /api/cameras` — list cameras with current DB-side status
- `GET  /api/cameras/status` — combined NxWitness + DB status
- `GET  /api/cameras/{id}` — camera details
- `POST /api/cameras/{id}/toggle` — start or stop the per-camera worker

### Detections / Alerts
- `GET    /api/detections/recent` — recent detections (with `person_count > 0`)
- `GET    /api/alerts/recent` — recent alerts
- `GET    /api/alerts/stats` — totals + alerts-per-camera
- `DELETE /api/alerts/{id}` — delete a single alert
- `DELETE /api/alerts` — delete all alerts

### Detection config
- `GET  /api/detection/config` — read `config.json`
- `POST /api/detection/config` — write `config.json` and hot-reload running workers
- `POST /api/system/reload-presets` — re-read DB-stored presets for all workers

### Presets (CRUD)
- `GET/POST/PUT/DELETE /api/presets[...]`
- `POST /api/presets/camera/{camera_id}/set-preset` — assign preset to a camera

### EVLOS integration
- `GET  /api/evlos/config`, `POST /api/evlos/test`
- `GET  /api/evlos/failed-alerts`
- `POST /api/evlos/enable`, `POST /api/evlos/disable` (runtime only)

### System
- `GET /health` — liveness probe
- `GET /api/metrics` — process / GPU / camera-FPS metrics
- `GET /api/system/memory` — detailed memory diagnostics
- `WebSocket /ws` — real-time alert + camera-status broadcast

## Troubleshooting

### CUDA Not Available
If you see "CUDA not available" warning:
1. Check NVIDIA driver: `nvidia-smi`
2. Verify CUDA installation: `nvcc --version`
3. Reinstall PyTorch with CUDA:
   ```bash
   pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
   ```

### Camera Streams Not Connecting
1. Verify NxWitness URL is accessible
2. Check credentials in `.env`
3. Test connection: `curl -u username:password https://your-server/api/v1/devices`
4. Check firewall settings

### High Memory Usage
1. Reduce `BATCH_SIZE` in `.env`
2. Lower `FRAME_QUEUE_SIZE`
3. Reduce number of active cameras
4. Use YOLOv8n instead of YOLOv8s

### Alerts Not Sending
1. Check NxWitness API endpoints in logs
2. Verify alert buffer status: `GET /api/alerts/buffer-status`
3. Check network connectivity to NxWitness server

### Frontend Build Fails
```bash
cd frontend
rm -rf node_modules
npm install
npm run build
```

## Performance Optimization

### GPU Optimization
- Use YOLOv8n for higher FPS
- Increase `BATCH_SIZE` (4-16) for better GPU utilization
- Reduce `STREAM_WIDTH` and `STREAM_HEIGHT` if needed

### CPU Optimization
- Reduce number of camera streams
- Increase `FRAME_SAMPLING` to skip more frames
- Use fewer `CONSUMER_THREADS`

### Network Optimization
- Deploy close to NxWitness server
- Use wired connection over WiFi
- Monitor bandwidth usage

## Development

### Adding New Features

**Backend:**
1. Create new router in `backend/routers/`
2. Register router in `main.py`
3. Update API documentation

**Frontend:**
1. Create component in `frontend/src/components/`
2. Add to App.jsx navigation
3. Update styling if needed

### Testing

**Backend:**
```bash
cd backend
pytest  # (if tests are added)
```

**Frontend:**
```bash
cd frontend
npm run test  # (if tests are added)
```

## Logging

Logs are stored in `logs/detection_YYYYMMDD.log` with daily rotation (30 days retention).

Log levels:
- **DEBUG**: Detailed information for debugging
- **INFO**: General information about system operation
- **WARNING**: Warning messages (non-critical)
- **ERROR**: Error messages (critical issues)

View logs:
```bash
tail -f logs/detection_$(date +%Y%m%d).log
```

## License

[Specify your license here]

## Support

For issues and questions:
1. Check this README
2. Review logs in `logs/` directory
3. Check API documentation at http://localhost:8000/docs
4. Contact support team

## Version

**v1.0.0** - Initial release

## Credits

- **YOLOv8**: Ultralytics
- **Backend**: FastAPI, OpenCV, PyTorch
- **Frontend**: React, Vite, TailwindCSS, Recharts
- **VMS**: NxWitness

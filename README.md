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

### Development Mode

**Terminal 1 - Backend:**
```bash
cd backend
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```

Access the application:
- Frontend: http://localhost:5173 (development server)
- Backend API: http://localhost:8000/docs (Swagger UI)

### Production Mode

**Build Frontend:**
```bash
cd frontend
npm run build
```

**Run Backend (serves frontend):**
```bash
cd backend
venv\Scripts\activate  # Windows
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Access the application: http://localhost:8000

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

### Backend (FastAPI)
```
backend/
├── main.py                 # FastAPI app + WebSocket + startup
├── config.py               # Configuration management
├── routers/
│   ├── cameras.py         # Camera API endpoints
│   ├── detection.py       # Detection config endpoints
│   └── alerts.py          # Alert endpoints
├── services/
│   ├── nx_witness.py      # NxWitness API client
│   ├── stream_manager.py  # Multi-threaded stream processing
│   ├── detector.py        # YOLOv8 detection
│   └── alert_manager.py   # Alert logic with cooldown
└── utils/
    ├── logger.py          # Logging configuration
    └── metrics.py         # Performance metrics
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
- `GET /api/cameras` - Get all cameras
- `GET /api/cameras/status` - Get real-time camera status
- `GET /api/cameras/{id}` - Get specific camera details
- `POST /api/cameras/{id}/restart` - Restart camera stream

### Detection
- `GET /api/detection/config` - Get current configuration
- `POST /api/detection/config` - Update configuration
- `GET /api/detection/status` - Get detection system status

### Alerts
- `GET /api/alerts` - Get alert history (with filters)
- `GET /api/alerts/export` - Export alerts to CSV
- `GET /api/alerts/stats` - Get alert statistics
- `GET /api/alerts/buffer-status` - Get alert buffer status

### System
- `GET /health` - Health check
- `GET /api/metrics` - System metrics
- `WebSocket /ws` - Real-time updates

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

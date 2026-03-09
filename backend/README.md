# Backend - Person Detection System

## Overview

FastAPI-based backend for YOLOv8 person detection with multi-threaded stream processing.

## Structure

```
backend/
├── main.py                 # FastAPI app + WebSocket + startup
├── config.py               # Configuration management
├── requirements.txt        # Python dependencies
├── routers/               # API endpoints
│   ├── cameras.py         # Camera management APIs
│   ├── detection.py       # Detection configuration APIs
│   └── alerts.py          # Alert management APIs
├── services/              # Core business logic
│   ├── nx_witness.py      # NxWitness VMS client
│   ├── stream_manager.py  # Multi-threaded stream processing
│   ├── detector.py        # YOLOv8 person detection
│   └── alert_manager.py   # Alert logic with cooldown
└── utils/                 # Utilities
    ├── logger.py          # Structured logging
    └── metrics.py         # Performance metrics
```

## Key Components

### main.py
- FastAPI application setup
- WebSocket endpoint for real-time updates
- Startup/shutdown lifecycle management
- Frontend serving (production)
- CORS configuration

### Services

#### nx_witness.py
- NxWitness API client
- Basic authentication
- Camera discovery
- Stream URL generation
- Alert sending

#### stream_manager.py
- Producer-Consumer pattern
- Producer threads: Read MJPEG streams
- Consumer threads: Process frames with YOLO
- Frame queue management
- Auto-reconnect on failures

#### detector.py
- YOLOv8 model loading
- Batch inference
- Person detection (class 0)
- GPU/CPU support
- Confidence filtering

#### alert_manager.py
- Alert triggering logic
- Per-camera cooldown
- Alert buffering
- Retry mechanism
- Alert history

### Routers

#### cameras.py
- `GET /api/cameras` - List all cameras
- `GET /api/cameras/status` - Real-time status
- `GET /api/cameras/{id}` - Camera details
- `POST /api/cameras/{id}/restart` - Restart stream

#### detection.py
- `GET /api/detection/config` - Get configuration
- `POST /api/detection/config` - Update configuration
- `GET /api/detection/status` - System status

#### alerts.py
- `GET /api/alerts` - Alert history
- `GET /api/alerts/export` - Export CSV
- `GET /api/alerts/stats` - Statistics
- `GET /api/alerts/buffer-status` - Buffer info

### Utils

#### logger.py
- Structured logging
- Console + file handlers
- Daily log rotation
- 30-day retention

#### metrics.py
- FPS tracking
- GPU usage monitoring
- Alert counting
- Performance history
- System uptime

## Running

### Development
```bash
# Activate virtual environment
venv\Scripts\activate

# Start with auto-reload
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Production
```bash
# Activate virtual environment
venv\Scripts\activate

# Start without reload
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

### Direct Python
```bash
python main.py
```

## Configuration

See [.env](../.env) or [.env.example](../.env.example) for all configuration options.

Key settings:
- `NX_SERVER_URL` - NxWitness server
- `YOLO_MODEL` - Model file (yolov8n.pt or yolov8s.pt)
- `DEVICE` - cuda:0 or cpu
- `CONFIDENCE_THRESHOLD` - Detection threshold (0.1-0.9)
- `BATCH_SIZE` - Frames per batch (1-16)

## API Documentation

When running, access interactive API docs at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Architecture Patterns

### Producer-Consumer
- **Producers**: 1 thread per camera (read frames)
- **Consumers**: 4 threads (process batches)
- **Queue**: Shared frame queue (1000 capacity)

### Async/Await
- FastAPI endpoints are async
- WebSocket handlers are async
- Background tasks use asyncio

### Thread Safety
- Locks for shared data structures
- Thread-safe queues
- Atomic operations

## Dependencies

Core:
- FastAPI 0.109.0 - Web framework
- Uvicorn 0.27.0 - ASGI server
- Pydantic 2.5.3 - Validation

AI/ML:
- ultralytics 8.1.11 - YOLOv8
- torch 2.1.2 - PyTorch
- torchvision 0.16.2 - Vision models

Vision:
- opencv-python-headless 4.9.0 - Image processing
- numpy 1.26.3 - Arrays

HTTP:
- requests 2.31.0 - HTTP client
- aiohttp 3.9.1 - Async HTTP
- websockets 12.0 - WebSocket

## Adding New Endpoints

1. Create router function in `routers/`
2. Import router in `main.py`
3. Register with `app.include_router()`
4. Test at http://localhost:8000/docs

Example:
```python
# routers/example.py
from fastapi import APIRouter

router = APIRouter(prefix="/api/example", tags=["example"])

@router.get("/")
async def get_example():
    return {"message": "Hello"}
```

```python
# main.py
from backend.routers import example
app.include_router(example.router)
```

## Logging

Logs are written to `logs/detection_YYYYMMDD.log`

Log levels:
- DEBUG - Detailed info
- INFO - General info
- WARNING - Warnings
- ERROR - Errors

Usage:
```python
from backend.utils.logger import logger

logger.info("Info message")
logger.warning("Warning message")
logger.error("Error message")
```

## Metrics

Track performance:
```python
from backend.utils.metrics import metrics

metrics.record_fps("camera_id", 25.5)
metrics.record_detection("camera_id", 2)
metrics.record_alert("camera_id")
```

Get summary:
```python
summary = metrics.get_summary()
# Returns: {avgFps, alertsToday, uptime, ...}
```

## Error Handling

All exceptions are caught and logged. API endpoints return appropriate HTTP status codes:
- 200 - Success
- 400 - Bad request
- 404 - Not found
- 500 - Server error

## Testing

```bash
# Run tests (if implemented)
pytest

# Test specific file
pytest tests/test_detector.py

# With coverage
pytest --cov=backend
```

## Performance

Expected on RTX 3090:
- 200-400 FPS total (20 cameras)
- 60-80% GPU utilization
- <100ms latency per detection
- 8-12GB GPU memory

Optimization tips:
- Increase BATCH_SIZE for better GPU usage
- Reduce STREAM_WIDTH/HEIGHT for speed
- Adjust FRAME_SAMPLING to skip frames
- Use YOLOv8n instead of YOLOv8s

## Troubleshooting

### CUDA not available
```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

### Import errors
```bash
# Ensure backend is in PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:/path/to/Safety"
```

### Port already in use
Change PORT in .env or use different port:
```bash
uvicorn main:app --port 8001
```

---

For more information, see [../README.md](../README.md)

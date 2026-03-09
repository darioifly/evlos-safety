# Person Detection System - Project Summary

## 📋 Overview

Complete end-to-end person detection system for NxWitness VMS using YOLOv8 AI model with GPU acceleration.

**Version:** 1.0.0
**Status:** ✅ Production Ready
**Platform:** Windows 10/11, Linux (Ubuntu 20.04+)
**License:** [Your License]

## 🎯 Key Features

### Detection
- ✅ **Real-time person detection** using YOLOv8n/YOLOv8s
- ✅ **GPU acceleration** (NVIDIA CUDA)
- ✅ **Batch processing** for optimal GPU utilization
- ✅ **Configurable confidence threshold** (0.1-0.9)
- ✅ **Multi-camera support** (up to 20 streams)

### Integration
- ✅ **NxWitness VMS integration** via REST API
- ✅ **MJPEG stream processing**
- ✅ **Automatic camera discovery**
- ✅ **Alert notifications** to NxWitness

### Performance
- ✅ **Multi-threaded architecture** (Producer-Consumer)
- ✅ **Frame sampling** (configurable)
- ✅ **Automatic retry** on failures
- ✅ **Alert cooldown** to prevent spam
- ✅ **Performance metrics** tracking

### User Interface
- ✅ **Modern React dashboard**
- ✅ **Real-time WebSocket updates**
- ✅ **Camera status grid**
- ✅ **Alert log with export**
- ✅ **Configuration panel**
- ✅ **Performance dashboard**

## 📁 Project Structure

```
Safety/
├── backend/                    # FastAPI Backend
│   ├── main.py                # Main application + WebSocket
│   ├── config.py              # Configuration management
│   ├── requirements.txt       # Python dependencies
│   ├── routers/              # API endpoints
│   │   ├── cameras.py        # Camera APIs
│   │   ├── detection.py      # Detection config APIs
│   │   └── alerts.py         # Alert APIs
│   ├── services/             # Core services
│   │   ├── nx_witness.py     # NxWitness client
│   │   ├── stream_manager.py # Multi-thread stream processing
│   │   ├── detector.py       # YOLOv8 detection
│   │   └── alert_manager.py  # Alert logic
│   └── utils/                # Utilities
│       ├── logger.py         # Logging
│       └── metrics.py        # Performance metrics
│
├── frontend/                  # React Frontend
│   ├── src/
│   │   ├── App.jsx           # Main component
│   │   ├── main.jsx          # Entry point
│   │   ├── components/       # UI components
│   │   │   ├── CameraGrid.jsx
│   │   │   ├── ConfigPanel.jsx
│   │   │   ├── AlertLog.jsx
│   │   │   └── Dashboard.jsx
│   │   ├── hooks/
│   │   │   └── useWebSocket.js
│   │   └── styles/
│   │       └── index.css     # TailwindCSS
│   ├── package.json
│   ├── vite.config.js
│   └── tailwind.config.js
│
├── logs/                      # Log files (auto-created)
├── .env                       # Environment configuration
├── .env.example              # Configuration template
├── .gitignore                # Git ignore rules
├── README.md                 # Full documentation
├── QUICKSTART.md            # Quick setup guide
├── CHANGELOG.md             # Version history
├── setup.bat                # Setup script
├── start_dev.bat            # Development startup
└── start_prod.bat           # Production startup
```

## 🛠️ Technology Stack

### Backend
| Component | Technology | Version |
|-----------|-----------|---------|
| Framework | FastAPI | 0.109.0 |
| Server | Uvicorn | 0.27.0 |
| AI Model | YOLOv8 | 8.1.11 |
| Deep Learning | PyTorch | 2.1.2 |
| Computer Vision | OpenCV | 4.9.0 |
| Validation | Pydantic | 2.5.3 |

### Frontend
| Component | Technology | Version |
|-----------|-----------|---------|
| Framework | React | 18.2.0 |
| Build Tool | Vite | 5.0.11 |
| Styling | TailwindCSS | 3.4.1 |
| State Management | TanStack Query | 5.17.0 |
| Charts | Recharts | 2.10.3 |
| HTTP Client | Axios | 1.6.5 |
| Icons | Lucide React | 0.303.0 |

## 🚀 Quick Start

### Installation
```bash
# Run automated setup
setup.bat

# Configure .env file
# Edit .env with your NxWitness credentials
```

### Development
```bash
# Start development servers
start_dev.bat

# Access:
# - Frontend: http://localhost:5173
# - Backend: http://localhost:8000
# - API Docs: http://localhost:8000/docs
```

### Production
```bash
# Build and start production server
start_prod.bat

# Access: http://localhost:8000
```

## 📊 System Requirements

### Minimum
- **OS:** Windows 10/11 or Ubuntu 20.04+
- **CPU:** 4 cores
- **RAM:** 8GB
- **GPU:** NVIDIA GTX 1060 (6GB VRAM)
- **Python:** 3.9+
- **Node.js:** 18.x+

### Recommended
- **OS:** Windows 11 or Ubuntu 22.04
- **CPU:** 8+ cores
- **RAM:** 32GB
- **GPU:** NVIDIA RTX 3090 (24GB VRAM)
- **Python:** 3.10+
- **Node.js:** 20.x+
- **CUDA:** 11.8+

## 🎛️ Configuration

### Key Settings (`.env`)

**NxWitness:**
```env
NX_SERVER_URL=https://your-server/cameras
NX_ADMIN_USERNAME=admin
NX_ADMIN_PASSWORD=your-password
```

**Detection:**
```env
YOLO_MODEL=yolov8n.pt          # or yolov8s.pt
CONFIDENCE_THRESHOLD=0.5        # 0.1-0.9
DEVICE=cuda:0                   # or cpu
MIN_PERSONS_FOR_ALERT=1
ALERT_COOLDOWN_SECONDS=5
```

**Performance:**
```env
BATCH_SIZE=8                    # Frames per batch
FRAME_SAMPLING=10               # Process 1/N frames
CONSUMER_THREADS=4              # GPU processing threads
```

## 📈 Performance Metrics

### Expected Performance (RTX 3090)
- **FPS per camera:** 15-30 fps (with YOLOv8n)
- **Total throughput:** 200-400 fps (20 cameras)
- **GPU utilization:** 60-80%
- **Latency:** < 100ms per detection
- **Memory usage:** 8-12GB GPU RAM

### Optimization Tips
1. Use YOLOv8n for maximum speed
2. Increase `BATCH_SIZE` (8-16) for better GPU utilization
3. Adjust `FRAME_SAMPLING` to balance accuracy vs. speed
4. Reduce `STREAM_WIDTH/HEIGHT` if needed

## 🔌 API Endpoints

### Cameras
- `GET /api/cameras` - List all cameras
- `GET /api/cameras/status` - Real-time status
- `POST /api/cameras/{id}/restart` - Restart stream

### Detection
- `GET /api/detection/config` - Get configuration
- `POST /api/detection/config` - Update configuration
- `GET /api/detection/status` - System status

### Alerts
- `GET /api/alerts` - Get alert history
- `GET /api/alerts/export` - Export CSV
- `GET /api/alerts/stats` - Statistics

### System
- `GET /health` - Health check
- `GET /api/metrics` - Performance metrics
- `WebSocket /ws` - Real-time updates

## 🐛 Common Issues

### CUDA Not Available
```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

### Camera Streams Not Connecting
1. Check `NX_SERVER_URL` and credentials
2. Verify network connectivity
3. Test API: `curl -u user:pass https://server/api/v1/devices`

### High GPU Memory Usage
1. Reduce `BATCH_SIZE`
2. Lower `STREAM_WIDTH` and `STREAM_HEIGHT`
3. Use YOLOv8n instead of YOLOv8s

## 📝 Next Steps

1. **Review** [README.md](README.md) for detailed documentation
2. **Follow** [QUICKSTART.md](QUICKSTART.md) for setup
3. **Check** [CHANGELOG.md](CHANGELOG.md) for version history
4. **Configure** `.env` with your settings
5. **Run** `setup.bat` to install dependencies
6. **Start** with `start_dev.bat` or `start_prod.bat`

## 🔮 Roadmap

### v1.1.0 (Planned)
- [ ] RTSP stream support
- [ ] Object tracking
- [ ] Zone-based detection
- [ ] Email notifications

### v1.2.0 (Planned)
- [ ] Multi-user authentication
- [ ] Dark mode
- [ ] Mobile app
- [ ] Advanced analytics

### v2.0.0 (Future)
- [ ] Docker deployment
- [ ] Kubernetes support
- [ ] Face recognition
- [ ] License plate detection

## 📞 Support

- **Documentation:** [README.md](README.md)
- **API Docs:** http://localhost:8000/docs
- **Logs:** `logs/detection_YYYYMMDD.log`

## 👥 Contributors

[Add your team here]

## 📄 License

[Specify your license]

---

**Last Updated:** 2024-10-21
**Version:** 1.0.0
**Status:** ✅ Production Ready

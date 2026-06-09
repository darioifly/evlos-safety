# Quick Start Guide

> **Production deploy on this host:** prefer the containerized stack —
> single image with GPU passthrough via WSL2, persistent bind mounts, and
> Windows boot-time autostart. See **[DOCKER.md](DOCKER.md)**.
>
> The bare-metal steps below remain valid for development, but
> production runs in Docker.

## 🚀 Fast Setup (Windows)

### 1. Run Setup Script
```bash
setup.bat
```

This will:
- Create Python virtual environment
- Install all Python dependencies
- Install all Node.js dependencies
- Create `.env` configuration file

### 2. Configure Environment

Edit `.env` file with your NxWitness credentials:
```env
NX_SERVER_URL=https://evlos.ifly.it/cameras
NX_ADMIN_USERNAME=admin
NX_ADMIN_PASSWORD=Sicurezza12!
```

### 3. Start the System

**Development Mode** (with hot reload):
```bash
start_dev.bat
```
- Backend: http://localhost:7002
- Frontend: http://localhost:5173

**Production Mode**:
```bash
start_prod.bat
```
- Full system: http://localhost:7002

## ⚙️ Manual Setup

### Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main_sqlite.py
```

### Frontend
```bash
cd frontend
npm install
npm run dev       # Development
npm run build     # Production build
```

## 🎯 First Steps After Installation

1. **Check Camera Connection**
   - Open http://localhost:5173 (dev) or http://localhost:7002 (prod)
   - Go to "Cameras" tab
   - Verify cameras appear with "Online" status

2. **Configure Detection**
   - Go to "Configuration" tab
   - Adjust settings:
     - Model: YOLOv8n (faster) or YOLOv8s (accurate)
     - Confidence: 0.5 (recommended)
     - Device: cuda:0 (GPU)
     - Min Persons: 1
     - Cooldown: 5 seconds

3. **Monitor Alerts**
   - Go to "Alerts" tab
   - Watch real-time person detection alerts
   - Export alerts to CSV if needed

4. **View Dashboard**
   - Go to "Dashboard" tab
   - Monitor system performance
   - Check FPS, GPU usage, alert statistics

## 🔧 Troubleshooting

### "CUDA not available"
```bash
# Install PyTorch with CUDA 12.1 support (matches ultralytics 8.3.x)
pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu121
```

### "Cannot connect to NxWitness"
- Check `NX_SERVER_URL` in `.env`
- Verify username/password
- Test connection: `curl -u admin:password https://your-server/api/v1/devices`

### Frontend build fails
```bash
cd frontend
rm -rf node_modules
npm install
npm run build
```

### Port already in use
Change port in `.env`:
```env
PORT=7003
```
Or stop whichever process is holding `7002` (bare-metal Python *or* the
container — they share the same port).

## 📊 System Check

After startup, verify:
- ✅ Backend API: http://localhost:7002/health
- ✅ API Docs: http://localhost:7002/docs
- ✅ Frontend: http://localhost:5173 (dev) or http://localhost:7002 (prod)
- ✅ WebSocket: Check connection status in UI header

## 🎬 Video Tutorial

[Coming soon]

## 📖 Full Documentation

See [README.md](README.md) for complete documentation.

## 🆘 Need Help?

1. Check logs in `logs/` directory
2. Review [README.md](README.md) troubleshooting section
3. Check API documentation at http://localhost:7002/docs
4. Contact support team

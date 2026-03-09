# Person Detection System - Documentation Index

## 📚 Quick Navigation

### 🚀 Getting Started
1. **[QUICKSTART.md](QUICKSTART.md)** - Fast setup guide (5 minutes)
2. **[INSTALLATION_CHECKLIST.md](INSTALLATION_CHECKLIST.md)** - Step-by-step installation
3. **[README.md](README.md)** - Complete documentation

### 📋 Project Information
- **[PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)** - High-level overview
- **[PROJECT_METRICS.md](PROJECT_METRICS.md)** - Code statistics and metrics
- **[CHANGELOG.md](CHANGELOG.md)** - Version history

### 🛠️ Setup & Configuration
- **[.env.example](.env.example)** - Configuration template
- **[setup.bat](setup.bat)** - Automated setup script
- **[check_system.bat](check_system.bat)** - System requirements check

### 🎮 Running the Application
- **[start_dev.bat](start_dev.bat)** - Development mode
- **[start_prod.bat](start_prod.bat)** - Production mode

## 📖 Documentation Guide

### For First-Time Users
**Recommended reading order:**
1. Start with [QUICKSTART.md](QUICKSTART.md)
2. Run `check_system.bat` to verify requirements
3. Run `setup.bat` to install
4. Follow [INSTALLATION_CHECKLIST.md](INSTALLATION_CHECKLIST.md)
5. Refer to [README.md](README.md) for detailed information

### For Developers
**Recommended reading order:**
1. [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) - Understand architecture
2. [PROJECT_METRICS.md](PROJECT_METRICS.md) - Review code structure
3. [README.md](README.md) - Technical details
4. Explore source code in `backend/` and `frontend/src/`

### For System Administrators
**Recommended reading order:**
1. [README.md](README.md) - Full technical documentation
2. [INSTALLATION_CHECKLIST.md](INSTALLATION_CHECKLIST.md) - Deployment guide
3. Review `.env` configuration options
4. Monitor `logs/` directory

## 🗂️ File Structure Overview

```
Safety/
│
├── 📄 Documentation
│   ├── INDEX.md                          ← You are here
│   ├── README.md                         ← Complete documentation
│   ├── QUICKSTART.md                     ← Fast setup guide
│   ├── PROJECT_SUMMARY.md                ← Overview
│   ├── PROJECT_METRICS.md                ← Statistics
│   ├── INSTALLATION_CHECKLIST.md         ← Installation steps
│   └── CHANGELOG.md                      ← Version history
│
├── 🔧 Configuration
│   ├── .env                              ← Your configuration (don't commit)
│   ├── .env.example                      ← Template
│   └── .gitignore                        ← Git ignore rules
│
├── 🚀 Scripts
│   ├── setup.bat                         ← Initial setup
│   ├── check_system.bat                  ← System verification
│   ├── start_dev.bat                     ← Development mode
│   └── start_prod.bat                    ← Production mode
│
├── 🐍 Backend (Python/FastAPI)
│   ├── main.py                           ← Main application
│   ├── config.py                         ← Configuration
│   ├── requirements.txt                  ← Dependencies
│   ├── routers/                          ← API endpoints
│   │   ├── cameras.py
│   │   ├── detection.py
│   │   └── alerts.py
│   ├── services/                         ← Business logic
│   │   ├── nx_witness.py
│   │   ├── stream_manager.py
│   │   ├── detector.py
│   │   └── alert_manager.py
│   └── utils/                            ← Utilities
│       ├── logger.py
│       └── metrics.py
│
├── ⚛️ Frontend (React/Vite)
│   ├── package.json                      ← Dependencies
│   ├── vite.config.js                    ← Build config
│   ├── tailwind.config.js                ← Styling config
│   └── src/
│       ├── main.jsx                      ← Entry point
│       ├── App.jsx                       ← Main component
│       ├── components/                   ← UI components
│       │   ├── CameraGrid.jsx
│       │   ├── ConfigPanel.jsx
│       │   ├── AlertLog.jsx
│       │   └── Dashboard.jsx
│       ├── hooks/
│       │   └── useWebSocket.js
│       └── styles/
│           └── index.css
│
└── 📊 Logs
    └── logs/                             ← Application logs (auto-created)
```

## 🎯 Common Tasks

### Installation
```bash
1. check_system.bat      # Verify requirements
2. setup.bat             # Install dependencies
3. Edit .env             # Configure settings
4. start_dev.bat         # Start development mode
```

### Development
```bash
# Start both servers
start_dev.bat

# Access:
# - Frontend: http://localhost:5173
# - Backend: http://localhost:8000
# - API Docs: http://localhost:8000/docs
```

### Production
```bash
# Build and start
start_prod.bat

# Access: http://localhost:8000
```

### Troubleshooting
```bash
1. Check logs/           # Review error logs
2. See README.md         # Troubleshooting section
3. Run check_system.bat  # Verify system
```

## 📞 Support & Resources

### Documentation
- **README.md** - Complete technical guide
- **API Docs** - http://localhost:8000/docs (when running)
- **Logs** - `logs/detection_YYYYMMDD.log`

### Key Sections in README
- Installation guide
- Configuration options
- API endpoints
- Troubleshooting
- Performance optimization

### Common Questions

**Q: How do I get started quickly?**
A: Follow [QUICKSTART.md](QUICKSTART.md)

**Q: What are the system requirements?**
A: See [README.md](README.md) - System Requirements section

**Q: How do I configure detection settings?**
A: Edit `.env` file or use web UI Configuration panel

**Q: Where are the logs?**
A: `logs/detection_YYYYMMDD.log`

**Q: How do I update configuration?**
A: Edit `.env` and restart, or use web UI

**Q: Camera streams not connecting?**
A: See [README.md](README.md) - Troubleshooting section

**Q: How do I optimize performance?**
A: See [README.md](README.md) - Performance Optimization section

## 🔄 Update & Maintenance

### Checking for Updates
```bash
# Check version
# See CHANGELOG.md for version history
```

### Updating Dependencies
```bash
# Backend
cd backend
pip install -r requirements.txt --upgrade

# Frontend
cd frontend
npm update
```

### Backup Configuration
```bash
# Important: Backup your .env file before updates
copy .env .env.backup
```

## 📝 Version Information

- **Current Version:** 1.0.0
- **Release Date:** 2024-10-21
- **Status:** Production Ready
- **Last Updated:** 2024-10-21

## 🏆 Quick Reference Card

| Task | Command | Documentation |
|------|---------|---------------|
| Check system | `check_system.bat` | [README.md](README.md) |
| Install | `setup.bat` | [QUICKSTART.md](QUICKSTART.md) |
| Configure | Edit `.env` | [README.md](README.md) |
| Start Dev | `start_dev.bat` | [QUICKSTART.md](QUICKSTART.md) |
| Start Prod | `start_prod.bat` | [README.md](README.md) |
| View Logs | `logs/` folder | [README.md](README.md) |
| API Docs | http://localhost:8000/docs | Auto-generated |
| Health Check | http://localhost:8000/health | [README.md](README.md) |

---

**Need help?** Start with [QUICKSTART.md](QUICKSTART.md) or [README.md](README.md)

**Report issues:** [Contact your support team]

**Version:** 1.0.0 | **Last Updated:** 2024-10-21

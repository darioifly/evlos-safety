# Installation Checklist

Complete this checklist to ensure proper installation and configuration of the Person Detection System.

## Pre-Installation

### System Requirements
- [ ] Windows 10/11 or Ubuntu 20.04+ installed
- [ ] At least 16GB RAM (32GB recommended)
- [ ] NVIDIA GPU with 6GB+ VRAM (RTX 3090 recommended)
- [ ] At least 50GB free disk space

### Software Prerequisites
- [ ] Python 3.9+ installed
  - Verify: `python --version`
- [ ] Node.js 18.x+ installed
  - Verify: `node --version`
- [ ] npm installed
  - Verify: `npm --version`
- [ ] NVIDIA Driver installed
  - Verify: `nvidia-smi`
- [ ] CUDA 11.8+ installed (optional but recommended)
  - Verify: `nvcc --version`

### Network Requirements
- [ ] Access to NxWitness server
- [ ] NxWitness server URL known
- [ ] Admin credentials for NxWitness available
- [ ] Port 8000 available (or change in config)

## Installation Steps

### 1. System Check
- [ ] Run `check_system.bat`
- [ ] Verify all prerequisites pass
- [ ] Note any warnings

### 2. Initial Setup
- [ ] Run `setup.bat`
- [ ] Wait for Python dependencies to install
- [ ] Wait for Node.js dependencies to install
- [ ] Verify no errors during installation

### 3. Configuration
- [ ] Open `.env` file
- [ ] Update `NX_SERVER_URL` with your NxWitness server
- [ ] Update `NX_ADMIN_USERNAME` with your username
- [ ] Update `NX_ADMIN_PASSWORD` with your password
- [ ] Review other settings (optional)
- [ ] Save `.env` file

### 4. GPU Setup (if using CUDA)
- [ ] Verify CUDA is detected: `nvidia-smi`
- [ ] Check `.env` has `DEVICE=cuda:0`
- [ ] If CUDA not available, change to `DEVICE=cpu`

## First Run - Development Mode

### 5. Start Development Servers
- [ ] Run `start_dev.bat`
- [ ] Wait for backend to start (watch console)
- [ ] Wait for frontend to start (watch console)
- [ ] Note any errors in console output

### 6. Verify Backend
- [ ] Open http://localhost:8000/health
- [ ] Should see: `{"status":"healthy",...}`
- [ ] Open http://localhost:8000/docs
- [ ] Swagger API documentation loads

### 7. Verify Frontend
- [ ] Open http://localhost:5173
- [ ] Homepage loads
- [ ] Check connection status (top right)
  - [ ] Shows "Connected" with green indicator

### 8. Test Camera Connection
- [ ] Go to "Cameras" tab
- [ ] Cameras should appear
- [ ] Some cameras show "Online" status
- [ ] Note: If all offline, check NxWitness credentials

### 9. Configure Detection
- [ ] Go to "Configuration" tab
- [ ] Review settings:
  - [ ] Model: YOLOv8n (for speed) or YOLOv8s (for accuracy)
  - [ ] Confidence: 0.5 (recommended)
  - [ ] Device: cuda:0 or cpu
  - [ ] Min Persons: 1
  - [ ] Cooldown: 5 seconds
- [ ] Click "Apply Configuration"
- [ ] Wait for success message

### 10. Monitor Detection
- [ ] Go to "Cameras" tab
- [ ] Watch for person count updates (if people visible)
- [ ] Note FPS for each camera

### 11. Check Alerts
- [ ] Go to "Alerts" tab
- [ ] Wait for alerts to appear (when persons detected)
- [ ] Verify alert details correct

### 12. Review Dashboard
- [ ] Go to "Dashboard" tab
- [ ] Check Average FPS shows value
- [ ] Check GPU Usage (if using CUDA)
- [ ] Review performance charts

## Production Deployment

### 13. Build Frontend
- [ ] Close development servers (Ctrl+C)
- [ ] Run: `cd frontend && npm run build`
- [ ] Verify `frontend/dist/` directory created
- [ ] Check for build errors

### 14. Start Production Server
- [ ] Run `start_prod.bat`
- [ ] Wait for server to start
- [ ] Note startup messages

### 15. Verify Production
- [ ] Open http://localhost:8000
- [ ] Application loads (frontend served by backend)
- [ ] Test all tabs (Cameras, Config, Alerts, Dashboard)
- [ ] Verify WebSocket connection (green indicator)

## Troubleshooting

### Common Issues Encountered
- [ ] CUDA not available
  - Solution: Install CUDA toolkit or use CPU
- [ ] Camera streams not connecting
  - Solution: Verify NxWitness URL and credentials
- [ ] Port 8000 already in use
  - Solution: Change `PORT` in `.env`
- [ ] Frontend not loading
  - Solution: Run `cd frontend && npm run build` again
- [ ] High memory usage
  - Solution: Reduce `BATCH_SIZE` in `.env`

### Log Verification
- [ ] Check `logs/detection_YYYYMMDD.log`
- [ ] No critical errors
- [ ] Cameras connecting successfully
- [ ] Detections being logged

## Performance Verification

### 16. Performance Check
- [ ] Average FPS > 10 (acceptable)
- [ ] Average FPS > 20 (good)
- [ ] GPU Usage 60-80% (optimal)
- [ ] No memory errors in logs
- [ ] Alerts being sent successfully

### 17. Stress Test (Optional)
- [ ] Enable all 20 cameras
- [ ] Monitor system resources
- [ ] Check for dropped frames
- [ ] Verify alerts still working
- [ ] Note maximum sustainable load

## Final Verification

### 18. Complete System Test
- [ ] All cameras showing correct status
- [ ] Person detection working
- [ ] Alerts being generated
- [ ] Alerts appearing in NxWitness (if configured)
- [ ] Configuration changes take effect
- [ ] Alert export to CSV works
- [ ] Dashboard metrics updating
- [ ] No errors in logs

### 19. Documentation Review
- [ ] Read README.md
- [ ] Understand configuration options
- [ ] Know how to restart services
- [ ] Know where to find logs
- [ ] Contact information for support available

### 20. Backup Configuration
- [ ] Save `.env` file backup
- [ ] Document any custom settings
- [ ] Note working configuration for reference

## Sign-Off

Installation completed by: _______________
Date: _______________
Verified by: _______________
Date: _______________

### Notes/Issues:
```
[Add any notes, issues encountered, or special configurations here]
```

## Next Steps

After successful installation:

1. **Monitor Performance**
   - Check logs daily for first week
   - Monitor GPU usage and temperatures
   - Track alert accuracy

2. **Optimize Settings**
   - Adjust confidence threshold based on results
   - Fine-tune alert cooldown
   - Optimize batch size for your GPU

3. **Regular Maintenance**
   - Review logs weekly
   - Update models if needed
   - Check for system updates

4. **Documentation**
   - Document any custom configurations
   - Keep track of parameter changes
   - Note optimal settings for reference

---

**Installation Checklist Version:** 1.0
**Last Updated:** 2024-10-21

# Running evlos-safety in Docker

Single-container deployment of evlos-safety: FastAPI backend + YOLOv8 PPE
detection + React SPA, all served from one process on port **7002**, with
NVIDIA GPU passthrough via WSL2.

This document covers the Windows-host workflow. The setup is **additive** —
the bare-metal workflow (`start_fastapi.bat`, `python main_sqlite.py`) still
works, just don't run both at the same time (they share port 7002 and the
GPU).

---

## 1. Prerequisites

| Component | Minimum | Verified version on this host |
|---|---|---|
| Windows | Windows 11 with WSL2 enabled | Windows 11 Pro 10.0.26200 |
| WSL2 default version | 2 (`wsl --status` must say `Versione predefinita: 2`) | OK |
| NVIDIA Windows driver | **545+** for CUDA 12.x in WSL2 | 581.95 (CUDA 13.0 capable) |
| Docker Desktop | **4.x** with WSL2 backend + NVIDIA GPU integration | 4.77.0 |
| Disk space | ~14 GB for the runtime image + model weights | — |

**You do NOT install a Linux NVIDIA driver inside WSL.** The Windows
driver exposes the GPU to WSL2 and to Docker Desktop's containers; the
CUDA libs come from the `nvidia/cuda:12.1.0-runtime-ubuntu22.04` base
image.

---

## 2. One-time setup

### 2.1 Install Docker Desktop

From an **elevated PowerShell** (Run as administrator):

```powershell
winget install -e --id Docker.DockerDesktop --accept-package-agreements --accept-source-agreements
```

A Windows reboot may be required. After install, launch Docker Desktop
(`Start → Docker Desktop`).

### 2.2 Docker Desktop GUI checks

* **Settings → General** → ✓ `Use the WSL 2 based engine` (default on
  recent versions).
* **Settings → General** → ✓ `Start Docker Desktop when you sign in` —
  this is half of the boot-time autostart mechanism. The other half is
  `restart: unless-stopped` in `docker-compose.yml`.
* **Settings → Resources → WSL Integration** → ✓ on Ubuntu (and on the
  default distro).
* **Settings → General** → ☐ `Enable Kubernetes` — leave OFF, it eats
  several GB of RAM.

### 2.3 Verify GPU reaches containers (single most important gate)

This must print the NVIDIA-SMI table from *inside* a container before
proceeding. Run from any shell (with `docker` on PATH):

```powershell
docker run --rm --gpus all nvidia/cuda:12.1.0-runtime-ubuntu22.04 nvidia-smi
```

If it fails, fix the WSL Integration toggle or the NVIDIA Windows driver
before going further — `docker compose up` won't work either.

### 2.4 Provide secrets via `.env`

The repo ships an `.env.example` at the root. Copy it and fill in the
real values (NxWitness password, EVLOS URL/key if needed):

```powershell
copy .env.example .env
notepad .env
```

`.env` is gitignored and is loaded at container start via `env_file:`. It
is **never** baked into the image (verified — `/app/.env` is absent).

---

## 3. Build and run

From the repo root:

```powershell
docker compose build           # ~5-15 min on first build; layer-cached after
docker compose up -d           # start in background
docker compose logs -f         # follow logs
docker compose ps              # status (should be `Up X (healthy)`)
```

Open `http://localhost:7002/` or `http://<lan-ip>:7002/` from any LAN PC.

Stop:
```powershell
docker compose down
```

---

## 4. Verification checklist

| Check | How |
|---|---|
| Container healthy | `docker compose ps` → `Up X (healthy)` |
| GPU inside container | `docker compose exec evlos-safety nvidia-smi` |
| Torch sees CUDA | `docker compose exec evlos-safety python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"` |
| `/health` | `curl http://localhost:7002/health` → `{"status":"ok","mode":"sqlite"}` |
| SPA loads | `curl -I http://localhost:7002/` → `HTTP/1.1 200 OK` |
| API endpoints | `curl http://localhost:7002/api/metrics` |
| WebSocket | dashboard loads; or `wscat -c ws://localhost:7002/ws` |
| Logs | `docker compose logs --tail=200 evlos-safety` — look for `Loading YOLO model ... on cuda:0` followed by `YOLO model loaded on cuda:0` |

A 503 on `/` means the frontend build stage didn't land. Rebuild and
check the build log for `npm ci` / `vite build` errors.

---

## 5. Persistent state and volumes

Every path the live code reads or writes is bind-mounted from the host so
state survives `docker compose down`/recreate:

| Host path | Container path | Contents |
|---|---|---|
| `backend/database/` | `/app/backend/database/` | SQLite WAL DB (single source of truth) |
| `backend/data/` | `/app/backend/data/` | Alert evidence archive + EVLOS retry spool |
| `backend/logs/` | `/app/backend/logs/` | Rotating log files (50 MB × 30 backups) |
| `backend/config.json` | `/app/backend/config.json` | Hot-reloaded runtime config |
| `backend/models/` | `/app/backend/models/` | PPE / helmet-vest weights (~290 MB) |
| `backend/yolov8n.pt` | `/app/backend/yolov8n.pt` | Small person-detection model |

`backend/data/static/alerts/` is treated as a **permanent evidence
archive** — the in-process cleanup task is disabled accordingly, so files
in there are never auto-deleted by the application.

Files written by the container land on the Windows filesystem and are
inspectable in Windows Explorer.

---

## 6. Autostart on Windows boot

Two layers of redundancy:

1. **Docker Desktop "Start on login"** — Settings → General. Sets
   `AutoStart: true` in `%APPDATA%\Docker\settings-store.json`.
2. **`restart: unless-stopped`** in `docker-compose.yml` — once the Docker
   engine is up, the container is recreated automatically.

Together those bring the stack up after every Windows login without any
extra glue. As a defence-in-depth backstop:

3. **Scheduled Task `evlos-safety-autostart`** — runs
   `scripts/start-evlos-stack.bat` 1 minute after each user logon. The
   script waits up to ~3 min for the Docker engine and then runs
   `docker compose up -d` (idempotent — no-op if already healthy).
   Auditable via `backend\logs\autostart.log`.

To register the Scheduled Task from PowerShell (no admin required — runs
as the current user with Limited run level):

```powershell
$script = "C:\Users\iflys\projects\evlos-safety\scripts\start-evlos-stack.bat"
$action  = New-ScheduledTaskAction -Execute "C:\Windows\System32\cmd.exe" -Argument "/c `"$script`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$trigger.Delay = "PT1M"
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
              -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::FromHours(1))
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
              -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName "evlos-safety-autostart" `
    -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
    -Description "Idempotent backstop: brings up the evlos-safety container after Docker Desktop is ready." `
    -Force
```

Verify:
```powershell
Get-ScheduledTask -TaskName "evlos-safety-autostart"
Start-ScheduledTask -TaskName "evlos-safety-autostart"    # one-shot smoke test
Get-Content backend\logs\autostart.log -Tail 10
```

**Caveat (intentional):** Docker Desktop runs per-user, not as a
pre-login service, so this brings the stack up *after* the user logs in.
Truly pre-login / headless boot would require running the Docker engine
as a Windows service (out of scope here).

---

## 7. Troubleshooting

### GPU not visible inside container
```powershell
docker run --rm --gpus all nvidia/cuda:12.1.0-runtime-ubuntu22.04 nvidia-smi
```
* If this fails: open Docker Desktop → Settings → Resources → WSL
  Integration → toggle Ubuntu off and back on, Apply & Restart.
* Also check that the NVIDIA Windows driver is recent (`nvidia-smi` on
  the host).

### `Can't get attribute 'C3k2' on <module 'ultralytics.nn.modules.block'>`
Model checkpoint was exported with `ultralytics >= 8.3` (YOLOv11 family),
which the container needs as well. `requirements.txt` pins `8.3.220`. If
you ever bump it down, this error returns.

### 503 on `/`
Frontend was not built into the image. Re-run `docker compose build` and
watch for `npm ci` / `vite build` failures.

### `docker-credential-desktop` not found
Symptom: `docker pull` fails with "executable file not found in %PATH%".
Fix: `C:\Program Files\Docker\Docker\resources\bin` must be on PATH.
Restart the shell after a fresh Docker Desktop install, or add it
manually for the current session:
```powershell
$env:PATH = "C:\Program Files\Docker\Docker\resources\bin;$env:PATH"
```

### Port 7002 already in use
Stop the bare-metal Python backend (`Stop-Process -Id <pid> -Force` or
close the terminal that runs `python main_sqlite.py`). Both deployments
bind the same port.

### GPU VRAM exhausted (CUDA OOM)
The bare-metal backend may still be holding VRAM. Stop it before
starting the container; verify with `nvidia-smi --query-gpu=memory.used,memory.free --format=csv`.

### Docker Desktop won't start as a service for pre-login boot
This is by design. Use the per-user autostart described in §6.

---

## 8. Updating

```powershell
git pull
docker compose build
docker compose up -d
```

`docker compose up -d` recreates the container with the new image while
preserving all bind-mounted state. No data loss expected.

---

## 9. Reverting to the bare-metal workflow

Nothing about the Docker setup deletes or modifies your venv. To go back
to the pre-Docker workflow:

```powershell
docker compose down              # stop the container
.\start_fastapi.bat              # or: cd backend; python main_sqlite.py
```

Both paths share the same `backend/database/surveillance.db`,
`backend/data/`, and `backend/config.json` on disk.

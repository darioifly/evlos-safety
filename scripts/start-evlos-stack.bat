@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================================
REM start-evlos-stack.bat
REM
REM Boot-time autostart BACKSTOP for the evlos-safety container.
REM
REM Primary autostart is the combination of (a) Docker Desktop's "start on
REM login" setting and (b) `restart: unless-stopped` in docker-compose.yml.
REM Together those already bring the container back automatically. This
REM script exists as a defence-in-depth: if Docker Desktop is slow to come
REM up, or someone ran `docker compose down` and forgot, the scheduled task
REM will idempotently start the stack again on the next login.
REM
REM Best practices applied:
REM   * Idempotent: `docker compose up -d` is a no-op when the service is
REM     already running and healthy.
REM   * Resilient to Docker engine cold-start: wait up to ~3 min for the
REM     engine to respond before giving up.
REM   * Anchored at the repo root via the script's own location, not CWD.
REM   * Writes a short log to backend\logs\autostart.log for audit.
REM ============================================================================

set "REPO_ROOT=%~dp0.."
pushd "%REPO_ROOT%" >nul 2>&1

set "LOG_DIR=%REPO_ROOT%\backend\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1
set "LOG_FILE=%LOG_DIR%\autostart.log"

call :log "================================================================"
call :log "start-evlos-stack.bat invoked"
call :log "repo: %REPO_ROOT%"

REM Wait for the Docker engine — `docker info` returns non-zero until the
REM daemon is ready. Up to ~3 minutes (36 * 5 s) of patience for Docker
REM Desktop to spin up after a fresh login.
set /a TRIES=0
:wait_docker
docker info >nul 2>&1
if not errorlevel 1 goto docker_ready
set /a TRIES+=1
if !TRIES! GEQ 36 (
    call :log "ERROR: Docker engine did not become ready after !TRIES! attempts"
    popd >nul 2>&1
    exit /b 1
)
call :log "Docker engine not ready yet (attempt !TRIES!/36); sleeping 5s"
timeout /t 5 /nobreak >nul
goto wait_docker

:docker_ready
call :log "Docker engine ready"

REM Bring up the stack. Idempotent: if already up, this is a no-op.
docker compose up -d >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    call :log "ERROR: docker compose up -d returned errorlevel %ERRORLEVEL%"
    popd >nul 2>&1
    exit /b 1
)
call :log "docker compose up -d completed OK"

popd >nul 2>&1
exit /b 0

:log
echo [%date% %time%] %~1
echo [%date% %time%] %~1 >> "%LOG_FILE%"
exit /b 0

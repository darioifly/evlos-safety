"""
Script to kill all backend processes and restart cleanly
"""
import psutil
import time
import subprocess
from pathlib import Path

def kill_all_backends():
    """Kill all main_sqlite.py processes"""
    killed = []

    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info['cmdline']
            if cmdline and 'main_sqlite.py' in ' '.join(cmdline):
                pid = proc.info['pid']
                print(f"Terminating backend process {pid}")
                proc.terminate()
                killed.append(pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if killed:
        print(f"Waiting 2 seconds for graceful shutdown...")
        time.sleep(2)

        # Force kill any remaining
        for pid in killed:
            try:
                proc = psutil.Process(pid)
                if proc.is_running():
                    print(f"Force killing process {pid}")
                    proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        print(f"Killed {len(killed)} backend processes")
    else:
        print("No backend processes found")

    return len(killed)

def start_backend():
    """Start a new backend process"""
    backend_dir = Path(__file__).parent
    venv_python = backend_dir / "venv" / "Scripts" / "python.exe"
    main_script = backend_dir / "main_sqlite.py"

    print(f"Starting new backend process...")
    proc = subprocess.Popen(
        [str(venv_python), str(main_script)],
        cwd=str(backend_dir)
    )
    print(f"Backend started with PID {proc.pid}")
    return proc.pid

if __name__ == "__main__":
    print("=" * 60)
    print("EVLOS SAFETY - Backend Restart Script")
    print("=" * 60)

    killed_count = kill_all_backends()

    if killed_count > 0:
        print("\nWaiting 3 seconds before restart...")
        time.sleep(3)

    new_pid = start_backend()

    print("\n" + "=" * 60)
    print(f"Backend restarted successfully!")
    print(f"New backend PID: {new_pid}")
    print("=" * 60)

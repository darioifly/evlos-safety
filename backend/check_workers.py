import psutil

print("="*60)
print("All Python processes:")
print("="*60)

worker_count = 0

# List all python processes
for p in psutil.process_iter(['pid', 'name']):
    if p.info['name'] and 'python' in p.info['name'].lower():
        try:
            cmdline = ' '.join(p.cmdline())
            print(f"PID {p.pid}: {p.name()}")
            if 'video_worker' in cmdline:
                print(f"  ** VIDEO WORKER **")
                print(f"  CMD: {cmdline}")
                worker_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

print("\n" + "="*60)
print(f"Totale video_worker.py processi trovati: {worker_count}")
print("="*60)

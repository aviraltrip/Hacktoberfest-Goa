"""
DemoToSkill Full-Stack Orchestration Script
Launches all three services concurrently:
1. ScholarshipPortal Demo Application: http://localhost:8080/ (and ?v=2)
2. FastAPI Backend & SSE API:         http://localhost:8000/
3. Vite + React Frontend Console:     http://localhost:5173/

Press Ctrl+C to cleanly stop all processes.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent

def launch_all():
    print("=" * 70)
    print("  DemoToSkill: Starting Full-Stack Development Services")
    print("=" * 70)

    processes = []

    try:
        demo_dir = ROOT_DIR / "demo_app"
        print("[1/3] Starting Demo App on http://localhost:8080 ...")
        env_utf8 = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        p_demo = subprocess.Popen(
            [sys.executable, "-m", "http.server", "8080", "--directory", str(demo_dir)],
            cwd=str(ROOT_DIR),
            env=env_utf8
        )
        processes.append(("Demo App (8080)", p_demo))

        print("[2/3] Starting FastAPI Backend on http://localhost:8000 ...")
        backend_dir = ROOT_DIR / "backend"
        p_backend = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--loop", "asyncio"],
            cwd=str(backend_dir),
            env=env_utf8
        )
        processes.append(("FastAPI Backend (8000)", p_backend))

        print("[3/3] Starting Vite Frontend Console on http://localhost:5173 ...")
        frontend_dir = ROOT_DIR / "frontend"
        npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
        p_frontend = subprocess.Popen(
            [npm_cmd, "run", "dev"],
            cwd=str(frontend_dir)
        )
        processes.append(("Vite Frontend (5173)", p_frontend))

        print("\n" + "=" * 70)
        print("  ALL SERVICES RUNNING:")
        print("  - Frontend Console: http://localhost:5173/")
        print("  - Backend API:      http://localhost:8000/docs")
        print("  - Demo Target App:  http://localhost:8080/ (mutated: ?v=2)")
        print("=" * 70)
        print("Press Ctrl+C to terminate all services.\n")

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping all DemoToSkill services...")
    finally:
        for name, proc in processes:
            print(f"Terminating {name}...")
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                proc.kill()
        print("All services stopped.")

if __name__ == "__main__":
    launch_all()

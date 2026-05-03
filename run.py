#!/usr/bin/env python3
"""Set up and run the SERP Tracker backend and frontend for local development.

Usage:
    python run.py                 # set up (if needed) and run both servers
    python run.py --setup-only    # install deps and exit
    python run.py --no-setup      # skip install checks, just run
    python run.py --backend-only  # run only the FastAPI server
    python run.py --frontend-only # run only the Vite dev server
    python run.py --no-playwright # skip 'playwright install chromium'
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
VENV_DIR = ROOT / ".venv"
REQUIREMENTS = BACKEND_DIR / "requirements.txt"

IS_WINDOWS = platform.system() == "Windows"
VENV_BIN = VENV_DIR / ("Scripts" if IS_WINDOWS else "bin")
VENV_PY = VENV_BIN / ("python.exe" if IS_WINDOWS else "python")
VENV_PIP = VENV_BIN / ("pip.exe" if IS_WINDOWS else "pip")

# ANSI colors for prefixed log output.
RESET = "\033[0m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
RED = "\033[31m"


def info(msg: str) -> None:
    print(f"{GREEN}[run.py]{RESET} {msg}", flush=True)


def warn(msg: str) -> None:
    print(f"{YELLOW}[run.py]{RESET} {msg}", flush=True)


def fail(msg: str) -> None:
    print(f"{RED}[run.py]{RESET} {msg}", flush=True)


def require(cmd: str) -> str:
    path = shutil.which(cmd)
    if not path:
        fail(f"required command '{cmd}' not found on PATH")
        sys.exit(1)
    return path


def run(cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> None:
    info(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, env=env)
    if result.returncode != 0:
        fail(f"command failed with exit {result.returncode}: {' '.join(cmd)}")
        sys.exit(result.returncode)


def ensure_venv() -> None:
    if VENV_PY.exists():
        return
    info(f"creating virtualenv at {VENV_DIR}")
    run([sys.executable, "-m", "venv", str(VENV_DIR)])


def ensure_backend_deps(install_playwright: bool) -> None:
    ensure_venv()
    info("installing backend Python dependencies")
    run([str(VENV_PY), "-m", "pip", "install", "--upgrade", "pip"])
    run([str(VENV_PY), "-m", "pip", "install", "-r", str(REQUIREMENTS)])
    if install_playwright:
        info("installing playwright chromium browser (this can take a minute)")
        run([str(VENV_PY), "-m", "playwright", "install", "chromium"])


def ensure_frontend_deps() -> None:
    require("npm")
    node_modules = FRONTEND_DIR / "node_modules"
    if node_modules.exists():
        info("frontend node_modules already present, skipping npm install")
        return
    info("installing frontend npm dependencies")
    run(["npm", "install"], cwd=FRONTEND_DIR)


def ensure_env_file() -> None:
    env_path = ROOT / ".env"
    if env_path.exists():
        return
    warn(".env not found — creating an empty one (config defaults will apply)")
    env_path.write_text("# Add backend env overrides here. See backend/app/config.py\n")


def stream_output(proc: subprocess.Popen, prefix: str, color: str) -> None:
    assert proc.stdout is not None
    for raw in proc.stdout:
        line = raw.rstrip("\n")
        print(f"{color}[{prefix}]{RESET} {line}", flush=True)


def spawn(cmd: list[str], cwd: Path, prefix: str, color: str, env: dict | None = None) -> subprocess.Popen:
    info(f"starting {prefix}: {' '.join(cmd)}")
    popen_kwargs: dict = dict(
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        text=True,
    )
    if IS_WINDOWS:
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    else:
        popen_kwargs["start_new_session"] = True  # own process group, so we can kill the tree
    proc = subprocess.Popen(cmd, **popen_kwargs)
    threading.Thread(target=stream_output, args=(proc, prefix, color), daemon=True).start()
    return proc


def terminate(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        if IS_WINDOWS:
            proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
        else:
            os.killpg(proc.pid, signal.SIGINT)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        try:
            if IS_WINDOWS:
                proc.kill()
            else:
                os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def run_servers(backend: bool, frontend: bool, backend_port: int, frontend_port: int) -> int:
    procs: list[subprocess.Popen] = []

    if backend:
        backend_cmd = [
            str(VENV_PY), "-m", "uvicorn", "backend.app.main:app",
            "--reload", "--host", "127.0.0.1", "--port", str(backend_port),
        ]
        procs.append(spawn(backend_cmd, ROOT, "backend", CYAN))

    if frontend:
        # Give backend a head start so the first proxied request doesn't 502.
        if backend:
            time.sleep(1.5)
        frontend_env = os.environ.copy()
        # Vite respects --port on the CLI; pass it through so users can override.
        frontend_cmd = ["npm", "run", "dev", "--", "--port", str(frontend_port), "--strictPort"]
        procs.append(spawn(frontend_cmd, FRONTEND_DIR, "frontend", MAGENTA, env=frontend_env))

    if not procs:
        fail("nothing to run (both --backend-only and --frontend-only disabled?)")
        return 1

    info("press Ctrl+C to stop")

    def shutdown(*_: object) -> None:
        info("shutting down…")
        for p in procs:
            terminate(p)

    signal.signal(signal.SIGINT, lambda *_: shutdown())
    signal.signal(signal.SIGTERM, lambda *_: shutdown())

    exit_code = 0
    try:
        while procs:
            for p in list(procs):
                rc = p.poll()
                if rc is not None:
                    label = "backend" if (backend and p is procs[0]) else "frontend"
                    if rc != 0:
                        fail(f"{label} exited with code {rc}, stopping the other process")
                        exit_code = rc
                        for other in procs:
                            if other is not p:
                                terminate(other)
                        return exit_code
                    procs.remove(p)
            time.sleep(0.3)
    except KeyboardInterrupt:
        shutdown()
    finally:
        for p in procs:
            terminate(p)
    return exit_code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Set up and run SERP Tracker (backend + frontend).")
    parser.add_argument("--setup-only", action="store_true", help="install dependencies and exit")
    parser.add_argument("--no-setup", action="store_true", help="skip dependency installation")
    parser.add_argument("--no-playwright", action="store_true", help="skip 'playwright install chromium'")
    parser.add_argument("--backend-only", action="store_true", help="run only the backend")
    parser.add_argument("--frontend-only", action="store_true", help="run only the frontend")
    parser.add_argument("--backend-port", type=int, default=1234, help="uvicorn port (default: 1234, matches vite proxy)")
    parser.add_argument("--frontend-port", type=int, default=5173, help="vite port (default: 5173)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.backend_only and args.frontend_only:
        fail("--backend-only and --frontend-only are mutually exclusive")
        return 2

    run_backend = not args.frontend_only
    run_frontend = not args.backend_only

    ensure_env_file()

    if not args.no_setup:
        if run_backend:
            ensure_backend_deps(install_playwright=not args.no_playwright)
        if run_frontend:
            ensure_frontend_deps()

    if args.setup_only:
        info("setup complete")
        return 0

    return run_servers(
        backend=run_backend,
        frontend=run_frontend,
        backend_port=args.backend_port,
        frontend_port=args.frontend_port,
    )


if __name__ == "__main__":
    sys.exit(main())

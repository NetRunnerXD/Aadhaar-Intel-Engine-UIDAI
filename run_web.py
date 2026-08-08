#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Aadhaar Intel Engine — professional web UI launcher.

Builds the React frontend (Node/npm) and serves the FastAPI API + SPA.

Usage:
    python run_web.py
    python run_web.py --port 8787
    python run_web.py --skip-build   # use existing web/frontend/dist
    python run_web.py --dev-api      # API only (pair with npm run dev)

Streamlit app is unchanged: streamlit run app.py
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "web" / "frontend"
DIST = FRONTEND / "dist"
DEFAULT_PORT = 8787


def _which(cmd: str) -> str | None:
    return shutil.which(cmd)


def ensure_python_deps():
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError:
        print("Installing FastAPI + uvicorn…")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "fastapi", "uvicorn[standard]", "pydantic"],
            cwd=str(ROOT),
        )


def ensure_frontend_build(skip_build: bool, force: bool) -> None:
    if skip_build and DIST.exists():
        print(f"Using existing build: {DIST}")
        return

    npm = _which("npm")
    node = _which("node")
    if not npm or not node:
        if DIST.exists():
            print("Node/npm not found — using existing frontend dist.")
            return
        print(
            "ERROR: Node.js and npm are required to build the React UI.\n"
            "Install from https://nodejs.org/ then re-run: python run_web.py"
        )
        sys.exit(1)

    print(f"Node: {subprocess.check_output([node, '-v'], text=True).strip()}")
    print(f"npm:  {subprocess.check_output([npm, '-v'], text=True).strip()}")

    if force or not (FRONTEND / "node_modules").exists():
        print("npm install…")
        subprocess.check_call([npm, "install"], cwd=str(FRONTEND))

    print("Building React frontend…")
    subprocess.check_call([npm, "run", "build"], cwd=str(FRONTEND))

    if not DIST.exists():
        print("ERROR: frontend build did not produce dist/")
        sys.exit(1)
    print(f"Build OK -> {DIST}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Launch Aadhaar Intel professional web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--skip-build", action="store_true", help="Skip npm build")
    parser.add_argument("--force-install", action="store_true", help="Force npm install")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--dev-api", action="store_true", help="API only (no static requirement)")
    args = parser.parse_args(argv)

    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    ensure_python_deps()
    if not args.dev_api:
        ensure_frontend_build(skip_build=args.skip_build, force=args.force_install)

    import uvicorn

    url = f"http://{args.host}:{args.port}"
    print("=" * 60)
    print("  Aadhaar Intel Engine — Professional Web UI")
    print(f"  Open: {url}")
    print("  Streamlit (unchanged): streamlit run app.py")
    print("=" * 60)

    if not args.no_browser and not args.dev_api:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    uvicorn.run(
        "web.api.main:app",
        host=args.host,
        port=args.port,
        reload=False,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

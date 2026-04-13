"""
passenger_wsgi.py — Phusion Passenger entry-point for Hostinger Python hosting.

Hostinger hPanel → Websites → Python App:
  - Python version : 3.10+ (recommended 3.11)
  - Application root: <this directory>
  - Application URL : /  (or a sub-path)
  - Application startup file: passenger_wsgi.py
  - Application Entry point : application

After creating the app in hPanel:
  1. SSH in and run:  source ~/virtualenv/<domain>/3.x/bin/activate
  2. pip install -r requirements.txt
  3. cp .env.example .env  → edit .env with your provider keys
  4. Restart the app in hPanel
"""

import sys
import os

# ── Make sure the project root is on sys.path ─────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# ── Load .env (provider keys, Flask config, etc.) ─────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_HERE, ".env"))
except ImportError:
    pass  # python-dotenv not yet installed; env vars must be set in hPanel

# ── Create WSGI application ────────────────────────────────────────────────
from app import create_app  # noqa: E402

application = create_app()

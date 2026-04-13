"""
wsgi.py — Gunicorn entry-point for Docker / production.
Usage: gunicorn -b 0.0.0.0:5000 wsgi:app
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app

app = create_app()

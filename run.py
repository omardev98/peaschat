"""
run.py - LocalChat server entry-point
======================================
Port resolution order (highest priority first):
  1. CLI argument       --port 8000
  2. Environment var    PORT=8000
  3. .env               FLASK_PORT=8000
  4. Default            7860

Usage:
  python run.py                       # port 7860
  python run.py --port 8000           # custom port
  python run.py --port 8080 --debug
  python run.py --production          # waitress WSGI (Windows-safe)
  PORT=9000 python run.py
"""

import argparse
import os
import socket
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _parse_args():
    p = argparse.ArgumentParser(
        description="LocalChat - Offline AI Document Assistant",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--host",       "-H", default=None, help="Bind host")
    p.add_argument("--port",       "-p", type=int, default=None, help="Bind port")
    p.add_argument("--debug",            action="store_true", help="Flask debug mode")
    p.add_argument("--no-reload",        action="store_true", help="Disable auto-reloader")
    p.add_argument("--production",       action="store_true", help="Use waitress")
    return p.parse_args()


def _port_free(host, port):
    h = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex((h, port)) != 0


def _banner(host, port, debug, server):
    bar = "=" * 58
    print(f"\n  {bar}")
    print(f"  LocalChat -- 100% Offline AI Document Assistant")
    print(f"  {bar}")
    print(f"  UI      :  http://127.0.0.1:{port}")
    print(f"  API     :  http://127.0.0.1:{port}/api")
    print(f"  Health  :  http://127.0.0.1:{port}/api/health")
    print(f"  Ollama  :  http://127.0.0.1:{port}/api/ollama-status")
    print(f"  {bar}")
    print(f"  Server  :  {server}")
    print(f"  Debug   :  {'ON' if debug else 'OFF'}")
    print(f"  Network :  http://{host}:{port}")
    print(f"  {bar}")
    print(f"\n  Prerequisites:")
    print(f"    ollama serve")
    print(f"    ollama pull llama3")
    print(f"    ollama pull nomic-embed-text")
    print(f"  {bar}\n")


def main():
    args = _parse_args()

    from config import FLASK_HOST, FLASK_PORT, FLASK_DEBUG

    host  = args.host  or os.environ.get("HOST",  FLASK_HOST)
    port  = args.port  or int(os.environ.get("PORT", FLASK_PORT))
    debug = args.debug or FLASK_DEBUG

    if not _port_free(host, port):
        print(f"\n  [ERROR] Port {port} is already in use.")
        print(f"          Try: python run.py --port 8000\n")
        sys.exit(1)

    try:
        from app import create_app
        app = create_app()
    except Exception as exc:
        print(f"\n  [FATAL] Failed to start: {exc}\n")
        sys.exit(1)

    on_windows   = sys.platform == "win32"
    use_reloader = debug and not args.no_reload and not on_windows
    server_name  = "waitress (production)" if args.production else "Werkzeug (development)"

    _banner(host, port, debug, server_name)

    if args.production:
        try:
            from waitress import serve
            print(f"  Serving with waitress on {host}:{port} ...\n")
            serve(app, host=host, port=port, threads=4)
        except ImportError:
            print("  [ERROR] pip install waitress\n")
            sys.exit(1)
    else:
        app.run(host=host, port=port, debug=debug,
                use_reloader=use_reloader, threaded=True)


if __name__ == "__main__":
    main()

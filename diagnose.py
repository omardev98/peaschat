"""
diagnose.py - Pre-flight checks for LocalChat
==============================================
Run BEFORE starting the server.
  python diagnose.py
  python diagnose.py --port 8000
"""

import argparse
import importlib
import os
import socket
import sys

def ok(m):   print(f"  [OK]   {m}")
def fail(m): print(f"  [FAIL] {m}")
def warn(m): print(f"  [WARN] {m}")
def info(m): print(f"  [INFO] {m}")
def head(m): print(f"\n{m}")

PASS = FAIL_COUNT = 0

def check(label, fn):
    global PASS, FAIL_COUNT
    try:
        r = fn()
        if r is False:
            fail(label); FAIL_COUNT += 1
        else:
            ok(label + (f"  ->  {r}" if isinstance(r, str) else ""))
            PASS += 1
    except Exception as e:
        fail(f"{label}  ->  {e}"); FAIL_COUNT += 1


def chk_python():
    v = sys.version_info
    if v < (3, 10): raise RuntimeError(f"Need Python 3.10+, got {v.major}.{v.minor}")
    return f"{v.major}.{v.minor}.{v.micro}"

def chk_import(mod, attr=None):
    def _():
        m = importlib.import_module(mod)
        if attr: getattr(m, attr)
        return getattr(m, "__version__", "ok")
    return _

def chk_dir(path):
    def _():
        if not os.path.isdir(path): raise RuntimeError(f"Missing: {path}")
        return path
    return _

def chk_file(path):
    def _():
        if not os.path.isfile(path): raise RuntimeError(f"Missing: {path}")
        return path
    return _

def chk_port(host, port):
    def _():
        h = "127.0.0.1" if host in ("0.0.0.0", "::") else host
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            if s.connect_ex((h, port)) == 0:
                raise RuntimeError(f"Port {port} in use -- try --port 8000")
        return f"{host}:{port} is free"
    return _

def chk_tesseract(cmd):
    def _():
        import subprocess
        r = subprocess.run([cmd, "--version"], capture_output=True, timeout=5)
        if r.returncode != 0: raise RuntimeError(f"Tesseract not working at {cmd}")
        ver = r.stdout.decode(errors="replace").split("\n")[0] or \
              r.stderr.decode(errors="replace").split("\n")[0]
        return ver.strip()
    return _

def chk_ollama(base_url):
    def _():
        import requests
        r = requests.get(f"{base_url}/api/tags", timeout=5)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        return f"running -- {len(models)} model(s) available"
    return _

def chk_ollama_model(base_url, model_name):
    def _():
        import requests
        r = requests.get(f"{base_url}/api/tags", timeout=5)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        found = any(m == model_name or m.startswith(model_name+":") for m in models)
        if not found:
            raise RuntimeError(f"Not pulled. Run: ollama pull {model_name}")
        return model_name
    return _

def chk_flask_app():
    from app import create_app
    app = create_app()
    rules = [r.rule for r in app.url_map.iter_rules()]
    req = ["/", "/api/health", "/api/upload", "/api/ask", "/api/documents", "/api/ollama-status"]
    missing = [r for r in req if r not in rules]
    if missing: raise RuntimeError(f"Missing routes: {missing}")
    return f"{len(rules)} routes"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=None)
    args = p.parse_args()

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    root = os.path.dirname(os.path.abspath(__file__))
    if root not in sys.path:
        sys.path.insert(0, root)

    from config import FLASK_HOST, FLASK_PORT, OLLAMA_BASE_URL, OLLAMA_LLM_MODEL, \
                       OLLAMA_EMBED_MODEL, TESSERACT_CMD

    port = args.port or FLASK_PORT

    head("1 / 6  Runtime")
    check("Python >= 3.10", chk_python)

    head("2 / 6  Python packages")
    for mod, attr in [
        ("flask",                    "Flask"),
        ("flask_cors",               "CORS"),
        ("dotenv",                   "load_dotenv"),
        ("pdfplumber",               None),
        ("PIL",                      "Image"),
        ("pytesseract",              None),
        ("langchain_text_splitters", "RecursiveCharacterTextSplitter"),
        ("langchain_community",      None),
        ("faiss",                    None),
        ("requests",                 None),
        ("numpy",                    None),
    ]:
        check(f"import {mod}", chk_import(mod, attr))

    for mod in ("waitress",):
        try:
            importlib.import_module(mod)
            ok(f"import {mod}  (production server available)")
        except ImportError:
            warn(f"{mod} not installed (pip install {mod})")

    head("3 / 6  Project files")
    check("templates/index.html", chk_file(os.path.join(root,"templates","index.html")))
    check("static/style.css",     chk_file(os.path.join(root,"static","style.css")))
    check("static/app.js",        chk_file(os.path.join(root,"static","app.js")))
    check("uploads/",             chk_dir(os.path.join(root,"uploads")))
    check("data/",                chk_dir(os.path.join(root,"data")))
    if os.path.isfile(os.path.join(root,".env")):
        ok(".env found")
    else:
        warn(".env missing -- copy .env.example -> .env")

    head("4 / 6  System tools")
    check(f"Tesseract OCR  ({TESSERACT_CMD})", chk_tesseract(TESSERACT_CMD))

    head("5 / 6  Ollama")
    info(f"Base URL      = {OLLAMA_BASE_URL}")
    info(f"LLM model     = {OLLAMA_LLM_MODEL}")
    info(f"Embed model   = {OLLAMA_EMBED_MODEL}")
    check("Ollama server running",                    chk_ollama(OLLAMA_BASE_URL))
    check(f"LLM   model pulled  ({OLLAMA_LLM_MODEL})",   chk_ollama_model(OLLAMA_BASE_URL, OLLAMA_LLM_MODEL))
    check(f"Embed model pulled  ({OLLAMA_EMBED_MODEL})",  chk_ollama_model(OLLAMA_BASE_URL, OLLAMA_EMBED_MODEL))

    head("6 / 6  Flask application")
    check("create_app() succeeds", chk_flask_app)
    check(f"Port {port} available", chk_port(FLASK_HOST, port))

    total = PASS + FAIL_COUNT
    bar   = "=" * 52
    print(f"\n  {bar}")
    if FAIL_COUNT == 0:
        print(f"  All {total} checks passed. Ready!")
        print(f"\n  Run:  python run.py --port {port}")
    else:
        print(f"  {FAIL_COUNT} / {total} checks FAILED. Fix above then retry.")
    print(f"  {bar}\n")
    sys.exit(0 if FAIL_COUNT == 0 else 1)


if __name__ == "__main__":
    main()

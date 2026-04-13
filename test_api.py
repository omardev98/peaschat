"""
test_api.py - End-to-end test for LocalChat API
================================================
Usage:
  python test_api.py                          # auto-creates sample PDF
  python test_api.py --pdf path/to/file.pdf
  python test_api.py --image path/to/img.png
  python test_api.py --base http://localhost:8000

Requires Ollama to be running with llama3 + nomic-embed-text pulled.
"""

import argparse
import json
import os
import sys
import tempfile
import time

import requests

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:7860/api")
TIMEOUT  = 180   # seconds (local LLM can be slow)


def ok(m):   print(f"  [PASS] {m}")
def fail(m): print(f"  [FAIL] {m}")
def head(m): print(f"\n=== {m} ===")


def make_sample_pdf(path):
    """Build a minimal valid PDF with known test content."""
    content_lines = [
        "Company: Acme Technologies",
        "CEO: Robert Chen, appointed in 2019",
        "Founded: San Francisco, 2010",
        "Revenue FY2024: 12.8 million USD",
        "Employees: 340 globally",
        "Products:",
        "  QuantumDB - database platform - 399 USD per month",
        "  CloudSync  - file sync service  - 79 USD per month",
        "Mission: Reliable software for everyone.",
    ]

    ops_lines = ["BT", "/F1 11 Tf", "50 750 Td", "14 TL"]
    for line in content_lines:
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        ops_lines.append(f"({safe}) Tj T*")
    ops_lines.append("ET")
    stream = "\n".join(ops_lines).encode("latin-1", errors="replace")

    o = {
        1: b"<</Type /Catalog /Pages 2 0 R>>",
        2: b"<</Type /Pages /Kids [3 0 R] /Count 1>>",
        3: (b"<</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]"
            b" /Contents 4 0 R /Resources <</Font <</F1 5 0 R>>>>>>"),
        4: b"<</Length " + str(len(stream)).encode() + b">>\nstream\n" + stream + b"\nendstream",
        5: b"<</Type /Font /Subtype /Type1 /BaseFont /Helvetica>>",
    }

    body  = b"%PDF-1.4\n"
    xrefs = {}
    for i in range(1, 6):
        xrefs[i] = len(body)
        body += str(i).encode() + b" 0 obj\n" + o[i] + b"\nendobj\n"

    xp  = len(body)
    xt  = b"xref\n0 6\n0000000000 65535 f \n"
    for i in range(1, 6):
        xt += str(xrefs[i]).zfill(10).encode() + b" 00000 n \n"
    body += xt + b"trailer\n<</Size 6 /Root 1 0 R>>\nstartxref\n" + str(xp).encode() + b"\n%%EOF"

    with open(path, "wb") as f:
        f.write(body)
    print(f"  [INFO] Created sample PDF ({len(body)} bytes): {path}")


# ── Tests ──────────────────────────────────────────────────────

PASSED = FAILED = 0

def run(label, fn, *a, **kw):
    global PASSED, FAILED
    try:
        r = fn(*a, **kw)
        PASSED += 1
        return r
    except AssertionError as e:
        fail(f"{label}: {e}"); FAILED += 1
    except requests.exceptions.ConnectionError:
        fail(f"{label}: Cannot connect to API. Is the server running?"); FAILED += 1
    return None


def test_health():
    head("Health check")
    r = requests.get(f"{BASE_URL}/health", timeout=5)
    print(f"  HTTP {r.status_code}  {r.json()}")
    assert r.status_code == 200
    ok("health")


def test_ollama_status():
    head("Ollama status")
    r = requests.get(f"{BASE_URL}/ollama-status", timeout=10)
    data = r.json()
    print(f"  HTTP {r.status_code}")
    print(f"  ollama_running : {data.get('ollama_running')}")
    print(f"  llm_model      : {data.get('llm_model')} ({data.get('llm_model_name')})")
    print(f"  embed_model    : {data.get('embed_model')} ({data.get('embed_model_name')})")
    if data.get("errors"):
        for e in data["errors"]:
            print(f"  [WARN] {e}")
    if r.status_code != 200:
        print("  [WARN] Ollama not ready -- /api/ask will fail")
    ok("ollama-status endpoint responded")


def test_upload(path, expected_type):
    head(f"Upload ({expected_type}): {os.path.basename(path)}")
    t0 = time.time()
    with open(path, "rb") as f:
        r = requests.post(
            f"{BASE_URL}/upload",
            files={"file": (os.path.basename(path), f)},
            timeout=TIMEOUT,
        )
    elapsed = time.time() - t0
    data = r.json()
    print(f"  HTTP {r.status_code}  ({elapsed:.1f}s)")
    print(f"  {json.dumps(data, indent=2)}")
    assert r.status_code == 201, f"Upload failed: {data.get('error')}"
    assert data.get("document_id"), "No document_id returned"
    ok(f"upload -> {data['document_id'][:16]}...")
    return data["document_id"]


def test_documents(doc_id):
    head("Document list")
    r = requests.get(f"{BASE_URL}/documents", timeout=5)
    data = r.json()
    print(f"  HTTP {r.status_code}  count={data.get('count')}")
    assert r.status_code == 200
    assert doc_id in data.get("documents", []), "doc_id missing from list"
    ok("document_id in /api/documents")


def test_ask(doc_id, question):
    head(f"Ask: {question!r}")
    t0  = time.time()
    r   = requests.post(
        f"{BASE_URL}/ask",
        json={"document_id": doc_id, "question": question},
        stream=True,
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, f"HTTP {r.status_code}"

    answer  = []
    decoder = __import__("codecs").getincrementaldecoder("utf-8")("replace")
    buf     = ""

    for chunk in r.iter_content(chunk_size=64):
        buf += decoder.decode(chunk)
        parts = buf.split("\n\n")
        buf   = parts.pop()
        for part in parts:
            for line in part.split("\n"):
                if not line.startswith("data: "): continue
                try: payload = json.loads(line[6:])
                except: continue
                if payload.get("error"):
                    print(f"\n  [ERROR] {payload['error']}")
                    assert False, payload["error"]
                if payload.get("token"):
                    answer.append(payload["token"])
                    print(payload["token"], end="", flush=True)

    print()
    full = "".join(answer)
    elapsed = time.time() - t0
    print(f"  Answer ({elapsed:.1f}s): {full[:200]}{'...' if len(full)>200 else ''}")
    assert full.strip(), "Empty answer received"
    ok(f"streaming answer received ({len(full)} chars)")
    return full


def test_errors(doc_id):
    head("Error handling")

    # Bad doc_id
    r = requests.post(f"{BASE_URL}/ask",
                      json={"document_id":"bad-id","question":"test"}, timeout=5)
    # Error comes as SSE for streaming endpoint
    # It might be 400 JSON for validation errors or 200 SSE with error token
    assert r.status_code in (400, 200), f"Unexpected status {r.status_code}"
    ok(f"bad document_id -> {r.status_code}")

    # Empty question
    r = requests.post(f"{BASE_URL}/ask",
                      json={"document_id":doc_id,"question":""}, timeout=5)
    assert r.status_code == 400
    ok(f"empty question -> {r.status_code}")

    # No file
    r = requests.post(f"{BASE_URL}/upload", timeout=5)
    assert r.status_code == 400
    ok(f"no file -> {r.status_code}")


# ── Main ───────────────────────────────────────────────────────

def main():
    global BASE_URL
    p = argparse.ArgumentParser()
    p.add_argument("--pdf",   default=None)
    p.add_argument("--image", default=None)
    p.add_argument("--base",  default=BASE_URL)
    args = p.parse_args()
    BASE_URL = args.base.rstrip("/")

    print(f"\nLocalChat API Test")
    print(f"API: {BASE_URL}\n")

    run("health",  test_health)
    run("ollama",  test_ollama_status)

    # Choose upload target
    cleanup = False
    if args.pdf:
        pdf_path = args.pdf
    elif args.image:
        pdf_path = None
        img_path = args.image
    else:
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.close()
        pdf_path = tmp.name
        make_sample_pdf(pdf_path)
        cleanup = True

    try:
        if args.image:
            doc_id = run("upload_image", test_upload, img_path, "image")
        else:
            doc_id = run("upload_pdf",   test_upload, pdf_path,  "pdf")

        if doc_id:
            run("documents", test_documents, doc_id)
            run("ask_1", test_ask, doc_id, "Who is the CEO?")
            run("ask_2", test_ask, doc_id, "When was the company founded?")
            run("ask_off", test_ask, doc_id,
                "What is the capital of the moon?")
            run("errors", test_errors, doc_id)
    finally:
        if cleanup and pdf_path and os.path.exists(pdf_path):
            os.remove(pdf_path)

    print(f"\n{'='*46}")
    print(f"  Results: {PASSED} passed, {FAILED} failed")
    print(f"{'='*46}\n")
    sys.exit(0 if FAILED == 0 else 1)


if __name__ == "__main__":
    main()

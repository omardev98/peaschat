"""
run_tests.py — LocalChat v1 API Test Suite
Real HTTP requests only. No mocking.
"""
import requests, httpx, json, io, os, sys, time, base64

BASE    = "http://localhost:7860"
API_KEY = "lc_qBLt7is28344WmQ1C38sCcGxwC0I5GKJfKouF2PrCB5d0RkQ"
CHAT    = f"{BASE}/v1/chat"
HEALTH  = f"{BASE}/v1/health"
AUTH    = {"Authorization": f"Bearer {API_KEY}"}

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
INFO = "\033[94m●\033[0m"
BOLD = "\033[1m"
END  = "\033[0m"

results = []

def ok(label, detail=""):
    results.append(True)
    print(f"  {PASS} {label}")
    if detail: print(f"      {detail}")

def fail(label, detail=""):
    results.append(False)
    print(f"  {FAIL} {label}")
    if detail: print(f"      {detail}")

def check(cond, label, detail=""):
    ok(label, detail) if cond else fail(label, detail)

def section(title):
    print(f"\n{BOLD}{'─'*55}{END}")
    print(f"{BOLD}  {title}{END}")
    print(f"{BOLD}{'─'*55}{END}")


# ══════════��═══════════════════════════════════════════════
# TEST 1 — Health Check
# ════════════════════════════════════════════���═════════════
section("TEST 1 — Health check  GET /v1/health")

try:
    r = requests.get(HEALTH, timeout=5)
    check(r.status_code == 200,
          "Returns 200 OK",
          f"Status: {r.status_code}")
    check("status" in r.json() or len(r.text) > 0,
          "Response body is not empty",
          r.text[:120])
except requests.exceptions.ConnectionError:
    fail("Server is not reachable at " + BASE)
    print(f"  {INFO} Make sure Flask is running: python run.py")
    sys.exit(1)


# ═══════════════════���══════════════════════════════════════
# TEST 2 — Text-only (JSON body)
# ══════════════════════════════════════════════════════════
section("TEST 2 — Text-only  POST /v1/chat  (JSON body)")

payload = {"message": "What is the capital of France?"}
r = requests.post(CHAT,
    headers={**AUTH, "Content-Type": "application/json"},
    json=payload,
    timeout=60
)

check(r.status_code == 200,
      "Returns 200",
      f"Status: {r.status_code}")

if r.status_code == 200:
    body = r.json()
    check("answer" in body or "message" in body or "content" in body,
          "Response contains answer field",
          str(body)[:200])

    answer_text = (body.get("answer") or
                   (body.get("message") or {}).get("content", "") if isinstance(body.get("message"), dict) else body.get("message", "") or
                   body.get("content") or "")
    check("paris" in answer_text.lower() or "france" in answer_text.lower(),
          "Answer mentions Paris / France",
          f"Answer: {answer_text[:150]}")

    if "provider" in body:
        print(f"  {INFO} Provider: {body['provider']}  Model: {body.get('model','?')}")
else:
    fail("Unexpected response", r.text[:200])


# ═══════════════════════════════════��══════════════════════
# TEST 3 — File upload (multipart/form-data)
# ═══════════════════════��══════════════════════════════════
section("TEST 3 — File upload  POST /v1/chat  (form-data)")

# 3a: .txt file
txt_bytes = b"""LocalChat Sales Report - Q1 2025
Total revenue : 850,000 MAD
Net profit    : 210,000 MAD
Top product   : Document Assistant Pro
Clients served: 142"""

print(f"  {INFO} Sub-test 3a: text file upload")
r = requests.post(CHAT,
    headers=AUTH,
    data={"message": "Summarize this document in 2 sentences."},
    files={"file": ("report.txt", io.BytesIO(txt_bytes), "text/plain")},
    timeout=60
)
check(r.status_code == 200, "3a: Returns 200 with txt file", f"Status: {r.status_code}")
if r.status_code == 200:
    body = r.json()
    file_flag = body.get("file_included", body.get("has_file", None))
    check(file_flag == True or file_flag is None,
          "3a: file_included flag is True (or field not present)",
          str(body)[:200])
    answer = (body.get("answer") or
              (body.get("message") or {}).get("content", "") if isinstance(body.get("message"), dict) else body.get("message", "") or
              body.get("content") or "")
    print(f"      Answer: {answer[:150]}")

# 3b: minimal PNG (1x1 white pixel)
print(f"  {INFO} Sub-test 3b: PNG image upload (OCR)")
minimal_png = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "YGBgAAAABAABJjAHggAAAABJRU5ErkJggg=="
)
r = requests.post(CHAT,
    headers=AUTH,
    data={"message": "Describe what you see in this image."},
    files={"file": ("photo.png", io.BytesIO(minimal_png), "image/png")},
    timeout=60
)
check(r.status_code in (200, 422), "3b: Returns 200 or 422 (blank image may have no OCR text)", f"Status: {r.status_code}")
if r.status_code == 200:
    body = r.json()
    answer = (body.get("answer") or
              (body.get("message") or {}).get("content", "") if isinstance(body.get("message"), dict) else body.get("message", "") or
              body.get("content") or "")
    print(f"      OCR answer: {answer[:150]}")

# 3c: minimal valid PDF
print(f"  {INFO} Sub-test 3c: PDF upload")
minimal_pdf = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Contents 4 0 R
/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 56>>
stream
BT /F1 12 Tf 72 720 Td (LocalChat PDF test page - hello world) Tj ET
endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000274 00000 n
0000000382 00000 n
trailer<</Size 6/Root 1 0 R>>
startxref
463
%%EOF"""

r = requests.post(CHAT,
    headers=AUTH,
    data={"message": "What does this PDF say?"},
    files={"file": ("sample.pdf", io.BytesIO(minimal_pdf), "application/pdf")},
    timeout=60
)
check(r.status_code in (200, 503),
      "3c: Endpoint reached with PDF (200 or 503 if provider busy)",
      f"Status: {r.status_code}")
if r.status_code == 200:
    body = r.json()
    answer = (body.get("answer") or
              (body.get("message") or {}).get("content", "") if isinstance(body.get("message"), dict) else body.get("message", "") or
              body.get("content") or "")
    print(f"      PDF answer: {answer[:150]}")


# ══════════════════════════════════════════════════════════
# TEST 4 — Streaming (SSE)
# ═════════════════════════════════════════════════════��════
section("TEST 4 — Streaming  POST /v1/chat  stream=true")

chunks_received = []
full_text       = ""

try:
    with httpx.stream(
        "POST", CHAT,
        headers=AUTH,
        data={"message": "Tell me a very short story in 3 sentences.", "stream": "true"},
        timeout=60
    ) as response:
        check(response.status_code == 200,
              "Streaming: Returns 200",
              f"Status: {response.status_code}")

        for line in response.iter_lines():
            if not line:
                continue
            if line.startswith("data:"):
                raw = line[5:].strip()
                if raw == "[DONE]":
                    break
                try:
                    chunk = json.loads(raw)
                    if chunk.get("done"):
                        break
                    # delta may be a plain string token OR an OpenAI-style dict
                    delta = chunk.get("delta", "")
                    if isinstance(delta, dict):
                        token = delta.get("content", "")
                    elif isinstance(delta, str) and delta:
                        token = delta
                    else:
                        token = (
                            chunk.get("token") or
                            chunk.get("content") or
                            chunk.get("text") or
                            (chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                             if chunk.get("choices") else "") or ""
                        )
                    full_text += token
                    chunks_received.append(token)
                except json.JSONDecodeError:
                    full_text += raw
                    chunks_received.append(raw)
            else:
                full_text += line
                chunks_received.append(line)

        check(len(chunks_received) > 0,
              "Streaming: received at least 1 chunk",
              f"Chunks received: {len(chunks_received)}")
        check(len(full_text) > 10,
              "Streaming: assembled text is not empty",
              f"Full text: {full_text[:150]}")

except httpx.ConnectError:
    fail("Streaming: cannot connect to server")
except Exception as e:
    fail("Streaming: unexpected error", str(e))


# ═══════════════════════════════════════���══════════════════
# TEST 5 — Auth failure cases
# ═════════════════════════════════════���════════════════════
section("TEST 5 — Auth failures")

# No header
r = requests.post(CHAT, json={"message": "hello"}, timeout=10)
check(r.status_code == 401, "No auth header → 401", f"Status: {r.status_code}")

# Wrong key
r = requests.post(CHAT,
    headers={"Authorization": "Bearer lc_thisisafakekeyxxxxxxxxxxxxxxxx"},
    json={"message": "hello"},
    timeout=10
)
check(r.status_code == 401, "Wrong key → 401", f"Status: {r.status_code}")

# Malformed header (no Bearer prefix)
r = requests.post(CHAT,
    headers={"Authorization": API_KEY},
    json={"message": "hello"},
    timeout=10
)
check(r.status_code == 401, "Missing 'Bearer' prefix → 401", f"Status: {r.status_code}")


# ═════════════════════════════════════════════��════════════
# TEST 6 — Edge cases
# ══════════════════════════════════════════════════════════
section("TEST 6 — Edge cases")

# Missing message field
r = requests.post(CHAT,
    headers={**AUTH, "Content-Type": "application/json"},
    json={},
    timeout=10
)
check(r.status_code == 422, "Empty body → 422", f"Status: {r.status_code}")

# Unsupported file type
r = requests.post(CHAT,
    headers=AUTH,
    data={"message": "What is this?"},
    files={"file": ("virus.exe", io.BytesIO(b"MZ fake"), "application/octet-stream")},
    timeout=10
)
check(r.status_code in (415, 422, 400),
      "Unsupported file type → 415/422/400",
      f"Status: {r.status_code}")

# Very long message
long_msg = "Repeat the word hello " * 200
r = requests.post(CHAT,
    headers={**AUTH, "Content-Type": "application/json"},
    json={"message": long_msg},
    timeout=60
)
check(r.status_code in (200, 422, 413),
      "Long message handled gracefully",
      f"Status: {r.status_code}")


# ═════════════════════��════════════════════════���═══════════
# RESULTS SUMMARY
# ══════════════════════════════════════════════════════════
section("RESULTS SUMMARY")
passed = sum(results)
total  = len(results)
pct    = int(passed / total * 100) if total else 0
bar    = ("█" * (passed * 20 // total)) + ("░" * (20 - passed * 20 // total)) if total else ""
print(f"  {bar}  {passed}/{total}  ({pct}%)")
if passed == total:
    print(f"\n  {PASS} {BOLD}All tests passed!{END}")
else:
    failed = total - passed
    print(f"\n  {FAIL} {BOLD}{failed} test(s) failed — review output above.{END}")

# LocalChat API — Complete Documentation

> Call your local AI from **any app, script, or tool** using a simple REST API.  
> Supports text chat, PDF analysis, image OCR, and streaming responses.

---

## Table of Contents

1. [Base URL & Requirements](#1-base-url--requirements)
2. [Authentication](#2-authentication)
3. [Endpoints](#3-endpoints)
   - [Health Check](#31-get-v1health)
   - [Active Provider](#32-get-v1providersactive)
   - [Chat](#33-post-v1chat)
   - [Chat with File](#34-post-v1chat-with-file)
   - [Streaming](#35-streaming-response)
4. [Response Format](#4-response-format)
5. [Error Codes](#5-error-codes)
6. [Code Examples](#6-code-examples)
   - [Python](#python)
   - [JavaScript / Node.js](#javascript--nodejs)
   - [PHP](#php)
   - [C#](#c)
   - [curl](#curl)
7. [Postman Setup](#7-postman-setup)
8. [Supported File Types](#8-supported-file-types)
9. [FAQ](#9-faq)

---

## 1. Base URL & Requirements

```
Base URL:  http://YOUR_SERVER_IP:7860
```

- LocalChat must be **running** on the host machine (`python run.py`)
- At least one **AI provider must be active** in Settings (`/settings`)
- You need a valid **API key** (create one at `/api-keys`)

> If calling from another machine on the same network, replace `localhost` with
> the host machine's local IP address (e.g. `192.168.1.50`).  
> To expose publicly, put it behind a reverse proxy (Nginx, Caddy).

---

## 2. Authentication

Every protected endpoint requires an API key. Send it in **one** of these ways:

### Option A — Authorization header (recommended)
```
Authorization: Bearer lc_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### Option B — X-API-Key header
```
X-API-Key: lc_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### How to get an API key
1. Open `http://localhost:7860/api-keys` in your browser
2. Enter a name → click **Create Key**
3. Copy the key — it is shown **only once**

API key format: `lc_` followed by 48 characters (e.g. `lc_A1b2C3d4...`)

---

## 3. Endpoints

### 3.1 GET /v1/health

Public health check. No authentication required.

**Request**
```
GET http://localhost:7860/v1/health
```

**Response 200**
```json
{
  "status": "ok",
  "version": "1.0"
}
```

---

### 3.2 GET /v1/providers/active

Returns the currently active AI provider.  
**Authentication required.**

**Request**
```
GET http://localhost:7860/v1/providers/active
Authorization: Bearer lc_your_key
```

**Response 200**
```json
{
  "provider": "gemini",
  "name": "Google Gemini",
  "model": "gemini-2.0-flash"
}
```

---

### 3.3 POST /v1/chat

Send a text message and receive an AI response.  
**Authentication required.**

**Request**
```
POST http://localhost:7860/v1/chat
Authorization: Bearer lc_your_key
Content-Type: application/json
```

**Body**
```json
{
  "message": "What is the capital of France?",
  "stream": false
}
```

| Field     | Type    | Required | Default | Description                        |
|-----------|---------|----------|---------|------------------------------------|
| `message` | string  | YES      | —       | Your question or prompt            |
| `stream`  | boolean | no       | false   | Set to true to stream the response |

**Response 200**
```json
{
  "id": "chatcmpl-a1b2c3d4e5f6",
  "object": "chat.completion",
  "created": 1718123456,
  "provider": "gemini",
  "model": "gemini-2.0-flash",
  "message": {
    "role": "assistant",
    "content": "The capital of France is Paris."
  },
  "usage": {
    "note": "Token counts are unavailable for local/proxied providers."
  }
}
```

---

### 3.4 POST /v1/chat (with file)

Send a message with an attached file (PDF, image, or text).  
The file is processed in memory — **not saved to disk**.  
**Authentication required.**

**Request**
```
POST http://localhost:7860/v1/chat
Authorization: Bearer lc_your_key
Content-Type: multipart/form-data
```

**Form fields**

| Field     | Type   | Required | Description                         |
|-----------|--------|----------|-------------------------------------|
| `message` | text   | YES      | Your question about the file        |
| `file`    | file   | no       | PDF, image, or .txt file            |
| `stream`  | text   | no       | "true" or "false" (default "false") |

**Response 200**
```json
{
  "id": "chatcmpl-a1b2c3d4e5f6",
  "object": "chat.completion",
  "created": 1718123456,
  "provider": "gemini",
  "model": "gemini-2.0-flash",
  "message": {
    "role": "assistant",
    "content": "The invoice is for client John Doe, dated March 2025, total amount: $1,240.00"
  }
}
```

---

### 3.5 Streaming Response

Set `stream: true` (JSON) or `stream=true` (form-data) to receive a
**Server-Sent Events (SSE)** stream instead of a single JSON response.

**SSE event format**
```
data: {"delta": "The ", "done": false}
data: {"delta": "capital ", "done": false}
data: {"delta": "is Paris.", "done": false}
data: {"delta": "", "done": true, "provider": "gemini", "model": "gemini-2.0-flash"}
```

Each line starts with `data: ` followed by a JSON object:

| Field      | Description                                      |
|------------|--------------------------------------------------|
| `delta`    | Next text token from the AI                      |
| `done`     | `true` on the last event                         |
| `provider` | Active provider slug (only on the last event)    |
| `model`    | Model name (only on the last event)              |
| `error`    | Error message if something went wrong            |

---

## 4. Response Format

All successful non-streaming responses return HTTP `200` with this JSON structure:

```json
{
  "id":       "chatcmpl-<12 hex chars>",
  "object":   "chat.completion",
  "created":  1718123456,
  "provider": "<slug>",
  "model":    "<model name>",
  "message": {
    "role":    "assistant",
    "content": "<AI answer>"
  }
}
```

To get the answer text from the response:
```
response.message.content
```

---

## 5. Error Codes

| HTTP Code | Error message | Cause & Fix |
|-----------|--------------|-------------|
| `401` | Unauthorized | Missing or invalid API key |
| `400` / `422` | message field is required | Request has no `message` field |
| `415` | Unsupported file type: .docx | Use pdf, jpg, png, txt instead |
| `422` | Could not read file: ... | File is corrupted or unreadable |
| `503` | No AI provider is active | Go to `/settings` and activate a provider |
| `500` | Provider error: ... | Provider API key invalid or provider is down |

**Error response format**
```json
{
  "error": "Unauthorized — provide a valid API key via 'Authorization: Bearer lc_...'"
}
```

---

## 6. Code Examples

### Python

```python
import requests

BASE    = "http://localhost:7860"
API_KEY = "lc_your_key_here"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}


# ── Text chat ──────────────────────────────────────────────────────────────
def chat(message: str) -> str:
    r = requests.post(
        f"{BASE}/v1/chat",
        headers=HEADERS,
        json={"message": message},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["message"]["content"]


# ── Chat with PDF ──────────────────────────────────────────────────────────
def chat_with_pdf(message: str, pdf_path: str) -> str:
    with open(pdf_path, "rb") as f:
        r = requests.post(
            f"{BASE}/v1/chat",
            headers=HEADERS,
            data={"message": message},
            files={"file": ("document.pdf", f, "application/pdf")},
            timeout=120,
        )
    r.raise_for_status()
    return r.json()["message"]["content"]


# ── Chat with image ────────────────────────────────────────────────────────
def chat_with_image(message: str, image_path: str) -> str:
    with open(image_path, "rb") as f:
        r = requests.post(
            f"{BASE}/v1/chat",
            headers=HEADERS,
            data={"message": message},
            files={"file": f},
            timeout=60,
        )
    r.raise_for_status()
    return r.json()["message"]["content"]


# ── Streaming ──────────────────────────────────────────────────────────────
def chat_stream(message: str):
    r = requests.post(
        f"{BASE}/v1/chat",
        headers=HEADERS,
        json={"message": message, "stream": True},
        stream=True,
        timeout=120,
    )
    r.raise_for_status()
    for line in r.iter_lines():
        if not line:
            continue
        text = line.decode("utf-8")
        if text.startswith("data:"):
            import json
            data = json.loads(text[5:].strip())
            if data.get("done"):
                break
            print(data.get("delta", ""), end="", flush=True)


# ── Usage ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(chat("What is the capital of France?"))
    print(chat_with_pdf("Summarize this document", "report.pdf"))
    chat_stream("Tell me a short story")
```

---

### JavaScript / Node.js

```javascript
const BASE    = "http://localhost:7860";
const API_KEY = "lc_your_key_here";
const HEADERS = { Authorization: `Bearer ${API_KEY}` };


// ── Text chat ──────────────────────────────────────────────────────────────
async function chat(message) {
  const res = await fetch(`${BASE}/v1/chat`, {
    method: "POST",
    headers: { ...HEADERS, "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) throw new Error(`Error ${res.status}: ${await res.text()}`);
  const data = await res.json();
  return data.message.content;
}


// ── Chat with file (browser) ───────────────────────────────────────────────
async function chatWithFile(message, fileInput) {
  const form = new FormData();
  form.append("message", message);
  form.append("file", fileInput.files[0]);

  const res = await fetch(`${BASE}/v1/chat`, {
    method: "POST",
    headers: HEADERS,   // NO Content-Type — browser sets it with boundary
    body: form,
  });
  if (!res.ok) throw new Error(`Error ${res.status}: ${await res.text()}`);
  return (await res.json()).message.content;
}


// ── Chat with file (Node.js) ───────────────────────────────────────────────
// npm install form-data node-fetch
async function chatWithFileNode(message, filePath) {
  const FormData = require("form-data");
  const fs       = require("fs");
  const fetch    = require("node-fetch");

  const form = new FormData();
  form.append("message", message);
  form.append("file", fs.createReadStream(filePath));

  const res = await fetch(`${BASE}/v1/chat`, {
    method: "POST",
    headers: { ...HEADERS, ...form.getHeaders() },
    body: form,
  });
  if (!res.ok) throw new Error(await res.text());
  return (await res.json()).message.content;
}


// ── Streaming ──────────────────────────────────────────────────────────────
async function chatStream(message, onToken) {
  const res = await fetch(`${BASE}/v1/chat`, {
    method: "POST",
    headers: { ...HEADERS, "Content-Type": "application/json" },
    body: JSON.stringify({ message, stream: true }),
  });
  const reader  = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer    = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop();
    for (const line of lines) {
      if (!line.startsWith("data:")) continue;
      const data = JSON.parse(line.slice(5).trim());
      if (data.done) return;
      if (data.delta) onToken(data.delta);
    }
  }
}


// ── Usage ──────────────────────────────────────────────────────────────────
chat("What is the capital of France?").then(console.log);
chatStream("Tell me a short story", token => process.stdout.write(token));
```

---

### PHP

```php
<?php
define('BASE',    'http://localhost:7860');
define('API_KEY', 'lc_your_key_here');


// ── Text chat ──────────────────────────────────────────────────────────────
function chat(string $message): string {
    $ch = curl_init(BASE . '/v1/chat');
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_POST           => true,
        CURLOPT_HTTPHEADER     => [
            'Authorization: Bearer ' . API_KEY,
            'Content-Type: application/json',
        ],
        CURLOPT_POSTFIELDS     => json_encode(['message' => $message]),
        CURLOPT_TIMEOUT        => 60,
    ]);
    $body = curl_exec($ch);
    $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    if ($code !== 200) throw new RuntimeException("Error $code: $body");
    return json_decode($body, true)['message']['content'];
}


// ── Chat with PDF ──────────────────────────────────────────────────────────
function chatWithFile(string $message, string $filePath): string {
    $ch = curl_init(BASE . '/v1/chat');
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_POST           => true,
        CURLOPT_HTTPHEADER     => [
            'Authorization: Bearer ' . API_KEY,
        ],
        CURLOPT_POSTFIELDS => [
            'message' => $message,
            'file'    => new CURLFile($filePath),
        ],
        CURLOPT_TIMEOUT => 120,
    ]);
    $body = curl_exec($ch);
    $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    if ($code !== 200) throw new RuntimeException("Error $code: $body");
    return json_decode($body, true)['message']['content'];
}


// ── Usage ──────────────────────────────────────────────────────────────────
echo chat("What is the capital of France?") . PHP_EOL;
echo chatWithFile("Summarize this invoice", "/path/to/invoice.pdf") . PHP_EOL;
```

---

### C#

```csharp
using System;
using System.IO;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;

public class LocalChatClient
{
    private readonly HttpClient _http;
    private const string Base   = "http://localhost:7860";
    private const string ApiKey = "lc_your_key_here";

    public LocalChatClient()
    {
        _http = new HttpClient();
        _http.DefaultRequestHeaders.Authorization =
            new AuthenticationHeaderValue("Bearer", ApiKey);
        _http.Timeout = TimeSpan.FromSeconds(120);
    }

    // ── Text chat ──────────────────────────────────────────────────────────
    public async Task<string> Chat(string message)
    {
        var body    = JsonSerializer.Serialize(new { message });
        var content = new StringContent(body, Encoding.UTF8, "application/json");
        var resp    = await _http.PostAsync($"{Base}/v1/chat", content);

        resp.EnsureSuccessStatusCode();
        var json = await resp.Content.ReadAsStringAsync();
        using var doc = JsonDocument.Parse(json);
        return doc.RootElement
                  .GetProperty("message")
                  .GetProperty("content")
                  .GetString()!;
    }

    // ── Chat with file ─────────────────────────────────────────────────────
    public async Task<string> ChatWithFile(string message, string filePath)
    {
        var form = new MultipartFormDataContent();
        form.Add(new StringContent(message), "message");

        var fileBytes   = await File.ReadAllBytesAsync(filePath);
        var fileContent = new ByteArrayContent(fileBytes);
        fileContent.Headers.ContentType =
            new MediaTypeHeaderValue("application/octet-stream");
        form.Add(fileContent, "file", Path.GetFileName(filePath));

        var resp = await _http.PostAsync($"{Base}/v1/chat", form);
        resp.EnsureSuccessStatusCode();

        var json = await resp.Content.ReadAsStringAsync();
        using var doc = JsonDocument.Parse(json);
        return doc.RootElement
                  .GetProperty("message")
                  .GetProperty("content")
                  .GetString()!;
    }

    // ── Usage ──────────────────────────────────────────────────────────────
    public static async Task Main()
    {
        var client = new LocalChatClient();

        // Text chat
        var answer = await client.Chat("What is the capital of France?");
        Console.WriteLine(answer);

        // With PDF
        var summary = await client.ChatWithFile(
            "Summarize this document",
            "C:/path/to/report.pdf"
        );
        Console.WriteLine(summary);
    }
}
```

---

### cURL

```bash
# ── Text chat ──────────────────────────────────────────────────────────────
curl -X POST http://localhost:7860/v1/chat \
  -H "Authorization: Bearer lc_your_key_here" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the capital of France?"}'


# ── Chat with PDF ──────────────────────────────────────────────────────────
curl -X POST http://localhost:7860/v1/chat \
  -H "Authorization: Bearer lc_your_key_here" \
  -F "message=Summarize this document" \
  -F "file=@/path/to/report.pdf"


# ── Chat with image (OCR) ──────────────────────────────────────────────────
curl -X POST http://localhost:7860/v1/chat \
  -H "Authorization: Bearer lc_your_key_here" \
  -F "message=What does this image show?" \
  -F "file=@/path/to/photo.jpg"


# ── Streaming ──────────────────────────────────────────────────────────────
curl -X POST http://localhost:7860/v1/chat \
  -H "Authorization: Bearer lc_your_key_here" \
  -H "Content-Type: application/json" \
  -d '{"message": "Tell me a short story", "stream": true}' \
  --no-buffer


# ── Health check (no auth) ─────────────────────────────────────────────────
curl http://localhost:7860/v1/health


# ── Active provider ────────────────────────────────────────────────────────
curl http://localhost:7860/v1/providers/active \
  -H "Authorization: Bearer lc_your_key_here"


# ── Extract answer from JSON response ──────────────────────────────────────
curl -s -X POST http://localhost:7860/v1/chat \
  -H "Authorization: Bearer lc_your_key_here" \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello"}' | python -c "import sys,json; print(json.load(sys.stdin)['message']['content'])"
```

---

## 7. Postman Setup

### Text chat
```
Method : POST
URL    : http://localhost:7860/v1/chat
Headers: Authorization → Bearer lc_your_key_here
Body   : raw → JSON
         { "message": "What is the capital of France?" }
```

### With PDF or image
```
Method : POST
URL    : http://localhost:7860/v1/chat
Headers: Authorization → Bearer lc_your_key_here
         (do NOT set Content-Type manually)
Body   : form-data
         message  [Text]  Summarize this document
         file     [File]  (click Select Files → pick PDF or image)
```

> To change a row from Text to File in Postman:
> click the small dropdown on the right of the **Key** column → select **File**

### Streaming
```
Body: form-data
  message  [Text]  Tell me a story
  stream   [Text]  true
```

---

## 8. Supported File Types

| Extension | Processing method | Notes |
|-----------|------------------|-------|
| `.pdf` | pdfplumber (text extraction) | Best for digital/native PDFs |
| `.txt` | Plain UTF-8 read | Any text file |
| `.png` `.jpg` `.jpeg` | Tesseract OCR | Best results with clear text images |
| `.webp` `.bmp` `.tiff` `.tif` | Tesseract OCR | Same as above |

> Scanned PDFs (image-only, no text layer) should be sent as images, not PDFs.  
> Max file size: 20 MB (default server limit).

---

## 9. FAQ

**Q: Can I call this API from a different computer?**  
A: Yes. Replace `localhost` with the host machine's IP address.  
Example: `http://192.168.1.50:7860/v1/chat`  
Make sure the firewall allows port `7860`.

**Q: Can I call it from a web browser / frontend JavaScript?**  
A: Yes. CORS is enabled for all `/v1/*` routes, so any origin can call it.

**Q: Can I call it from a mobile app?**  
A: Yes, as long as the phone is on the same network and can reach the host IP + port.

**Q: What happens if the AI provider is offline?**  
A: You get HTTP `503` with `{"error": "No AI provider is active"}`.  
Fix: Go to `/settings` and activate/configure a working provider.

**Q: Is there rate limiting?**  
A: No. LocalChat is a single-user local app — no rate limiting is applied.

**Q: Can I have multiple API keys?**  
A: Yes. Create as many keys as you need at `/api-keys`. Each key can be revoked independently.

**Q: How do I revoke a key?**  
A: Go to `http://localhost:7860/api-keys` → click **Revoke** next to the key.

**Q: Is the API compatible with the OpenAI SDK?**  
A: Partially — the response format is similar but not identical.  
Use the plain `requests` / `fetch` approach shown above instead of the OpenAI SDK.

**Q: Can I send a conversation history?**  
A: `/api/ask` supports a `history` array. `/v1/chat` is stateless (no history) — maintain history in your app and include context in the `message` field.

---

## Quick Reference Card

```
BASE URL  : http://localhost:7860

ENDPOINTS:
  GET  /v1/health              → Health check (no auth)
  GET  /v1/providers/active    → Active provider info
  POST /v1/chat                → Chat (text or file)

AUTH:
  Authorization: Bearer lc_your_key_here

BODY (JSON):
  { "message": "your question", "stream": false }

BODY (form-data with file):
  message = your question
  file    = <file>
  stream  = true | false

RESPONSE:
  response.message.content  ← the AI answer

ERRORS:
  401 → bad key
  422 → missing message
  415 → unsupported file type
  503 → no provider active
```

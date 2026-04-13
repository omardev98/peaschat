FROM python:3.12-slim

# ── System deps (Tesseract OCR + build tools) ──────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-fra \
        tesseract-ocr-ara \
        libglib2.0-0 \
        libgl1 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python deps (layer-cached until requirements change) ──────────────────
COPY requirements.docker.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# ── App source ────────────────────────────────────────────────────────────
COPY . .

# ── Persistent data directories ───────────────────────────────────────────
RUN mkdir -p data uploads
VOLUME ["/app/data", "/app/uploads"]

# ── Runtime config ────────────────────────────────────────────────────────
ENV FLASK_HOST=0.0.0.0 \
    FLASK_PORT=5000 \
    TESSERACT_CMD=/usr/bin/tesseract

EXPOSE 5000

# ── Start with gunicorn (4 workers, 120s timeout for large file uploads) ──
CMD ["gunicorn", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "2", \
     "--threads", "4", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "wsgi:app"]

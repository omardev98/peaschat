"""
document_parser.py
──────────────────
Extracts text from PDFs and images, then splits into chunks.

PDF   → pdfplumber (text layer extraction)
Image → pytesseract OCR (Tesseract backend)
"""

import logging
import os
from pathlib import Path
from typing import List

from config import (
    CHUNK_SIZE, CHUNK_OVERLAP,
    TESSERACT_CMD, IMAGE_EXTENSIONS,
)

try:
    import pdfplumber
    from PIL import Image, ImageFilter, ImageEnhance
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
except ImportError:
    pdfplumber = None
    pytesseract = None
    Image = None

logger = logging.getLogger(__name__)


# ── PDF text extraction ────────────────────────────────────────────────────

def extract_text_from_pdf(path: str) -> str:
    """
    Extract all text from a PDF using pdfplumber.
    Returns the concatenated page texts.

    Raises:
        ValueError: if the PDF has no extractable text (e.g. scanned without OCR).
    """
    pages: List[str] = []
    with pdfplumber.open(path) as pdf:
        logger.info("PDF '%s': %d page(s)", Path(path).name, len(pdf.pages))
        for i, page in enumerate(pdf.pages, 1):
            text = page.extract_text()
            if text and text.strip():
                pages.append(text.strip())
            else:
                logger.debug("Page %d: no text (image-only?)", i)

    if not pages:
        raise ValueError(
            "No text found in PDF. "
            "If this is a scanned PDF, convert pages to images and upload them separately."
        )

    return "\n\n".join(pages)


# ── Image OCR extraction ────────────────────────────────────────────────────

def _preprocess_image(img: Image.Image) -> Image.Image:
    """
    Lightly preprocess the image to improve OCR accuracy:
    - Normalise mode to RGB or L
    - Sharpen slightly
    - Increase contrast
    """
    if img.mode not in ("RGB", "L", "RGBA"):
        img = img.convert("RGB")
    if img.mode == "RGBA":
        # Flatten alpha onto white background
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        img = bg
    # Mild sharpening
    img = img.filter(ImageFilter.SHARPEN)
    # Boost contrast
    img = ImageEnhance.Contrast(img).enhance(1.5)
    return img


def extract_text_from_image(path: str) -> str:
    """
    Run Tesseract OCR on an image file.

    Raises:
        RuntimeError: if Tesseract is not installed or not found.
        ValueError:   if OCR produces no text.
    """
    try:
        img = Image.open(path)
        img = _preprocess_image(img)

        # --oem 3: LSTM + Legacy (most accurate)
        # --psm 3: auto page segmentation
        custom_cfg = r"--oem 3 --psm 3"
        text = pytesseract.image_to_string(img, lang="eng", config=custom_cfg)

    except pytesseract.TesseractNotFoundError:
        raise RuntimeError(
            f"Tesseract not found at '{TESSERACT_CMD}'. "
            "Install Tesseract and set TESSERACT_CMD in .env.\n"
            "Windows: https://github.com/UB-Mannheim/tesseract/wiki\n"
            "Linux:   sudo apt install tesseract-ocr\n"
            "macOS:   brew install tesseract"
        )
    except Exception as exc:
        raise RuntimeError(f"OCR failed: {exc}") from exc

    if not text.strip():
        raise ValueError(
            "OCR returned no text. "
            "Check that the image contains legible text and is not too small or blurry."
        )

    return text.strip()


# ── Dispatcher ────────────────────────────────────────────────────────────

def extract_text(file_path: str) -> str:
    """
    Auto-detect file type and extract text.
      .pdf  → pdfplumber
      image → pytesseract OCR
    """
    ext = Path(file_path).suffix.lower().lstrip(".")
    if ext == "pdf":
        return extract_text_from_pdf(file_path)
    elif ext in IMAGE_EXTENSIONS:
        return extract_text_from_image(file_path)
    else:
        raise ValueError(f"Unsupported file type: .{ext}")


# ── Chunking ────────────────────────────────────────────────────────────────

def split_text(text: str) -> List[str]:
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ImportError as exc:
        raise RuntimeError(
            "langchain-text-splitters is not installed. "
            "Run: pip install langchain-text-splitters"
        ) from exc
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = [c.strip() for c in splitter.split_text(text) if c.strip()]
    logger.info("Split into %d chunk(s)", len(chunks))
    return chunks


# ── Public API ────────────────────────────────────────────────────────────

def parse_document(file_path: str) -> List[str]:
    """Full pipeline: extract text → split into chunks."""
    text   = extract_text(file_path)
    chunks = split_text(text)
    return chunks

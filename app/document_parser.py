"""
document_parser.py — MVP-2b

Thin wrappers around pypdf + python-docx + stdlib email that turn uploaded
document bytes into plain text. The text then feeds into
`copilot_engine.extract_demand`, which runs the Claude-Haiku item extractor
and catalog matcher.

Scope is deliberately narrow:
- PDF: visible text layer only (no OCR — scanned PDFs return empty)
- DOCX: paragraph + table text (merged with newlines)
- EML / raw email: body text via stdlib `email.parser`
- TXT / CSV: decoded as UTF-8 with best-effort fallback

Keep it pure-Python (no system deps) so Railway's Dockerfile stays fast.
"""
from __future__ import annotations

import io
import logging
from email import policy
from email.parser import BytesParser

log = logging.getLogger(__name__)


def detect_format(filename: str, content_type: str, raw: bytes) -> str:
    """Best-effort format detection: filename ext wins, content-type is
    tie-breaker, magic bytes for the common cases."""
    name = (filename or "").lower()
    ct = (content_type or "").lower()

    if name.endswith(".pdf") or "pdf" in ct or raw[:4] == b"%PDF":
        return "pdf"
    if name.endswith(".docx") or "wordprocessingml" in ct or "officedocument" in ct:
        return "docx"
    if name.endswith(".eml") or ct.startswith("message/"):
        return "eml"
    if name.endswith(".txt") or name.endswith(".csv") or ct.startswith("text/"):
        return "text"
    # Zip starts with PK — could be docx if ext was lost
    if raw[:2] == b"PK":
        return "docx"
    return "unknown"


def extract_text_from_pdf(raw: bytes) -> str:
    """Pull visible text layer from a PDF. Returns '' when file is a scan or
    parsing fails — OCR is out of scope."""
    try:
        from pypdf import PdfReader
    except ImportError:
        log.error("pypdf not installed — cannot parse PDF")
        return ""

    try:
        reader = PdfReader(io.BytesIO(raw))
        parts = []
        for page in reader.pages[:30]:  # cap at 30 pages
            txt = page.extract_text() or ""
            if txt.strip():
                parts.append(txt)
        return "\n\n".join(parts).strip()
    except Exception as exc:
        log.warning("PDF parse failed: %s", exc)
        return ""


def extract_text_from_docx(raw: bytes) -> str:
    """Pull paragraphs + table cells from a DOCX, merged with newlines."""
    try:
        from docx import Document
    except ImportError:
        log.error("python-docx not installed — cannot parse DOCX")
        return ""

    try:
        doc = Document(io.BytesIO(raw))
    except Exception as exc:
        log.warning("DOCX parse failed: %s", exc)
        return ""

    chunks: list[str] = []
    for para in doc.paragraphs:
        text = (para.text or "").strip()
        if text:
            chunks.append(text)
    for table in doc.tables:
        for row in table.rows:
            cells = [(cell.text or "").strip() for cell in row.cells]
            cells = [c for c in cells if c]
            if cells:
                chunks.append(" | ".join(cells))
    return "\n".join(chunks)


def extract_text_from_eml(raw: bytes) -> str:
    """Pull From/Subject + plain-text body from an .eml file.

    Prefers `text/plain` parts; falls back to stripped `text/html` so the
    LLM still gets something to work on.
    """
    try:
        msg = BytesParser(policy=policy.default).parsebytes(raw)
    except Exception as exc:
        log.warning("EML parse failed: %s", exc)
        return _decode_bytes(raw)

    header_lines = []
    for key in ("From", "Subject"):
        val = msg.get(key)
        if val:
            header_lines.append(f"{key}: {val}")
    body = ""
    if msg.is_multipart():
        # Walk and grab first text/plain; fall back to html if none found
        plain = None
        html = None
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain" and plain is None:
                plain = _safe_get_content(part)
            elif ctype == "text/html" and html is None:
                html = _safe_get_content(part)
        body = plain or html or ""
    else:
        body = _safe_get_content(msg)

    return "\n".join(filter(None, ["\n".join(header_lines), body])).strip()


def _safe_get_content(part) -> str:
    try:
        return part.get_content() or ""
    except Exception:
        try:
            payload = part.get_payload(decode=True) or b""
            return _decode_bytes(payload)
        except Exception:
            return ""


def _decode_bytes(raw: bytes) -> str:
    for enc in ("utf-8", "utf-16", "cp1250", "iso-8859-2", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def extract_text(filename: str, content_type: str, raw: bytes) -> tuple[str, str]:
    """Dispatcher — returns (extracted_text, detected_format).

    Format is returned so callers can surface the choice to the user
    ('Wykryto PDF, 12 stron...') and for telemetry.
    """
    fmt = detect_format(filename, content_type, raw)
    if fmt == "pdf":
        return extract_text_from_pdf(raw), "pdf"
    if fmt == "docx":
        return extract_text_from_docx(raw), "docx"
    if fmt == "eml":
        return extract_text_from_eml(raw), "eml"
    if fmt == "text":
        return _decode_bytes(raw), "text"
    # Last resort — try decoding as text so LLM still has a shot
    return _decode_bytes(raw), "unknown"

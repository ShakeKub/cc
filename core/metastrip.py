"""Metadata stripper — remove EXIF/author metadata from images, DOCX, and PDFs."""

import io
import zipfile
import re
from pathlib import Path


# ── Images ────────────────────────────────────────────────────────────────────

def strip_image(src: str, dst: str | None = None) -> dict:
    """Strip EXIF and all metadata from a JPEG/PNG/TIFF/WebP image."""
    try:
        from PIL import Image
    except ImportError:
        return {"ok": False, "error": "Pillow not installed. Run: pip install Pillow"}

    src_path = Path(src)
    dst_path = Path(dst) if dst else src_path.with_stem(src_path.stem + "_clean")

    try:
        with Image.open(src_path) as img:
            fmt = img.format or "PNG"
            # Convert and save without metadata
            clean = Image.new(img.mode, img.size)
            clean.putdata(list(img.getdata()))
            clean.save(str(dst_path), format=fmt)
        return {"ok": True, "output": str(dst_path), "format": fmt}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def read_image_meta(src: str) -> dict:
    """Read EXIF and basic metadata from an image."""
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
    except ImportError:
        return {"error": "Pillow not installed"}

    try:
        with Image.open(src) as img:
            info: dict = {"format": img.format, "mode": img.mode, "size": img.size}
            exif_raw = img._getexif() if hasattr(img, "_getexif") else None
            if exif_raw:
                info["exif"] = {TAGS.get(k, k): str(v)[:200] for k, v in exif_raw.items()}
            else:
                info["exif"] = {}
        return info
    except Exception as exc:
        return {"error": str(exc)}


# ── DOCX ──────────────────────────────────────────────────────────────────────

_DOCX_CLEAN_CORE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:dcterms="http://purl.org/dc/terms/"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title></dc:title>
  <dc:subject></dc:subject>
  <dc:creator></dc:creator>
  <cp:keywords></cp:keywords>
  <dc:description></dc:description>
  <cp:lastModifiedBy></cp:lastModifiedBy>
  <cp:revision>1</cp:revision>
</cp:coreProperties>"""

_DOCX_CLEAN_APP = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
  <Application>Microsoft Office Word</Application>
  <Company></Company>
  <Manager></Manager>
</Properties>"""


def read_docx_meta(src: str) -> dict:
    """Read metadata from a DOCX file."""
    try:
        with zipfile.ZipFile(src, "r") as zf:
            meta: dict = {}
            if "docProps/core.xml" in zf.namelist():
                xml = zf.read("docProps/core.xml").decode("utf-8", errors="replace")
                for tag in ("dc:creator", "cp:lastModifiedBy", "dc:title",
                            "dc:subject", "dc:description", "cp:revision"):
                    m = re.search(rf"<{re.escape(tag)}>(.*?)</{re.escape(tag)}>", xml, re.S)
                    meta[tag] = m.group(1).strip() if m else ""
            if "docProps/app.xml" in zf.namelist():
                xml = zf.read("docProps/app.xml").decode("utf-8", errors="replace")
                for tag in ("Application", "Company", "Manager"):
                    m = re.search(rf"<{re.escape(tag)}>(.*?)</{re.escape(tag)}>", xml, re.S)
                    meta[tag] = m.group(1).strip() if m else ""
        return meta
    except Exception as exc:
        return {"error": str(exc)}


def strip_docx(src: str, dst: str | None = None) -> dict:
    """Strip author/company metadata from a DOCX file."""
    src_path = Path(src)
    dst_path = Path(dst) if dst else src_path.with_stem(src_path.stem + "_clean")

    try:
        buf = io.BytesIO()
        with zipfile.ZipFile(src_path, "r") as zin, \
             zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == "docProps/core.xml":
                    data = _DOCX_CLEAN_CORE.encode("utf-8")
                elif item.filename == "docProps/app.xml":
                    data = _DOCX_CLEAN_APP.encode("utf-8")
                zout.writestr(item, data)

        dst_path.write_bytes(buf.getvalue())
        return {"ok": True, "output": str(dst_path)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ── PDF ───────────────────────────────────────────────────────────────────────

def read_pdf_meta(src: str) -> dict:
    """Read metadata from a PDF file."""
    try:
        import pypdf
        with open(src, "rb") as f:
            r = pypdf.PdfReader(f)
            return dict(r.metadata or {})
    except ImportError:
        pass
    try:
        import PyPDF2
        with open(src, "rb") as f:
            r = PyPDF2.PdfReader(f)
            return dict(r.metadata or {})
    except ImportError:
        return {"error": "pypdf not installed. Run: pip install pypdf"}
    except Exception as exc:
        return {"error": str(exc)}


def strip_pdf(src: str, dst: str | None = None) -> dict:
    """Strip all metadata from a PDF file."""
    src_path = Path(src)
    dst_path = Path(dst) if dst else src_path.with_stem(src_path.stem + "_clean")

    reader_mod = None
    try:
        import pypdf
        reader_mod = pypdf
    except ImportError:
        try:
            import PyPDF2 as pypdf
            reader_mod = pypdf
        except ImportError:
            return {"ok": False, "error": "pypdf not installed. Run: pip install pypdf"}

    try:
        reader = reader_mod.PdfReader(str(src_path))
        writer = reader_mod.PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        writer.add_metadata({})
        with open(str(dst_path), "wb") as f:
            writer.write(f)
        return {"ok": True, "output": str(dst_path)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ── dispatcher ────────────────────────────────────────────────────────────────

def strip(src: str, dst: str | None = None) -> dict:
    """Auto-detect file type and strip metadata."""
    suffix = Path(src).suffix.lower()
    if suffix in (".jpg", ".jpeg", ".png", ".tiff", ".tif", ".webp", ".bmp"):
        return strip_image(src, dst)
    if suffix in (".docx",):
        return strip_docx(src, dst)
    if suffix == ".pdf":
        return strip_pdf(src, dst)
    return {"ok": False, "error": f"Unsupported file type: '{suffix}'"}


def read_meta(src: str) -> dict:
    """Auto-detect and return metadata."""
    suffix = Path(src).suffix.lower()
    if suffix in (".jpg", ".jpeg", ".png", ".tiff", ".tif", ".webp", ".bmp"):
        return read_image_meta(src)
    if suffix in (".docx",):
        return read_docx_meta(src)
    if suffix == ".pdf":
        return read_pdf_meta(src)
    return {"error": f"Unsupported type: '{suffix}'"}

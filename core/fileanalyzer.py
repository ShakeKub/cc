"""File analyzer — magic bytes, entropy, strings, PE/ELF/Mach-O headers."""

import math
import os
import stat
import struct
from collections import Counter
from pathlib import Path

# ── Magic byte signatures (longest first for accurate matching) ───────────────
_SIGNATURES: list[tuple[bytes, int, str]] = [
    (b"SCENC",         0, "Encrypted file (.scenc — this tool)"),
    (b"\x89PNG\r\n\x1a\n", 0, "PNG image"),
    (b"\xff\xd8\xff",  0, "JPEG image"),
    (b"GIF87a",        0, "GIF image (87a)"),
    (b"GIF89a",        0, "GIF image (89a)"),
    (b"BM",            0, "BMP image"),
    (b"RIFF",          0, "RIFF container (WAV/AVI/WebP)"),
    (b"OggS",          0, "OGG audio/video"),
    (b"ID3",           0, "MP3 audio (ID3 tag)"),
    (b"\x00\x00\x00 ftyp", 0, "MP4/MOV video"),
    (b"\x00\x00\x01\xb3", 0, "MPEG video"),
    (b"fLaC",          0, "FLAC audio"),
    (b"7z\xbc\xaf\x27\x1c", 0, "7-Zip archive"),
    (b"Rar!\x1a\x07\x01", 0, "RAR5 archive"),
    (b"Rar!\x1a\x07\x00", 0, "RAR4 archive"),
    (b"\x1f\x8b",      0, "GZIP archive"),
    (b"BZ",            0, "BZIP2 archive"),
    (b"\xfd7zXZ\x00",  0, "XZ archive"),
    (b"PK\x03\x04",    0, "ZIP / Office Open XML (.docx/.xlsx/.pptx/.zip)"),
    (b"PK\x05\x06",    0, "ZIP (empty)"),
    (b"%PDF",          0, "PDF document"),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", 0, "MS Office legacy (.doc/.xls/.ppt)"),
    (b"\x4d\x5a",      0, "Windows PE / MZ executable (.exe/.dll/.sys)"),
    (b"\x7fELF",       0, "ELF binary (Linux/Unix executable/library)"),
    (b"\xca\xfe\xba\xbe", 0, "Mach-O fat binary (macOS universal)"),
    (b"\xcf\xfa\xed\xfe", 0, "Mach-O 64-bit LE (macOS)"),
    (b"\xce\xfa\xed\xfe", 0, "Mach-O 32-bit LE (macOS)"),
    (b"\xfe\xed\xfa\xcf", 0, "Mach-O 64-bit BE (macOS)"),
    (b"\xfe\xed\xfa\xce", 0, "Mach-O 32-bit BE (macOS)"),
    (b"SQLite format 3", 0, "SQLite database"),
    (b"\x00\x00\x01\x00", 0, "Windows icon (.ico)"),
    (b"<!DOCTYPE html", 0, "HTML document"),
    (b"<html",         0, "HTML document"),
    (b"<?xml",         0, "XML document"),
    (b"#!/",           0, "Shell script / shebang"),
    (b"MThd",          0, "MIDI audio"),
    (b"\x42\x4d",      0, "BMP image"),
    (b"\x00\x01\x00\x00", 0, "TrueType font (.ttf)"),
    (b"OTTO",          0, "OpenType font (.otf)"),
    (b"wOFF",          0, "WOFF font"),
]


def detect_type(header: bytes) -> str:
    for magic, offset, label in _SIGNATURES:
        end = offset + len(magic)
        if len(header) >= end and header[offset:end] == magic:
            return label
    # fallback: check printable content
    try:
        header.decode("utf-8")
        return "Text / UTF-8"
    except UnicodeDecodeError:
        pass
    return "Unknown / Binary"


def entropy(data: bytes) -> float:
    """Shannon entropy in bits per byte (0–8). >7.5 = likely encrypted/compressed."""
    if not data:
        return 0.0
    counts = Counter(data)
    total  = len(data)
    return -sum((c / total) * math.log2(c / total) for c in counts.values())


def entropy_label(e: float) -> str:
    if e < 1.0:  return "Very low (sparse/structured)"
    if e < 3.5:  return "Low (text/source code)"
    if e < 6.0:  return "Medium (mixed content)"
    if e < 7.2:  return "High (compressed?)"
    return "Very high — likely encrypted or compressed"


def extract_strings(data: bytes, min_len: int = 6) -> list[str]:
    """Extract printable ASCII strings ≥ min_len chars."""
    results = []
    cur: list[str] = []
    for b in data:
        c = chr(b)
        if c.isprintable() and b < 128:
            cur.append(c)
        else:
            if len(cur) >= min_len:
                results.append("".join(cur))
            cur = []
    if len(cur) >= min_len:
        results.append("".join(cur))
    return results


def _parse_pe(data: bytes) -> dict:
    """Parse minimal PE header info from a Windows executable."""
    info: dict = {}
    try:
        if len(data) < 64 or data[:2] != b"MZ":
            return info
        pe_offset = struct.unpack_from("<I", data, 60)[0]
        if pe_offset + 24 > len(data):
            return info
        if data[pe_offset:pe_offset + 4] != b"PE\x00\x00":
            return info
        machine = struct.unpack_from("<H", data, pe_offset + 4)[0]
        machines = {0x14c: "x86 (32-bit)", 0x8664: "x86-64 (64-bit)",
                    0x1c0: "ARM", 0xaa64: "ARM64"}
        info["machine"]   = machines.get(machine, f"0x{machine:04x}")
        info["timestamp"] = struct.unpack_from("<I", data, pe_offset + 8)[0]
        characteristics  = struct.unpack_from("<H", data, pe_offset + 22)[0]
        flags = []
        if characteristics & 0x0002: flags.append("executable")
        if characteristics & 0x2000: flags.append("DLL")
        if characteristics & 0x0020: flags.append("large-address-aware")
        info["characteristics"] = flags
    except Exception:
        pass
    return info


def _parse_elf(data: bytes) -> dict:
    """Parse minimal ELF header info."""
    info: dict = {}
    try:
        if len(data) < 16 or data[:4] != b"\x7fELF":
            return info
        bits  = {1: "32-bit", 2: "64-bit"}.get(data[4], "?")
        endian = {1: "LE", 2: "BE"}.get(data[5], "?")
        types = {0: "unknown", 1: "relocatable", 2: "executable",
                 3: "shared object", 4: "core dump"}
        e_type = struct.unpack_from("<H" if data[5] == 1 else ">H", data, 16)[0]
        info["bits"]   = bits
        info["endian"] = endian
        info["type"]   = types.get(e_type, f"0x{e_type:04x}")
    except Exception:
        pass
    return info


def analyze(path: str, max_strings: int = 200, sample_bytes: int = 1024 * 1024) -> dict:
    """Full analysis of a file. Returns a comprehensive info dict."""
    p = Path(path)
    if not p.is_file():
        return {"ok": False, "error": "File not found."}

    result: dict = {"ok": True, "path": str(p), "name": p.name}

    # Basic stat
    try:
        st = p.stat()
        result["size"]    = st.st_size
        result["mtime"]   = st.st_mtime
        result["mode"]    = stat.filemode(st.st_mode)
    except Exception as exc:
        result["stat_error"] = str(exc)

    # Read sample
    try:
        with p.open("rb") as f:
            sample = f.read(sample_bytes)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    header = sample[:512]
    result["file_type"] = detect_type(header)

    ent = entropy(sample)
    result["entropy"]       = round(ent, 3)
    result["entropy_label"] = entropy_label(ent)

    result["strings"] = extract_strings(sample, min_len=6)[:max_strings]
    result["string_count"] = len(result["strings"])

    # Format-specific parsing
    result["pe_info"]  = _parse_pe(sample)
    result["elf_info"] = _parse_elf(sample)

    # Extension vs magic mismatch
    ext = p.suffix.lower()
    ft  = result["file_type"].lower()
    mismatch = False
    if ext in (".exe", ".dll") and "pe" not in ft and "mz" not in ft:
        mismatch = True
    elif ext in (".jpg", ".jpeg") and "jpeg" not in ft:
        mismatch = True
    elif ext == ".png" and "png" not in ft:
        mismatch = True
    elif ext == ".pdf" and "pdf" not in ft:
        mismatch = True
    result["extension_mismatch"] = mismatch

    return result

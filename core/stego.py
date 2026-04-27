"""LSB steganography — hide and extract arbitrary data in PNG/BMP images."""

import os
import struct
from pathlib import Path

# Header: 4-byte magic + 1-byte version + 1-byte flags + 4-byte data_len = 10 bytes
_MAGIC   = b"STEG"
_VERSION = b"\x01"
_HDR_LEN = 10   # bytes


def _require_pil():
    try:
        from PIL import Image
        return Image
    except ImportError:
        raise ImportError("Pillow not installed. Run: pip install Pillow")


def _to_bits(data: bytes) -> list[int]:
    bits = []
    for byte in data:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    return bits


def _from_bits(bits: list[int]) -> bytes:
    out = bytearray()
    for i in range(0, len(bits) - 7, 8):
        out.append(int("".join(str(b) for b in bits[i:i + 8]), 2))
    return bytes(out)


def _xor_keystream(data: bytes, password: str) -> bytes:
    import hashlib
    pw = password.encode("utf-8")
    stream = b""
    i = 0
    while len(stream) < len(data):
        stream += hashlib.sha256(pw + i.to_bytes(4, "big")).digest()
        i += 1
    return bytes(a ^ b for a, b in zip(data, stream))


def capacity(image_path: str) -> int:
    """Max bytes that can be hidden in this image."""
    Image = _require_pil()
    with Image.open(image_path) as img:
        w, h = img.size
    return max((w * h * 3) // 8 - _HDR_LEN, 0)


def hide(cover_path: str, data: bytes, output_path: str, password: str | None = "") -> dict:
    """Embed *data* into *cover_path*. Saves lossless PNG to *output_path*."""
    Image = _require_pil()

    encrypted = bool(password)
    payload   = _xor_keystream(data, password) if encrypted else data
    flags     = b"\x01" if encrypted else b"\x00"
    header    = _MAGIC + _VERSION + flags + struct.pack(">I", len(payload))
    message   = header + payload

    with Image.open(cover_path) as img:
        img    = img.convert("RGB")
        w, h   = img.size
        pixels = list(img.getdata())

    max_bytes = (w * h * 3) // 8
    if len(message) > max_bytes:
        return {
            "ok": False,
            "error": f"Data ({len(message)} B) exceeds image capacity ({max_bytes} B).",
        }

    bits = _to_bits(message)
    idx  = 0
    new_pixels = []

    for r, g, b in pixels:
        if idx < len(bits): r = (r & ~1) | bits[idx]; idx += 1
        if idx < len(bits): g = (g & ~1) | bits[idx]; idx += 1
        if idx < len(bits): b = (b & ~1) | bits[idx]; idx += 1
        new_pixels.append((r, g, b))

    out = Path(output_path)
    if out.suffix.lower() not in (".png", ".bmp"):
        out = out.with_suffix(".png")

    result_img = Image.new("RGB", (w, h))
    result_img.putdata(new_pixels)
    result_img.save(str(out), format="PNG")

    return {
        "ok":          True,
        "output":      str(out),
        "hidden_bytes": len(data),
        "encrypted":   encrypted,
        "capacity":    f"{len(message)}/{max_bytes} B used",
    }


def extract(stego_path: str, password: str | None = "") -> bytes:
    """Extract data hidden by *hide()* from *stego_path* and return raw bytes."""
    Image = _require_pil()

    with Image.open(stego_path) as img:
        img    = img.convert("RGB")
        pixels = list(img.getdata())

    # Collect all LSBs
    all_bits: list[int] = []
    for r, g, b in pixels:
        all_bits += [r & 1, g & 1, b & 1]

    if len(all_bits) < _HDR_LEN * 8:
        raise ValueError("Image too small to contain data.")

    header = _from_bits(all_bits[: _HDR_LEN * 8])

    if header[:4] != _MAGIC:
        raise ValueError("No hidden data found (magic mismatch).")

    encrypted = bool(header[5] & 0x01)
    data_len  = struct.unpack(">I", header[6:10])[0]

    start = _HDR_LEN * 8
    end   = start + data_len * 8

    if end > len(all_bits):
        raise ValueError("Corrupted: data length exceeds image capacity.")

    payload = _from_bits(all_bits[start:end])

    if encrypted:
        if not password:
            raise ValueError("Data is password-protected - provide password.")
        payload = _xor_keystream(payload, password)

    return payload

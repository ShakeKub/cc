"""File Encryption — AES-256-GCM with scrypt key derivation."""

from __future__ import annotations
import os
import struct
from pathlib import Path
from typing import Any

_EXT = ".scenc"
_MAGIC = b"SCENC1\x00\x00"   # 8-byte header magic
_SALT_LEN = 32
_NONCE_LEN = 12
_TAG_LEN = 16


def _derive_key(password: str, salt: bytes) -> bytes:
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    from cryptography.hazmat.backends import default_backend
    kdf = Scrypt(salt=salt, length=32, n=2**15, r=8, p=1,
                 backend=default_backend())
    return kdf.derive(password.encode("utf-8"))


def encrypt_file(src: Path, password: str, logger=None) -> dict[str, Any]:
    """Encrypt src → src.scenc. Returns {"ok", "dst", "error"}."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        src = Path(src)
        dst = src.with_suffix(src.suffix + _EXT)

        salt = os.urandom(_SALT_LEN)
        nonce = os.urandom(_NONCE_LEN)
        key = _derive_key(password, salt)

        plaintext = src.read_bytes()
        aesgcm = AESGCM(key)
        ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext, None)

        with open(dst, "wb") as f:
            f.write(_MAGIC)
            f.write(salt)
            f.write(nonce)
            f.write(ciphertext_with_tag)

        if logger:
            logger.log_action("encrypt", str(src))
        return {"ok": True, "dst": dst, "error": ""}
    except Exception as e:
        return {"ok": False, "dst": None, "error": str(e)}


def decrypt_file(src: Path, password: str, logger=None) -> dict[str, Any]:
    """Decrypt src.scenc → src (without .scenc). Returns {"ok", "dst", "error"}."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        src = Path(src)
        if not str(src).endswith(_EXT):
            return {"ok": False, "dst": None, "error": "Not a .scenc file"}

        raw = src.read_bytes()
        off = 0

        magic = raw[off:off + 8]; off += 8
        if magic != _MAGIC:
            return {"ok": False, "dst": None, "error": "Invalid file header"}

        salt = raw[off:off + _SALT_LEN]; off += _SALT_LEN
        nonce = raw[off:off + _NONCE_LEN]; off += _NONCE_LEN
        ciphertext_with_tag = raw[off:]

        key = _derive_key(password, salt)
        aesgcm = AESGCM(key)

        try:
            plaintext = aesgcm.decrypt(nonce, ciphertext_with_tag, None)
        except Exception:
            return {"ok": False, "dst": None, "error": "Wrong password or corrupted file"}

        dst = Path(str(src)[: -len(_EXT)])
        dst.write_bytes(plaintext)

        if logger:
            logger.log_action("decrypt", str(src))
        return {"ok": True, "dst": dst, "error": ""}
    except Exception as e:
        return {"ok": False, "dst": None, "error": str(e)}


def encrypt_folder(folder: Path, password: str, logger=None) -> dict[str, Any]:
    """Encrypt every non-.scenc file in folder recursively."""
    folder = Path(folder)
    results = {"encrypted": 0, "skipped": 0, "errors": []}
    for f in folder.rglob("*"):
        if not f.is_file():
            continue
        if str(f).endswith(_EXT):
            results["skipped"] += 1
            continue
        r = encrypt_file(f, password, logger)
        if r["ok"]:
            results["encrypted"] += 1
        else:
            results["errors"].append(f"{f.name}: {r['error']}")
    return results


def decrypt_folder(folder: Path, password: str, logger=None) -> dict[str, Any]:
    """Decrypt every .scenc file in folder recursively."""
    folder = Path(folder)
    results = {"decrypted": 0, "failed": 0, "errors": []}
    for f in folder.rglob(f"*{_EXT}"):
        if not f.is_file():
            continue
        r = decrypt_file(f, password, logger)
        if r["ok"]:
            results["decrypted"] += 1
        else:
            results["failed"] += 1
            results["errors"].append(f"{f.name}: {r['error']}")
    return results


def crypto_available() -> bool:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        return True
    except ImportError:
        return False

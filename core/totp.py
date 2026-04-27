"""TOTP/2FA generator — RFC 6238 implementation + encrypted local secret store."""

import base64
import hashlib
import hmac
import json
import os
import struct
import time
from pathlib import Path

# ── Pure TOTP (no external deps) ─────────────────────────────────────────────

def _hotp(key: bytes, counter: int, digits: int = 6) -> str:
    msg = struct.pack(">Q", counter)
    h   = hmac.new(key, msg, hashlib.sha1).digest()
    off = h[-1] & 0x0F
    code = struct.unpack(">I", h[off:off + 4])[0] & 0x7FFF_FFFF
    return str(code % (10 ** digits)).zfill(digits)


def _b32_decode(secret: str) -> bytes:
    s = secret.upper().strip().replace(" ", "")
    pad = (8 - len(s) % 8) % 8
    return base64.b32decode(s + "=" * pad)


def generate_code(secret_b32: str, digits: int = 6, period: int = 30) -> str:
    """Generate current TOTP code from a base32-encoded secret."""
    key     = _b32_decode(secret_b32)
    counter = int(time.time()) // period
    return _hotp(key, counter, digits)


def remaining_seconds(period: int = 30) -> int:
    """Seconds until current TOTP window expires."""
    return period - (int(time.time()) % period)


def verify_code(secret_b32: str, code: str, window: int = 1, period: int = 30) -> bool:
    """Verify a TOTP code, accepting ±window periods for clock skew."""
    key     = _b32_decode(secret_b32)
    counter = int(time.time()) // period
    for offset in range(-window, window + 1):
        if hmac.compare_digest(_hotp(key, counter + offset), code.strip()):
            return True
    return False


def generate_secret() -> str:
    """Generate a random base32 secret (20 bytes = 160 bits)."""
    return base64.b32encode(os.urandom(20)).decode().rstrip("=")


# ── Encrypted vault ──────────────────────────────────────────────────────────

_VAULT_VERSION = 1


def _derive_key(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)


def _aes_gcm_encrypt(key: bytes, plaintext: bytes) -> tuple[bytes, bytes]:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    ct    = AESGCM(key).encrypt(nonce, plaintext, None)
    return nonce, ct


def _aes_gcm_decrypt(key: bytes, nonce: bytes, ct: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return AESGCM(key).decrypt(nonce, ct, None)


class TOTPVault:
    """Encrypted local store for TOTP secrets."""

    def __init__(self, vault_path: str):
        self.path = Path(vault_path)

    # ── low-level ─────────────────────────────────────────────

    def _load_raw(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _decrypt_entries(self, raw: dict, password: str) -> list[dict]:
        salt  = bytes.fromhex(raw["salt"])
        nonce = bytes.fromhex(raw["nonce"])
        ct    = bytes.fromhex(raw["ciphertext"])
        key   = _derive_key(password, salt)
        try:
            plain = _aes_gcm_decrypt(key, nonce, ct)
        except Exception:
            raise ValueError("Wrong master password.")
        return json.loads(plain.decode("utf-8"))

    def _save_entries(self, entries: list[dict], password: str):
        salt        = os.urandom(32)
        key         = _derive_key(password, salt)
        plain       = json.dumps(entries, ensure_ascii=False).encode("utf-8")
        nonce, ct   = _aes_gcm_encrypt(key, plain)
        raw = {
            "version":    _VAULT_VERSION,
            "salt":       salt.hex(),
            "nonce":      nonce.hex(),
            "ciphertext": ct.hex(),
        }
        self.path.write_text(json.dumps(raw, indent=2), encoding="utf-8")

    # ── public API ────────────────────────────────────────────

    def exists(self) -> bool:
        return self.path.exists()

    def init(self, password: str):
        """Create an empty vault with *password*."""
        self._save_entries([], password)

    def list_entries(self, password: str) -> list[dict]:
        raw = self._load_raw()
        if not raw:
            return []
        return self._decrypt_entries(raw, password)

    def add(self, password: str, name: str, secret: str,
            issuer: str = "", digits: int = 6, period: int = 30) -> dict:
        # Validate secret
        try:
            _b32_decode(secret)
        except Exception:
            return {"ok": False, "error": "Invalid base32 secret."}

        entries = self.list_entries(password)
        if any(e["name"] == name for e in entries):
            return {"ok": False, "error": f"Entry '{name}' already exists."}

        entries.append({
            "name":   name,
            "secret": secret.upper().strip(),
            "issuer": issuer,
            "digits": digits,
            "period": period,
        })
        self._save_entries(entries, password)
        return {"ok": True}

    def delete(self, password: str, name: str) -> dict:
        entries = self.list_entries(password)
        new     = [e for e in entries if e["name"] != name]
        if len(new) == len(entries):
            return {"ok": False, "error": f"Entry '{name}' not found."}
        self._save_entries(new, password)
        return {"ok": True}

    def get_code(self, password: str, name: str) -> dict:
        entries = self.list_entries(password)
        for e in entries:
            if e["name"] == name:
                code = generate_code(e["secret"], e.get("digits", 6), e.get("period", 30))
                return {
                    "ok": True,
                    "name":    e["name"],
                    "issuer":  e.get("issuer", ""),
                    "code":    code,
                    "expires": remaining_seconds(e.get("period", 30)),
                }
        return {"ok": False, "error": f"Entry '{name}' not found."}

    def get_all_codes(self, password: str) -> list[dict]:
        results = []
        for e in self.list_entries(password):
            code = generate_code(e["secret"], e.get("digits", 6), e.get("period", 30))
            results.append({
                "name":    e["name"],
                "issuer":  e.get("issuer", ""),
                "code":    code,
                "expires": remaining_seconds(e.get("period", 30)),
            })
        return results

"""Encrypted local password manager — AES-256-GCM vault with PBKDF2 master key."""

import hashlib
import json
import os
import time
from pathlib import Path


_VAULT_VERSION = 1
_KDF_ITERS     = 200_000


def _derive(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _KDF_ITERS)


def _encrypt(key: bytes, plaintext: bytes) -> tuple[bytes, bytes]:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    return nonce, AESGCM(key).encrypt(nonce, plaintext, None)


def _decrypt(key: bytes, nonce: bytes, ct: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return AESGCM(key).decrypt(nonce, ct, None)


# ── Vault ──────────────────────────────────────────────────────────────────────

class PasswordVault:
    """Encrypted local password store. Each entry has name/username/password/url/notes."""

    def __init__(self, vault_path: str):
        self.path = Path(vault_path)

    def exists(self) -> bool:
        return self.path.exists()

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _decrypt_entries(self, raw: dict, password: str) -> list[dict]:
        salt  = bytes.fromhex(raw["salt"])
        nonce = bytes.fromhex(raw["nonce"])
        ct    = bytes.fromhex(raw["ciphertext"])
        key   = _derive(password, salt)
        try:
            plain = _decrypt(key, nonce, ct)
        except Exception:
            raise ValueError("Wrong master password or corrupted vault.")
        return json.loads(plain.decode("utf-8"))

    def _save(self, entries: list[dict], password: str):
        salt      = os.urandom(32)
        key       = _derive(password, salt)
        plain     = json.dumps(entries, ensure_ascii=False, indent=2).encode("utf-8")
        nonce, ct = _encrypt(key, plain)
        self.path.write_text(json.dumps({
            "version":    _VAULT_VERSION,
            "salt":       salt.hex(),
            "nonce":      nonce.hex(),
            "ciphertext": ct.hex(),
        }, indent=2), encoding="utf-8")

    # ── public ────────────────────────────────────────────────

    def init(self, password: str):
        """Create an empty vault."""
        self._save([], password)

    def verify(self, password: str) -> bool:
        """Return True if *password* opens the vault."""
        try:
            self._decrypt_entries(self._load(), password)
            return True
        except Exception:
            return False

    def list_entries(self, password: str) -> list[dict]:
        raw = self._load()
        if not raw:
            return []
        return self._decrypt_entries(raw, password)

    def add(self, password: str, name: str, username: str = "",
            entry_pw: str = "", url: str = "", notes: str = "") -> dict:
        entries = self.list_entries(password)
        if any(e["name"] == name for e in entries):
            return {"ok": False, "error": f"Entry '{name}' already exists."}
        entries.append({
            "id":       len(entries) + 1,
            "name":     name,
            "username": username,
            "password": entry_pw,
            "url":      url,
            "notes":    notes,
            "created":  time.time(),
            "modified": time.time(),
        })
        self._save(entries, password)
        return {"ok": True}

    def update(self, password: str, name: str, **kwargs) -> dict:
        entries = self.list_entries(password)
        for e in entries:
            if e["name"] == name:
                for k, v in kwargs.items():
                    if k in ("username", "password", "url", "notes"):
                        e[k] = v
                e["modified"] = time.time()
                self._save(entries, password)
                return {"ok": True}
        return {"ok": False, "error": f"Entry '{name}' not found."}

    def get(self, password: str, name: str) -> dict | None:
        for e in self.list_entries(password):
            if e["name"] == name:
                return e
        return None

    def search(self, password: str, query: str) -> list[dict]:
        q = query.lower()
        return [
            e for e in self.list_entries(password)
            if q in e["name"].lower()
            or q in e.get("username", "").lower()
            or q in e.get("url", "").lower()
            or q in e.get("notes", "").lower()
        ]

    def delete(self, password: str, name: str) -> dict:
        entries = self.list_entries(password)
        new     = [e for e in entries if e["name"] != name]
        if len(new) == len(entries):
            return {"ok": False, "error": f"Entry '{name}' not found."}
        self._save(new, password)
        return {"ok": True}

    def change_master(self, old_password: str, new_password: str) -> dict:
        try:
            entries = self.list_entries(old_password)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        self._save(entries, new_password)
        return {"ok": True}

    def export_plaintext(self, password: str, out_path: str) -> dict:
        """Export all entries as plaintext JSON (WARNING: unencrypted!)."""
        try:
            entries = self.list_entries(password)
            Path(out_path).write_text(
                json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            return {"ok": True, "path": out_path, "count": len(entries)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

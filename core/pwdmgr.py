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
        self._master_password: str | None = None
        self._unlocked: bool = False

    def exists(self) -> bool:
        return self.path.exists()

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    @staticmethod
    def _normalize_entries(entries: list[dict]) -> list[dict]:
        normalized: list[dict] = []
        used: set[int] = set()
        next_id = 1
        for row in entries:
            item = dict(row)
            rid = item.get("id")
            if isinstance(rid, int) and rid > 0 and rid not in used:
                assigned = rid
            else:
                while next_id in used:
                    next_id += 1
                assigned = next_id
                next_id += 1
            item["id"] = assigned
            used.add(assigned)
            normalized.append(item)
        return normalized

    def _resolve_password(self, password: str | None) -> str:
        if password:
            return password
        if self._unlocked and self._master_password:
            return self._master_password
        raise ValueError("Vault is locked.")

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
        self._master_password = password
        self._unlocked = True

    def load(self, password: str) -> bool:
        """Unlock an existing vault with *password*. Returns False on failure."""
        raw = self._load()
        if not raw:
            self._master_password = None
            self._unlocked = False
            return False
        try:
            entries = self._decrypt_entries(raw, password)
            normalized = self._normalize_entries(entries)
            if normalized != entries:
                self._save(normalized, password)
            self._master_password = password
            self._unlocked = True
            return True
        except Exception:
            self._master_password = None
            self._unlocked = False
            return False

    def verify(self, password: str) -> bool:
        """Return True if *password* opens the vault."""
        return self.load(password)

    def list_entries(self, password: str | None = None) -> list[dict]:
        password = self._resolve_password(password)
        raw = self._load()
        if not raw:
            return []
        entries = self._decrypt_entries(raw, password)
        normalized = self._normalize_entries(entries)
        if normalized != entries:
            self._save(normalized, password)
        return normalized

    def add(self, *args, **kwargs) -> dict:
        """
        Supported calls:
          add(password, name, username="", entry_pw="", url="", notes="")
          add(name, username="", entry_pw="", url="", notes="")  # when unlocked
        """
        if not args:
            return {"ok": False, "error": "Missing arguments."}

        if self._unlocked and self._master_password and args[0] != self._master_password:
            password = self._master_password
            name = str(args[0])
            username = str(args[1]) if len(args) > 1 else str(kwargs.get("username", ""))
            entry_pw = str(args[2]) if len(args) > 2 else str(kwargs.get("entry_pw", kwargs.get("password", "")))
        else:
            if len(args) < 2:
                return {"ok": False, "error": "Missing arguments."}
            password = str(args[0])
            name = str(args[1])
            username = str(args[2]) if len(args) > 2 else str(kwargs.get("username", ""))
            entry_pw = str(args[3]) if len(args) > 3 else str(kwargs.get("entry_pw", kwargs.get("password", "")))

        url = str(kwargs.get("url", ""))
        notes = str(kwargs.get("notes", ""))

        entries = self.list_entries(password)
        if any(e["name"] == name for e in entries):
            return {"ok": False, "error": f"Entry '{name}' already exists."}

        new_id = max((int(e.get("id", 0)) for e in entries), default=0) + 1

        entries.append({
            "id":       new_id,
            "name":     name,
            "username": username,
            "password": entry_pw,
            "url":      url,
            "notes":    notes,
            "created":  time.time(),
            "modified": time.time(),
        })
        self._save(entries, password)
        if self._master_password is None:
            self._master_password = password
            self._unlocked = True
        return {"ok": True}

    def update(self, *args, **kwargs) -> dict:
        """
        Supported calls:
          update(password, name_or_id, ...)
          update(name_or_id, ...)  # when unlocked
        """
        if not args:
            return {"ok": False, "error": "Missing target."}

        if len(args) == 1 and self._unlocked and self._master_password:
            password = self._master_password
            target = args[0]
        elif len(args) >= 2:
            password = str(args[0])
            target = args[1]
        else:
            return {"ok": False, "error": "Vault is locked."}

        entries = self.list_entries(password)

        def _match(entry: dict) -> bool:
            if isinstance(target, int) or (isinstance(target, str) and target.isdigit()):
                return int(entry.get("id", -1)) == int(target)
            return entry.get("name") == str(target)

        for e in entries:
            if _match(e):
                for k, v in kwargs.items():
                    if k in ("name", "username", "password", "url", "notes"):
                        e[k] = v
                e["modified"] = time.time()
                self._save(entries, password)
                return {"ok": True}
        return {"ok": False, "error": "Entry not found."}

    def get(self, *args) -> dict | None:
        """
        Supported calls:
          get(password, name_or_id)
          get(name_or_id)  # when unlocked
        """
        if not args:
            return None

        if len(args) == 1 and self._unlocked and self._master_password:
            password = self._master_password
            target = args[0]
        elif len(args) >= 2:
            password = str(args[0])
            target = args[1]
        else:
            return None

        for e in self.list_entries(password):
            if isinstance(target, int) or (isinstance(target, str) and target.isdigit()):
                if int(e.get("id", -1)) == int(target):
                    return e
            elif e.get("name") == str(target):
                return e
        return None

    def search(self, *args) -> list[dict]:
        """
        Supported calls:
          search(password, query)
          search(query)  # when unlocked
        """
        if not args:
            return []

        if len(args) == 1 and self._unlocked and self._master_password:
            password = self._master_password
            query = str(args[0])
        elif len(args) >= 2:
            password = str(args[0])
            query = str(args[1])
        else:
            return []

        q = query.lower()
        return [
            e for e in self.list_entries(password)
            if q in e["name"].lower()
            or q in e.get("username", "").lower()
            or q in e.get("url", "").lower()
            or q in e.get("notes", "").lower()
        ]

    def delete(self, *args) -> dict:
        """
        Supported calls:
          delete(password, name_or_id)
          delete(name_or_id)  # when unlocked
        """
        if not args:
            return {"ok": False, "error": "Missing target."}

        if len(args) == 1 and self._unlocked and self._master_password:
            password = self._master_password
            target = args[0]
        elif len(args) >= 2:
            password = str(args[0])
            target = args[1]
        else:
            return {"ok": False, "error": "Vault is locked."}

        entries = self.list_entries(password)
        if isinstance(target, int) or (isinstance(target, str) and target.isdigit()):
            tid = int(target)
            new = [e for e in entries if int(e.get("id", -1)) != tid]
        else:
            name = str(target)
            new = [e for e in entries if e.get("name") != name]

        if len(new) == len(entries):
            return {"ok": False, "error": "Entry not found."}
        self._save(new, password)
        return {"ok": True}

    def change_master(self, old_password: str, new_password: str) -> dict:
        try:
            entries = self.list_entries(old_password)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        self._save(entries, new_password)
        self._master_password = new_password
        self._unlocked = True
        return {"ok": True}

    def export_plaintext(self, *args) -> dict:
        """Export all entries as plaintext JSON (WARNING: unencrypted!)."""
        if not args:
            return {"ok": False, "error": "Missing output path."}

        if len(args) == 1 and self._unlocked and self._master_password:
            password = self._master_password
            out_path = str(args[0])
        elif len(args) >= 2:
            password = str(args[0])
            out_path = str(args[1])
        else:
            return {"ok": False, "error": "Vault is locked."}

        try:
            entries = self.list_entries(password)
            Path(out_path).write_text(
                json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            return {"ok": True, "path": out_path, "count": len(entries)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

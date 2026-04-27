"""File Encryption — multi-algorithm with auto-detect and password cracker.

Supported algorithms (all use scrypt KDF):
  AES-256-GCM       — default, authenticated
  AES-128-GCM       — faster, still authenticated
  AES-256-CBC+HMAC  — widely compatible, CBC+PKCS7+HMAC-SHA256
  ChaCha20-Poly1305 — fast, authenticated (mobile-friendly)
  Fernet            — simple symmetric (cryptography lib)

File format (v1 legacy — AES-256-GCM only):
  [8]  magic b"SCENC1\\x00\\x00"
  [32] salt
  [12] nonce
  [n]  ciphertext+tag

File format (v2 — all algorithms):
  [8]  magic  (identifies algorithm, see ALGOS)
  [1]  n_exp  (scrypt N = 2**n_exp)
  [1]  r      (scrypt r)
  [1]  p      (scrypt p)
  [1]  0x00   reserved
  [32] salt
  [?]  nonce/IV  (length depends on algo)
  [n]  ciphertext (+ tag for AEAD, + 32-byte HMAC for CBC)
"""

from __future__ import annotations

import os
import struct
import string
import random
import threading
import time
from pathlib import Path
from typing import Any, Callable

# ── Algorithm registry ────────────────────────────────────────────────────────
# (magic_8_bytes, key_len, nonce_len, display_name)
ALGOS: dict[str, tuple[bytes, int, int]] = {
    "AES-256-GCM":       (b"SCENC1\x00\x00", 32, 12),
    "AES-256-CBC":       (b"SCENC2\x00\x00", 64, 16),  # 64 = 32 enc + 32 mac key
    "ChaCha20-Poly1305": (b"SCENC3\x00\x00", 32, 12),
    "AES-128-GCM":       (b"SCENC4\x00\x00", 16, 12),
    "Fernet":            (b"SCENC5\x00\x00", 32,  0),  # Fernet manages its own IV
}
MAGIC_TO_ALGO: dict[bytes, str] = {v[0]: k for k, v in ALGOS.items()}
DEFAULT_ALGO = "AES-256-GCM"
_EXT = ".scenc"

# Legacy v1 header (SCENC1 only — no KDF params stored → assume n=32768, r=8, p=1)
_V1_MAGIC = b"SCENC1\x00\x00"
_SALT_LEN  = 32
_HDR_KDF   = 4   # n_exp + r + p + reserved bytes in v2 header


# ── KDF ───────────────────────────────────────────────────────────────────────

def _derive_key(password: str, salt: bytes, key_len: int,
                n: int = 32768, r: int = 8, p: int = 1) -> bytes:
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    from cryptography.hazmat.backends import default_backend
    kdf = Scrypt(salt=salt, length=key_len, n=n, r=r, p=p,
                 backend=default_backend())
    return kdf.derive(password.encode("utf-8"))


# ── Low-level encrypt/decrypt per algorithm ───────────────────────────────────

def _encrypt_algo(algo: str, key: bytes, nonce: bytes, plaintext: bytes) -> bytes:
    if algo in ("AES-256-GCM", "AES-128-GCM"):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        return AESGCM(key).encrypt(nonce, plaintext, None)

    if algo == "ChaCha20-Poly1305":
        from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
        return ChaCha20Poly1305(key).encrypt(nonce, plaintext, None)

    if algo == "AES-256-CBC":
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives.padding import PKCS7
        from cryptography.hazmat.primitives import hmac, hashes
        enc_key, mac_key = key[:32], key[32:]
        padder = PKCS7(128).padder()
        padded = padder.update(plaintext) + padder.finalize()
        cipher = Cipher(algorithms.AES(enc_key), modes.CBC(nonce))
        enc = cipher.encryptor()
        ct = enc.update(padded) + enc.finalize()
        h = hmac.HMAC(mac_key, hashes.SHA256())
        h.update(nonce + ct)
        return ct + h.finalize()   # append 32-byte MAC

    if algo == "Fernet":
        import base64
        from cryptography.fernet import Fernet
        return Fernet(base64.urlsafe_b64encode(key)).encrypt(plaintext)

    raise ValueError(f"Unknown algorithm: {algo}")


def _decrypt_algo(algo: str, key: bytes, nonce: bytes, ciphertext: bytes) -> bytes:
    if algo in ("AES-256-GCM", "AES-128-GCM"):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        return AESGCM(key).decrypt(nonce, ciphertext, None)

    if algo == "ChaCha20-Poly1305":
        from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
        return ChaCha20Poly1305(key).decrypt(nonce, ciphertext, None)

    if algo == "AES-256-CBC":
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives.padding import PKCS7
        from cryptography.hazmat.primitives import hmac, hashes
        from cryptography.hazmat.primitives.hmac import HMAC
        from cryptography.exceptions import InvalidSignature
        enc_key, mac_key = key[:32], key[32:]
        ct, expected_mac = ciphertext[:-32], ciphertext[-32:]
        h = HMAC(mac_key, hashes.SHA256())
        h.update(nonce + ct)
        h.verify(expected_mac)   # raises InvalidSignature on wrong password
        cipher = Cipher(algorithms.AES(enc_key), modes.CBC(nonce))
        dec = cipher.decryptor()
        padded = dec.update(ct) + dec.finalize()
        unpadder = PKCS7(128).unpadder()
        return unpadder.update(padded) + unpadder.finalize()

    if algo == "Fernet":
        import base64
        from cryptography.fernet import Fernet, InvalidToken
        return Fernet(base64.urlsafe_b64encode(key)).decrypt(ciphertext)

    raise ValueError(f"Unknown algorithm: {algo}")


# ── File-level encrypt / decrypt ──────────────────────────────────────────────

def encrypt_file(src: Path | str, password: str, logger=None,
                 algo: str = DEFAULT_ALGO,
                 scrypt_n: int = 32768) -> dict[str, Any]:
    """Encrypt src → src.scenc.  Returns {ok, dst, algo, error}."""
    try:
        if algo not in ALGOS:
            return {"ok": False, "dst": None, "algo": algo,
                    "error": f"Unknown algorithm '{algo}'"}
        src = Path(src)
        dst = src.with_suffix(src.suffix + _EXT)

        magic, key_len, nonce_len = ALGOS[algo]
        salt  = os.urandom(_SALT_LEN)
        nonce = os.urandom(nonce_len) if nonce_len else b""

        key       = _derive_key(password, salt, key_len, n=scrypt_n)
        plaintext = src.read_bytes()
        ciphertext = _encrypt_algo(algo, key, nonce, plaintext)

        with open(dst, "wb") as f:
            f.write(magic)
            if magic != _V1_MAGIC:
                n_exp = scrypt_n.bit_length() - 1
                f.write(bytes([n_exp, 8, 1, 0]))  # n_exp, r, p, reserved
            f.write(salt)
            if nonce:
                f.write(nonce)
            f.write(ciphertext)

        if logger:
            logger.log_action("encrypt", str(src), category="fileencrypt")
        return {"ok": True, "dst": dst, "algo": algo, "error": ""}
    except Exception as e:
        return {"ok": False, "dst": None, "algo": algo, "error": str(e)}


def _parse_header(raw: bytes) -> tuple[str, int, int, int, int] | None:
    """
    Returns (algo, kdf_n, kdf_r, kdf_p, data_offset) or None if not recognized.
    data_offset points to salt start.
    """
    if len(raw) < 8:
        return None
    magic = raw[:8]
    algo = MAGIC_TO_ALGO.get(magic)
    if algo is None:
        return None

    if magic == _V1_MAGIC:
        return algo, 32768, 8, 1, 8

    # v2: 4 KDF-param bytes follow magic
    if len(raw) < 12:
        return None
    n_exp, r, p, _ = raw[8], raw[9], raw[10], raw[11]
    n = 2 ** n_exp
    return algo, n, r, p, 12


def decrypt_file(src: Path | str, password: str, logger=None) -> dict[str, Any]:
    """Auto-detect algorithm and decrypt.  Returns {ok, dst, algo, error}."""
    try:
        src = Path(src)
        if not str(src).endswith(_EXT):
            return {"ok": False, "dst": None, "algo": "?",
                    "error": "Not a .scenc file"}

        raw = src.read_bytes()
        parsed = _parse_header(raw)
        if parsed is None:
            return {"ok": False, "dst": None, "algo": "?",
                    "error": "Unrecognized file header"}

        algo, kdf_n, kdf_r, kdf_p, off = parsed
        _, key_len, nonce_len = ALGOS[algo]

        salt  = raw[off: off + _SALT_LEN];  off += _SALT_LEN
        nonce = raw[off: off + nonce_len];  off += nonce_len
        ct    = raw[off:]

        key = _derive_key(password, salt, key_len, n=kdf_n, r=kdf_r, p=kdf_p)
        plaintext = _decrypt_algo(algo, key, nonce, ct)

        dst = Path(str(src)[:-len(_EXT)])
        dst.write_bytes(plaintext)

        if logger:
            logger.log_action("decrypt", str(src), category="fileencrypt")
        return {"ok": True, "dst": dst, "algo": algo, "error": ""}
    except Exception as e:
        return {"ok": False, "dst": None, "algo": "?",
                "error": "Wrong password or corrupted file"}


# ── Folder helpers ────────────────────────────────────────────────────────────

def encrypt_folder(folder: Path, password: str, logger=None,
                   algo: str = DEFAULT_ALGO) -> dict[str, Any]:
    folder = Path(folder)
    results: dict[str, Any] = {"encrypted": 0, "skipped": 0, "errors": []}
    for f in folder.rglob("*"):
        if not f.is_file():
            continue
        if str(f).endswith(_EXT):
            results["skipped"] += 1
            continue
        r = encrypt_file(f, password, logger, algo)
        if r["ok"]:
            results["encrypted"] += 1
        else:
            results["errors"].append(f"{f.name}: {r['error']}")
    return results


def decrypt_folder(folder: Path, password: str, logger=None) -> dict[str, Any]:
    folder = Path(folder)
    results: dict[str, Any] = {"decrypted": 0, "failed": 0, "errors": []}
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


# ── Password cracker ──────────────────────────────────────────────────────────

# Embedded common-password list (top ~300)
_COMMON_PASSWORDS = """
123456 password 123456789 12345678 12345 1234567 1234567890 qwerty abc123
111111 123123 admin letmein welcome monkey dragon master pass1234
password1 iloveyou sunshine princess qwerty123 1q2w3e4r 000000 654321
superman batman secret 123321 666666 88888888 1234 7777777 1q2w3e
pass hello admin123 login 696969 shadow master 159753 aa123456 donald
freedom whatever qazwsx trustno1 jennifer soccer baseball baseball1
summer shadow michael jessica dragon charlie andrew thomas george
charlie1 andrea joshua michelle jessica1 daniel robert george1 jordan
soccer1 harley ranger hockey dakota cookie 1234567890 test changeme
abc password123 pass123 p@ssword p@ss123 p@ssw0rd P@ssw0rd Admin123
admin1 adminadmin root toor guest 12341234 asdfgh asdfghjkl zxcvbnm
q1w2e3r4 passw0rd 1111 2222 3333 4444 5555 6666 7777 8888 9999
1111111 2222222 7654321 11111111 22222222 33333333 55555555 99999999
""".split()

_CHARSETS = {
    "digits":      string.digits,
    "lower":       string.ascii_lowercase,
    "upper":       string.ascii_uppercase,
    "alpha":       string.ascii_letters,
    "alnum":       string.ascii_letters + string.digits,
    "alnum+syms":  string.ascii_letters + string.digits + "!@#$%^&*_-.",
    "symbols":     string.printable.strip(),
}

# Path to the bundled wordlist shipped alongside this module
_BUNDLED_WORDLIST = Path(__file__).parent / "wordlist.txt"


def _bundled_wordlist_size() -> int:
    """Return line count of the bundled wordlist (0 if missing)."""
    try:
        return sum(1 for _ in _BUNDLED_WORDLIST.open("rb"))
    except Exception:
        return 0


def _try_password(raw: bytes, parsed: tuple, password: str) -> bool:
    """Return True if password decrypts the ciphertext successfully."""
    try:
        algo, kdf_n, kdf_r, kdf_p, off = parsed
        _, key_len, nonce_len = ALGOS[algo]
        salt  = raw[off: off + _SALT_LEN]; off += _SALT_LEN
        nonce = raw[off: off + nonce_len]; off += nonce_len
        ct    = raw[off:]
        key   = _derive_key(password, salt, key_len, n=kdf_n, r=kdf_r, p=kdf_p)
        _decrypt_algo(algo, key, nonce, ct)
        return True
    except Exception:
        return False


def crack_file(
    src: Path | str,
    wordlist_file: Path | str | None = None,
    use_bundled_wordlist: bool = True,
    extra_passwords: list[str] | None = None,
    # brute-force options
    bf_mode: str = "systematic",   # "systematic" | "random" | "both" | "none"
    charset: str = "alnum",
    min_len: int = 1,
    max_len: int = 4,
    max_random: int = 50_000,
    # callbacks
    progress_cb: Callable[[int, str, float, str], None] | None = None,
    stop_event: threading.Event | None = None,
) -> dict[str, Any]:
    """
    Crack a .scenc file by trying passwords in order:
      1. Built-in top-300 common passwords (instant)
      2. extra_passwords supplied by caller
      3. Bundled wordlist.txt  (~393k real passwords, auto-loaded)
      4. User-supplied wordlist_file
      5. Systematic brute-force (itertools.product — exhaustive, guaranteed)
      6. Random brute-force    (random strings, catches longer passwords)

    progress_cb(attempt_count, current_password, speed_per_sec, phase_name)
    Returns {ok, password, algo, attempts, elapsed, phase, error}
    """
    import itertools

    src = Path(src)
    if not src.is_file():
        return {"ok": False, "password": None, "algo": "?",
                "attempts": 0, "elapsed": 0, "phase": "", "error": "File not found"}

    raw = src.read_bytes()
    parsed = _parse_header(raw)
    if parsed is None:
        return {"ok": False, "password": None, "algo": "?",
                "attempts": 0, "elapsed": 0, "phase": "",
                "error": "Unrecognized file format — only .scenc files supported"}

    algo     = parsed[0]
    attempts = 0
    t0       = time.time()
    _stop    = stop_event or threading.Event()
    _phase   = ["init"]

    def _try(pw: str) -> bool:
        nonlocal attempts
        attempts += 1
        result = _try_password(raw, parsed, pw)
        if progress_cb and attempts % 3 == 0:
            elapsed = time.time() - t0
            speed   = attempts / elapsed if elapsed > 0 else 0
            progress_cb(attempts, pw, speed, _phase[0])
        return result

    def _done(pw: str) -> dict[str, Any]:
        return {"ok": True, "password": pw, "algo": algo,
                "attempts": attempts, "elapsed": time.time() - t0,
                "phase": _phase[0], "error": ""}

    def _fail() -> dict[str, Any]:
        return {"ok": False, "password": None, "algo": algo,
                "attempts": attempts, "elapsed": time.time() - t0,
                "phase": _phase[0], "error": "Password not found"}

    def _run_list(label: str, iterable) -> dict | None:
        """Iterate over (password,) items; return result dict or None."""
        _phase[0] = label
        for pw in iterable:
            if _stop.is_set():
                return _fail()
            pw = pw.rstrip("\n\r") if isinstance(pw, str) else pw
            if pw and _try(pw):
                return _done(pw)
        return None

    # ── Phase 1: embedded top-300 ────────────────────────────────────────────
    r = _run_list("common", _COMMON_PASSWORDS)
    if r:
        return r

    # ── Phase 2: caller extras ────────────────────────────────────────────────
    if extra_passwords:
        r = _run_list("extras", extra_passwords)
        if r:
            return r

    # ── Phase 3: bundled wordlist ────────────────────────────────────────────
    if use_bundled_wordlist and _BUNDLED_WORDLIST.is_file():
        _phase[0] = "wordlist (bundled)"
        try:
            with _BUNDLED_WORDLIST.open("r", encoding="utf-8", errors="ignore") as wf:
                for line in wf:
                    if _stop.is_set():
                        return _fail()
                    pw = line.rstrip("\n\r")
                    if pw and _try(pw):
                        return _done(pw)
        except Exception:
            pass

    # ── Phase 4: user wordlist ────────────────────────────────────────────────
    if wordlist_file:
        _phase[0] = "wordlist (user)"
        try:
            with open(wordlist_file, "r", encoding="utf-8", errors="ignore") as wf:
                for line in wf:
                    if _stop.is_set():
                        return _fail()
                    pw = line.rstrip("\n\r")
                    if pw and _try(pw):
                        return _done(pw)
        except Exception:
            pass

    # ── Phase 5: systematic brute-force (exhaustive) ─────────────────────────
    chars = _CHARSETS.get(charset, _CHARSETS["alnum"])

    if bf_mode in ("systematic", "both"):
        _phase[0] = "brute-force (systematic)"
        for length in range(min_len, max_len + 1):
            if _stop.is_set():
                return _fail()
            for combo in itertools.product(chars, repeat=length):
                if _stop.is_set():
                    return _fail()
                pw = "".join(combo)
                if _try(pw):
                    return _done(pw)

    # ── Phase 6: random brute-force ───────────────────────────────────────────
    if bf_mode in ("random", "both"):
        _phase[0] = "brute-force (random)"
        rand_done = 0
        length    = min_len
        while rand_done < max_random and not _stop.is_set():
            pw = "".join(random.choices(chars, k=length))
            if _try(pw):
                return _done(pw)
            rand_done += 1
            # slowly increase length to cover more space
            if rand_done % max(1, max_random // (max_len - min_len + 1)) == 0:
                length = min(length + 1, max_len)

    return _fail()


# ── Availability check ────────────────────────────────────────────────────────

def crypto_available() -> bool:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        return True
    except ImportError:
        return False


def available_algos() -> list[str]:
    """Return list of algorithm names that can actually be used."""
    available = []
    for name in ALGOS:
        try:
            if name in ("AES-256-GCM", "AES-128-GCM"):
                from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            elif name == "ChaCha20-Poly1305":
                from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
            elif name == "AES-256-CBC":
                from cryptography.hazmat.primitives.ciphers import Cipher
            elif name == "Fernet":
                from cryptography.fernet import Fernet
            available.append(name)
        except ImportError:
            pass
    return available

"""Hash cracker — MD5, SHA1, SHA256, SHA512, bcrypt (optional)."""

import hashlib
import itertools
import random
import time
from pathlib import Path

from . import fileencrypt as _enc_mod

_COMMON_PASSWORDS = _enc_mod._COMMON_PASSWORDS
_CHARSETS         = _enc_mod._CHARSETS
_BUNDLED_WORDLIST = _enc_mod._BUNDLED_WORDLIST

SUPPORTED = ["md5", "sha1", "sha256", "sha512", "bcrypt"]


def detect_algo(hash_str: str) -> str | None:
    """Guess algorithm from hash format/length."""
    h = hash_str.strip()
    if h.startswith(("$2a$", "$2b$", "$2y$")):
        return "bcrypt"
    lengths = {32: "md5", 40: "sha1", 64: "sha256", 128: "sha512"}
    try:
        int(h, 16)
        return lengths.get(len(h))
    except ValueError:
        return None


def _compute(password: str, algo: str) -> str:
    b = password.encode("utf-8", errors="replace")
    if algo == "md5":    return hashlib.md5(b).hexdigest()
    if algo == "sha1":   return hashlib.sha1(b).hexdigest()
    if algo == "sha256": return hashlib.sha256(b).hexdigest()
    if algo == "sha512": return hashlib.sha512(b).hexdigest()
    return ""


def _check_bcrypt(password: str, target: str) -> bool:
    try:
        import bcrypt
        return bcrypt.checkpw(
            password.encode("utf-8", errors="replace"),
            target.encode("ascii"),
        )
    except Exception:
        return False


def crack_hash(
    target_hash: str,
    algo: str | None = None,
    wordlist_file=None,
    use_bundled_wordlist: bool = True,
    extra_passwords=None,
    bf_mode: str = "systematic",
    charset: str = "alnum",
    min_len: int = 1,
    max_len: int = 6,
    max_random: int = 200_000,
    progress_cb=None,
    stop_event=None,
) -> dict:
    """Crack a hash string. progress_cb(attempts, current_pw, speed, phase)."""
    target = target_hash.strip()
    if algo is None:
        algo = detect_algo(target)
    if algo is None:
        return {
            "ok": False, "password": None, "algo": "unknown",
            "attempts": 0, "elapsed": 0.0,
            "error": "Cannot detect hash type. Check length or provide algo explicitly.",
        }

    is_bcrypt = (algo == "bcrypt")
    target_cmp = target.lower()
    t0 = time.time()
    attempts = [0]
    _phase = ["common passwords"]
    # bcrypt ~100ms/check → report every attempt; fast hashes → every 1000
    _report_every = 1 if is_bcrypt else 1000

    class _NullEvent:
        def is_set(self): return False

    _stop = stop_event or _NullEvent()
    chars = _CHARSETS.get(charset, _CHARSETS["alnum"])

    def _match(pw: str) -> bool:
        if is_bcrypt:
            return _check_bcrypt(pw, target)
        return _compute(pw, algo) == target_cmp

    def _try(pw: str) -> bool:
        attempts[0] += 1
        if progress_cb and attempts[0] % _report_every == 0:
            elapsed = time.time() - t0
            progress_cb(attempts[0], pw, attempts[0] / max(elapsed, 0.001), _phase[0])
        return _match(pw)

    def _done(pw: str) -> dict:
        return {
            "ok": True, "password": pw, "algo": algo,
            "attempts": attempts[0], "elapsed": time.time() - t0, "error": None,
        }

    def _fail() -> dict:
        return {
            "ok": False, "password": None, "algo": algo,
            "attempts": attempts[0], "elapsed": time.time() - t0,
            "error": "Password not found",
        }

    # Phase 1 — common passwords
    for pw in _COMMON_PASSWORDS:
        if _stop.is_set(): return _fail()
        if _try(pw): return _done(pw)

    # Phase 2 — caller extras
    if extra_passwords:
        _phase[0] = "extra passwords"
        for pw in extra_passwords:
            if _stop.is_set(): return _fail()
            if _try(pw): return _done(pw)

    # Phase 3 — bundled wordlist
    if use_bundled_wordlist and _BUNDLED_WORDLIST.is_file():
        _phase[0] = "bundled wordlist"
        with _BUNDLED_WORDLIST.open("r", encoding="utf-8", errors="ignore") as wf:
            for line in wf:
                if _stop.is_set(): return _fail()
                pw = line.rstrip("\n\r")
                if pw and _try(pw): return _done(pw)

    # Phase 4 — user wordlist
    if wordlist_file and Path(wordlist_file).is_file():
        _phase[0] = "user wordlist"
        with open(wordlist_file, "r", encoding="utf-8", errors="ignore") as wf:
            for line in wf:
                if _stop.is_set(): return _fail()
                pw = line.rstrip("\n\r")
                if pw and _try(pw): return _done(pw)

    if is_bcrypt:
        return _fail()  # brute-forcing bcrypt is impractical

    # Phase 5 — systematic brute-force
    if bf_mode in ("systematic", "both"):
        _phase[0] = "brute-force (systematic)"
        for length in range(min_len, max_len + 1):
            for combo in itertools.product(chars, repeat=length):
                if _stop.is_set(): return _fail()
                pw = "".join(combo)
                if _try(pw): return _done(pw)

    # Phase 6 — random brute-force
    if bf_mode in ("random", "both"):
        _phase[0] = "brute-force (random)"
        rand_done = 0
        length = min_len
        step = max(1, max_random // max(max_len - min_len + 1, 1))
        while rand_done < max_random and not _stop.is_set():
            pw = "".join(random.choices(chars, k=length))
            if _try(pw): return _done(pw)
            rand_done += 1
            if rand_done % step == 0:
                length = min(length + 1, max_len)

    return _fail()

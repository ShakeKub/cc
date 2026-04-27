"""PDF password cracker using pypdf (or PyPDF2 fallback)."""

import itertools
import random
import time
from pathlib import Path

from . import fileencrypt as _enc_mod

_COMMON_PASSWORDS = _enc_mod._COMMON_PASSWORDS
_CHARSETS         = _enc_mod._CHARSETS
_BUNDLED_WORDLIST = _enc_mod._BUNDLED_WORDLIST


def _get_reader(path: Path):
    """Return an open PdfReader (pypdf preferred, PyPDF2 fallback)."""
    try:
        import pypdf
        return pypdf.PdfReader(str(path))
    except ImportError:
        pass
    try:
        import PyPDF2
        return PyPDF2.PdfReader(str(path))
    except ImportError:
        return None


def backend_available() -> bool:
    try:
        import pypdf  # noqa: F401
        return True
    except ImportError:
        pass
    try:
        import PyPDF2  # noqa: F401
        return True
    except ImportError:
        return False


def is_encrypted(path: Path) -> bool:
    r = _get_reader(path)
    if r is None:
        return False
    return bool(r.is_encrypted)


def _test_pdf(path: Path, password: str) -> bool:
    try:
        r = _get_reader(path)
        if r is None:
            return False
        if not r.is_encrypted:
            return True
        result = r.decrypt(password)
        return result != 0
    except Exception:
        return False


def crack_pdf(
    src,
    wordlist_file=None,
    use_bundled_wordlist: bool = True,
    extra_passwords=None,
    bf_mode: str = "systematic",
    charset: str = "alnum",
    min_len: int = 1,
    max_len: int = 4,
    max_random: int = 50_000,
    progress_cb=None,
    stop_event=None,
) -> dict:
    """Crack a password-protected PDF. progress_cb(attempts, pw, speed, phase)."""
    if not backend_available():
        return {
            "ok": False, "password": None,
            "attempts": 0, "elapsed": 0.0,
            "error": "No PDF library found. Run: pip install pypdf",
        }

    path = Path(src)
    t0 = time.time()
    attempts = [0]
    _phase = ["common passwords"]

    class _NullEvent:
        def is_set(self): return False

    _stop = stop_event or _NullEvent()
    chars = _CHARSETS.get(charset, _CHARSETS["alnum"])

    def _try(pw: str) -> bool:
        attempts[0] += 1
        if progress_cb:
            elapsed = time.time() - t0
            progress_cb(attempts[0], pw, attempts[0] / max(elapsed, 0.001), _phase[0])
        return _test_pdf(path, pw)

    def _done(pw: str) -> dict:
        return {
            "ok": True, "password": pw,
            "attempts": attempts[0], "elapsed": time.time() - t0, "error": None,
        }

    def _fail() -> dict:
        return {
            "ok": False, "password": None,
            "attempts": attempts[0], "elapsed": time.time() - t0,
            "error": "Password not found",
        }

    # Phase 1 — common passwords
    for pw in _COMMON_PASSWORDS:
        if _stop.is_set(): return _fail()
        if _try(pw): return _done(pw)

    # Phase 2 — extras
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

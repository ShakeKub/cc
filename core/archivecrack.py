"""Archive password cracker — supports .zip, .7z and .rar archives."""

import itertools
import random
import shutil
import subprocess
import time
import zipfile
from pathlib import Path

from . import fileencrypt as _enc_mod

_COMMON_PASSWORDS = _enc_mod._COMMON_PASSWORDS
_CHARSETS         = _enc_mod._CHARSETS
_BUNDLED_WORDLIST = _enc_mod._BUNDLED_WORDLIST


# ── tool detection ─────────────────────────────────────────────────────────────

def _which(*names: str) -> str | None:
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def check_tools() -> dict:
    """Report available backends for each format."""
    tools: dict = {}

    tools["7z_binary"] = _which("7z", "7zz", "7za")
    tools["unrar_binary"] = _which("unrar", "rar")

    try:
        import py7zr
        tools["py7zr"] = py7zr.__version__
    except ImportError:
        tools["py7zr"] = None

    try:
        import rarfile
        tools["rarfile"] = rarfile.__version__
    except ImportError:
        tools["rarfile"] = None

    return tools


# ── per-format password testers ────────────────────────────────────────────────

def _test_zip(path: Path, password: str) -> bool:
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            if not names:
                return True
            # test() raises RuntimeError on wrong password / bad CRC
            zf.read(names[0], pwd=password.encode("utf-8", errors="replace"))
        return True
    except RuntimeError:
        return False
    except Exception:
        return False


def _test_7z_binary(binary: str, path: Path, password: str) -> bool:
    try:
        r = subprocess.run(
            [binary, "t", f"-p{password}", "-bso0", "-bse0", str(path)],
            capture_output=True, timeout=20,
        )
        return r.returncode == 0
    except Exception:
        return False


def _test_7z_py(path: Path, password: str) -> bool:
    try:
        import py7zr
        with py7zr.SevenZipFile(str(path), mode="r", password=password) as z:
            names = z.getnames()
            if names:
                z.read(names[:1])
        return True
    except Exception:
        return False


def _test_rar_binary(binary: str, path: Path, password: str) -> bool:
    # unrar: "unrar t -p<pw> archive"
    # rar:   "rar t -p<pw> archive"
    try:
        r = subprocess.run(
            [binary, "t", f"-p{password}", str(path)],
            capture_output=True, timeout=20,
        )
        return r.returncode == 0
    except Exception:
        return False


def _test_rar_via_7z(binary: str, path: Path, password: str) -> bool:
    return _test_7z_binary(binary, path, password)


def _test_rar_py(path: Path, password: str) -> bool:
    try:
        import rarfile
        rf = rarfile.RarFile(str(path))
        rf.setpassword(password)
        names = rf.namelist()
        if names:
            rf.read(names[0])
        return True
    except Exception:
        return False


# ── tester factory ─────────────────────────────────────────────────────────────

class UnsupportedFormat(Exception):
    pass


def _make_tester(path: Path):
    """Return (tester_fn, description) for *path*, or raise UnsupportedFormat."""
    suffix = path.suffix.lower()

    if suffix == ".zip":
        return _test_zip, "zipfile (built-in)"

    elif suffix == ".7z":
        binary = _which("7z", "7zz", "7za")
        if binary:
            name = Path(binary).name
            return lambda p, pw: _test_7z_binary(binary, p, pw), f"7z binary ({name})"
        try:
            import py7zr  # noqa: F401
            return _test_7z_py, "py7zr"
        except ImportError:
            pass
        raise UnsupportedFormat(
            "No .7z backend found. Run: brew install sevenzip  OR  pip install py7zr"
        )

    elif suffix == ".rar":
        unrar = _which("unrar", "rar")
        if unrar:
            name = Path(unrar).name
            return lambda p, pw: _test_rar_binary(unrar, p, pw), f"unrar binary ({name})"
        # 7z can open RAR too
        sevenz = _which("7z", "7zz", "7za")
        if sevenz:
            name = Path(sevenz).name
            return lambda p, pw: _test_rar_via_7z(sevenz, p, pw), f"7z binary ({name})"
        try:
            import rarfile  # noqa: F401
            return _test_rar_py, "rarfile"
        except ImportError:
            pass
        raise UnsupportedFormat(
            "No .rar backend found. Run: brew install rar  OR  pip install rarfile"
        )

    else:
        raise UnsupportedFormat(f"Unsupported archive format: '{suffix}'. Supported: .zip .7z .rar")


# ── main API ───────────────────────────────────────────────────────────────────

def crack_archive(
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
    """Try to crack the password of a .zip/.7z/.rar archive.

    progress_cb(attempts, current_pw, speed_per_sec, phase_name)
    Returns dict: ok, password, archive_type, backend, attempts, elapsed, error
    """
    path = Path(src)
    t0 = time.time()
    attempts = [0]
    _phase = ["common passwords"]

    class _NullEvent:
        def is_set(self): return False

    _stop = stop_event or _NullEvent()
    archive_type = path.suffix.lstrip(".").lower()

    try:
        tester, backend = _make_tester(path)
    except UnsupportedFormat as exc:
        return {
            "ok": False, "password": None,
            "archive_type": archive_type, "backend": None,
            "attempts": 0, "elapsed": 0.0, "error": str(exc),
        }

    chars = _CHARSETS.get(charset, _CHARSETS["alnum"])

    def _try(pw: str) -> bool:
        attempts[0] += 1
        if progress_cb:
            elapsed = time.time() - t0
            speed = attempts[0] / max(elapsed, 0.001)
            progress_cb(attempts[0], pw, speed, _phase[0])
        return tester(path, pw)

    def _done(pw: str) -> dict:
        return {
            "ok": True, "password": pw,
            "archive_type": archive_type, "backend": backend,
            "attempts": attempts[0], "elapsed": time.time() - t0, "error": None,
        }

    def _fail() -> dict:
        return {
            "ok": False, "password": None,
            "archive_type": archive_type, "backend": backend,
            "attempts": attempts[0], "elapsed": time.time() - t0,
            "error": "Password not found",
        }

    # Phase 1 — common passwords
    for pw in _COMMON_PASSWORDS:
        if _stop.is_set(): return _fail()
        if _try(pw): return _done(pw)

    # Phase 2 — caller-supplied extras
    if extra_passwords:
        _phase[0] = "extra passwords"
        for pw in extra_passwords:
            if _stop.is_set(): return _fail()
            if _try(pw): return _done(pw)

    # Phase 3 — bundled wordlist (~393k passwords)
    if use_bundled_wordlist and _BUNDLED_WORDLIST.is_file():
        _phase[0] = "bundled wordlist"
        with _BUNDLED_WORDLIST.open("r", encoding="utf-8", errors="ignore") as wf:
            for line in wf:
                if _stop.is_set(): return _fail()
                pw = line.rstrip("\n\r")
                if pw and _try(pw): return _done(pw)

    # Phase 4 — user-supplied wordlist file
    if wordlist_file and Path(wordlist_file).is_file():
        _phase[0] = "user wordlist"
        with open(wordlist_file, "r", encoding="utf-8", errors="ignore") as wf:
            for line in wf:
                if _stop.is_set(): return _fail()
                pw = line.rstrip("\n\r")
                if pw and _try(pw): return _done(pw)

    # Phase 5 — systematic brute-force (exhaustive up to max_len)
    if bf_mode in ("systematic", "both"):
        _phase[0] = "brute-force (systematic)"
        for length in range(min_len, max_len + 1):
            for combo in itertools.product(chars, repeat=length):
                if _stop.is_set(): return _fail()
                if _try("".join(combo)): return _done("".join(combo))

    # Phase 6 — random brute-force (covers longer passwords)
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

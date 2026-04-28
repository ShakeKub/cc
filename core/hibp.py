"""HaveIBeenPwned — check passwords (k-anonymity, free) and emails (API key)."""

import hashlib
import urllib.error
import urllib.parse
import urllib.request


_PW_URL    = "https://api.pwnedpasswords.com/range/{prefix}"
_EMAIL_URL = "https://haveibeenpwned.com/api/v3/breachedaccount/{email}"
_PASTE_URL = "https://haveibeenpwned.com/api/v3/pasteaccount/{email}"
_UA        = "ByteSweep/1.0"


def _get(url: str, headers: dict | None = None, timeout: int = 10) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.reason


def check_password(password: str) -> dict:
    """Check if *password* has been seen in breaches using k-anonymity (SHA1 range API).

    Only the first 5 characters of the SHA1 hash are sent to the API.
    Returns: {pwned: bool, count: int, hash: str, error: str|None}
    """
    sha1 = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix, suffix = sha1[:5], sha1[5:]

    status, body = _get(_PW_URL.format(prefix=prefix))
    if status != 200:
        return {"pwned": False, "count": 0, "hash": sha1,
                "error": f"API error {status}: {body[:100]}"}

    for line in body.splitlines():
        parts = line.strip().split(":")
        if len(parts) == 2 and parts[0].upper() == suffix:
            count = int(parts[1])
            return {"pwned": True, "count": count, "hash": sha1, "error": None}

    return {"pwned": False, "count": 0, "hash": sha1, "error": None}


def check_email_breaches(email: str, api_key: str, truncate: bool = False) -> list[dict] | dict:
    """Check email against HIBP breach database. Requires a paid API key.

    Returns list[breach] on success and {"error": ...} on error.
    """
    import json
    url = _EMAIL_URL.format(email=urllib.parse.quote(email))
    if truncate:
        url += "?truncateResponse=true"

    headers = {
        "hibp-api-key": api_key,
        "User-Agent": _UA,
    }
    status, body = _get(url, headers=headers)

    if status == 200:
        try:
            breaches = json.loads(body)
        except Exception:
            breaches = []
        return breaches if isinstance(breaches, list) else []
    if status == 404:
        return []
    if status == 401:
        return {"error": "Invalid API key. Get one at haveibeenpwned.com/API/Key"}
    if status == 429:
        return {"error": "Rate limited - wait a moment and retry."}

    return {"error": f"API error {status}: {body[:100]}"}


def check_email_pastes(email: str, api_key: str) -> dict:
    """Check if email appears in pastes (Pastebin, etc.). Requires API key."""
    import json
    url = _PASTE_URL.format(email=urllib.parse.quote(email))
    headers = {"hibp-api-key": api_key, "User-Agent": _UA}
    status, body = _get(url, headers=headers)

    if status == 200:
        try:
            pastes = json.loads(body)
        except Exception:
            pastes = []
        return {"found": True, "pastes": pastes, "count": len(pastes), "error": None}
    if status == 404:
        return {"found": False, "pastes": [], "count": 0, "error": None}

    return {"found": False, "pastes": [], "count": 0,
            "error": f"API error {status}: {body[:100]}"}


def check_multiple_passwords(passwords: list[str]) -> dict[str, dict]:
    """Batch check a list of passwords. Returns mapping password -> result."""
    return {pw: check_password(pw) for pw in passwords}

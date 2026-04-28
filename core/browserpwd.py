"""Browser saved-password exporter — for migration/backup of YOUR OWN browser data.
Only reads from the current user's profile. Passwords may be encrypted; decryption
requires the same Windows user session (DPAPI) or Firefox master password."""

import json, os, platform, re, sqlite3, base64, shutil, tempfile
from pathlib import Path

def _chrome_profiles() -> list[Path]:
    sys = platform.system()
    if sys == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA","")) / "Google/Chrome/User Data"
    elif sys == "Darwin":
        base = Path.home() / "Library/Application Support/Google/Chrome"
    else:
        base = Path.home() / ".config/google-chrome"
    if not base.is_dir():
        # Try Chromium, Brave, Edge
        for alt in ("Chromium", "BraveSoftware/Brave-Browser", "Microsoft/Edge"):
            if sys == "Windows":
                b2 = Path(os.environ.get("LOCALAPPDATA","")) / alt / "User Data"
            elif sys == "Darwin":
                b2 = Path.home() / "Library/Application Support" / alt
            else:
                b2 = Path.home() / ".config" / alt.lower().replace("/","-")
            if b2.is_dir():
                base = b2; break
    profiles = []
    if not base.is_dir():
        return profiles
    for entry in base.iterdir():
        if entry.is_dir() and (entry.name == "Default" or entry.name.startswith("Profile")):
            ld = entry / "Login Data"
            if ld.is_file():
                profiles.append(ld)
    return profiles

def _decrypt_chrome_win(encrypted: bytes) -> str:
    """Attempt DPAPI decryption of a Chrome password blob (same user only)."""
    if not encrypted:
        return ""
    try:
        import ctypes, ctypes.wintypes
        # v10/v11 prefix: encrypted with AES-256-GCM using a DPAPI-wrapped key
        if encrypted[:3] in (b"v10", b"v11"):
            return "[encrypted - requires Chrome key extraction]"
        # Older DPAPI-only blobs
        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", ctypes.wintypes.DWORD),
                        ("pbData", ctypes.POINTER(ctypes.c_char))]
        n = len(encrypted)
        buf = (ctypes.c_char * n)(*encrypted)
        blob_in  = DATA_BLOB(n, buf)
        blob_out = DATA_BLOB()
        ok = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None, 0,
            ctypes.byref(blob_out))
        if ok:
            result = ctypes.string_at(blob_out.pbData, blob_out.cbData)
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
            return result.decode("utf-8", errors="replace")
    except Exception:
        pass
    return "[encrypted]"

def read_chrome_logins(profile_path: str | None = None) -> list[dict]:
    """Read Chrome/Chromium saved logins. Passwords decrypted on Windows (same user)."""
    profiles = [Path(profile_path)] if profile_path else _chrome_profiles()
    results = []
    for ldf in profiles:
        tmp = None
        try:
            # Copy DB so Chrome can have it locked
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
            tmp.close()
            shutil.copy2(ldf, tmp.name)
            con = sqlite3.connect(tmp.name)
            cur = con.execute("SELECT origin_url, username_value, password_value, date_created FROM logins")
            for row in cur.fetchall():
                url, user, enc_pw, date_created = row
                if platform.system() == "Windows" and enc_pw:
                    pw = _decrypt_chrome_win(enc_pw)
                else:
                    pw = "[encrypted - Windows only]" if enc_pw else ""
                results.append({
                    "browser": "Chrome/Chromium",
                    "profile": ldf.parent.name,
                    "url": url, "username": user, "password": pw,
                })
            con.close()
        except Exception as e:
            results.append({"browser": "Chrome/Chromium", "error": str(e)})
        finally:
            if tmp:
                try: os.unlink(tmp.name)
                except Exception: pass
    return results

def _firefox_profiles() -> list[Path]:
    sys = platform.system()
    if sys == "Windows":
        base = Path(os.environ.get("APPDATA","")) / "Mozilla/Firefox/Profiles"
    elif sys == "Darwin":
        base = Path.home() / "Library/Application Support/Firefox/Profiles"
    else:
        base = Path.home() / ".mozilla/firefox"
    if not base.is_dir():
        return []
    return [p for p in base.iterdir() if p.is_dir() and (p / "logins.json").is_file()]

def read_firefox_logins(profile_path: str | None = None) -> list[dict]:
    """Read Firefox logins.json — passwords remain base64-encoded (NSS encrypted)."""
    profiles = [Path(profile_path)] if profile_path else _firefox_profiles()
    results = []
    for prof in profiles:
        lj = prof / "logins.json"
        try:
            data = json.loads(lj.read_text(encoding="utf-8"))
            for login in data.get("logins", []):
                results.append({
                    "browser": "Firefox",
                    "profile": prof.name,
                    "url":      login.get("hostname", ""),
                    "username": base64.b64decode(login.get("encryptedUsername","")).decode("latin-1") \
                                if login.get("encryptedUsername","").startswith("M") \
                                else "[NSS encrypted]",
                    "password": "[NSS encrypted — use Firefox Export to CSV for plaintext]",
                    "times_used": login.get("timesUsed", 0),
                })
        except Exception as e:
            results.append({"browser": "Firefox", "profile": str(prof), "error": str(e)})
    return results

def export_all(output_path: str | None = None) -> dict:
    chrome = read_chrome_logins()
    firefox = read_firefox_logins()
    all_logins = chrome + firefox
    if output_path:
        rows = ["browser,profile,url,username,password"]
        for e in all_logins:
            if "error" not in e:
                def q(s): return '"' + str(s).replace('"','""') + '"'
                rows.append(",".join(q(e.get(k,"")) for k in ("browser","profile","url","username","password")))
        Path(output_path).write_text("\n".join(rows), encoding="utf-8")
    return {"chrome": len(chrome), "firefox": len(firefox), "total": len(all_logins),
            "logins": all_logins}

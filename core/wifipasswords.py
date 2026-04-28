"""WiFi password viewer — cross-platform."""
import os, platform, re, subprocess
from typing import NamedTuple

class WifiProfile(NamedTuple):
    ssid: str
    auth: str
    password: str | None

def list_profiles() -> list[WifiProfile]:
    sys = platform.system()
    if sys == "Windows":   return _win()
    if sys == "Darwin":    return _mac()
    return _linux()

def _win() -> list[WifiProfile]:
    out = []
    rc, txt, _ = _run(["netsh", "wlan", "show", "profiles"])
    if rc != 0: return []
    for line in txt.splitlines():
        m = re.search(r":\s*(.+)$", line)
        if m and ("Profile" in line or "Profil" in line or "All User" in line or "Uživatel" in line):
            ssid = m.group(1).strip()
            if not ssid: continue
            rc2, detail, _ = _run(["netsh", "wlan", "show", "profile", f"name={ssid}", "key=clear"])
            auth = pw = None
            for l in detail.splitlines():
                if "Authentication" in l or "Ověření" in l:
                    auth = l.split(":", 1)[-1].strip()
                if "Key Content" in l or "Obsah klíče" in l:
                    pw = l.split(":", 1)[-1].strip()
            out.append(WifiProfile(ssid, auth or "", pw))
    return out

def _mac() -> list[WifiProfile]:
    out = []
    rc, txt, _ = _run(["/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport", "-s"])
    if rc != 0:
        rc, txt, _ = _run(["networksetup", "-listallhardwareports"])
    # macOS requires keychain access per-SSID
    rc, txt, _ = _run(["networksetup", "-listpreferredwirelessnetworks", "en0"])
    for line in txt.splitlines()[1:]:
        ssid = line.strip()
        if not ssid: continue
        rc2, pw, _ = _run(["security", "find-generic-password", "-D",
                            "AirPort network password", "-a", ssid, "-w"])
        out.append(WifiProfile(ssid, "", pw.strip() if rc2 == 0 else None))
    return out

def _linux() -> list[WifiProfile]:
    out = []
    # NetworkManager profiles
    nm_dir = "/etc/NetworkManager/system-connections"
    if os.path.isdir(nm_dir):
        for fn in os.listdir(nm_dir):
            fp = os.path.join(nm_dir, fn)
            try:
                txt = open(fp, errors="replace").read()
                ssid = auth = pw = None
                for line in txt.splitlines():
                    if line.startswith("ssid="):   ssid = line.split("=",1)[1]
                    if line.startswith("key-mgmt="): auth = line.split("=",1)[1]
                    if line.startswith("psk="):    pw = line.split("=",1)[1]
                if ssid:
                    out.append(WifiProfile(ssid, auth or "", pw))
            except Exception:
                pass
    return out

def _run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return r.returncode, r.stdout, r.stderr
    except Exception as e:
        return -1, "", str(e)

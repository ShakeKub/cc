"""System proxy manager — read/set/clear proxy settings."""
import os, platform, subprocess

def _run(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except Exception as e:
        return -1, "", str(e)

def get_proxy() -> dict:
    sys = platform.system()
    if sys == "Windows":   return _get_win()
    if sys == "Darwin":    return _get_mac()
    return _get_linux()

def set_proxy(host: str, port: int, bypass: str = "") -> dict:
    sys = platform.system()
    if sys == "Windows":   return _set_win(host, port, bypass)
    if sys == "Darwin":    return _set_mac(host, port)
    return _set_linux(host, port)

def clear_proxy() -> dict:
    sys = platform.system()
    if sys == "Windows":   return _clear_win()
    if sys == "Darwin":    return _clear_mac()
    return _clear_linux()

# ── Windows ───────────────────────────────────────────────────
_WIN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"

def _get_win() -> dict:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN_KEY) as k:
            def _v(name):
                try: return winreg.QueryValueEx(k, name)[0]
                except: return None
            return {"enabled": bool(_v("ProxyEnable")),
                    "server":  _v("ProxyServer") or "",
                    "bypass":  _v("ProxyOverride") or "",
                    "auto_url":_v("AutoConfigURL") or ""}
    except Exception as e:
        return {"enabled": False, "error": str(e)}

def _set_win(host, port, bypass) -> dict:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, "ProxyEnable", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(k, "ProxyServer",  0, winreg.REG_SZ, f"{host}:{port}")
            if bypass:
                winreg.SetValueEx(k, "ProxyOverride", 0, winreg.REG_SZ, bypass)
        _run(["netsh", "winhttp", "set", "proxy", f"{host}:{port}"])
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def _clear_win() -> dict:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, "ProxyEnable", 0, winreg.REG_DWORD, 0)
        _run(["netsh", "winhttp", "reset", "proxy"])
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ── macOS ─────────────────────────────────────────────────────
def _get_mac() -> dict:
    rc, out, _ = _run(["networksetup", "-getwebproxy", "Wi-Fi"])
    enabled = "Yes" in out
    server = port = ""
    for line in out.splitlines():
        if "Server:" in line: server = line.split(":",1)[1].strip()
        if "Port:"   in line: port   = line.split(":",1)[1].strip()
    return {"enabled": enabled, "server": f"{server}:{port}" if server else "", "bypass": ""}

def _set_mac(host, port) -> dict:
    for iface in ("Wi-Fi", "Ethernet"):
        _run(["networksetup", "-setwebproxy",   iface, host, str(port)])
        _run(["networksetup", "-setsecurewebproxy", iface, host, str(port)])
    return {"ok": True}

def _clear_mac() -> dict:
    for iface in ("Wi-Fi", "Ethernet"):
        _run(["networksetup", "-setwebproxystate",       iface, "off"])
        _run(["networksetup", "-setsecurewebproxystate", iface, "off"])
    return {"ok": True}

# ── Linux ─────────────────────────────────────────────────────
def _get_linux() -> dict:
    p = os.environ.get("https_proxy") or os.environ.get("http_proxy") or ""
    return {"enabled": bool(p), "server": p, "bypass": os.environ.get("no_proxy",""),
            "note": "Linux: shows current process env — system-wide proxy is distro-specific"}

def _set_linux(host, port) -> dict:
    val = f"http://{host}:{port}"
    conf = "/etc/environment"
    try:
        lines = open(conf).readlines() if os.path.isfile(conf) else []
        filtered = [l for l in lines if not l.startswith(("http_proxy","https_proxy","HTTP_PROXY","HTTPS_PROXY"))]
        filtered += [f"http_proxy={val}\n", f"https_proxy={val}\n",
                     f"HTTP_PROXY={val}\n",  f"HTTPS_PROXY={val}\n"]
        open(conf, "w").writelines(filtered)
        return {"ok": True}
    except PermissionError:
        return {"ok": False, "error": "Permission denied — run as root"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def _clear_linux() -> dict:
    conf = "/etc/environment"
    try:
        if os.path.isfile(conf):
            lines = [l for l in open(conf) if not l.startswith(
                ("http_proxy","https_proxy","HTTP_PROXY","HTTPS_PROXY"))]
            open(conf, "w").writelines(lines)
        return {"ok": True}
    except PermissionError:
        return {"ok": False, "error": "Permission denied — run as root"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

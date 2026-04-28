"""Windows / OS activation and license info."""
import platform, subprocess, re

def _run(cmd, timeout=20):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           errors="replace")
        return r.returncode, r.stdout + r.stderr, ""
    except Exception as e:
        return -1, "", str(e)

def get_info() -> dict:
    sys = platform.system()
    if sys == "Windows": return _win()
    if sys == "Darwin":  return _mac()
    return _linux()

def _win() -> dict:
    # slmgr /dli — license info
    rc, out, _ = _run(["cscript", "//NoLogo",
                        r"C:\Windows\System32\slmgr.vbs", "/dli"])
    info: dict = {"platform": "Windows", "raw_dli": out}
    for line in out.splitlines():
        if "Name:" in line:         info["product_name"] = line.split(":",1)[1].strip()
        if "Description:" in line:  info["description"]  = line.split(":",1)[1].strip()
        if "License Status:" in line or "Stav licence:" in line:
            info["license_status"] = line.split(":",1)[1].strip()
        if "Partial Product Key:" in line:
            info["partial_key"] = line.split(":",1)[1].strip()

    # slmgr /xpr — expiry
    rc2, out2, _ = _run(["cscript", "//NoLogo",
                          r"C:\Windows\System32\slmgr.vbs", "/xpr"])
    info["expiry_info"] = out2.strip()
    info["activated"]   = "Licensed" in out or "Activated" in out or "Licencováno" in out

    # Also try winver / systeminfo for OS name
    rc3, out3, _ = _run(["systeminfo", "/fo", "list"])
    for line in out3.splitlines():
        if "OS Name:" in line or "Název OS:" in line:
            info["os_name"] = line.split(":",1)[1].strip()
        if "OS Version:" in line or "Verze OS:" in line:
            info["os_version"] = line.split(":",1)[1].strip()
    return info

def _mac() -> dict:
    rc, out, _ = _run(["sw_vers"])
    info = {"platform": "macOS"}
    for line in out.splitlines():
        if "ProductName:" in line:    info["os_name"] = line.split(":",1)[1].strip()
        if "ProductVersion:" in line: info["os_version"] = line.split(":",1)[1].strip()
        if "BuildVersion:" in line:   info["build"] = line.split(":",1)[1].strip()
    info["activated"] = True  # macOS doesn't use activation keys
    info["license_status"] = "macOS does not require activation"
    return info

def _linux() -> dict:
    info = {"platform": "Linux", "os_name": platform.platform(),
            "os_version": platform.release(), "activated": True,
            "license_status": "Linux is free/open-source"}
    try:
        for line in open("/etc/os-release", errors="replace"):
            if line.startswith("PRETTY_NAME="):
                info["os_name"] = line.split("=",1)[1].strip().strip('"')
    except Exception:
        pass
    return info

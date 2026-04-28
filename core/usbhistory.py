"""USB device connection history — cross-platform."""
import os, platform, re, subprocess
from pathlib import Path

def _run(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except Exception as e:
        return -1, "", str(e)

def list_usb_history() -> list[dict]:
    sys = platform.system()
    if sys == "Windows": return _win()
    if sys == "Darwin":  return _mac()
    return _linux()

def _win() -> list[dict]:
    try:
        import winreg
        devices = []
        key_path = r"SYSTEM\CurrentControlSet\Enum\USBSTOR"
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
        except OSError:
            return []
        i = 0
        while True:
            try:
                device_class = winreg.EnumKey(key, i); i += 1
            except OSError:
                break
            try:
                class_key = winreg.OpenKey(key, device_class)
                j = 0
                while True:
                    try:
                        instance = winreg.EnumKey(class_key, j); j += 1
                    except OSError:
                        break
                    try:
                        inst_key = winreg.OpenKey(class_key, instance)
                        def _v(k, name):
                            try: return winreg.QueryValueEx(k, name)[0]
                            except: return ""
                        friendly = _v(inst_key, "FriendlyName")
                        mfg      = _v(inst_key, "Mfg")
                        devices.append({
                            "name":         friendly or device_class,
                            "instance_id":  instance,
                            "manufacturer": mfg,
                            "type":         device_class.split("&")[0] if "&" in device_class else device_class,
                        })
                    except OSError:
                        pass
            except OSError:
                pass
        return devices
    except ImportError:
        return []

def _mac() -> list[dict]:
    rc, out, _ = _run(["system_profiler", "SPUSBDataType"])
    devices, cur = [], {}
    for line in out.splitlines():
        line = line.strip()
        if line.endswith(":") and not any(c in line for c in ("USB", "Hub", "Host")):
            if cur.get("name"): devices.append(cur)
            cur = {"name": line.rstrip(":"), "manufacturer": "", "serial": ""}
        elif "Manufacturer:" in line:
            cur["manufacturer"] = line.split(":",1)[1].strip()
        elif "Serial Number:" in line:
            cur["serial"] = line.split(":",1)[1].strip()
    if cur.get("name"): devices.append(cur)
    return devices

def _linux() -> list[dict]:
    devices = []
    # Try lsusb for current devices
    rc, out, _ = _run(["lsusb"])
    if rc == 0:
        for line in out.splitlines():
            m = re.match(r"Bus \d+ Device \d+: ID [\da-f:]+\s*(.*)", line)
            if m:
                devices.append({"name": m.group(1).strip(), "current": True})
    # Historical from syslog/journal
    rc, hist, _ = _run(["journalctl", "-k", "--no-pager", "-n", "500",
                         "--grep", "usb", "-o", "short"])
    seen = set()
    for line in hist.splitlines():
        m = re.search(r"New USB device found.*?idVendor=[\da-f]+, idProduct=[\da-f]+.*?Manufacturer: (.+)", line)
        if m:
            name = m.group(1)
            if name not in seen:
                seen.add(name)
                devices.append({"name": name, "current": False, "log_line": line[:120]})
    return devices

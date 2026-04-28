"""Service manager — cross-platform list/start/stop/enable/disable."""
import os, platform, re, subprocess

def _run(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except Exception as e:
        return -1, "", str(e)

def list_services(filter_name: str = "") -> list[dict]:
    sys = platform.system()
    if sys == "Windows":   svcs = _list_win()
    elif sys == "Darwin":  svcs = _list_mac()
    else:                  svcs = _list_linux()
    if filter_name:
        fl = filter_name.lower()
        svcs = [s for s in svcs if fl in s["name"].lower() or fl in s.get("display","").lower()]
    return svcs

def _list_win() -> list[dict]:
    rc, out, _ = _run(["sc", "query", "type=", "all", "state=", "all"])
    svcs, cur = [], {}
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("SERVICE_NAME:"):
            if cur: svcs.append(cur)
            cur = {"name": line.split(":",1)[1].strip(), "display": "", "status": "", "start": ""}
        elif "DISPLAY_NAME" in line:
            cur["display"] = line.split(":",1)[1].strip()
        elif "STATE" in line:
            m = re.search(r"\d+\s+(\w+)", line)
            if m: cur["status"] = m.group(1)
        elif "START_TYPE" in line:
            m = re.search(r"\d+\s+(.+)", line)
            if m: cur["start"] = m.group(1).strip()
    if cur: svcs.append(cur)
    return svcs

def _list_linux() -> list[dict]:
    rc, out, _ = _run(["systemctl", "list-units", "--type=service", "--all",
                        "--no-pager", "--plain", "--no-legend"])
    svcs = []
    for line in out.splitlines():
        parts = line.split(None, 4)
        if len(parts) >= 3:
            svcs.append({"name": parts[0], "display": parts[4].strip() if len(parts)>4 else "",
                          "status": parts[2], "start": parts[1]})
    return svcs

def _list_mac() -> list[dict]:
    rc, out, _ = _run(["launchctl", "list"])
    svcs = []
    for line in out.splitlines()[1:]:
        parts = line.split(None, 2)
        if len(parts) == 3:
            svcs.append({"name": parts[2], "display": parts[2],
                          "status": "running" if parts[0] != "-" else "stopped",
                          "pid": parts[0], "start": ""})
    return svcs

def start_service(name: str) -> dict:
    if platform.system() == "Windows":
        rc, o, e = _run(["net", "start", name])
    elif platform.system() == "Darwin":
        rc, o, e = _run(["launchctl", "start", name])
    else:
        rc, o, e = _run(["systemctl", "start", name])
    return {"ok": rc == 0, "output": (o + e).strip()}

def stop_service(name: str) -> dict:
    if platform.system() == "Windows":
        rc, o, e = _run(["net", "stop", name])
    elif platform.system() == "Darwin":
        rc, o, e = _run(["launchctl", "stop", name])
    else:
        rc, o, e = _run(["systemctl", "stop", name])
    return {"ok": rc == 0, "output": (o + e).strip()}

def enable_service(name: str) -> dict:
    if platform.system() == "Windows":
        rc, o, e = _run(["sc", "config", name, "start=", "auto"])
    elif platform.system() == "Darwin":
        rc, o, e = _run(["launchctl", "enable", f"system/{name}"])
    else:
        rc, o, e = _run(["systemctl", "enable", name])
    return {"ok": rc == 0, "output": (o + e).strip()}

def disable_service(name: str) -> dict:
    if platform.system() == "Windows":
        rc, o, e = _run(["sc", "config", name, "start=", "disabled"])
    elif platform.system() == "Darwin":
        rc, o, e = _run(["launchctl", "disable", f"system/{name}"])
    else:
        rc, o, e = _run(["systemctl", "disable", name])
    return {"ok": rc == 0, "output": (o + e).strip()}

def service_info(name: str) -> dict:
    if platform.system() == "Windows":
        rc, o, _ = _run(["sc", "qc", name])
        return {"name": name, "raw": o}
    elif platform.system() == "Darwin":
        rc, o, _ = _run(["launchctl", "print", f"system/{name}"])
        return {"name": name, "raw": o}
    else:
        rc, o, _ = _run(["systemctl", "status", "--no-pager", name])
        return {"name": name, "raw": o}

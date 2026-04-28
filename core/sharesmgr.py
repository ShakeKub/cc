"""Network share manager — list, add, remove shares (cross-platform)."""
import os, platform, re, subprocess

def _run(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except Exception as e:
        return -1, "", str(e)

def list_shares() -> list[dict]:
    sys = platform.system()
    if sys == "Windows":   return _list_win()
    if sys == "Darwin":    return _list_mac()
    return _list_linux()

def _list_win() -> list[dict]:
    rc, out, _ = _run(["net", "share"])
    shares = []
    for line in out.splitlines()[4:]:
        parts = line.split(None, 2)
        if len(parts) >= 2 and parts[0] not in ("Share", "---", ""):
            shares.append({"name": parts[0], "path": parts[1] if len(parts) > 1 else "",
                           "comment": parts[2].strip() if len(parts) > 2 else ""})
    return shares

def _list_mac() -> list[dict]:
    rc, out, _ = _run(["sharing", "-l"])
    shares = []
    current = {}
    for line in out.splitlines():
        if line.startswith("name:"):
            if current: shares.append(current)
            current = {"name": line.split(":",1)[1].strip(), "path": "", "comment": ""}
        elif line.strip().startswith("path:"):
            current["path"] = line.split(":",1)[1].strip()
    if current: shares.append(current)
    return shares

def _list_linux() -> list[dict]:
    shares = []
    smb = "/etc/samba/smb.conf"
    if os.path.isfile(smb):
        name = None
        for line in open(smb, errors="replace"):
            line = line.strip()
            m = re.match(r"^\[(.+)\]$", line)
            if m:
                name = m.group(1)
            elif name and line.startswith("path"):
                path = line.split("=",1)[1].strip()
                shares.append({"name": name, "path": path, "comment": ""})
    return shares

def add_share(name: str, path: str, comment: str = "") -> dict:
    sys = platform.system()
    if sys != "Windows":
        return {"ok": False, "error": "Add share supported on Windows only"}
    cmd = ["net", "share", f"{name}={path}"]
    if comment: cmd += [f"/REMARK:{comment}"]
    rc, out, err = _run(cmd)
    return {"ok": rc == 0, "error": err.strip() or out.strip()}

def remove_share(name: str) -> dict:
    sys = platform.system()
    if sys == "Windows":
        rc, out, err = _run(["net", "share", name, "/delete"])
        return {"ok": rc == 0, "error": err.strip() or out.strip()}
    if sys == "Darwin":
        rc, out, err = _run(["sharing", "-r", name])
        return {"ok": rc == 0, "error": err.strip()}
    return {"ok": False, "error": "Not implemented on Linux"}

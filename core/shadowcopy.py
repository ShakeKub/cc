"""Shadow Copy / VSS manager — Windows only."""
import platform, re, subprocess

def _run(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except Exception as e:
        return -1, "", str(e)

def _is_windows():
    return platform.system() == "Windows"

def list_shadows() -> list[dict]:
    if not _is_windows():
        return []
    rc, out, _ = _run(["vssadmin", "list", "shadows"])
    shadows, cur = [], {}
    for line in out.splitlines():
        line = line.strip()
        if "Shadow Copy ID:" in line:
            if cur: shadows.append(cur)
            m = re.search(r"\{[^}]+\}", line)
            cur = {"id": m.group(0) if m else "", "volume": "", "path": "", "created": "", "provider": ""}
        elif "Original Volume:" in line:
            cur["volume"] = line.split(":",1)[1].strip()
        elif "Shadow Copy Volume:" in line:
            cur["path"] = line.split(":",1)[1].strip()
        elif "Creation Time:" in line:
            cur["created"] = line.split(":",1)[1].strip()
        elif "Provider:" in line:
            cur["provider"] = line.split(":",1)[1].strip()
    if cur: shadows.append(cur)
    return shadows

def create_shadow(volume: str = "C:") -> dict:
    if not _is_windows():
        return {"ok": False, "error": "Windows only"}
    rc, out, err = _run(["vssadmin", "create", "shadow", f"/for={volume}"], timeout=60)
    ok = rc == 0
    shadow_id = ""
    for line in out.splitlines():
        if "Shadow Copy ID:" in line:
            m = re.search(r"\{[^}]+\}", line)
            if m: shadow_id = m.group(0)
    return {"ok": ok, "shadow_id": shadow_id, "output": (out + err).strip()}

def delete_shadow(shadow_id: str) -> dict:
    if not _is_windows():
        return {"ok": False, "error": "Windows only"}
    rc, out, err = _run(["vssadmin", "delete", "shadows", f"/shadow={shadow_id}", "/quiet"])
    return {"ok": rc == 0, "output": (out + err).strip()}

def mount_shadow(shadow_path: str, mount_point: str) -> dict:
    """Create a symlink/mount to browse shadow copy files."""
    if not _is_windows():
        return {"ok": False, "error": "Windows only"}
    rc, out, err = _run(["mklink", "/d", mount_point, shadow_path + "\\"])
    return {"ok": rc == 0, "output": (out + err).strip()}

def list_volumes_with_shadows() -> list[str]:
    if not _is_windows():
        return []
    rc, out, _ = _run(["vssadmin", "list", "volumes"])
    return [l.split(":",1)[1].strip() for l in out.splitlines() if "Volume path:" in l]

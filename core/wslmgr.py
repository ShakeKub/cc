"""WSL (Windows Subsystem for Linux) manager."""
import os, re, subprocess
from pathlib import Path

def _run(cmd, timeout=30, input=None):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, input=input, errors="replace")
        return r.returncode, r.stdout, r.stderr
    except FileNotFoundError:
        return -2, "", "WSL not installed"
    except Exception as e:
        return -1, "", str(e)

def is_available() -> bool:
    rc, _, _ = _run(["wsl", "--status"], timeout=5)
    return rc == 0

def list_distros() -> list[dict]:
    rc, out, err = _run(["wsl", "--list", "--verbose"])
    if rc != 0:
        return [{"error": err or "WSL not available"}]
    distros = []
    for line in out.splitlines()[1:]:
        line = line.replace("\x00", "").strip()
        if not line: continue
        default = line.startswith("*")
        parts = line.lstrip("*").split()
        if len(parts) >= 3:
            distros.append({
                "name":    parts[0],
                "state":   parts[1],
                "version": parts[2],
                "default": default,
            })
    return distros

def start_distro(name: str) -> dict:
    rc, out, err = _run(["wsl", "-d", name, "--", "echo", "started"])
    return {"ok": rc == 0, "output": (out + err).strip()}

def stop_distro(name: str) -> dict:
    rc, out, err = _run(["wsl", "--terminate", name])
    return {"ok": rc == 0, "output": (out + err).strip()}

def shutdown_all() -> dict:
    rc, out, err = _run(["wsl", "--shutdown"])
    return {"ok": rc == 0, "output": (out + err).strip()}

def export_distro(name: str, output_path: str) -> dict:
    rc, out, err = _run(["wsl", "--export", name, output_path], timeout=300)
    return {"ok": rc == 0, "output": (out + err).strip()}

def import_distro(name: str, install_path: str, tar_path: str) -> dict:
    rc, out, err = _run(["wsl", "--import", name, install_path, tar_path], timeout=300)
    return {"ok": rc == 0, "output": (out + err).strip()}

def unregister_distro(name: str) -> dict:
    rc, out, err = _run(["wsl", "--unregister", name])
    return {"ok": rc == 0, "output": (out + err).strip()}

def set_default(name: str) -> dict:
    rc, out, err = _run(["wsl", "--set-default", name])
    return {"ok": rc == 0, "output": (out + err).strip()}

def run_command(distro: str, command: str) -> dict:
    rc, out, err = _run(["wsl", "-d", distro, "--", "bash", "-c", command], timeout=30)
    return {"ok": rc == 0, "output": out, "error": err}

def update_wsl() -> dict:
    rc, out, err = _run(["wsl", "--update"], timeout=120)
    return {"ok": rc == 0, "output": (out + err).strip()}

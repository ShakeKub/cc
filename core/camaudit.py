"""Webcam / Microphone access auditor — cross-platform."""

import os
import platform
import sqlite3
import subprocess
from pathlib import Path


# ── macOS ─────────────────────────────────────────────────────

def _macos_tcc(service: str) -> list[dict]:
    """Read macOS TCC database for camera/microphone grants."""
    results: list[dict] = []
    db_paths = [
        Path.home() / "Library/Application Support/com.apple.TCC/TCC.db",
        Path("/Library/Application Support/com.apple.TCC/TCC.db"),
    ]
    for db in db_paths:
        if not db.is_file():
            continue
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            cur = con.execute(
                "SELECT client, auth_value, last_modified FROM access WHERE service=?",
                (service,),
            )
            for row in cur.fetchall():
                client, auth_value, ts = row
                allowed = auth_value in (1, 2)
                results.append({
                    "app":     client,
                    "allowed": allowed,
                    "source":  db.name,
                })
            con.close()
        except Exception:
            pass
    return results


def _macos_audit() -> dict:
    camera = _macos_tcc("kTCCServiceCamera")
    mic    = _macos_tcc("kTCCServiceMicrophone")

    # Fallback: system_profiler if TCC unreadable
    if not camera:
        try:
            r = subprocess.run(
                ["system_profiler", "SPCameraDataType"],
                capture_output=True, text=True, timeout=10,
            )
            camera = [{"app": line.strip(), "allowed": True, "source": "system_profiler"}
                      for line in r.stdout.splitlines() if "Camera" in line]
        except Exception:
            pass

    return {"camera": camera, "microphone": mic}


# ── Linux ─────────────────────────────────────────────────────

def _linux_audit() -> dict:
    """Check which processes have /dev/video* or /dev/snd/* open."""
    camera: list[dict] = []
    mic:    list[dict] = []

    video_devs = list(Path("/dev").glob("video*"))
    audio_devs = list(Path("/dev/snd").glob("*")) if Path("/dev/snd").is_dir() else []

    import psutil
    for proc in psutil.process_iter(["pid", "name", "open_files"]):
        try:
            for f in proc.open_files():
                fp = Path(f.path)
                if any(fp == d for d in video_devs):
                    camera.append({"app": proc.name(), "pid": proc.pid,
                                   "device": f.path, "allowed": True, "source": "proc"})
                elif any(fp == d for d in audio_devs):
                    mic.append({"app": proc.name(), "pid": proc.pid,
                                "device": f.path, "allowed": True, "source": "proc"})
        except (psutil.AccessDenied, psutil.NoSuchProcess, Exception):
            pass

    return {"camera": camera, "microphone": mic}


# ── Windows ───────────────────────────────────────────────────

def _windows_audit() -> dict:
    """Read Windows capability consent store for camera and microphone."""
    camera: list[dict] = []
    mic:    list[dict] = []

    try:
        import winreg
        bases = [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]
        services = {
            "webcam":      ("camera",     camera),
            "microphone":  ("microphone", mic),
        }
        consent_root = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore"
        for hive in bases:
            for svc, (_, lst) in services.items():
                try:
                    key = winreg.OpenKey(hive, f"{consent_root}\\{svc}")
                    i = 0
                    while True:
                        try:
                            sub = winreg.EnumKey(key, i)
                            try:
                                sk = winreg.OpenKey(key, sub)
                                val, _ = winreg.QueryValueEx(sk, "Value")
                                allowed = val == "Allow"
                                lst.append({"app": sub.replace("#", "\\"),
                                            "allowed": allowed, "source": "registry"})
                            except OSError:
                                pass
                            i += 1
                        except OSError:
                            break
                except OSError:
                    pass
    except ImportError:
        pass

    return {"camera": camera, "microphone": mic}


# ── Public API ────────────────────────────────────────────────

def audit() -> dict:
    """Return {camera: [...], microphone: [...]} for the current platform."""
    sys = platform.system()
    if sys == "Darwin":
        return _macos_audit()
    elif sys == "Linux":
        return _linux_audit()
    else:
        return _windows_audit()

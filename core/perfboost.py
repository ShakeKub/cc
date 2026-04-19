"""Performance Boost — one-click speed-up for Windows."""

import os
import subprocess
from typing import Any

from core.logger import CleanerLogger

BLOAT_PROCESSES = [
    "Teams.exe", "teams.exe",
    "OneDrive.exe",
    "Discord.exe",
    "Spotify.exe",
    "Slack.exe",
    "skype.exe", "Skype.exe",
    "SearchIndexer.exe",
    "MsMpEng.exe",   # Windows Defender scan — skip, dangerous
    "SysMain",       # service, not a process name here
]

# Processes safe to kill for perf boost
KILL_TARGETS = {n.lower() for n in [
    "Teams.exe", "OneDrive.exe", "Discord.exe",
    "Spotify.exe", "Slack.exe", "skype.exe",
]}

# Services to stop temporarily
STOP_SERVICES = ["SysMain", "WSearch"]


def kill_background_apps(logger: CleanerLogger) -> dict[str, Any]:
    """Kill known background bloat processes. Returns killed/skipped counts."""
    if os.name != "nt":
        return {"killed": 0, "skipped": 0, "names": []}
    try:
        import psutil
    except ImportError:
        return {"killed": 0, "skipped": 0, "names": []}

    killed = []
    skipped = 0
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = proc.info["name"] or ""
            if name.lower() in KILL_TARGETS:
                proc.kill()
                killed.append(name)
                logger.log("perf_kill", "perfboost", f"Killed: {name}")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            skipped += 1
    return {"killed": len(killed), "skipped": skipped, "names": killed}


def trim_ram(logger: CleanerLogger) -> dict[str, Any]:
    """Trim working sets of all processes. Returns trimmed/skipped/freed."""
    if os.name != "nt":
        return {"trimmed": 0, "skipped": 0, "freed": 0}
    try:
        import psutil, ctypes
        from ctypes import wintypes
    except ImportError:
        return {"trimmed": 0, "skipped": 0, "freed": 0}

    PROCESS_SET_QUOTA = 0x0100
    PROCESS_QUERY_LIMITED = 0x1000
    k32 = ctypes.windll.kernel32
    before = psutil.virtual_memory().available
    trimmed = skipped = 0

    for proc in psutil.process_iter(["pid"]):
        try:
            handle = k32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_QUERY_LIMITED,
                                     False, proc.pid)
            if handle:
                k32.SetProcessWorkingSetSize(handle, ctypes.c_size_t(-1), ctypes.c_size_t(-1))
                k32.CloseHandle(handle)
                trimmed += 1
        except Exception:
            skipped += 1

    after = psutil.virtual_memory().available
    freed = max(0, after - before)
    logger.log("perf_trim_ram", "perfboost", f"Trimmed {trimmed} procs, freed ~{freed//1024//1024} MB")
    return {"trimmed": trimmed, "skipped": skipped, "freed": freed}


def set_high_performance(logger: CleanerLogger) -> bool:
    """Switch power plan to High Performance."""
    if os.name != "nt":
        return False
    try:
        r = subprocess.run(
            ["powercfg", "/setactive", "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            logger.log("perf_power_plan", "perfboost", "Switched to High Performance")
            return True
        # fallback: use SCHEME_MIN alias
        r2 = subprocess.run(
            ["powercfg", "/setactive", "SCHEME_MIN"],
            capture_output=True, text=True, timeout=10,
        )
        ok = r2.returncode == 0
        if ok:
            logger.log("perf_power_plan", "perfboost", "Switched to High Performance (SCHEME_MIN)")
        return ok
    except Exception as e:
        logger.error(f"Power plan switch failed: {e}")
        return False


def disable_visual_effects(logger: CleanerLogger) -> bool:
    """Set Windows to best performance visual settings."""
    if os.name != "nt":
        return False
    script = (
        "$path = 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\VisualEffects'; "
        "if (!(Test-Path $path)) { New-Item -Path $path -Force | Out-Null }; "
        "Set-ItemProperty -Path $path -Name VisualFXSetting -Value 2; "
        "$p2 = 'HKCU:\\Control Panel\\Desktop'; "
        "Set-ItemProperty -Path $p2 -Name UserPreferencesMask -Value ([byte[]](0x90,0x12,0x03,0x80,0x10,0x00,0x00,0x00)) -Type Binary; "
        "Set-ItemProperty -Path $p2 -Name DragFullWindows -Value '0'; "
        "Set-ItemProperty -Path $p2 -Name MenuShowDelay -Value '0'; "
        "$p3 = 'HKCU:\\Control Panel\\Desktop\\WindowMetrics'; "
        "Set-ItemProperty -Path $p3 -Name MinAnimate -Value '0'"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=15,
        )
        ok = r.returncode == 0
        if ok:
            logger.log("perf_visual_effects", "perfboost", "Visual effects set to best performance")
        return ok
    except Exception as e:
        logger.error(f"Visual effects toggle failed: {e}")
        return False


def stop_heavy_services(logger: CleanerLogger) -> dict[str, bool]:
    """Temporarily stop SysMain and WSearch services."""
    if os.name != "nt":
        return {}
    results = {}
    for svc in STOP_SERVICES:
        try:
            r = subprocess.run(
                ["sc", "stop", svc],
                capture_output=True, text=True, timeout=15,
            )
            success = r.returncode in (0, 1062)  # 1062 = not started
            results[svc] = success
            logger.log("perf_stop_svc", "perfboost", f"{'Stopped' if success else 'Failed'}: {svc}")
        except Exception as e:
            results[svc] = False
            logger.error(f"Stop service {svc} failed: {e}")
    return results

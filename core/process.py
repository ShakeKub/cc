"""Process manager - list, kill, monitor CPU/RAM, detect suspicious."""

import os
from typing import Any
import psutil
from core.logger import CleanerLogger


# Known system processes that should not be killed
SYSTEM_PROCESSES = {
    "system", "smss.exe", "csrss.exe", "wininit.exe", "services.exe",
    "lsass.exe", "svchost.exe", "winlogon.exe", "dwm.exe", "explorer.exe",
    "taskhostw.exe", "runtimebroker.exe", "sihost.exe", "fontdrvhost.exe",
    "memory compression", "system idle process", "registry",
}

# Processes that commonly indicate resource hogs
KNOWN_HEAVY_PROCESSES = {
    "chrome.exe", "firefox.exe", "msedge.exe", "teams.exe",
    "discord.exe", "spotify.exe", "slack.exe", "code.exe",
    "devenv.exe", "java.exe", "node.exe", "python.exe",
}


def list_processes(sort_by: str = "memory",
                   logger: CleanerLogger | None = None) -> list[dict[str, Any]]:
    """List all running processes with CPU and memory usage."""
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info',
                                      'memory_percent', 'status', 'username',
                                      'create_time', 'exe']):
        try:
            info = proc.info
            name = info.get('name', 'Unknown')
            mem_info = info.get('memory_info')
            processes.append({
                "pid": info['pid'],
                "name": name,
                "cpu_percent": info.get('cpu_percent', 0) or 0,
                "memory_bytes": mem_info.rss if mem_info else 0,
                "memory_percent": info.get('memory_percent', 0) or 0,
                "status": info.get('status', 'unknown'),
                "username": info.get('username', 'N/A'),
                "exe": info.get('exe', ''),
                "is_system": name.lower() in SYSTEM_PROCESSES,
                "is_heavy": name.lower() in KNOWN_HEAVY_PROCESSES,
                "suspicious": _check_suspicious_process(info),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    # Sort
    if sort_by == "memory":
        processes.sort(key=lambda p: p["memory_bytes"], reverse=True)
    elif sort_by == "cpu":
        processes.sort(key=lambda p: p["cpu_percent"], reverse=True)
    elif sort_by == "name":
        processes.sort(key=lambda p: p["name"].lower())
    elif sort_by == "pid":
        processes.sort(key=lambda p: p["pid"])

    if logger:
        logger.info(f"Listed {len(processes)} running processes")
    return processes


def _check_suspicious_process(info: dict) -> dict[str, Any] | None:
    """Check if a process looks suspicious."""
    name = info.get('name', '').lower()
    exe = info.get('exe', '') or ''
    reasons = []

    # Process running from temp directory
    if exe and ('temp' in exe.lower() or 'tmp' in exe.lower()):
        reasons.append("Running from temp directory")

    # Process with no executable path but not a system process
    if not exe and name not in SYSTEM_PROCESSES and info.get('pid', 0) > 4:
        reasons.append("No executable path found")

    # Process name mimicking system process (e.g., svchost vs svch0st)
    system_names = {"svchost", "csrss", "lsass", "services", "winlogon"}
    for sys_name in system_names:
        if name.replace(".exe", "") != sys_name and _is_similar(name.replace(".exe", ""), sys_name):
            reasons.append(f"Name similar to system process: {sys_name}")

    # Very high resource usage
    mem_percent = info.get('memory_percent', 0) or 0
    if mem_percent > 50:
        reasons.append(f"Very high memory usage: {mem_percent:.1f}%")

    if reasons:
        return {"reasons": reasons, "risk": "high" if len(reasons) > 1 else "medium"}
    return None


def _is_similar(name1: str, name2: str) -> bool:
    """Simple similarity check using character substitution detection."""
    if abs(len(name1) - len(name2)) > 1:
        return False
    if name1 == name2:
        return False
    # Check for common substitutions (0 for o, 1 for l, etc.)
    substitutions = {"0": "o", "1": "l", "3": "e", "5": "s"}
    normalized1 = name1
    for k, v in substitutions.items():
        normalized1 = normalized1.replace(k, v)
    return normalized1 == name2


def kill_process(pid: int, logger: CleanerLogger, force: bool = False) -> bool:
    """Kill a process by PID."""
    try:
        proc = psutil.Process(pid)
        name = proc.name()

        # Safety check - don't kill system processes
        if name.lower() in SYSTEM_PROCESSES:
            logger.error(f"Refused to kill system process: {name} (PID {pid})")
            return False

        if force:
            proc.kill()
        else:
            proc.terminate()
            proc.wait(timeout=5)

        logger.log("kill_process", "process",
                  f"{'Killed' if force else 'Terminated'}: {name} (PID {pid})")
        return True
    except psutil.NoSuchProcess:
        logger.warning(f"Process not found: PID {pid}")
        return False
    except psutil.AccessDenied:
        logger.error(f"Access denied killing PID {pid}")
        return False
    except psutil.TimeoutExpired:
        if not force:
            return kill_process(pid, logger, force=True)
        logger.error(f"Timeout killing PID {pid}")
        return False


def get_process_tree(pid: int) -> list[dict[str, Any]]:
    """Get process tree (parent + children) for a given PID."""
    tree = []
    try:
        proc = psutil.Process(pid)
        # Parent
        try:
            parent = proc.parent()
            if parent:
                tree.append({
                    "pid": parent.pid,
                    "name": parent.name(),
                    "relationship": "parent",
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        # Self
        tree.append({
            "pid": proc.pid,
            "name": proc.name(),
            "relationship": "self",
        })

        # Children
        for child in proc.children(recursive=True):
            try:
                tree.append({
                    "pid": child.pid,
                    "name": child.name(),
                    "relationship": "child",
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return tree


def get_system_summary() -> dict[str, Any]:
    """Get overall system resource summary."""
    cpu = psutil.cpu_percent(interval=0.5, percpu=True)
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    return {
        "cpu_per_core": cpu,
        "cpu_average": sum(cpu) / len(cpu) if cpu else 0,
        "cpu_count": len(cpu),
        "memory_total": mem.total,
        "memory_used": mem.used,
        "memory_percent": mem.percent,
        "swap_total": swap.total,
        "swap_used": swap.used,
        "swap_percent": swap.percent,
        "process_count": len(psutil.pids()),
        "boot_time": psutil.boot_time(),
    }

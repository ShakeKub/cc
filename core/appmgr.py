"""App Manager — list running user apps, kill, block/unblock internet via firewall."""

from __future__ import annotations
import subprocess
from typing import Any

import psutil

_SYSTEM_PROC_NAMES = {
    "system", "smss.exe", "csrss.exe", "wininit.exe", "services.exe",
    "lsass.exe", "svchost.exe", "winlogon.exe", "dwm.exe", "explorer.exe",
    "taskhostw.exe", "runtimebroker.exe", "sihost.exe", "fontdrvhost.exe",
    "memory compression", "system idle process", "registry", "ntoskrnl.exe",
    "spoolsv.exe", "audiodg.exe", "dashost.exe", "searchindexer.exe",
    "securityhealthsystray.exe", "ctfmon.exe", "conhost.exe",
}

_BROWSER_NAMES = {
    "chrome.exe", "firefox.exe", "msedge.exe", "opera.exe", "brave.exe",
    "vivaldi.exe", "iexplore.exe", "microsoftedge.exe", "chromium.exe",
}

_RULE_PREFIX = "SC_BLOCK_"


def _run(cmd: list[str], timeout: int = 15) -> tuple[int, str, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
        return r.returncode, r.stdout, r.stderr
    except Exception as e:
        return -1, "", str(e)


def list_user_apps(logger=None) -> list[dict[str, Any]]:
    """Return user-facing processes with CPU, RAM, connection count, and block status."""
    blocked_exes = {b.get("exe", "").lower() for b in get_blocked_apps()}
    results: list[dict[str, Any]] = []

    for proc in psutil.process_iter(["pid", "name", "exe", "cpu_percent",
                                      "memory_info", "username", "status"]):
        try:
            info = proc.info
            name_lower = (info.get("name") or "").lower()
            exe = info.get("exe") or ""

            if name_lower in _SYSTEM_PROC_NAMES or not exe:
                continue

            try:
                conns = proc.net_connections()
                active_conns = sum(1 for c in conns if c.raddr)
            except Exception:
                active_conns = 0

            mem = info.get("memory_info")
            category = "browser" if name_lower in _BROWSER_NAMES else "user"

            results.append({
                "pid":              info["pid"],
                "name":             info.get("name", ""),
                "exe":              exe,
                "cpu_percent":      info.get("cpu_percent", 0) or 0,
                "memory_bytes":     mem.rss if mem else 0,
                "status":           info.get("status", ""),
                "active_conns":     active_conns,
                "is_blocked":       exe.lower() in blocked_exes,
                "category":         category,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    results.sort(key=lambda x: x["memory_bytes"], reverse=True)
    return results


def block_app_internet(exe_path: str, logger=None) -> dict[str, Any]:
    """Add an outbound Windows Firewall rule that blocks the app."""
    from pathlib import Path
    rule_name = _RULE_PREFIX + Path(exe_path).name
    # Remove any existing rule first (idempotent)
    _run(["netsh", "advfirewall", "firewall", "delete", "rule", f"name={rule_name}"])
    code, _, err_out = _run([
        "netsh", "advfirewall", "firewall", "add", "rule",
        f"name={rule_name}", "dir=out", "action=block",
        f"program={exe_path}", "enable=yes",
    ])
    ok = code == 0
    if logger and ok:
        logger.log_action("block_internet", f"Blocked outbound: {exe_path}")
    return {"ok": ok, "rule_name": rule_name, "error": err_out if not ok else ""}


def unblock_app_internet(exe_path: str, logger=None) -> dict[str, Any]:
    """Remove the outbound firewall block for an app."""
    from pathlib import Path
    rule_name = _RULE_PREFIX + Path(exe_path).name
    code, _, _ = _run([
        "netsh", "advfirewall", "firewall", "delete", "rule", f"name={rule_name}",
    ])
    ok = code == 0
    if logger and ok:
        logger.log_action("unblock_internet", f"Unblocked outbound: {exe_path}")
    return {"ok": ok, "rule_name": rule_name}


def get_blocked_apps() -> list[dict[str, str]]:
    """Return list of {name, exe} for all SC_BLOCK_* firewall rules."""
    code, out, _ = _run([
        "netsh", "advfirewall", "firewall", "show", "rule",
        f"name={_RULE_PREFIX}*", "verbose",
    ], timeout=20)
    results: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("Rule Name:"):
            if current.get("name", "").startswith(_RULE_PREFIX):
                results.append(current)
            current = {"name": line.split(":", 1)[1].strip(), "exe": ""}
        elif line.startswith("Program:"):
            current["exe"] = line.split(":", 1)[1].strip()
    if current.get("name", "").startswith(_RULE_PREFIX):
        results.append(current)
    return results


def kill_app(pid: int, logger=None) -> bool:
    try:
        p = psutil.Process(pid)
        name = p.name()
        p.kill()
        if logger:
            logger.log_action("kill_app", f"Killed {name} PID {pid}")
        return True
    except Exception:
        return False

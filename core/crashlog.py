"""Windows crash / error log reader (Event Log + minidumps)."""

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path


def _ps(cmd: str, timeout: int = 30) -> str:
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=timeout,
        )
        return r.stdout.strip()
    except Exception:
        return ""


def get_crash_events(hours: int = 72, max_events: int = 200, logger=None) -> list[dict]:
    """
    Pull Critical (level 1) and Error (level 2) events from System and Application logs.
    Returns list of {time, source, id, level, message}.
    """
    cmd = (
        f"$since=(Get-Date).AddHours(-{hours}); "
        "Get-WinEvent -FilterHashtable @{LogName='System','Application';Level=1,2;StartTime=$since} "
        f"-MaxEvents {max_events} -ErrorAction SilentlyContinue | "
        "Select-Object TimeCreated,ProviderName,Id,LevelDisplayName,"
        "@{n='Msg';e={$_.Message -replace '`n',' ' -replace '`r','' }} | "
        "ConvertTo-Json -Compress"
    )
    raw = _ps(cmd, timeout=45)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        events = []
        for d in data:
            events.append({
                "time":    str(d.get("TimeCreated", ""))[:19].replace("T", " "),
                "source":  d.get("ProviderName", ""),
                "id":      str(d.get("Id", "")),
                "level":   d.get("LevelDisplayName", ""),
                "message": (d.get("Msg") or "")[:300].strip(),
            })
        return events
    except (json.JSONDecodeError, TypeError):
        return []


def get_minidumps(logger=None) -> list[dict]:
    """Return list of minidump files from C:\\Windows\\Minidump."""
    dump_dir = Path("C:/Windows/Minidump")
    if not dump_dir.exists():
        return []
    dumps = []
    for f in sorted(dump_dir.glob("*.dmp"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            st = f.stat()
            dumps.append({
                "path":     str(f),
                "name":     f.name,
                "size":     st.st_size,
                "modified": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
            })
        except OSError:
            continue
    return dumps[:50]


def get_bsod_summary(logger=None) -> list[dict]:
    """Read BugCheck events (BSOD) from System log."""
    cmd = (
        "Get-WinEvent -FilterHashtable @{LogName='System';Id=1001} "
        "-MaxEvents 20 -ErrorAction SilentlyContinue | "
        "Select-Object TimeCreated,Message | ConvertTo-Json -Compress"
    )
    raw = _ps(cmd, timeout=20)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        return [
            {
                "time":    str(d.get("TimeCreated", ""))[:19].replace("T", " "),
                "message": (d.get("Message") or "")[:200].strip(),
            }
            for d in data
        ]
    except (json.JSONDecodeError, TypeError):
        return []

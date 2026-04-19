"""Windows Update Manager — list installed, pending, pause/resume updates."""

import os
import subprocess
from datetime import datetime
from core.logger import CleanerLogger


def get_installed_updates(logger: CleanerLogger, limit: int = 30) -> list[dict]:
    """Return recently installed hotfixes via Get-HotFix."""
    if os.name != "nt":
        return []
    script = (
        f"Get-HotFix | Sort-Object InstalledOn -Descending | "
        f"Select-Object -First {limit} HotFixID, Description, InstalledOn, InstalledBy | "
        "ConvertTo-Json -Compress"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return []
        import json
        raw = json.loads(r.stdout)
        if isinstance(raw, dict):
            raw = [raw]
        updates = []
        for item in raw:
            installed_on = ""
            ts = item.get("InstalledOn")
            if ts and isinstance(ts, dict):
                ms = ts.get("value", 0)
                try:
                    installed_on = datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d")
                except Exception:
                    pass
            elif isinstance(ts, str):
                installed_on = ts[:10]
            updates.append({
                "id":          item.get("HotFixID", ""),
                "description": item.get("Description", ""),
                "installed_on": installed_on,
                "installed_by": item.get("InstalledBy", ""),
            })
        return updates
    except Exception as e:
        logger.error(f"get_installed_updates error: {e}")
        return []


def check_pending_updates(logger: CleanerLogger) -> list[dict]:
    """Check for pending Windows Updates via WUA COM API through PowerShell."""
    if os.name != "nt":
        return []
    script = (
        "$Session = New-Object -ComObject Microsoft.Update.Session; "
        "$Searcher = $Session.CreateUpdateSearcher(); "
        "try { $Result = $Searcher.Search('IsInstalled=0 and Type=\\'Software\\''); "
        "$Result.Updates | Select-Object Title, MsrcSeverity, @{N='Size';E={[math]::Round($_.MaxDownloadSize/1MB,1)}} | "
        "ConvertTo-Json -Compress } catch { '[]' }"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=60,
        )
        if not r.stdout.strip() or r.stdout.strip() == "[]":
            return []
        import json
        raw = json.loads(r.stdout)
        if isinstance(raw, dict):
            raw = [raw]
        return [
            {
                "title":    item.get("Title", "")[:70],
                "severity": item.get("MsrcSeverity") or "Unknown",
                "size_mb":  item.get("Size", 0),
            }
            for item in (raw or [])
        ]
    except Exception as e:
        logger.error(f"check_pending_updates error: {e}")
        return []


def get_update_pause_status(logger: CleanerLogger) -> dict:
    """Return current pause/resume status and pause end date."""
    if os.name != "nt":
        return {}
    script = (
        "Get-ItemProperty -Path 'HKLM:\\SOFTWARE\\Microsoft\\WindowsUpdate\\UX\\Settings' "
        "-Name PauseUpdatesStartTime, PauseQualityUpdatesStartTime, PauseFeatureUpdatesStartTime "
        "-ErrorAction SilentlyContinue | ConvertTo-Json -Compress"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=10,
        )
        import json
        data = json.loads(r.stdout) if r.stdout.strip() else {}
        paused = any(v for k, v in data.items() if "Pause" in k and v)
        return {"paused": paused, "raw": data}
    except Exception:
        return {"paused": False, "raw": {}}


def pause_updates(days: int, logger: CleanerLogger) -> bool:
    """Pause Windows Updates for the given number of days (max 35)."""
    if os.name != "nt":
        return False
    days = min(days, 35)
    script = (
        f"$d = (Get-Date).AddDays({days}).ToString('yyyy-MM-ddTHH:mm:ssZ'); "
        "$p = 'HKLM:\\SOFTWARE\\Microsoft\\WindowsUpdate\\UX\\Settings'; "
        "Set-ItemProperty -Path $p -Name PauseUpdatesStartTime -Value (Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ') -Type String; "
        "Set-ItemProperty -Path $p -Name PauseQualityUpdatesStartTime -Value (Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ') -Type String; "
        "Set-ItemProperty -Path $p -Name PauseQualityUpdatesEndTime -Value $d -Type String"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=15,
        )
        ok = r.returncode == 0
        logger.log("pause_updates", "winupdate",
                   f"Updates paused for {days} days" if ok else f"Pause failed: {r.stderr}")
        return ok
    except Exception as e:
        logger.error(f"pause_updates error: {e}")
        return False


def resume_updates(logger: CleanerLogger) -> bool:
    """Remove pause on Windows Updates."""
    if os.name != "nt":
        return False
    script = (
        "$p = 'HKLM:\\SOFTWARE\\Microsoft\\WindowsUpdate\\UX\\Settings'; "
        "Remove-ItemProperty -Path $p -Name PauseUpdatesStartTime -ErrorAction SilentlyContinue; "
        "Remove-ItemProperty -Path $p -Name PauseQualityUpdatesStartTime -ErrorAction SilentlyContinue; "
        "Remove-ItemProperty -Path $p -Name PauseQualityUpdatesEndTime -ErrorAction SilentlyContinue"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=15,
        )
        ok = r.returncode == 0
        logger.log("resume_updates", "winupdate",
                   "Updates resumed" if ok else f"Resume failed: {r.stderr}")
        return ok
    except Exception as e:
        logger.error(f"resume_updates error: {e}")
        return False


def trigger_update_check(logger: CleanerLogger) -> bool:
    """Trigger Windows Update check via usoclient."""
    if os.name != "nt":
        return False
    try:
        r = subprocess.run(["usoclient", "StartScan"],
                           capture_output=True, text=True, timeout=10)
        ok = r.returncode == 0
        logger.log("trigger_update", "winupdate", "Update scan triggered" if ok else "Trigger failed")
        return ok
    except Exception as e:
        logger.error(f"trigger_update error: {e}")
        return False

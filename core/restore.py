"""Windows System Restore Point manager (PowerShell-backed)."""

import json
import re
import subprocess


def _ps(cmd: str, timeout: int = 30) -> tuple[str, int]:
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=timeout,
        )
        return r.stdout.strip(), r.returncode
    except Exception as e:
        return str(e), -1


def _parse_date(s: str) -> str:
    m = re.search(r"/Date\((\d+)\)/", str(s))
    if m:
        from datetime import datetime
        return datetime.fromtimestamp(int(m.group(1)) / 1000).strftime("%Y-%m-%d %H:%M")
    s = str(s)[:19]
    return s.replace("T", " ")


def list_restore_points(logger=None) -> list[dict]:
    """Return list of restore points: {seq, description, created, type}."""
    out, _ = _ps(
        "Get-ComputerRestorePoint | "
        "Select-Object SequenceNumber,Description,CreationTime,RestorePointType | "
        "ConvertTo-Json -Compress"
    )
    if not out:
        return []
    try:
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        return [
            {
                "seq":         int(d.get("SequenceNumber", 0)),
                "description": d.get("Description", ""),
                "created":     _parse_date(d.get("CreationTime", "")),
                "type":        str(d.get("RestorePointType", "")),
            }
            for d in data
        ]
    except (json.JSONDecodeError, TypeError):
        return []


def create_restore_point(description: str, logger=None) -> bool:
    """Create a new MODIFY_SETTINGS restore point. Requires admin + SR enabled."""
    cmd = (
        f'Enable-ComputerRestore -Drive "C:\\" -ErrorAction SilentlyContinue; '
        f'Checkpoint-Computer -Description "{description}" '
        f'-RestorePointType "MODIFY_SETTINGS" -ErrorAction Stop'
    )
    _, rc = _ps(cmd, timeout=120)
    if logger:
        logger.log("restore_create", "restore", f"desc={description} rc={rc}")
    return rc == 0


def delete_restore_point(seq: int, logger=None) -> bool:
    """Delete a restore point by sequence number."""
    _, rc = _ps(f"Remove-ComputerRestorePoint -RestorePoint {seq}", timeout=30)
    if logger:
        logger.log("restore_delete", "restore", f"seq={seq} rc={rc}")
    return rc == 0


def delete_all_restore_points(logger=None) -> bool:
    """Delete all restore points for C:\ via vssadmin."""
    _, rc = _ps(
        'vssadmin delete shadows /for=C: /all /quiet',
        timeout=60,
    )
    if logger:
        logger.log("restore_delete_all", "restore", f"rc={rc}")
    return rc == 0

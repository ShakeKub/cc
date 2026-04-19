"""File recovery — Recycle Bin browser and Volume Shadow Copy (VSS) restore."""

import json
import subprocess
from datetime import datetime


def _ps(cmd: str, timeout: int = 20) -> str:
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=timeout,
        )
        return r.stdout.strip()
    except Exception:
        return ""


# ── Recycle Bin ──────────────────────────────────────────────

def get_recycle_bin_items(logger=None) -> list[dict]:
    """List all items currently in the Recycle Bin via Shell COM object."""
    cmd = (
        "$sh = New-Object -ComObject Shell.Application; "
        "$rb = $sh.Namespace(10); "
        "$items = $rb.Items(); "
        "if ($items.Count -eq 0) { '[]'; return }; "
        "$items | ForEach-Object { "
        "  [PSCustomObject]@{ "
        "    Name = $_.Name; "
        "    Path = $_.Path; "
        "    Size = $_.Size; "
        "    Type = $_.Type; "
        "    Date = $rb.GetDetailsOf($_, 2) "    # "Date deleted" column
        "  } "
        "} | ConvertTo-Json -Compress"
    )
    raw = _ps(cmd, timeout=15)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        return [
            {
                "name": d.get("Name", ""),
                "path": d.get("Path", ""),
                "size": int(d.get("Size") or 0),
                "type": d.get("Type", ""),
                "date": d.get("Date", ""),
            }
            for d in data
        ]
    except (json.JSONDecodeError, TypeError):
        return []


def restore_recycle_item(item: dict, logger=None) -> bool:
    """Restore a single Recycle Bin item to its original location."""
    name = item.get("name", "").replace('"', '`"')
    cmd = (
        "$sh = New-Object -ComObject Shell.Application; "
        "$rb = $sh.Namespace(10); "
        f'$item = $rb.Items() | Where-Object {{ $_.Name -eq "{name}" }} | '
        "Select-Object -First 1; "
        "if ($item) { $item.InvokeVerb('Restore') } else { exit 1 }"
    )
    _ps(cmd, timeout=15)
    if logger:
        logger.log("recycle_restore", "recovery", f"file={item['name']}")
    return True


def restore_all_recycle(logger=None) -> bool:
    """Restore every item from the Recycle Bin."""
    cmd = (
        "$sh = New-Object -ComObject Shell.Application; "
        "$rb = $sh.Namespace(10); "
        "foreach ($item in $rb.Items()) { $item.InvokeVerb('Restore') }"
    )
    _ps(cmd, timeout=60)
    if logger:
        logger.log("recycle_restore_all", "recovery", "all")
    return True


def empty_recycle_bin(logger=None) -> bool:
    """Permanently empty the Recycle Bin."""
    out = _ps("Clear-RecycleBin -Force -ErrorAction SilentlyContinue", timeout=30)
    if logger:
        logger.log("recycle_empty", "recovery", "emptied")
    return True


# ── Volume Shadow Copies ─────────────────────────────────────

def get_shadow_copies(logger=None) -> list[dict]:
    """List available Volume Shadow Copies (VSS snapshots)."""
    raw = _ps(
        "Get-WmiObject Win32_ShadowCopy | "
        "Select-Object ID,InstallDate,VolumeName,DeviceObject | "
        "ConvertTo-Json -Compress",
        timeout=15,
    )
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        out = []
        for d in data:
            raw_date = str(d.get("InstallDate", ""))
            try:
                date = datetime.strptime(raw_date[:14], "%Y%m%d%H%M%S").strftime("%Y-%m-%d %H:%M")
            except Exception:
                date = raw_date[:16]
            out.append({
                "id":     d.get("ID", ""),
                "date":   date,
                "volume": d.get("VolumeName", ""),
                "device": d.get("DeviceObject", ""),
            })
        return sorted(out, key=lambda x: x["date"], reverse=True)
    except (json.JSONDecodeError, TypeError):
        return []


def restore_from_shadow(shadow: dict, rel_path: str, dest_dir: str, logger=None) -> bool:
    """
    Copy a file from a shadow copy to dest_dir.

    shadow   — entry from get_shadow_copies()
    rel_path — path relative to volume root, e.g. "Users\\alice\\doc.txt"
    dest_dir — destination folder for the recovered file
    """
    device = shadow.get("device", "")
    link   = "C:\\__sc_recovery__"
    rel    = rel_path.lstrip("\\/")

    cmd = (
        # Create a temporary directory junction pointing at the shadow
        f'cmd /c mklink /d "{link}" "{device}\\" 2>nul | Out-Null; '
        f'$src = "{link}\\{rel}"; '
        f'if (Test-Path $src) {{ '
        f'  Copy-Item $src -Destination "{dest_dir}" -Force; $true '
        f'}} else {{ $false }}; '
        # Always clean up the junction
        f'cmd /c rmdir "{link}" 2>nul | Out-Null'
    )
    out = _ps(cmd, timeout=30)
    if logger:
        logger.log("shadow_restore", "recovery",
                   f"shadow={shadow['id']} file={rel_path} dest={dest_dir}")
    return "True" in out

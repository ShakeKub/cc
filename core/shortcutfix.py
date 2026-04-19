"""Shortcut Fixer — scan .lnk files and find/fix broken targets."""

import os
import struct
import subprocess
from pathlib import Path
from core.logger import CleanerLogger

SCAN_DIRS = [
    Path(os.path.expanduser("~")) / "Desktop",
    Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop",
    Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu",
    Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / r"Microsoft\Windows\Start Menu",
]


def _get_lnk_target_powershell(lnk_path: str) -> str:
    """Resolve .lnk target path via PowerShell Shell COM."""
    try:
        script = (
            f"$sh = New-Object -ComObject WScript.Shell; "
            f"$sc = $sh.CreateShortcut('{lnk_path}'); "
            f"$sc.TargetPath"
        )
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip()
    except Exception:
        return ""


def find_broken_shortcuts(extra_dirs: list[str] | None = None,
                           logger: CleanerLogger | None = None) -> list[dict]:
    """Scan known locations for .lnk files with missing targets."""
    dirs = list(SCAN_DIRS)
    if extra_dirs:
        dirs += [Path(d) for d in extra_dirs]

    broken = []
    for scan_dir in dirs:
        if not scan_dir.exists():
            continue
        try:
            for lnk in scan_dir.rglob("*.lnk"):
                try:
                    target = _get_lnk_target_powershell(str(lnk))
                    if target and not Path(target).exists():
                        broken.append({
                            "lnk_path": str(lnk),
                            "name":     lnk.stem,
                            "target":   target,
                            "location": str(lnk.parent),
                        })
                except Exception:
                    pass
        except Exception as e:
            if logger:
                logger.error(f"shortcut scan error in {scan_dir}: {e}")

    if logger:
        logger.log("find_broken_shortcuts", "shortcutfix",
                   f"Found {len(broken)} broken shortcuts")
    return broken


def delete_shortcut(shortcut: dict, logger: CleanerLogger) -> bool:
    """Delete the .lnk file."""
    try:
        p = Path(shortcut["lnk_path"])
        if p.exists():
            p.unlink()
        logger.log("delete_shortcut", "shortcutfix", f"Deleted: {shortcut['lnk_path']}")
        return True
    except OSError as e:
        logger.error(f"delete_shortcut error: {e}")
        return False


def delete_shortcuts(shortcuts: list[dict], logger: CleanerLogger) -> int:
    """Delete multiple shortcuts. Returns count deleted."""
    return sum(1 for s in shortcuts if delete_shortcut(s, logger))

"""System cleaning module - temp files, caches, DNS, recycle bin, etc."""

import os
import shutil
import subprocess
import ctypes
import json
from functools import lru_cache
from pathlib import Path
from typing import Generator
from core.logger import CleanerLogger


# Protected system directories that must never be deleted
PROTECTED_DIRS = {
    "system32", "syswow64", "winsxs", "drivers",
    "boot", "assembly", "microsoft.net",
}

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


@lru_cache(maxsize=1)
def _protected_paths_from_config() -> list[str]:
    try:
        if _CONFIG_PATH.exists():
            cfg = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            paths = cfg.get("protected_paths", [])
            return [str(p).strip().lower().rstrip("/\\") for p in paths if str(p).strip()]
    except Exception:
        pass
    return []


def _is_protected(path: Path) -> bool:
    """Check if path is a protected system location."""
    parts_lower = [p.lower() for p in path.parts]
    if any(p in PROTECTED_DIRS for p in parts_lower):
        return True
    path_str = str(path).lower()
    for protected in _protected_paths_from_config():
        if not protected:
            continue
        if path_str == protected:
            return True
        if path_str.startswith(protected) and path_str[len(protected):len(protected)+1] in ("/", "\\"):
            return True
    return False


def _safe_remove(path: Path, logger: CleanerLogger) -> int:
    """Safely remove a file or directory, returning bytes actually freed."""
    if _is_protected(path):
        logger.warning(f"Skipped protected path: {path}")
        return 0
    try:
        if path.is_file():
            size = path.stat().st_size
            path.unlink()
            # Verify the file was actually deleted before reporting freed space
            if not path.exists():
                return size
            logger.warning(f"File still exists after deletion attempt: {path}")
            return 0
        elif path.is_dir():
            # Measure size BEFORE attempting removal
            try:
                size_before = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
            except (PermissionError, OSError):
                size_before = 0
            shutil.rmtree(path, ignore_errors=False)
            return size_before
    except PermissionError:
        logger.warning(f"Permission denied: {path}")
    except Exception as e:
        # Check if this was a directory that was partially removed
        if path.is_dir() and path.exists():
            try:
                size_after = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
                freed = size_before - size_after  # type: ignore[possibly-undefined]
                if freed > 0:
                    logger.warning(f"Partial deletion of {path}: freed {freed} bytes, {e}")
                    return freed
            except Exception:
                pass
        logger.error(f"Error removing {path}: {e}")
    return 0


def scan_temp_files(logger: CleanerLogger) -> list[dict]:
    """Scan for temporary files across standard locations."""
    results = []
    temp_dirs = []

    # User temp directory
    user_temp = os.environ.get("TEMP", os.environ.get("TMP", ""))
    if user_temp:
        temp_dirs.append(Path(user_temp))

    # Windows temp
    win_dir = os.environ.get("WINDIR", r"C:\Windows")
    temp_dirs.append(Path(win_dir) / "Temp")

    # Prefetch
    temp_dirs.append(Path(win_dir) / "Prefetch")

    for temp_dir in temp_dirs:
        if not temp_dir.exists():
            continue
        try:
            for item in temp_dir.iterdir():
                if _is_protected(item):
                    continue
                try:
                    if item.is_file():
                        size = item.stat().st_size
                    elif item.is_dir():
                        size = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
                    else:
                        continue
                    results.append({
                        "path": str(item),
                        "size": size,
                        "type": "file" if item.is_file() else "directory",
                        "category": "temp",
                        "location": str(temp_dir),
                    })
                except (PermissionError, OSError):
                    pass
        except PermissionError:
            logger.warning(f"Cannot access: {temp_dir}")

    logger.info(f"Scanned temp files: found {len(results)} items")
    return results


def clean_temp_files(logger: CleanerLogger) -> int:
    """Clean all temporary files. Returns total bytes freed."""
    total_freed = 0
    items = scan_temp_files(logger)
    for item in items:
        path = Path(item["path"])
        freed = _safe_remove(path, logger)
        if freed > 0:
            total_freed += freed
            logger.log("clean_temp", "cleaning", f"Removed: {path}", freed)
    return total_freed


def clean_recycle_bin(logger: CleanerLogger) -> bool:
    """Empty the Windows Recycle Bin."""
    try:
        # SHEmptyRecycleBin flags: SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND
        ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x0007)
        logger.log("clean_recycle_bin", "cleaning", "Recycle Bin emptied")
        return True
    except Exception as e:
        logger.error(f"Failed to empty Recycle Bin: {e}")
        return False


def clean_windows_update_cache(logger: CleanerLogger) -> int:
    """Clean Windows Update download cache."""
    total_freed = 0
    cache_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "SoftwareDistribution" / "Download"
    if cache_dir.exists():
        # Stop Windows Update service first
        try:
            subprocess.run(["net", "stop", "wuauserv"], capture_output=True, timeout=30)
        except Exception:
            pass
        for item in cache_dir.iterdir():
            freed = _safe_remove(item, logger)
            total_freed += freed
        # Restart Windows Update service
        try:
            subprocess.run(["net", "start", "wuauserv"], capture_output=True, timeout=30)
        except Exception:
            pass
        logger.log("clean_wu_cache", "cleaning", "Windows Update cache cleaned", total_freed)
    return total_freed


def clean_dns_cache(logger: CleanerLogger) -> bool:
    """Flush the DNS resolver cache."""
    try:
        result = subprocess.run(
            ["ipconfig", "/flushdns"],
            capture_output=True, text=True, timeout=15,
        )
        success = result.returncode == 0
        logger.log("flush_dns", "cleaning", "DNS cache flushed", success=success)
        return success
    except Exception as e:
        logger.error(f"Failed to flush DNS: {e}")
        return False


def clean_thumbnail_cache(logger: CleanerLogger) -> int:
    """Clean Windows thumbnail cache files."""
    total_freed = 0
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if not local_app_data:
        return 0
    cache_dir = Path(local_app_data) / "Microsoft" / "Windows" / "Explorer"
    if cache_dir.exists():
        for item in cache_dir.glob("thumbcache_*.db"):
            freed = _safe_remove(item, logger)
            total_freed += freed
        logger.log("clean_thumbs", "cleaning", "Thumbnail cache cleaned", total_freed)
    return total_freed


def clean_clipboard(logger: CleanerLogger) -> bool:
    """Clear clipboard history."""
    try:
        ctypes.windll.user32.OpenClipboard(0)
        ctypes.windll.user32.EmptyClipboard()
        ctypes.windll.user32.CloseClipboard()
        logger.log("clean_clipboard", "cleaning", "Clipboard cleared")
        return True
    except Exception as e:
        logger.error(f"Failed to clear clipboard: {e}")
        return False


def clean_old_logs(logger: CleanerLogger) -> int:
    """Remove old Windows log files."""
    total_freed = 0
    log_dirs = [
        Path(os.environ.get("WINDIR", r"C:\Windows")) / "Logs",
        Path(os.environ.get("WINDIR", r"C:\Windows")) / "Debug",
    ]
    for log_dir in log_dirs:
        if not log_dir.exists():
            continue
        for item in log_dir.rglob("*.log"):
            if _is_protected(item):
                continue
            try:
                # Only remove logs older than 30 days
                import time
                age_days = (time.time() - item.stat().st_mtime) / 86400
                if age_days > 30:
                    freed = _safe_remove(item, logger)
                    total_freed += freed
            except (PermissionError, OSError):
                pass
    logger.log("clean_logs", "cleaning", "Old log files cleaned", total_freed)
    return total_freed


def scan_all(logger: CleanerLogger) -> dict:
    """Perform a full scan and return summary of cleanable items."""
    temp = scan_temp_files(logger)
    total_size = sum(item["size"] for item in temp)
    return {
        "temp_files": len(temp),
        "temp_size": total_size,
        "items": temp,
        "categories": {
            "Temporary Files": {"count": len(temp), "size": total_size},
            "DNS Cache": {"count": 1, "size": 0},
            "Thumbnail Cache": {"count": 1, "size": 0},
            "Clipboard": {"count": 1, "size": 0},
        },
    }


def clean_all(logger: CleanerLogger, profile: dict | None = None) -> dict:
    """Run full cleaning based on profile settings. Returns results summary."""
    if profile is None:
        profile = {
            "temp_files": True, "recycle_bin": True, "dns_cache": True,
            "thumbnail_cache": True, "windows_update_cache": False,
            "prefetch": True, "old_logs": True,
        }
    results = {"total_freed": 0, "actions": []}

    if profile.get("temp_files"):
        freed = clean_temp_files(logger)
        results["total_freed"] += freed
        results["actions"].append(("Temp files", freed))

    if profile.get("recycle_bin"):
        clean_recycle_bin(logger)
        results["actions"].append(("Recycle Bin", 0))

    if profile.get("dns_cache"):
        clean_dns_cache(logger)
        results["actions"].append(("DNS Cache", 0))

    if profile.get("thumbnail_cache"):
        freed = clean_thumbnail_cache(logger)
        results["total_freed"] += freed
        results["actions"].append(("Thumbnail Cache", freed))

    if profile.get("windows_update_cache"):
        freed = clean_windows_update_cache(logger)
        results["total_freed"] += freed
        results["actions"].append(("WU Cache", freed))

    if profile.get("old_logs"):
        freed = clean_old_logs(logger)
        results["total_freed"] += freed
        results["actions"].append(("Old Logs", freed))

    clean_clipboard(logger)
    results["actions"].append(("Clipboard", 0))

    return results

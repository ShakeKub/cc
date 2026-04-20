"""Gaming utilities — spoofer for MTA San Andreas and FiveM."""

import os
import secrets
import shutil
from pathlib import Path
from typing import Any
from core.logger import CleanerLogger

# ── MTA San Andreas ──────────────────────────────────────────────────────────

_MTA_REG_ROOTS = [
    r"Software\Multi Theft Auto: San Andreas All\Common\Settings",
    r"Software\Multi Theft Auto: San Andreas All\1.5\Settings",
    r"Software\Multi Theft Auto: San Andreas All\1.6\Settings",
]
_MTA_SERIAL_VALUE = "serial"


def _winreg():
    import winreg as _wr
    return _wr


def get_mta_serial(logger: CleanerLogger) -> dict[str, str]:
    """Return current MTA serials from all known registry locations."""
    if os.name != "nt":
        return {}
    wr = _winreg()
    found: dict[str, str] = {}
    for path in _MTA_REG_ROOTS:
        try:
            key = wr.OpenKey(wr.HKEY_CURRENT_USER, path, 0, wr.KEY_READ)
            try:
                val, _ = wr.QueryValueEx(key, _MTA_SERIAL_VALUE)
                found[path] = str(val)
            except OSError:
                pass
            wr.CloseKey(key)
        except OSError:
            pass
    return found


def set_mta_serial(new_serial: str, logger: CleanerLogger) -> dict[str, bool]:
    """Write new_serial to every MTA registry location that exists."""
    if os.name != "nt":
        return {}
    wr = _winreg()
    results: dict[str, bool] = {}
    for path in _MTA_REG_ROOTS:
        try:
            key = wr.OpenKey(wr.HKEY_CURRENT_USER, path, 0, wr.KEY_SET_VALUE)
            wr.SetValueEx(key, _MTA_SERIAL_VALUE, 0, wr.REG_SZ, new_serial)
            wr.CloseKey(key)
            results[path] = True
            logger.log("mta_spoof", "gaming", f"Set MTA serial at {path}: {new_serial}")
        except OSError:
            results[path] = False
    return results


def generate_mta_serial() -> str:
    """Generate a random valid-looking MTA serial (32 uppercase hex chars)."""
    return secrets.token_hex(16).upper()


def delete_mta_serial(logger: CleanerLogger) -> dict[str, bool]:
    """Delete the serial value — MTA regenerates from hardware on next launch."""
    if os.name != "nt":
        return {}
    wr = _winreg()
    results: dict[str, bool] = {}
    for path in _MTA_REG_ROOTS:
        try:
            key = wr.OpenKey(wr.HKEY_CURRENT_USER, path, 0, wr.KEY_SET_VALUE)
            try:
                wr.DeleteValue(key, _MTA_SERIAL_VALUE)
                results[path] = True
                logger.log("mta_serial_del", "gaming", f"Deleted MTA serial at {path}")
            except OSError:
                results[path] = False
            wr.CloseKey(key)
        except OSError:
            results[path] = False
    return results


# ── FiveM / CitizenFX ────────────────────────────────────────────────────────

_FIVEM_LOCAL   = Path(os.environ.get("LOCALAPPDATA", "")) / "FiveM"
_CITFX_APPDATA = Path(os.environ.get("APPDATA", ""))      / "CitizenFX"

_FIVEM_CACHE_DIRS = [
    _FIVEM_LOCAL / "FiveM.app" / "data" / "cache",
    _FIVEM_LOCAL / "FiveM.app" / "data" / "game-storage",
    _FIVEM_LOCAL / "FiveM.app" / "data" / "nui-storage",
    _FIVEM_LOCAL / "FiveM.app" / "data" / "server-cache",
    _FIVEM_LOCAL / "FiveM.app" / "data" / "server-cache-priv",
]

_FIVEM_ID_FILES = [
    _CITFX_APPDATA / "ros_id.dat",
    _CITFX_APPDATA / "ros_auth.dat",
    _FIVEM_LOCAL   / "FiveM.app" / "data" / "game-storage" / "game_storage.db",
    _FIVEM_LOCAL   / "FiveM.app" / "data" / "game-storage" / "game_storage.db-wal",
    _FIVEM_LOCAL   / "FiveM.app" / "data" / "game-storage" / "game_storage.db-shm",
]


def get_fivem_info() -> dict[str, Any]:
    """Return FiveM installation paths and whether identity files exist."""
    return {
        "installed":     _FIVEM_LOCAL.exists(),
        "app_dir":       str(_FIVEM_LOCAL),
        "citfx_dir":     str(_CITFX_APPDATA),
        "ros_id_exists": (_CITFX_APPDATA / "ros_id.dat").exists(),
        "cache_dirs":    [str(d) for d in _FIVEM_CACHE_DIRS if d.exists()],
        "id_files":      [str(f) for f in _FIVEM_ID_FILES if f.exists()],
    }


def clear_fivem_identity(logger: CleanerLogger) -> dict[str, Any]:
    """
    Remove FiveM cached identity tokens and game-storage cache.
    Does NOT touch FiveM.exe or downloaded resources.
    """
    removed_files = 0
    removed_dirs  = 0
    errors: list[str] = []

    for f in _FIVEM_ID_FILES:
        try:
            if f.exists():
                f.unlink()
                removed_files += 1
                logger.log("fivem_spoof", "gaming", f"Removed: {f}")
        except OSError as e:
            errors.append(str(e))

    for cache_dir in _FIVEM_CACHE_DIRS:
        if not cache_dir.exists():
            continue
        for child in cache_dir.iterdir():
            try:
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                    removed_dirs += 1
                else:
                    child.unlink()
                    removed_files += 1
            except OSError as e:
                errors.append(str(e))

    logger.log("fivem_spoof_done", "gaming",
               f"FiveM identity cleared: {removed_files} files, {removed_dirs} dirs removed")
    return {"removed_files": removed_files, "removed_dirs": removed_dirs, "errors": errors}


def clear_fivem_full_cache(logger: CleanerLogger) -> dict[str, Any]:
    """Full FiveM cache wipe — identity + all downloaded server resource cache."""
    result = clear_fivem_identity(logger)

    extra_dirs = [
        _FIVEM_LOCAL / "FiveM.app" / "data" / "server-cache",
        _FIVEM_LOCAL / "FiveM.app" / "data" / "server-cache-priv",
    ]
    for d in extra_dirs:
        if d.exists():
            for child in d.iterdir():
                try:
                    if child.is_dir():
                        shutil.rmtree(child, ignore_errors=True)
                        result["removed_dirs"] += 1
                    else:
                        child.unlink()
                        result["removed_files"] += 1
                except OSError as e:
                    result["errors"].append(str(e))

    logger.log("fivem_full_cache", "gaming",
               f"FiveM full cache cleared: {result['removed_files']} files")
    return result

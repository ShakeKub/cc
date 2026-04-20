"""Gaming utilities — spoofer for MTA San Andreas and FiveM."""

import os
import secrets
import shutil
from pathlib import Path
from typing import Any
from core.logger import CleanerLogger

# ── MTA San Andreas ──────────────────────────────────────────────────────────

# Root keys to search — both HKCU and HKLM, both 32/64-bit views
_MTA_REG_BASE   = r"Software\Multi Theft Auto: San Andreas All"
_MTA_SERIAL_VALUE = "serial"


def _winreg():
    import winreg as _wr
    return _wr


def _mta_find_serial_locations() -> list[tuple]:
    """
    Recursively walk every subkey under the MTA root in both HKCU and HKLM
    and return (hive, full_subkey_path) for every key that contains a 'serial' value.
    """
    if os.name != "nt":
        return []
    wr = _winreg()
    found: list[tuple] = []

    hives = [
        (wr.HKEY_CURRENT_USER, "HKCU"),
        (wr.HKEY_LOCAL_MACHINE, "HKLM"),
    ]
    flags_list = [wr.KEY_READ, wr.KEY_READ | wr.KEY_WOW64_32KEY]

    def _recurse(hive, path: str):
        for flags in flags_list:
            try:
                key = wr.OpenKey(hive, path, 0, flags)
            except OSError:
                continue
            # Check for serial value in this key
            try:
                wr.QueryValueEx(key, _MTA_SERIAL_VALUE)
                if (hive, path) not in found:
                    found.append((hive, path))
            except OSError:
                pass
            # Recurse into subkeys
            i = 0
            while True:
                try:
                    subname = wr.EnumKey(key, i)
                    i += 1
                    _recurse(hive, f"{path}\\{subname}")
                except OSError:
                    break
            wr.CloseKey(key)

    for hive, _ in hives:
        _recurse(hive, _MTA_REG_BASE)

    return found


def get_mta_serial(logger: CleanerLogger) -> dict[str, str]:
    """
    Return current MTA serials discovered by scanning the full registry tree.
    Returns {full_key_path: serial_value}.
    """
    if os.name != "nt":
        return {}
    wr = _winreg()
    result: dict[str, str] = {}
    for hive, path in _mta_find_serial_locations():
        try:
            key = wr.OpenKey(hive, path, 0, wr.KEY_READ)
            val, _ = wr.QueryValueEx(key, _MTA_SERIAL_VALUE)
            wr.CloseKey(key)
            hive_name = "HKCU" if hive == wr.HKEY_CURRENT_USER else "HKLM"
            result[f"{hive_name}\\{path}"] = str(val)
        except OSError:
            pass
    return result


def set_mta_serial(new_serial: str, logger: CleanerLogger) -> dict[str, bool]:
    """
    Write new_serial to every MTA location that currently holds a serial.
    If no serial exists yet, write it to the most likely default location.
    """
    if os.name != "nt":
        return {}
    wr = _winreg()
    locations = _mta_find_serial_locations()

    # If MTA has never been launched, serial doesn't exist yet —
    # pre-write it to the expected 1.6 path so MTA picks it up.
    if not locations:
        fallback = rf"{_MTA_REG_BASE}\1.6\Settings"
        try:
            key = wr.CreateKeyEx(wr.HKEY_CURRENT_USER, fallback, 0, wr.KEY_SET_VALUE)
            wr.SetValueEx(key, _MTA_SERIAL_VALUE, 0, wr.REG_SZ, new_serial)
            wr.CloseKey(key)
            logger.log("mta_spoof", "gaming", f"Pre-wrote MTA serial at {fallback}: {new_serial}")
            return {f"HKCU\\{fallback}": True}
        except OSError as e:
            logger.error(f"set_mta_serial fallback failed: {e}")
            return {}

    results: dict[str, bool] = {}
    for hive, path in locations:
        hive_name = "HKCU" if hive == wr.HKEY_CURRENT_USER else "HKLM"
        try:
            key = wr.OpenKey(hive, path, 0, wr.KEY_SET_VALUE)
            wr.SetValueEx(key, _MTA_SERIAL_VALUE, 0, wr.REG_SZ, new_serial)
            wr.CloseKey(key)
            results[f"{hive_name}\\{path}"] = True
            logger.log("mta_spoof", "gaming", f"Set MTA serial at {hive_name}\\{path}: {new_serial}")
        except OSError as e:
            results[f"{hive_name}\\{path}"] = False
            logger.error(f"set_mta_serial error at {path}: {e}")
    return results


def generate_mta_serial() -> str:
    """Generate a random valid-looking MTA serial (32 uppercase hex chars)."""
    return secrets.token_hex(16).upper()


def delete_mta_serial(logger: CleanerLogger) -> dict[str, bool]:
    """Delete the serial value from all found locations — MTA regenerates on next launch."""
    if os.name != "nt":
        return {}
    wr = _winreg()
    results: dict[str, bool] = {}
    for hive, path in _mta_find_serial_locations():
        hive_name = "HKCU" if hive == wr.HKEY_CURRENT_USER else "HKLM"
        label = f"{hive_name}\\{path}"
        try:
            key = wr.OpenKey(hive, path, 0, wr.KEY_SET_VALUE)
            wr.DeleteValue(key, _MTA_SERIAL_VALUE)
            wr.CloseKey(key)
            results[label] = True
            logger.log("mta_serial_del", "gaming", f"Deleted MTA serial at {label}")
        except OSError as e:
            results[label] = False
            logger.error(f"delete_mta_serial error at {path}: {e}")
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

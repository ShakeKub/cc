"""Registry cleaner - scan, fix, backup, restore invalid entries."""

import json
import os
import subprocess
import winreg
from datetime import datetime
from pathlib import Path
from typing import Any
from core.logger import CleanerLogger


# Registry locations to scan for invalid entries
SCAN_LOCATIONS = [
    # Shared DLLs
    (winreg.HKEY_LOCAL_MACHINE,
     r"SOFTWARE\Microsoft\Windows\CurrentVersion\SharedDLLs",
     "shared_dlls"),
    # File extensions
    (winreg.HKEY_CLASSES_ROOT, "", "file_associations"),
    # App Paths
    (winreg.HKEY_LOCAL_MACHINE,
     r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
     "app_paths"),
    # Uninstall entries
    (winreg.HKEY_LOCAL_MACHINE,
     r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
     "uninstall"),
    (winreg.HKEY_CURRENT_USER,
     r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
     "uninstall_user"),
    # MUI Cache
    (winreg.HKEY_CURRENT_USER,
     r"SOFTWARE\Classes\Local Settings\Software\Microsoft\Windows\Shell\MuiCache",
     "mui_cache"),
]

RISK_LEVELS = {
    "shared_dlls": "medium",
    "file_associations": "low",
    "app_paths": "low",
    "uninstall": "medium",
    "uninstall_user": "low",
    "mui_cache": "low",
}


def scan_invalid_entries(logger: CleanerLogger,
                         progress_callback=None) -> list[dict[str, Any]]:
    """Scan registry for invalid entries (broken paths, missing files)."""
    invalid = []
    total_scanned = 0

    for hive, key_path, category in SCAN_LOCATIONS:
        try:
            if category == "shared_dlls":
                invalid.extend(_scan_shared_dlls(hive, key_path, logger))
            elif category == "app_paths":
                invalid.extend(_scan_app_paths(hive, key_path, logger))
            elif category in ("uninstall", "uninstall_user"):
                invalid.extend(_scan_uninstall_entries(hive, key_path, logger))
            elif category == "mui_cache":
                invalid.extend(_scan_mui_cache(hive, key_path, logger))
            elif category == "file_associations":
                invalid.extend(_scan_file_associations(hive, logger))

            total_scanned += 1
            if progress_callback:
                progress_callback(total_scanned, len(SCAN_LOCATIONS))
        except Exception as e:
            logger.error(f"Error scanning {category}: {e}")

    logger.info(f"Registry scan complete: {len(invalid)} invalid entries found")
    return invalid


def _scan_shared_dlls(hive, key_path: str, logger: CleanerLogger) -> list[dict]:
    """Find SharedDLLs entries pointing to non-existent files."""
    invalid = []
    try:
        key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
        i = 0
        while True:
            try:
                name, value, _ = winreg.EnumValue(key, i)
                if not Path(name).exists():
                    invalid.append({
                        "category": "Shared DLLs",
                        "key_path": f"HKLM\\{key_path}",
                        "value_name": name,
                        "value_data": str(value),
                        "issue": f"File not found: {name}",
                        "risk": "medium",
                        "hive": hive,
                        "full_key": key_path,
                    })
                i += 1
            except OSError:
                break
        winreg.CloseKey(key)
    except OSError:
        pass
    return invalid


def _scan_app_paths(hive, key_path: str, logger: CleanerLogger) -> list[dict]:
    """Find App Paths entries pointing to non-existent executables."""
    invalid = []
    try:
        key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
        i = 0
        while True:
            try:
                subkey_name = winreg.EnumKey(key, i)
                subkey = winreg.OpenKey(key, subkey_name)
                try:
                    exe_path, _ = winreg.QueryValueEx(subkey, "")
                    if exe_path and not Path(exe_path.strip('"')).exists():
                        invalid.append({
                            "category": "App Paths",
                            "key_path": f"HKLM\\{key_path}\\{subkey_name}",
                            "value_name": "(Default)",
                            "value_data": exe_path,
                            "issue": f"Executable not found: {exe_path}",
                            "risk": "low",
                            "hive": hive,
                            "full_key": f"{key_path}\\{subkey_name}",
                        })
                except (FileNotFoundError, OSError):
                    pass
                winreg.CloseKey(subkey)
                i += 1
            except OSError:
                break
        winreg.CloseKey(key)
    except OSError:
        pass
    return invalid


def _scan_uninstall_entries(hive, key_path: str, logger: CleanerLogger) -> list[dict]:
    """Find uninstall entries with invalid paths."""
    invalid = []
    hive_name = "HKLM" if hive == winreg.HKEY_LOCAL_MACHINE else "HKCU"
    try:
        key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
        i = 0
        while True:
            try:
                subkey_name = winreg.EnumKey(key, i)
                subkey = winreg.OpenKey(key, subkey_name)
                try:
                    uninstall_str, _ = winreg.QueryValueEx(subkey, "UninstallString")
                    exe = uninstall_str.strip('"').split('"')[0].split(" ")[0]
                    if exe and not Path(exe).exists() and not exe.lower().startswith("msiexec"):
                        name = ""
                        try:
                            name, _ = winreg.QueryValueEx(subkey, "DisplayName")
                        except (FileNotFoundError, OSError):
                            name = subkey_name
                        invalid.append({
                            "category": "Uninstall Entries",
                            "key_path": f"{hive_name}\\{key_path}\\{subkey_name}",
                            "value_name": name or subkey_name,
                            "value_data": uninstall_str,
                            "issue": f"Uninstaller not found: {exe}",
                            "risk": "medium",
                            "hive": hive,
                            "full_key": f"{key_path}\\{subkey_name}",
                        })
                except (FileNotFoundError, OSError):
                    pass
                winreg.CloseKey(subkey)
                i += 1
            except OSError:
                break
        winreg.CloseKey(key)
    except OSError:
        pass
    return invalid


def _scan_mui_cache(hive, key_path: str, logger: CleanerLogger) -> list[dict]:
    """Find MUI cache entries for non-existent files."""
    invalid = []
    try:
        key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
        i = 0
        while True:
            try:
                name, value, _ = winreg.EnumValue(key, i)
                # MUI cache names often contain file paths
                if name and "." in name and not name.startswith("@"):
                    filepath = name.split(".")[0] + "." + name.split(".")[1]
                    if not Path(filepath).exists():
                        invalid.append({
                            "category": "MUI Cache",
                            "key_path": f"HKCU\\{key_path}",
                            "value_name": name,
                            "value_data": str(value),
                            "issue": "Cached entry for missing application",
                            "risk": "low",
                            "hive": hive,
                            "full_key": key_path,
                        })
                i += 1
            except OSError:
                break
        winreg.CloseKey(key)
    except OSError:
        pass
    return invalid


def _scan_file_associations(hive, logger: CleanerLogger) -> list[dict]:
    """Find file associations pointing to non-existent handlers."""
    invalid = []
    try:
        key = winreg.OpenKey(hive, "", 0, winreg.KEY_READ)
        i = 0
        checked = 0
        while checked < 500:  # Limit scan depth
            try:
                subkey_name = winreg.EnumKey(key, i)
                i += 1
                if not subkey_name.startswith("."):
                    continue
                checked += 1
                # Check the associated program
                try:
                    subkey = winreg.OpenKey(key, subkey_name)
                    default_val, _ = winreg.QueryValueEx(subkey, "")
                    if default_val:
                        try:
                            prog_key = winreg.OpenKey(hive, f"{default_val}\\shell\\open\\command")
                            cmd, _ = winreg.QueryValueEx(prog_key, "")
                            exe = cmd.strip('"').split('"')[0].split(" ")[0]
                            if exe and not Path(exe).exists() and "%" not in exe:
                                invalid.append({
                                    "category": "File Associations",
                                    "key_path": f"HKCR\\{subkey_name}",
                                    "value_name": subkey_name,
                                    "value_data": cmd,
                                    "issue": f"Handler not found: {exe}",
                                    "risk": "low",
                                    "hive": hive,
                                    "full_key": subkey_name,
                                })
                            winreg.CloseKey(prog_key)
                        except OSError:
                            pass
                    winreg.CloseKey(subkey)
                except OSError:
                    pass
            except OSError:
                break
        winreg.CloseKey(key)
    except OSError:
        pass
    return invalid


def backup_registry(backup_dir: str = "backups", logger: CleanerLogger | None = None) -> str:
    """Create a full registry backup using reg.exe export."""
    backup_path = Path(backup_dir)
    backup_path.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_path / f"registry_backup_{timestamp}.reg"

    try:
        result = subprocess.run(
            ["reg", "export", "HKLM", str(backup_file), "/y"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            if logger:
                logger.log("backup_registry", "registry",
                          f"Registry backed up to: {backup_file}")
            return str(backup_file)
    except Exception as e:
        if logger:
            logger.error(f"Registry backup failed: {e}")

    return ""


def restore_registry(backup_file: str, logger: CleanerLogger) -> bool:
    """Restore registry from a backup file."""
    if not Path(backup_file).exists():
        logger.error(f"Backup file not found: {backup_file}")
        return False
    try:
        result = subprocess.run(
            ["reg", "import", backup_file],
            capture_output=True, text=True, timeout=120,
        )
        success = result.returncode == 0
        if success:
            logger.log("restore_registry", "registry", f"Registry restored from: {backup_file}")
        else:
            logger.error(f"Registry restore failed: {result.stderr}")
        return success
    except Exception as e:
        logger.error(f"Registry restore error: {e}")
        return False


def fix_invalid_entry(entry: dict, logger: CleanerLogger) -> bool:
    """Remove a single invalid registry entry."""
    try:
        if entry.get("category") == "Shared DLLs":
            key = winreg.OpenKey(entry["hive"], entry["full_key"], 0, winreg.KEY_WRITE)
            winreg.DeleteValue(key, entry["value_name"])
            winreg.CloseKey(key)
        elif entry.get("category") == "MUI Cache":
            key = winreg.OpenKey(entry["hive"], entry["full_key"], 0, winreg.KEY_WRITE)
            winreg.DeleteValue(key, entry["value_name"])
            winreg.CloseKey(key)
        else:
            # For subkey-based entries, delete the entire subkey
            winreg.DeleteKey(entry["hive"], entry["full_key"])

        logger.log("fix_registry", "registry",
                  f"Removed invalid entry: {entry['value_name']}", risk_level=entry["risk"])
        return True
    except OSError as e:
        logger.error(f"Cannot fix registry entry: {entry['value_name']} - {e}")
        return False


def fix_all_invalid(entries: list[dict], logger: CleanerLogger,
                    auto_backup: bool = True) -> dict[str, int]:
    """Fix all invalid registry entries. Returns counts."""
    if auto_backup:
        backup_registry(logger=logger)

    results = {"fixed": 0, "failed": 0, "skipped": 0}
    for entry in entries:
        if entry.get("risk") == "high":
            results["skipped"] += 1
            continue
        if fix_invalid_entry(entry, logger):
            results["fixed"] += 1
        else:
            results["failed"] += 1

    return results

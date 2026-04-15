"""Startup manager - view, enable/disable, detect suspicious entries."""

import os
import winreg
from pathlib import Path
from typing import Any
from core.logger import CleanerLogger


# Registry locations for startup entries
STARTUP_REG_KEYS = [
    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run", "HKCU"),
    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce", "HKCU"),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run", "HKLM"),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce", "HKLM"),
]

# Startup folders
STARTUP_FOLDERS = [
    lambda: Path(os.environ.get("APPDATA", "")) /
            "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup",
    lambda: Path(os.environ.get("PROGRAMDATA", "")) /
            "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup",
]

# Known safe startup entries (by publisher or name pattern)
KNOWN_SAFE = {
    "securityhealthsystray", "windowsdefender", "realtek", "nvidia",
    "intel", "windows security", "onedrive",
}

# Suspicious indicators
SUSPICIOUS_INDICATORS = [
    "temp", "tmp", "appdata\\local\\temp", "downloads\\",
    ".vbs", ".bat", ".cmd", ".ps1", "powershell -e",
    "regsvr32", "mshta", "wscript", "cscript",
]


def get_startup_entries(logger: CleanerLogger) -> list[dict[str, Any]]:
    """Get all startup entries from registry and startup folders."""
    entries = []

    # Registry entries
    for hive, key_path, hive_name in STARTUP_REG_KEYS:
        try:
            key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
            i = 0
            while True:
                try:
                    name, value, val_type = winreg.EnumValue(key, i)
                    impact = _estimate_impact(value)
                    suspicious = _check_suspicious(name, value)
                    entries.append({
                        "name": name,
                        "command": value,
                        "location": f"{hive_name}\\{key_path}",
                        "type": "registry",
                        "enabled": True,
                        "impact": impact,
                        "suspicious": suspicious,
                        "hive": hive,
                        "key_path": key_path,
                    })
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(key)
        except OSError:
            pass

    # Startup folder entries
    for folder_fn in STARTUP_FOLDERS:
        folder = folder_fn()
        if folder.exists():
            for item in folder.iterdir():
                if item.is_file() and item.suffix in (".lnk", ".exe", ".bat", ".cmd"):
                    impact = _estimate_impact(str(item))
                    suspicious = _check_suspicious(item.name, str(item))
                    entries.append({
                        "name": item.stem,
                        "command": str(item),
                        "location": str(folder),
                        "type": "folder",
                        "enabled": True,
                        "impact": impact,
                        "suspicious": suspicious,
                    })

    # Check disabled entries (stored in Approved registry)
    disabled_key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
    for hive, hive_name in [(winreg.HKEY_CURRENT_USER, "HKCU"),
                             (winreg.HKEY_LOCAL_MACHINE, "HKLM")]:
        try:
            key = winreg.OpenKey(hive, disabled_key, 0, winreg.KEY_READ)
            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, i)
                    # Check if disabled (first bytes indicate status)
                    if isinstance(value, bytes) and len(value) >= 4:
                        is_enabled = value[0] in (0x02, 0x06)
                        # Update corresponding entry
                        for entry in entries:
                            if entry["name"] == name and hive_name in entry.get("location", ""):
                                entry["enabled"] = is_enabled
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(key)
        except OSError:
            pass

    logger.info(f"Found {len(entries)} startup entries")
    return entries


def _estimate_impact(command: str) -> str:
    """Estimate the startup impact level of a program."""
    cmd_lower = command.lower()
    # High impact: heavy apps
    high_impact = ["steam", "discord", "teams", "skype", "spotify", "onedrive",
                   "adobe", "java", "update"]
    if any(h in cmd_lower for h in high_impact):
        return "high"
    # Low impact: system utilities
    low_impact = ["security", "defender", "audio", "touchpad", "bluetooth"]
    if any(l in cmd_lower for l in low_impact):
        return "low"
    return "medium"


def _check_suspicious(name: str, command: str) -> bool:
    """Check if a startup entry looks suspicious."""
    combined = (name + " " + command).lower()
    # Safe entries
    if any(safe in combined for safe in KNOWN_SAFE):
        return False
    # Check suspicious indicators
    return any(indicator in combined for indicator in SUSPICIOUS_INDICATORS)


def disable_startup_entry(entry: dict, logger: CleanerLogger) -> bool:
    """Disable a startup entry by modifying the Approved registry."""
    if entry["type"] != "registry":
        # For folder entries, rename the file
        path = Path(entry["command"])
        if path.exists():
            try:
                disabled_path = path.with_suffix(path.suffix + ".disabled")
                path.rename(disabled_path)
                logger.log("disable_startup", "startup",
                          f"Disabled: {entry['name']}")
                return True
            except OSError as e:
                logger.error(f"Cannot disable {entry['name']}: {e}")
                return False
        return False

    # For registry entries, set the disabled flag in StartupApproved
    hive_name = "HKCU" if "HKCU" in entry["location"] else "HKLM"
    hive = winreg.HKEY_CURRENT_USER if hive_name == "HKCU" else winreg.HKEY_LOCAL_MACHINE
    approved_key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"

    try:
        key = winreg.OpenKey(hive, approved_key, 0, winreg.KEY_WRITE)
        # Disabled flag: 0x03 followed by zeros then timestamp
        disabled_data = b'\x03' + b'\x00' * 11
        winreg.SetValueEx(key, entry["name"], 0, winreg.REG_BINARY, disabled_data)
        winreg.CloseKey(key)
        logger.log("disable_startup", "startup", f"Disabled: {entry['name']}")
        return True
    except OSError as e:
        logger.error(f"Cannot disable {entry['name']}: {e}")
        return False


def enable_startup_entry(entry: dict, logger: CleanerLogger) -> bool:
    """Re-enable a disabled startup entry."""
    if entry["type"] != "registry":
        # For folder entries, rename back
        name = entry["name"]
        parent = Path(entry["location"])
        for item in parent.iterdir():
            if item.stem.startswith(name) and item.suffix == ".disabled":
                try:
                    original = item.with_suffix("")
                    item.rename(original)
                    logger.log("enable_startup", "startup", f"Enabled: {name}")
                    return True
                except OSError:
                    pass
        return False

    hive_name = "HKCU" if "HKCU" in entry["location"] else "HKLM"
    hive = winreg.HKEY_CURRENT_USER if hive_name == "HKCU" else winreg.HKEY_LOCAL_MACHINE
    approved_key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"

    try:
        key = winreg.OpenKey(hive, approved_key, 0, winreg.KEY_WRITE)
        enabled_data = b'\x02' + b'\x00' * 11
        winreg.SetValueEx(key, entry["name"], 0, winreg.REG_BINARY, enabled_data)
        winreg.CloseKey(key)
        logger.log("enable_startup", "startup", f"Enabled: {entry['name']}")
        return True
    except OSError as e:
        logger.error(f"Cannot enable {entry['name']}: {e}")
        return False


def remove_startup_entry(entry: dict, logger: CleanerLogger) -> bool:
    """Completely remove a startup entry."""
    if entry["type"] == "folder":
        path = Path(entry["command"])
        try:
            if path.exists():
                path.unlink()
            logger.log("remove_startup", "startup", f"Removed: {entry['name']}")
            return True
        except OSError as e:
            logger.error(f"Cannot remove {entry['name']}: {e}")
            return False

    # Remove from registry
    try:
        key = winreg.OpenKey(entry["hive"], entry["key_path"], 0, winreg.KEY_WRITE)
        winreg.DeleteValue(key, entry["name"])
        winreg.CloseKey(key)
        logger.log("remove_startup", "startup", f"Removed: {entry['name']}")
        return True
    except OSError as e:
        logger.error(f"Cannot remove {entry['name']}: {e}")
        return False

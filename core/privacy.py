"""Privacy & security - telemetry, tracking, secure deletion, suspicious files."""

import os
import subprocess
import winreg
from pathlib import Path
from typing import Any
from core.logger import CleanerLogger


# Windows telemetry registry settings
TELEMETRY_SETTINGS = {
    "AllowTelemetry": {
        "key": r"SOFTWARE\Policies\Microsoft\Windows\DataCollection",
        "hive": winreg.HKEY_LOCAL_MACHINE,
        "type": winreg.REG_DWORD,
        "disabled_value": 0,
        "enabled_value": 3,
        "description": "Windows diagnostic data collection level",
    },
    "DisableAdvertisingId": {
        "key": r"SOFTWARE\Microsoft\Windows\CurrentVersion\AdvertisingInfo",
        "hive": winreg.HKEY_CURRENT_USER,
        "type": winreg.REG_DWORD,
        "disabled_value": 0,
        "enabled_value": 1,
        "description": "Advertising ID for app personalization",
        "value_name": "Enabled",
    },
    "DisableWebSearch": {
        "key": r"SOFTWARE\Policies\Microsoft\Windows\Explorer",
        "hive": winreg.HKEY_CURRENT_USER,
        "type": winreg.REG_DWORD,
        "disabled_value": 1,
        "enabled_value": 0,
        "description": "Web search in Start Menu",
        "value_name": "DisableSearchBoxSuggestions",
    },
    "DisableActivityHistory": {
        "key": r"SOFTWARE\Policies\Microsoft\Windows\System",
        "hive": winreg.HKEY_LOCAL_MACHINE,
        "type": winreg.REG_DWORD,
        "disabled_value": 0,
        "enabled_value": 1,
        "description": "Activity History (Timeline)",
        "value_name": "EnableActivityFeed",
    },
    "DisableLocationTracking": {
        "key": r"SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\location",
        "hive": winreg.HKEY_CURRENT_USER,
        "type": winreg.REG_SZ,
        "disabled_value": "Deny",
        "enabled_value": "Allow",
        "description": "Location access for apps",
        "value_name": "Value",
    },
}

# Known tracking file locations
TRACKING_LOCATIONS = [
    # Recent files
    lambda: Path(os.environ.get("APPDATA", "")) /
            "Microsoft" / "Windows" / "Recent",
    # Jump lists
    lambda: Path(os.environ.get("APPDATA", "")) /
            "Microsoft" / "Windows" / "Recent" / "AutomaticDestinations",
    lambda: Path(os.environ.get("APPDATA", "")) /
            "Microsoft" / "Windows" / "Recent" / "CustomDestinations",
    # Activity timeline
    lambda: Path(os.environ.get("LOCALAPPDATA", "")) /
            "ConnectedDevicesPlatform",
    # Diagnostic data
    lambda: Path(os.environ.get("LOCALAPPDATA", "")) /
            "Diagnostics",
]

# Suspicious file patterns (heuristic detection)
SUSPICIOUS_PATTERNS = {
    "extensions": [".scr", ".pif", ".com", ".vbs", ".wsf", ".hta"],
    "double_extensions": True,
    "hidden_exe_in_temp": True,
    "unsigned_in_system": True,
}


def get_telemetry_status(logger: CleanerLogger) -> list[dict[str, Any]]:
    """Get current status of all telemetry settings."""
    results = []
    for name, config in TELEMETRY_SETTINGS.items():
        value_name = config.get("value_name", name)
        current_value = None
        enabled = True

        try:
            key = winreg.OpenKey(config["hive"], config["key"], 0, winreg.KEY_READ)
            current_value, _ = winreg.QueryValueEx(key, value_name)
            winreg.CloseKey(key)
            enabled = current_value != config["disabled_value"]
        except (FileNotFoundError, OSError):
            enabled = True  # Default is typically enabled

        results.append({
            "name": name,
            "description": config["description"],
            "enabled": enabled,
            "current_value": current_value,
        })

    return results


def disable_telemetry(setting_name: str, logger: CleanerLogger) -> bool:
    """Disable a specific telemetry setting."""
    config = TELEMETRY_SETTINGS.get(setting_name)
    if not config:
        return False

    value_name = config.get("value_name", setting_name)
    try:
        # Create key if it doesn't exist
        key = winreg.CreateKeyEx(config["hive"], config["key"], 0, winreg.KEY_WRITE)
        winreg.SetValueEx(key, value_name, 0, config["type"], config["disabled_value"])
        winreg.CloseKey(key)
        logger.log("disable_telemetry", "privacy",
                  f"Disabled: {config['description']}")
        return True
    except OSError as e:
        logger.error(f"Cannot disable {setting_name}: {e}")
        return False


def enable_telemetry(setting_name: str, logger: CleanerLogger) -> bool:
    """Re-enable a telemetry setting."""
    config = TELEMETRY_SETTINGS.get(setting_name)
    if not config:
        return False

    value_name = config.get("value_name", setting_name)
    try:
        key = winreg.CreateKeyEx(config["hive"], config["key"], 0, winreg.KEY_WRITE)
        winreg.SetValueEx(key, value_name, 0, config["type"], config["enabled_value"])
        winreg.CloseKey(key)
        logger.log("enable_telemetry", "privacy",
                  f"Enabled: {config['description']}")
        return True
    except OSError as e:
        logger.error(f"Cannot enable {setting_name}: {e}")
        return False


def scan_tracking_files(logger: CleanerLogger) -> list[dict[str, Any]]:
    """Scan for tracking and activity history files."""
    results = []
    for loc_fn in TRACKING_LOCATIONS:
        loc = loc_fn()
        if loc.exists():
            total_size = 0
            file_count = 0
            try:
                for item in loc.rglob("*"):
                    if item.is_file():
                        try:
                            total_size += item.stat().st_size
                            file_count += 1
                        except (PermissionError, OSError):
                            pass
            except PermissionError:
                pass
            if file_count > 0:
                results.append({
                    "path": str(loc),
                    "files": file_count,
                    "size": total_size,
                    "category": loc.name,
                })

    logger.info(f"Found {len(results)} tracking data locations")
    return results


def clean_tracking_files(logger: CleanerLogger) -> int:
    """Remove tracking and activity history files. Returns bytes freed."""
    import shutil
    total_freed = 0
    for loc_fn in TRACKING_LOCATIONS:
        loc = loc_fn()
        if loc.exists():
            try:
                for item in loc.rglob("*"):
                    if item.is_file():
                        try:
                            size = item.stat().st_size
                            item.unlink()
                            total_freed += size
                        except (PermissionError, OSError):
                            pass
            except PermissionError:
                pass

    logger.log("clean_tracking", "privacy",
              f"Removed tracking files: freed {total_freed} bytes", total_freed)
    return total_freed


def scan_suspicious_files(path: str = None,
                          logger: CleanerLogger | None = None) -> list[dict[str, Any]]:
    """Scan for suspicious files using heuristic detection."""
    suspicious = []
    scan_dirs = []

    if path:
        scan_dirs.append(Path(path))
    else:
        # Default scan locations
        temp = os.environ.get("TEMP", "")
        if temp:
            scan_dirs.append(Path(temp))
        downloads = Path.home() / "Downloads"
        if downloads.exists():
            scan_dirs.append(downloads)

    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        try:
            for item in scan_dir.rglob("*"):
                if not item.is_file():
                    continue
                try:
                    reasons = []
                    name_lower = item.name.lower()

                    # Check suspicious extensions
                    if item.suffix.lower() in SUSPICIOUS_PATTERNS["extensions"]:
                        reasons.append(f"Suspicious extension: {item.suffix}")

                    # Check double extensions (e.g., file.pdf.exe)
                    if SUSPICIOUS_PATTERNS["double_extensions"]:
                        parts = item.name.split(".")
                        if len(parts) > 2 and parts[-1].lower() in ["exe", "scr", "bat", "cmd"]:
                            reasons.append("Double extension detected")

                    # Check hidden executables in temp
                    if SUSPICIOUS_PATTERNS["hidden_exe_in_temp"]:
                        if "temp" in str(scan_dir).lower() and item.suffix.lower() == ".exe":
                            # Check if it's hidden
                            try:
                                import stat
                                if item.stat().st_file_attributes & stat.FILE_ATTRIBUTE_HIDDEN:
                                    reasons.append("Hidden executable in temp directory")
                            except (AttributeError, OSError):
                                pass

                    if reasons:
                        suspicious.append({
                            "path": str(item),
                            "name": item.name,
                            "size": item.stat().st_size,
                            "reasons": reasons,
                            "risk": "high" if len(reasons) > 1 else "medium",
                        })
                except (PermissionError, OSError):
                    pass
        except PermissionError:
            pass

    if logger:
        logger.info(f"Suspicious file scan: found {len(suspicious)} items")
    return suspicious


def secure_delete(filepath: str, passes: int = 3,
                  logger: CleanerLogger | None = None) -> bool:
    """Securely delete a file using DoD 5220.22-M overwrite method."""
    from core.disk import secure_shred
    return secure_shred(filepath, passes, logger)

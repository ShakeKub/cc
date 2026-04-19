"""Windows context menu (right-click) entry manager."""

import os
import subprocess

try:
    import winreg
except ImportError:
    winreg = None


_LOCATIONS: list[tuple[str, str]] = [
    (r"*\shell",                                          "All Files"),
    (r"*\shellex\ContextMenuHandlers",                    "All Files (ext)"),
    (r"Directory\shell",                                  "Folders"),
    (r"Directory\Background\shell",                       "Folder Background"),
    (r"Directory\Background\shellex\ContextMenuHandlers", "Folder Bg (ext)"),
    (r"Drive\shell",                                      "Drives"),
    (r"DesktopBackground\Shell",                          "Desktop"),
]


def _get_command(parent_key, child_name: str) -> str:
    try:
        ck = winreg.OpenKey(parent_key, f"{child_name}\\command", 0, winreg.KEY_READ)
        val, _ = winreg.QueryValueEx(ck, "")
        winreg.CloseKey(ck)
        return str(val)
    except OSError:
        return ""


def get_context_menu_entries(logger=None) -> list[dict]:
    """Return all context menu shell entries visible in HKCR."""
    if not winreg:
        return []
    entries = []
    for sub, location in _LOCATIONS:
        try:
            k = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, sub, 0, winreg.KEY_READ)
        except OSError:
            continue
        i = 0
        while True:
            try:
                child = winreg.EnumKey(k, i)
                i += 1
            except OSError:
                break
            # Keys starting with "-" are disabled (Regedit convention)
            enabled = not child.startswith("-")
            display = child.lstrip("-")
            cmd = _get_command(k, child)
            entries.append({
                "name":     display,
                "raw_name": child,
                "command":  cmd,
                "location": location,
                "reg_sub":  sub,
                "enabled":  enabled,
            })
        winreg.CloseKey(k)
    return entries


def _reg_rename(hkcr_path: str, old_name: str, new_name: str) -> bool:
    """Rename a registry key via reg.exe copy+delete (winreg has no rename)."""
    old_full = f"HKCR\\{hkcr_path}\\{old_name}"
    new_full = f"HKCR\\{hkcr_path}\\{new_name}"
    r1 = subprocess.run(
        ["reg", "copy", old_full, new_full, "/s", "/f"],
        capture_output=True, text=True,
    )
    if r1.returncode != 0:
        return False
    subprocess.run(["reg", "delete", old_full, "/f"], capture_output=True)
    return True


def disable_entry(entry: dict, logger=None) -> bool:
    """Prefix key name with '-' to hide it from the context menu."""
    if not winreg or not entry.get("enabled"):
        return False
    ok = _reg_rename(entry["reg_sub"], entry["raw_name"], "-" + entry["raw_name"])
    if ok and logger:
        logger.log("ctx_disable", "contextmenu", f"entry={entry['name']} loc={entry['location']}")
    return ok


def enable_entry(entry: dict, logger=None) -> bool:
    """Remove leading '-' to re-enable a disabled entry."""
    if not winreg or entry.get("enabled"):
        return False
    new_name = entry["raw_name"].lstrip("-")
    ok = _reg_rename(entry["reg_sub"], entry["raw_name"], new_name)
    if ok and logger:
        logger.log("ctx_enable", "contextmenu", f"entry={entry['name']} loc={entry['location']}")
    return ok


def delete_entry(entry: dict, logger=None) -> bool:
    """Permanently remove a context menu key."""
    if not winreg:
        return False
    full = f"HKCR\\{entry['reg_sub']}\\{entry['raw_name']}"
    r = subprocess.run(["reg", "delete", full, "/f"], capture_output=True)
    if logger:
        logger.log("ctx_delete", "contextmenu", f"entry={entry['name']} loc={entry['location']}")
    return r.returncode == 0

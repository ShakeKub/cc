"""Environment Variables Editor — user and system scope."""

import os
import subprocess
from core.logger import CleanerLogger

_USER_KEY   = r"Environment"
_SYSTEM_KEY = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"


def _winreg():
    import winreg as _wr
    return _wr


def get_env_vars(scope: str = "user") -> list[dict]:
    """Return environment variables for 'user' or 'system' scope."""
    if os.name != "nt":
        return []
    wr = _winreg()
    hive = wr.HKEY_CURRENT_USER if scope == "user" else wr.HKEY_LOCAL_MACHINE
    key_path = _USER_KEY if scope == "user" else _SYSTEM_KEY
    entries = []
    try:
        key = wr.OpenKey(hive, key_path, 0, wr.KEY_READ)
        i = 0
        while True:
            try:
                name, value, vtype = wr.EnumValue(key, i)
                entries.append({"name": name, "value": str(value), "type": vtype, "scope": scope})
                i += 1
            except OSError:
                break
        wr.CloseKey(key)
    except OSError:
        pass
    return sorted(entries, key=lambda x: x["name"].upper())


def set_env_var(name: str, value: str, scope: str, logger: CleanerLogger) -> bool:
    """Create or update an environment variable."""
    if os.name != "nt":
        return False
    wr = _winreg()
    hive = wr.HKEY_CURRENT_USER if scope == "user" else wr.HKEY_LOCAL_MACHINE
    key_path = _USER_KEY if scope == "user" else _SYSTEM_KEY
    try:
        key = wr.OpenKey(hive, key_path, 0, wr.KEY_SET_VALUE)
        vtype = wr.REG_EXPAND_SZ if "%" in value else wr.REG_SZ
        wr.SetValueEx(key, name, 0, vtype, value)
        wr.CloseKey(key)
        _broadcast_env_change()
        logger.log("set_env_var", "envvars", f"Set {scope} var: {name}={value}")
        return True
    except OSError as e:
        logger.error(f"set_env_var error: {e}")
        return False


def delete_env_var(name: str, scope: str, logger: CleanerLogger) -> bool:
    """Delete an environment variable."""
    if os.name != "nt":
        return False
    wr = _winreg()
    hive = wr.HKEY_CURRENT_USER if scope == "user" else wr.HKEY_LOCAL_MACHINE
    key_path = _USER_KEY if scope == "user" else _SYSTEM_KEY
    try:
        key = wr.OpenKey(hive, key_path, 0, wr.KEY_SET_VALUE)
        wr.DeleteValue(key, name)
        wr.CloseKey(key)
        _broadcast_env_change()
        logger.log("del_env_var", "envvars", f"Deleted {scope} var: {name}")
        return True
    except OSError as e:
        logger.error(f"del_env_var error: {e}")
        return False


def _broadcast_env_change():
    """Notify running programs that environment has changed."""
    try:
        import ctypes
        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        SMTO_ABORTIFHUNG = 0x0002
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment",
            SMTO_ABORTIFHUNG, 5000, None,
        )
    except Exception:
        pass

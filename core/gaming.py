"""Gaming utilities — spoofer for MTA San Andreas and FiveM."""

import os
import re
import secrets
import shutil
from pathlib import Path
from typing import Any
from core.logger import CleanerLogger

# ── MTA San Andreas ──────────────────────────────────────────────────────────

_MTA_REG_BASE     = r"Software\Multi Theft Auto: San Andreas All"
_MTA_SERIAL_VALUE = "serial"

# All directories where MTA may store coreconfig.xml
_MTA_APPDATA_ROOT = Path(os.environ.get("APPDATA",      "")) / "MTA San Andreas All"
_MTA_LOCAL_ROOT   = Path(os.environ.get("LOCALAPPDATA", "")) / "MTA San Andreas All"
_MTA_PROGDATA_ROOT = Path(os.environ.get("PROGRAMDATA",  r"C:\ProgramData")) / "MTA San Andreas All"


def _winreg():
    import winreg as _wr
    return _wr


# ── process discovery ────────────────────────────────────────

def find_mta_processes() -> list[dict]:
    """Return all running processes whose name or path looks like MTA."""
    try:
        import psutil
    except ImportError:
        return []
    procs = []
    keywords = ("mta", "Multi Theft Auto", "gta_sa", "gta-sa")
    for proc in psutil.process_iter(["pid", "name", "exe"]):
        try:
            name = proc.info["name"] or ""
            exe  = proc.info["exe"]  or ""
            if any(k.lower() in name.lower() or k.lower() in exe.lower()
                   for k in keywords):
                procs.append({
                    "pid":  proc.info["pid"],
                    "name": name,
                    "exe":  exe,
                    "install_dir": str(Path(exe).parent) if exe else "",
                })
        except Exception:
            pass
    return procs


def get_mta_install_dir_from_process() -> str:
    """
    Return the MTA installation directory by inspecting the running process.
    Returns empty string if MTA is not running.
    """
    procs = find_mta_processes()
    for p in procs:
        if p["install_dir"]:
            return p["install_dir"]
    return ""


# ── config-file serial (coreconfig.xml) ─────────────────────

def _find_coreconfig_files() -> list[Path]:
    """
    Return all coreconfig.xml paths by searching every location MTA might use:
    - %APPDATA%\\MTA San Andreas All\\
    - %LOCALAPPDATA%\\MTA San Andreas All\\
    - %PROGRAMDATA%\\MTA San Andreas All\\
    - Parent directories derived from running MTA process paths
    - The install directory itself
    """
    configs: list[Path] = []
    seen: set[Path] = set()

    def _add(p: Path):
        if p.exists() and p not in seen:
            seen.add(p)
            configs.append(p)

    def _scan_dir(d: Path):
        """Check d and its MTA/mta subfolder for coreconfig.xml."""
        if not d.exists():
            return
        _add(d / "coreconfig.xml")
        _add(d / "MTA"  / "coreconfig.xml")
        _add(d / "mta"  / "coreconfig.xml")

    def _scan_root(root: Path):
        if not root.exists():
            return
        _scan_dir(root)
        for child in root.iterdir():
            if child.is_dir():
                _scan_dir(child)

    _scan_root(_MTA_APPDATA_ROOT)
    _scan_root(_MTA_LOCAL_ROOT)
    _scan_root(_MTA_PROGDATA_ROOT)

    # Walk up from every running MTA process's exe path
    for proc in find_mta_processes():
        exe_path = proc.get("exe", "")
        if not exe_path:
            continue
        p = Path(exe_path).parent
        for _ in range(5):
            _scan_dir(p)
            if "mta san andreas" in p.name.lower():
                _scan_root(p)
            p = p.parent
            if p == p.parent:
                break

    return configs


def get_mta_serial_from_config() -> dict[str, str]:
    """
    Read MTA serial(s) from coreconfig.xml files.
    Returns {config_path: serial}.
    """
    result: dict[str, str] = {}
    serial_re = re.compile(r"<serial>([A-Fa-f0-9]{32})</serial>", re.IGNORECASE)
    for cfg in _find_coreconfig_files():
        try:
            text = cfg.read_text(encoding="utf-8", errors="replace")
            m = serial_re.search(text)
            if m:
                result[str(cfg)] = m.group(1).upper()
        except OSError:
            pass
    return result


def set_mta_serial_in_config(cfg_path: str, new_serial: str,
                               logger: CleanerLogger) -> bool:
    """Replace the <serial> value inside a coreconfig.xml file."""
    path = Path(cfg_path)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        serial_re = re.compile(r"<serial>[A-Fa-f0-9]{0,64}</serial>", re.IGNORECASE)
        if serial_re.search(text):
            new_text = serial_re.sub(f"<serial>{new_serial}</serial>", text)
        else:
            # Tag absent — insert before </config> or append
            if "</config>" in text:
                new_text = text.replace("</config>",
                                        f"  <serial>{new_serial}</serial>\n</config>")
            else:
                new_text = text.rstrip() + f"\n<serial>{new_serial}</serial>\n"
        path.write_text(new_text, encoding="utf-8")
        logger.log("mta_spoof_cfg", "gaming",
                   f"Set serial in {cfg_path}: {new_serial}")
        return True
    except OSError as e:
        logger.error(f"set_mta_serial_in_config error: {e}")
        return False


# ── registry serial ──────────────────────────────────────────

def _mta_find_serial_locations() -> list[tuple]:
    """
    Recursively walk every subkey under the MTA root in HKCU + HKLM (32 & 64-bit)
    and return (hive, full_subkey_path) for each key that holds a 'serial' value.
    """
    if os.name != "nt":
        return []
    wr = _winreg()
    found: list[tuple] = []
    flags_list = [wr.KEY_READ, wr.KEY_READ | wr.KEY_WOW64_32KEY]

    def _recurse(hive, path: str):
        for flags in flags_list:
            try:
                key = wr.OpenKey(hive, path, 0, flags)
            except OSError:
                continue
            try:
                wr.QueryValueEx(key, _MTA_SERIAL_VALUE)
                if (hive, path) not in found:
                    found.append((hive, path))
            except OSError:
                pass
            i = 0
            while True:
                try:
                    sub = wr.EnumKey(key, i); i += 1
                    _recurse(hive, f"{path}\\{sub}")
                except OSError:
                    break
            wr.CloseKey(key)

    for hive in (wr.HKEY_CURRENT_USER, wr.HKEY_LOCAL_MACHINE):
        _recurse(hive, _MTA_REG_BASE)
    return found


def get_mta_serial(logger: CleanerLogger) -> dict[str, str]:
    """
    Return all found MTA serials — config files first, then registry.
    Returns {source_label: serial_value}.
    """
    result: dict[str, str] = {}

    # Config files are the primary source
    result.update(get_mta_serial_from_config())

    # Registry fallback
    if os.name == "nt":
        wr = _winreg()
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
    Write new_serial to every found location (config files + registry).
    Falls back to pre-writing the registry key if nothing exists yet.
    """
    results: dict[str, bool] = {}

    # Config files
    for cfg_path in _find_coreconfig_files():
        results[str(cfg_path)] = set_mta_serial_in_config(
            str(cfg_path), new_serial, logger
        )

    # Registry
    if os.name == "nt":
        wr = _winreg()
        locations = _mta_find_serial_locations()
        if not locations and not results:
            # Nothing found anywhere — pre-write to default registry path
            fallback = rf"{_MTA_REG_BASE}\1.6\Settings"
            try:
                key = wr.CreateKeyEx(wr.HKEY_CURRENT_USER, fallback, 0,
                                     wr.KEY_SET_VALUE)
                wr.SetValueEx(key, _MTA_SERIAL_VALUE, 0, wr.REG_SZ, new_serial)
                wr.CloseKey(key)
                results[f"HKCU\\{fallback}"] = True
                logger.log("mta_spoof", "gaming",
                           f"Pre-wrote serial at {fallback}: {new_serial}")
            except OSError as e:
                logger.error(f"set_mta_serial fallback: {e}")
        for hive, path in locations:
            hive_name = "HKCU" if hive == wr.HKEY_CURRENT_USER else "HKLM"
            label = f"{hive_name}\\{path}"
            try:
                key = wr.OpenKey(hive, path, 0, wr.KEY_SET_VALUE)
                wr.SetValueEx(key, _MTA_SERIAL_VALUE, 0, wr.REG_SZ, new_serial)
                wr.CloseKey(key)
                results[label] = True
                logger.log("mta_spoof", "gaming",
                           f"Set serial at {label}: {new_serial}")
            except OSError as e:
                results[label] = False
                logger.error(f"set_mta_serial reg error at {path}: {e}")

    return results


def generate_mta_serial() -> str:
    """Generate a random valid-looking MTA serial (32 uppercase hex chars)."""
    return secrets.token_hex(16).upper()


def delete_mta_serial(logger: CleanerLogger) -> dict[str, bool]:
    """Remove serial from all found locations — MTA regenerates on next launch."""
    results: dict[str, bool] = {}

    # Config files — replace with empty tag
    serial_re = re.compile(r"<serial>[A-Fa-f0-9]{0,64}</serial>", re.IGNORECASE)
    for cfg in _find_coreconfig_files():
        try:
            text = cfg.read_text(encoding="utf-8", errors="replace")
            new_text = serial_re.sub("<serial></serial>", text)
            cfg.write_text(new_text, encoding="utf-8")
            results[str(cfg)] = True
            logger.log("mta_serial_del", "gaming", f"Cleared serial in {cfg}")
        except OSError as e:
            results[str(cfg)] = False
            logger.error(f"delete_mta_serial cfg error: {e}")

    # Registry
    if os.name == "nt":
        wr = _winreg()
        for hive, path in _mta_find_serial_locations():
            hive_name = "HKCU" if hive == wr.HKEY_CURRENT_USER else "HKLM"
            label = f"{hive_name}\\{path}"
            try:
                key = wr.OpenKey(hive, path, 0, wr.KEY_SET_VALUE)
                wr.DeleteValue(key, _MTA_SERIAL_VALUE)
                wr.CloseKey(key)
                results[label] = True
                logger.log("mta_serial_del", "gaming", f"Deleted serial at {label}")
            except OSError as e:
                results[label] = False
                logger.error(f"delete_mta_serial reg error at {path}: {e}")

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

"""Gaming utilities — spoofer (MTA, FiveM), optimizer, installed games scanner."""

import os
import secrets
import shutil
import subprocess
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
    """
    Return current MTA serials from all known registry locations.
    Returns {reg_path: serial_value}.
    """
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
    """
    Write new_serial to every MTA registry location that exists.
    Returns {reg_path: success}.
    """
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
    """
    Delete the serial value entirely — MTA will regenerate from hardware on next launch.
    Returns {reg_path: success}.
    """
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

# Subdirectories/files within FiveM.app\data that hold cached hardware tokens
_FIVEM_CACHE_DIRS = [
    _FIVEM_LOCAL / "FiveM.app" / "data" / "cache",
    _FIVEM_LOCAL / "FiveM.app" / "data" / "game-storage",
    _FIVEM_LOCAL / "FiveM.app" / "data" / "nui-storage",
    _FIVEM_LOCAL / "FiveM.app" / "data" / "server-cache",
    _FIVEM_LOCAL / "FiveM.app" / "data" / "server-cache-priv",
]

# Individual files that store identity tokens
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
        "installed":       _FIVEM_LOCAL.exists(),
        "app_dir":         str(_FIVEM_LOCAL),
        "citfx_dir":       str(_CITFX_APPDATA),
        "ros_id_exists":   (_CITFX_APPDATA / "ros_id.dat").exists(),
        "cache_dirs":      [str(d) for d in _FIVEM_CACHE_DIRS if d.exists()],
        "id_files":        [str(f) for f in _FIVEM_ID_FILES if f.exists()],
    }


def clear_fivem_identity(logger: CleanerLogger) -> dict[str, Any]:
    """
    Remove FiveM cached identity tokens and cache so they regenerate on next launch.
    Does NOT touch FiveM.exe itself or saved resources.
    Returns summary counts.
    """
    removed_files = 0
    removed_dirs  = 0
    errors: list[str] = []

    # Remove individual identity files
    for f in _FIVEM_ID_FILES:
        try:
            if f.exists():
                f.unlink()
                removed_files += 1
                logger.log("fivem_spoof", "gaming", f"Removed: {f}")
        except OSError as e:
            errors.append(str(e))

    # Clear cache directories (contents only, keep the dir)
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
    return {
        "removed_files": removed_files,
        "removed_dirs":  removed_dirs,
        "errors":        errors,
    }


def clear_fivem_full_cache(logger: CleanerLogger) -> dict[str, Any]:
    """
    Full FiveM cache wipe — identity + all downloaded server resources cache.
    Preserves FiveM.exe and user settings.
    """
    result = clear_fivem_identity(logger)

    # Also wipe server resource cache
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


# ── Gaming Optimizer ─────────────────────────────────────────────────────────

def enable_game_mode(logger: CleanerLogger) -> bool:
    """Enable Windows Game Mode via registry."""
    if os.name != "nt":
        return False
    wr = _winreg()
    try:
        key = wr.CreateKeyEx(
            wr.HKEY_CURRENT_USER,
            r"Software\Microsoft\GameBar",
            0, wr.KEY_SET_VALUE,
        )
        wr.SetValueEx(key, "AutoGameModeEnabled", 0, wr.REG_DWORD, 1)
        wr.SetValueEx(key, "AllowAutoGameMode",   0, wr.REG_DWORD, 1)
        wr.CloseKey(key)
        logger.log("game_mode_on", "gaming", "Windows Game Mode enabled")
        return True
    except OSError as e:
        logger.error(f"enable_game_mode: {e}")
        return False


def disable_game_bar(logger: CleanerLogger) -> bool:
    """Disable Xbox Game Bar overlay (reduces overhead while gaming)."""
    if os.name != "nt":
        return False
    wr = _winreg()
    try:
        key = wr.CreateKeyEx(
            wr.HKEY_CURRENT_USER,
            r"Software\Microsoft\GameBar",
            0, wr.KEY_SET_VALUE,
        )
        wr.SetValueEx(key, "ShowStartupPanel",         0, wr.REG_DWORD, 0)
        wr.SetValueEx(key, "GamePanelStartupTipIndex", 0, wr.REG_DWORD, 3)
        wr.SetValueEx(key, "UseNexusForGameBarEnabled", 0, wr.REG_DWORD, 0)
        wr.CloseKey(key)

        # Also disable via policy key
        pol_key = wr.CreateKeyEx(
            wr.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\GameDVR",
            0, wr.KEY_SET_VALUE,
        )
        wr.SetValueEx(pol_key, "AppCaptureEnabled", 0, wr.REG_DWORD, 0)
        wr.CloseKey(pol_key)

        logger.log("disable_gamebar", "gaming", "Game Bar and DVR disabled")
        return True
    except OSError as e:
        logger.error(f"disable_game_bar: {e}")
        return False


def set_gpu_high_priority(logger: CleanerLogger) -> bool:
    """Set GPU scheduling priority for better gaming frame times."""
    if os.name != "nt":
        return False
    wr = _winreg()
    try:
        # Hardware-accelerated GPU scheduling (HAGS) — requires reboot
        key = wr.CreateKeyEx(
            wr.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers",
            0, wr.KEY_SET_VALUE,
        )
        wr.SetValueEx(key, "HwSchMode", 0, wr.REG_DWORD, 2)
        wr.CloseKey(key)

        # GPU process priority
        key2 = wr.CreateKeyEx(
            wr.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games",
            0, wr.KEY_SET_VALUE,
        )
        wr.SetValueEx(key2, "GPU Priority",          0, wr.REG_DWORD, 8)
        wr.SetValueEx(key2, "Priority",              0, wr.REG_DWORD, 6)
        wr.SetValueEx(key2, "Scheduling Category",   0, wr.REG_SZ, "High")
        wr.SetValueEx(key2, "SFIO Priority",         0, wr.REG_SZ, "High")
        wr.CloseKey(key2)

        logger.log("gpu_priority", "gaming", "GPU priority set to High")
        return True
    except OSError as e:
        logger.error(f"set_gpu_high_priority: {e}")
        return False


def disable_fullscreen_optimizations(logger: CleanerLogger) -> bool:
    """Disable fullscreen optimizations system-wide (reduces latency for some games)."""
    if os.name != "nt":
        return False
    wr = _winreg()
    try:
        key = wr.CreateKeyEx(
            wr.HKEY_CURRENT_USER,
            r"System\GameConfigStore",
            0, wr.KEY_SET_VALUE,
        )
        wr.SetValueEx(key, "GameDVR_FSEBehaviorMode",      0, wr.REG_DWORD, 2)
        wr.SetValueEx(key, "GameDVR_HonorUserFSEBehaviorMode", 0, wr.REG_DWORD, 1)
        wr.SetValueEx(key, "GameDVR_DXGIHonorFSEWindowsCompatible", 0, wr.REG_DWORD, 1)
        wr.SetValueEx(key, "GameDVR_EFSEProcessMaskCompatible",      0, wr.REG_DWORD, 0)
        wr.CloseKey(key)
        logger.log("fso_disable", "gaming", "Fullscreen optimizations disabled")
        return True
    except OSError as e:
        logger.error(f"disable_fullscreen_optimizations: {e}")
        return False


# ── Installed Games Scanner ──────────────────────────────────────────────────

def find_installed_games(logger: CleanerLogger) -> list[dict[str, Any]]:
    """Scan Steam, Epic, GOG, and Ubisoft Connect for installed games."""
    games: list[dict[str, Any]] = []

    # --- Steam ---
    steam_paths = _find_steam_libraries()
    for lib in steam_paths:
        acf_dir = lib / "steamapps"
        if not acf_dir.exists():
            continue
        for acf in acf_dir.glob("appmanifest_*.acf"):
            try:
                data = _parse_acf(acf)
                name = data.get("name", "")
                install_dir = data.get("installdir", "")
                size = int(data.get("SizeOnDisk", 0))
                if name:
                    games.append({
                        "name":     name,
                        "platform": "Steam",
                        "path":     str(acf_dir / "common" / install_dir),
                        "size_gb":  round(size / 1024**3, 1),
                        "app_id":   data.get("appid", ""),
                    })
            except Exception:
                pass

    # --- Epic Games ---
    epic_manifests = Path(os.environ.get("PROGRAMDATA", "")) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    if epic_manifests.exists():
        import json
        for mf in epic_manifests.glob("*.item"):
            try:
                data = json.loads(mf.read_text(encoding="utf-8"))
                name = data.get("DisplayName", "")
                path = data.get("InstallLocation", "")
                if name and path:
                    size = _dir_size(Path(path))
                    games.append({
                        "name":     name,
                        "platform": "Epic",
                        "path":     path,
                        "size_gb":  round(size / 1024**3, 1),
                        "app_id":   data.get("CatalogItemId", ""),
                    })
            except Exception:
                pass

    # --- GOG Galaxy ---
    gog_db = Path(os.environ.get("PROGRAMDATA", "")) / "GOG.com" / "Galaxy" / "storage" / "galaxy-2.0.db"
    if gog_db.exists():
        try:
            import sqlite3
            con = sqlite3.connect(str(gog_db))
            cur = con.cursor()
            cur.execute("SELECT productId, title, installPath FROM InstalledBaseProducts")
            for row in cur.fetchall():
                pid, title, install_path = row
                if title and install_path:
                    size = _dir_size(Path(install_path))
                    games.append({
                        "name":     title,
                        "platform": "GOG",
                        "path":     install_path,
                        "size_gb":  round(size / 1024**3, 1),
                        "app_id":   str(pid),
                    })
            con.close()
        except Exception:
            pass

    # --- Ubisoft Connect ---
    ubi_reg = r"SOFTWARE\WOW6432Node\Ubisoft\Launcher\Installs"
    if os.name == "nt":
        wr = _winreg()
        try:
            root = wr.OpenKey(wr.HKEY_LOCAL_MACHINE, ubi_reg, 0, wr.KEY_READ)
            i = 0
            while True:
                try:
                    app_id = wr.EnumKey(root, i)
                    i += 1
                    sub = wr.OpenKey(root, app_id)
                    try:
                        install_dir, _ = wr.QueryValueEx(sub, "InstallDir")
                        name_path = Path(install_dir)
                        size = _dir_size(name_path)
                        games.append({
                            "name":     name_path.name,
                            "platform": "Ubisoft",
                            "path":     install_dir,
                            "size_gb":  round(size / 1024**3, 1),
                            "app_id":   app_id,
                        })
                    except OSError:
                        pass
                    wr.CloseKey(sub)
                except OSError:
                    break
            wr.CloseKey(root)
        except OSError:
            pass

    games.sort(key=lambda g: g["size_gb"], reverse=True)
    logger.log("find_games", "gaming", f"Found {len(games)} installed games")
    return games


def _find_steam_libraries() -> list[Path]:
    """Return all Steam library folders."""
    paths: list[Path] = []
    if os.name != "nt":
        return paths
    wr = _winreg()
    steam_path = ""
    for reg_path in (
        r"SOFTWARE\Valve\Steam",
        r"SOFTWARE\WOW6432Node\Valve\Steam",
    ):
        try:
            key = wr.OpenKey(wr.HKEY_LOCAL_MACHINE, reg_path, 0, wr.KEY_READ)
            steam_path, _ = wr.QueryValueEx(key, "InstallPath")
            wr.CloseKey(key)
            break
        except OSError:
            pass

    if not steam_path:
        return paths

    base = Path(steam_path)
    paths.append(base)

    # Parse libraryfolders.vdf for additional library paths
    vdf = base / "steamapps" / "libraryfolders.vdf"
    if vdf.exists():
        try:
            text = vdf.read_text(encoding="utf-8", errors="replace")
            import re
            for m in re.finditer(r'"path"\s+"([^"]+)"', text):
                p = Path(m.group(1))
                if p.exists() and p not in paths:
                    paths.append(p)
        except Exception:
            pass

    return paths


def _parse_acf(path: Path) -> dict[str, str]:
    """Parse a Steam ACF manifest file into a flat dict."""
    data: dict[str, str] = {}
    try:
        import re
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r'"(\w+)"\s+"([^"]*)"', text):
            data[m.group(1)] = m.group(2)
    except Exception:
        pass
    return data


def _dir_size(path: Path) -> int:
    """Return total size of a directory tree in bytes (best-effort)."""
    total = 0
    try:
        for f in path.rglob("*"):
            try:
                if f.is_file():
                    total += f.stat().st_size
            except OSError:
                pass
    except Exception:
        pass
    return total

"""Advanced uninstaller - list, uninstall, deep clean, batch operations."""

import os
import subprocess
import winreg
from pathlib import Path
from typing import Any
from core.logger import CleanerLogger


# Registry locations for installed programs
UNINSTALL_KEYS = [
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
]


def _read_reg_value(key, name: str, default=""):
    """Safely read a registry value."""
    try:
        value, _ = winreg.QueryValueEx(key, name)
        return value
    except (FileNotFoundError, OSError):
        return default


def list_installed_programs(logger: CleanerLogger) -> list[dict[str, Any]]:
    """List all installed programs from the registry."""
    programs = []
    seen = set()

    for hive, key_path in UNINSTALL_KEYS:
        try:
            reg_key = winreg.OpenKey(hive, key_path)
        except OSError:
            continue

        try:
            i = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(reg_key, i)
                    i += 1
                    try:
                        subkey = winreg.OpenKey(reg_key, subkey_name)
                        name = _read_reg_value(subkey, "DisplayName")
                        if not name or name in seen:
                            winreg.CloseKey(subkey)
                            continue
                        seen.add(name)

                        # Check if it's a system component (skip those)
                        system_component = _read_reg_value(subkey, "SystemComponent", 0)
                        if system_component == 1:
                            winreg.CloseKey(subkey)
                            continue

                        program = {
                            "name": name,
                            "version": _read_reg_value(subkey, "DisplayVersion"),
                            "publisher": _read_reg_value(subkey, "Publisher"),
                            "install_date": _read_reg_value(subkey, "InstallDate"),
                            "install_location": _read_reg_value(subkey, "InstallLocation"),
                            "uninstall_string": _read_reg_value(subkey, "UninstallString"),
                            "quiet_uninstall": _read_reg_value(subkey, "QuietUninstallString"),
                            "size": _read_reg_value(subkey, "EstimatedSize", 0),
                            "reg_key": subkey_name,
                            "hive": "HKLM" if hive == winreg.HKEY_LOCAL_MACHINE else "HKCU",
                        }
                        programs.append(program)
                        winreg.CloseKey(subkey)
                    except OSError:
                        pass
                except OSError:
                    break
        finally:
            winreg.CloseKey(reg_key)

    programs.sort(key=lambda p: p["name"].lower())
    logger.info(f"Found {len(programs)} installed programs")
    return programs


def search_programs(programs: list[dict], query: str) -> list[dict]:
    """Filter programs by search query."""
    query_lower = query.lower()
    return [p for p in programs if query_lower in p["name"].lower()
            or query_lower in p.get("publisher", "").lower()]


def uninstall_program(program: dict, logger: CleanerLogger, silent: bool = False) -> bool:
    """Uninstall a program using its uninstall string."""
    uninstall_cmd = program.get("quiet_uninstall") if silent else None
    if not uninstall_cmd:
        uninstall_cmd = program.get("uninstall_string")
    if not uninstall_cmd:
        logger.error(f"No uninstall command for: {program['name']}")
        return False

    try:
        # Handle MsiExec uninstallers
        if "msiexec" in uninstall_cmd.lower():
            if silent and "/quiet" not in uninstall_cmd.lower():
                uninstall_cmd += " /quiet /norestart"
            result = subprocess.run(uninstall_cmd, shell=True, capture_output=True,
                                    text=True, timeout=300)
        else:
            if silent:
                # Try common silent switches
                for switch in ["/S", "/s", "/silent", "/quiet", "/VERYSILENT"]:
                    test_cmd = f'{uninstall_cmd} {switch}'
                    result = subprocess.run(test_cmd, shell=True, capture_output=True,
                                            text=True, timeout=300)
                    if result.returncode == 0:
                        break
                else:
                    result = subprocess.run(uninstall_cmd, shell=True, capture_output=True,
                                            text=True, timeout=300)
            else:
                result = subprocess.run(uninstall_cmd, shell=True, capture_output=True,
                                        text=True, timeout=300)

        success = result.returncode == 0
        logger.log(
            "uninstall", "uninstaller",
            f"{'Uninstalled' if success else 'Failed to uninstall'}: {program['name']}",
            success=success,
        )
        return success
    except subprocess.TimeoutExpired:
        logger.error(f"Uninstall timed out: {program['name']}")
        return False
    except Exception as e:
        logger.error(f"Uninstall error for {program['name']}: {e}")
        return False


def find_leftovers(program: dict, logger: CleanerLogger) -> dict[str, list[str]]:
    """Find leftover files and registry entries after uninstall."""
    leftovers = {"files": [], "registry": [], "dirs": []}
    name = program["name"]
    publisher = program.get("publisher", "")
    install_loc = program.get("install_location", "")

    # Check install location
    if install_loc and Path(install_loc).exists():
        leftovers["dirs"].append(install_loc)
        for item in Path(install_loc).rglob("*"):
            if item.is_file():
                leftovers["files"].append(str(item))

    # Check common locations for leftover files
    search_dirs = [
        Path(os.environ.get("APPDATA", "")) / name,
        Path(os.environ.get("LOCALAPPDATA", "")) / name,
        Path(os.environ.get("PROGRAMDATA", "")) / name,
    ]
    if publisher:
        search_dirs.extend([
            Path(os.environ.get("APPDATA", "")) / publisher / name,
            Path(os.environ.get("LOCALAPPDATA", "")) / publisher / name,
        ])

    for search_dir in search_dirs:
        if search_dir.exists():
            leftovers["dirs"].append(str(search_dir))
            for item in search_dir.rglob("*"):
                if item.is_file():
                    leftovers["files"].append(str(item))

    # Check registry for leftover keys
    search_terms = [name.lower().replace(" ", "")]
    if publisher:
        search_terms.append(publisher.lower().replace(" ", ""))

    reg_locations = [
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE"),
    ]
    for hive, base_key in reg_locations:
        try:
            key = winreg.OpenKey(hive, base_key)
            i = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(key, i)
                    if any(term in subkey_name.lower() for term in search_terms):
                        hive_name = "HKCU" if hive == winreg.HKEY_CURRENT_USER else "HKLM"
                        leftovers["registry"].append(f"{hive_name}\\{base_key}\\{subkey_name}")
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(key)
        except OSError:
            pass

    logger.info(f"Found leftovers for {name}: {len(leftovers['files'])} files, "
                f"{len(leftovers['registry'])} registry entries")
    return leftovers


def remove_leftovers(leftovers: dict[str, list[str]], logger: CleanerLogger) -> int:
    """Remove leftover files and directories. Returns bytes freed."""
    import shutil
    total_freed = 0

    # Remove files first
    for filepath in leftovers.get("files", []):
        try:
            path = Path(filepath)
            if path.exists():
                size = path.stat().st_size
                path.unlink()
                total_freed += size
                logger.log("remove_leftover", "uninstaller", f"Removed file: {filepath}", size)
        except (PermissionError, OSError) as e:
            logger.warning(f"Cannot remove: {filepath} - {e}")

    # Remove directories
    for dirpath in leftovers.get("dirs", []):
        try:
            path = Path(dirpath)
            if path.exists():
                size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
                shutil.rmtree(path, ignore_errors=True)
                total_freed += size
                logger.log("remove_leftover", "uninstaller", f"Removed dir: {dirpath}", size)
        except (PermissionError, OSError) as e:
            logger.warning(f"Cannot remove dir: {dirpath} - {e}")

    # Remove registry entries
    for reg_path in leftovers.get("registry", []):
        try:
            parts = reg_path.split("\\", 1)
            hive = winreg.HKEY_CURRENT_USER if parts[0] == "HKCU" else winreg.HKEY_LOCAL_MACHINE
            winreg.DeleteKey(hive, parts[1])
            logger.log("remove_leftover", "uninstaller", f"Removed registry: {reg_path}")
        except OSError as e:
            logger.warning(f"Cannot remove registry: {reg_path} - {e}")

    return total_freed


def remove_traced_files(files: list[str], logger: CleanerLogger) -> int:
    """Remove files traced during an application's runtime. Returns bytes freed."""
    total_freed = 0
    for filepath in files:
        try:
            path = Path(filepath)
            if path.exists() and path.is_file():
                size = path.stat().st_size
                path.unlink()
                total_freed += size
                logger.log("remove_traced", "uninstaller", f"Removed traced file: {filepath}", size)
        except (PermissionError, OSError) as e:
            logger.warning(f"Cannot remove traced file: {filepath} - {e}")
    return total_freed


def detect_orphaned_entries(logger: CleanerLogger) -> list[dict]:
    """Detect registry entries pointing to non-existent install locations."""
    orphaned = []
    programs = list_installed_programs(logger)
    for prog in programs:
        install_loc = prog.get("install_location", "")
        uninstall_str = prog.get("uninstall_string", "")
        is_orphan = False

        if install_loc and not Path(install_loc).exists():
            is_orphan = True
        elif uninstall_str:
            # Extract executable path from uninstall string
            exe_path = uninstall_str.strip('"').split('"')[0]
            if exe_path and not Path(exe_path).exists():
                is_orphan = True

        if is_orphan:
            orphaned.append(prog)

    logger.info(f"Found {len(orphaned)} orphaned registry entries")
    return orphaned


def batch_uninstall(programs: list[dict], logger: CleanerLogger,
                    silent: bool = True) -> dict[str, bool]:
    """Uninstall multiple programs. Returns dict of name -> success."""
    results = {}
    for prog in programs:
        results[prog["name"]] = uninstall_program(prog, logger, silent)
    return results

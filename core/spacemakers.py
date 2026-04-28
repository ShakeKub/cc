"""High-value space maker cleanup helpers."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

from core.cleaner import PROTECTED_DIRS, clean_recycle_bin as clean_windows_recycle_bin
from core.logger import CleanerLogger
from core.scanfilter import PRESET_FOLDERS
from core.tweaks import apply_tweak

DEV_JUNK_DIRS = {"node_modules", ".venv", "__pycache__", "target", ".gradle", ".m2"}

SYSTEM_SKIP_FRAGS = {
    frag.lower()
    for preset in ("system_win", "system_mac", "system_linux")
    for frag in PRESET_FOLDERS.get(preset, [])
}

PACKAGE_CACHE_LABELS = {
    "npm": "npm cache",
    "pip": "pip cache",
    "cargo": "cargo registry / git cache",
    "brew": "Homebrew cache",
    "conda": "conda packages",
}

APP_CACHE_LABELS = {
    "spotify": "Spotify cache",
    "discord": "Discord cache",
    "teams": "Teams cache",
    "slack": "Slack cache",
    "vscode": "VS Code cache",
    "steam": "Steam shader cache",
    "electron": "Electron app caches",
}

_BACKUP_PATTERNS = (
    re.compile(r"^copy(\s*\(\d+\))?\s+of\s+", re.IGNORECASE),
    re.compile(r".*_old(\.|$)", re.IGNORECASE),
    re.compile(r".*_backup(\.|$)", re.IGNORECASE),
    re.compile(r".*\.bak(\.|$)", re.IGNORECASE),
    re.compile(r".*~$", re.IGNORECASE),
)


def _is_windows() -> bool:
    return os.name == "nt"


def _path_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file() and not path.is_symlink():
        try:
            return path.stat().st_size
        except OSError:
            return 0

    total = 0
    try:
        for item in path.rglob("*"):
            try:
                if item.is_file() and not item.is_symlink():
                    total += item.stat().st_size
            except (PermissionError, OSError):
                pass
    except (PermissionError, OSError):
        return 0
    return total


def _safe_remove(path: Path, logger: CleanerLogger | None = None) -> int:
    if not path.exists():
        return 0
    if _is_protected_path(path):
        if logger:
            logger.warning(f"Skipped protected path: {path}")
        return 0

    try:
        if path.is_file() or path.is_symlink():
            size = path.stat().st_size if path.exists() else 0
            path.unlink(missing_ok=True)
            return size
        if path.is_dir():
            size = _path_size(path)
            shutil.rmtree(path)
            return size
    except PermissionError:
        if logger:
            logger.warning(f"Permission denied: {path}")
    except Exception as exc:
        if logger:
            logger.error(f"Error removing {path}: {exc}")
    return 0


def _is_protected_path(path: Path) -> bool:
    parts_lower = [part.lower() for part in path.parts]
    return any(part in PROTECTED_DIRS for part in parts_lower)


def _is_system_path(path: Path) -> bool:
    text = str(path).replace("\\", "/").lower()
    if _is_protected_path(path):
        return True
    return any(frag in text for frag in SYSTEM_SKIP_FRAGS)


def _drive_roots() -> list[Path]:
    roots: list[Path] = []
    try:
        import psutil

        seen: set[str] = set()
        for partition in psutil.disk_partitions(all=False):
            mountpoint = partition.mountpoint
            if not mountpoint or mountpoint in seen:
                continue
            root = Path(mountpoint)
            if root.exists():
                seen.add(mountpoint)
                roots.append(root)
    except Exception:
        pass

    if not roots:
        roots.append(Path("C:\\") if _is_windows() else Path("/"))
    return roots


def _dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for record in records:
        key = os.path.normcase(os.path.abspath(record["path"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    deduped.sort(key=lambda item: item.get("size", 0), reverse=True)
    return deduped


def _record(path: Path, kind: str, label: str, reason: str | None = None) -> dict[str, Any]:
    return {
        "path": str(path),
        "name": path.name,
        "kind": kind,
        "label": label,
        "reason": reason or label,
        "size": _path_size(path),
    }


def _collect_directory_candidates(
    roots: Iterable[Path],
    targets: set[str],
    label: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for root in roots:
        if not root.exists():
            continue
        try:
            for dirpath, dirnames, _filenames in os.walk(root, topdown=True, followlinks=False):
                current = Path(dirpath)
                if _is_system_path(current):
                    dirnames[:] = []
                    continue

                if current.name.lower() in targets:
                    results.append(_record(current, "directory", label))
                    dirnames[:] = []
                    continue

                for dirname in list(dirnames):
                    child = current / dirname
                    if _is_system_path(child):
                        dirnames.remove(dirname)
                        continue
                    if dirname.lower() in targets:
                        results.append(_record(child, "directory", label))
                        dirnames.remove(dirname)
        except (PermissionError, OSError):
            continue
    return _dedupe_records(results)


def _collect_file_candidates(
    roots: Iterable[Path],
    matcher,
    label: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for root in roots:
        if not root.exists():
            continue
        try:
            for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
                current = Path(dirpath)
                if _is_system_path(current):
                    dirnames[:] = []
                    continue

                for filename in filenames:
                    try:
                        item = current / filename
                        if not item.is_file() or item.is_symlink():
                            continue
                        if matcher(item):
                            results.append(_record(item, "file", label))
                    except (PermissionError, OSError):
                        continue
        except (PermissionError, OSError):
            continue
    return _dedupe_records(results)


def _remove_unique_paths(items: list[dict[str, Any]], logger: CleanerLogger, action: str, category: str) -> int:
    total = 0
    unique_paths = []
    seen: set[str] = set()
    for item in items:
        path = str(item.get("path", ""))
        if not path or path in seen:
            continue
        seen.add(path)
        unique_paths.append(Path(path))

    unique_paths.sort(key=lambda p: len(p.parts), reverse=True)
    for path in unique_paths:
        freed = _safe_remove(path, logger)
        if freed > 0:
            total += freed
            logger.log(action, category, f"Removed: {path}", freed)
    return total


def scan_dev_junk() -> list[dict[str, Any]]:
    """Find dev junk directories across mounted drives."""
    return _collect_directory_candidates(_drive_roots(), DEV_JUNK_DIRS, "Development junk")


def clean_dev_junk(logger: CleanerLogger) -> int:
    """Delete all detected dev junk directories."""
    items = scan_dev_junk()
    total = _remove_unique_paths(items, logger, "clean_dev_junk", "space_makers")
    if total > 0:
        logger.log("clean_dev_junk", "space_makers", f"Removed {len(items)} dev junk location(s)", total)
    return total


def _npm_cache_candidates() -> list[Path]:
    candidates: list[Path] = []
    env = os.environ
    for key in ("NPM_CONFIG_CACHE", "npm_config_cache"):
        value = env.get(key)
        if value:
            candidates.append(Path(value))

    for base_key in ("LOCALAPPDATA", "APPDATA"):
        base = env.get(base_key)
        if not base:
            continue
        candidates.extend([
            Path(base) / "npm-cache",
            Path(base) / "npm" / "cache",
        ])

    return candidates


def _pip_cache_candidates() -> list[Path]:
    candidates: list[Path] = []
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "cache", "dir"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if result.returncode == 0:
            cache_dir = result.stdout.strip().splitlines()[-1].strip()
            if cache_dir:
                candidates.append(Path(cache_dir))
    except Exception:
        pass

    home = Path.home()
    candidates.extend([
        home / ".cache" / "pip",
        Path(os.environ.get("LOCALAPPDATA", "")) / "pip" / "Cache",
    ])
    return candidates


def _cargo_cache_candidates() -> list[Path]:
    home = Path.home()
    return [
        home / ".cargo" / "registry",
        home / ".cargo" / "git",
    ]


def _brew_cache_candidates() -> list[Path]:
    home = Path.home()
    return [
        home / "Library" / "Caches" / "Homebrew",
        Path("/opt/homebrew/var/homebrew/cache"),
        Path("/usr/local/Homebrew/Library/Caches/Homebrew"),
    ]


def _conda_cache_candidates() -> list[Path]:
    candidates: list[Path] = []
    for key in ("CONDA_PREFIX", "CONDA_EXE"):
        value = os.environ.get(key)
        if not value:
            continue
        path = Path(value)
        if path.name.lower() == "conda.exe":
            path = path.parent
        candidates.append(path.parent / "pkgs")
        candidates.append(path.parent.parent / "pkgs")

    try:
        result = subprocess.run(["conda", "info", "--base"], capture_output=True, text=True, timeout=20)
        if result.returncode == 0:
            base = result.stdout.strip().splitlines()[-1].strip()
            if base:
                candidates.append(Path(base) / "pkgs")
    except Exception:
        pass

    home = Path.home()
    candidates.extend([
        home / "anaconda3" / "pkgs",
        home / "miniconda3" / "pkgs",
        home / "mambaforge" / "pkgs",
    ])
    return candidates


def _unique_existing_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        if not path:
            continue
        text = str(path)
        if text in seen:
            continue
        seen.add(text)
        if path.exists():
            result.append(path)
    return result


def scan_package_caches() -> list[dict[str, Any]]:
    """Find package manager caches."""
    candidates = []
    for label, raw_paths in {
        "npm": _npm_cache_candidates(),
        "pip": _pip_cache_candidates(),
        "cargo": _cargo_cache_candidates(),
        "brew": _brew_cache_candidates(),
        "conda": _conda_cache_candidates(),
    }.items():
        for path in _unique_existing_paths(raw_paths):
            candidates.append(_record(path, "directory", PACKAGE_CACHE_LABELS[label]))
    return _dedupe_records(candidates)


def clean_package_caches(logger: CleanerLogger) -> int:
    """Delete package manager caches."""
    items = scan_package_caches()
    total = _remove_unique_paths(items, logger, "clean_package_cache", "space_makers")
    if total > 0:
        logger.log("clean_package_cache", "space_makers", f"Removed {len(items)} cache location(s)", total)
    return total


def _spotify_cache_candidates() -> list[Path]:
    env = os.environ
    candidates: list[Path] = []
    for base_key in ("LOCALAPPDATA", "APPDATA"):
        base = env.get(base_key)
        if base:
            root = Path(base) / "Spotify"
            candidates.extend([
                root / "Storage",
                root / "Cache",
                root / "Code Cache",
                root / "GPUCache",
                root / "Browser" / "Cache",
            ])
    candidates.extend([
        Path.home() / "AppData" / "Local" / "Packages" / "SpotifyAB.SpotifyMusic_zpdnekdrzrea0" / "LocalCache",
    ])
    return candidates


def _discord_cache_candidates() -> list[Path]:
    env = os.environ
    candidates: list[Path] = []
    for base_key in ("APPDATA", "LOCALAPPDATA"):
        base = env.get(base_key)
        if base:
            for app in ("Discord", "discordcanary", "discordptb"):
                root = Path(base) / app
                candidates.extend([
                    root / "Cache",
                    root / "Code Cache",
                    root / "GPUCache",
                    root / "Service Worker" / "CacheStorage",
                    root / "Local Storage",
                ])
    return candidates


def _teams_cache_candidates() -> list[Path]:
    env = os.environ
    candidates: list[Path] = []
    local = env.get("LOCALAPPDATA", "")
    roaming = env.get("APPDATA", "")
    candidates.extend([
        Path(local) / "Microsoft" / "Teams" / "Cache",
        Path(local) / "Microsoft" / "Teams" / "blob_storage",
        Path(local) / "Microsoft" / "Teams" / "databases",
        Path(local) / "Microsoft" / "Teams" / "GPUCache",
        Path(local) / "Microsoft" / "Teams" / "IndexedDB",
        Path(local) / "Microsoft" / "Teams" / "Local Storage",
        Path(local) / "Microsoft" / "Teams" / "tmp",
        Path(local) / "Packages" / "MSTeams_8wekyb3d8bbwe" / "LocalCache",
        Path(roaming) / "Microsoft" / "Teams" / "Cache",
    ])
    return candidates


def _slack_cache_candidates() -> list[Path]:
    base = Path(os.environ.get("APPDATA", "")) / "Slack"
    return [
        base / "Cache",
        base / "Code Cache",
        base / "GPUCache",
        base / "Service Worker" / "CacheStorage",
    ]


def _vscode_cache_candidates() -> list[Path]:
    env = os.environ
    candidates: list[Path] = []
    for base_key in ("APPDATA", "LOCALAPPDATA"):
        base = env.get(base_key)
        if base:
            root = Path(base) / "Code"
            candidates.extend([
                root / "Cache",
                root / "Code Cache",
                root / "GPUCache",
                root / "CachedData",
                root / "Service Worker" / "CacheStorage",
            ])
    return candidates


def _steam_cache_candidates() -> list[Path]:
    env = os.environ
    candidates: list[Path] = []
    for base_key in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = env.get(base_key)
        if not base:
            continue
        root = Path(base) / "Steam"
        candidates.extend([
            root / "steamapps" / "shadercache",
            root / "appcache",
            root / "htmlcache",
        ])
    return candidates


def _electron_cache_candidates() -> list[Path]:
    env = os.environ
    candidates: list[Path] = []
    for base_key in ("APPDATA", "LOCALAPPDATA"):
        base = env.get(base_key)
        if not base:
            continue
        base_path = Path(base)
        for child in base_path.iterdir() if base_path.exists() else []:
            if not child.is_dir():
                continue
            candidates.extend([
                child / "Cache",
                child / "Code Cache",
                child / "GPUCache",
                child / "Service Worker" / "CacheStorage",
                child / "blob_storage",
                child / "tmp",
            ])
    return candidates


def scan_app_caches() -> list[dict[str, Any]]:
    """Find targeted app caches."""
    candidates = []
    groups = {
        "spotify": _spotify_cache_candidates(),
        "discord": _discord_cache_candidates(),
        "teams": _teams_cache_candidates(),
        "slack": _slack_cache_candidates(),
        "vscode": _vscode_cache_candidates(),
        "steam": _steam_cache_candidates(),
        "electron": _electron_cache_candidates(),
    }
    for key, raw_paths in groups.items():
        for path in _unique_existing_paths(raw_paths):
            candidates.append(_record(path, "directory", APP_CACHE_LABELS[key]))
    return _dedupe_records(candidates)


def clean_app_caches(logger: CleanerLogger) -> int:
    """Delete app cache directories."""
    items = scan_app_caches()
    total = _remove_unique_paths(items, logger, "clean_app_cache", "space_makers")
    if total > 0:
        logger.log("clean_app_cache", "space_makers", f"Removed {len(items)} cache location(s)", total)
    return total


def scan_old_backups() -> list[dict[str, Any]]:
    """Find forgotten backup files across mounted drives."""
    return _collect_file_candidates(
        _drive_roots(),
        lambda item: _is_backup_name(item.name),
        "Old backup",
    )


def clean_old_backups(logger: CleanerLogger) -> int:
    """Delete old backup files."""
    items = scan_old_backups()
    total = _remove_unique_paths(items, logger, "clean_old_backup", "space_makers")
    if total > 0:
        logger.log("clean_old_backup", "space_makers", f"Removed {len(items)} backup file(s)", total)
    return total


def _is_backup_name(name: str) -> bool:
    return any(pattern.match(name) for pattern in _BACKUP_PATTERNS)


def empty_trash(logger: CleanerLogger) -> int:
    """Empty Recycle Bin on Windows or Trash on other platforms."""
    if _is_windows():
        clean_windows_recycle_bin(logger)
        return 0

    total = 0
    trash_locations = [
        Path.home() / ".Trash",
        Path.home() / ".local" / "share" / "Trash" / "files",
        Path.home() / ".local" / "share" / "Trash" / "info",
    ]
    for location in trash_locations:
        if not location.exists():
            continue
        try:
            for item in location.iterdir():
                total += _safe_remove(item, logger)
        except (PermissionError, OSError):
            continue
    if logger:
        logger.log("empty_trash", "space_makers", "Emptied Trash", total)
    return total


def clean_component_store(logger: CleanerLogger) -> dict[str, Any]:
    """Run DISM component store cleanup and remove Windows.old if present."""
    if not _is_windows():
        return {"ok": False, "message": "Windows only", "freed": 0, "windows_old_removed": False}

    result = {"ok": False, "message": "", "freed": 0, "windows_old_removed": False, "windows_old_size": 0}
    try:
        proc = subprocess.run(
            ["dism", "/online", "/cleanup-image", "/startcomponentcleanup", "/resetbase"],
            capture_output=True,
            text=True,
            timeout=3600,
        )
        result["ok"] = proc.returncode == 0
        result["message"] = proc.stdout.strip() or proc.stderr.strip()
    except Exception as exc:
        result["message"] = str(exc)

    system_drive = os.environ.get("SystemDrive", "C:")
    windows_old = Path(f"{system_drive}\\Windows.old")
    if windows_old.exists():
        old_size = _path_size(windows_old)
        result["windows_old_size"] = old_size
        freed = _safe_remove(windows_old, logger)
        if freed > 0:
            result["windows_old_removed"] = True
            result["freed"] += freed

    result["ok"] = bool(result["ok"] or result["windows_old_removed"])
    if logger:
        logger.log(
            "component_store_cleanup",
            "space_makers",
            f"dism_ok={result['ok']} windows_old_removed={result['windows_old_removed']}",
            result["freed"],
            success=bool(result["ok"]),
        )
    return result


def disable_hibernation(logger: CleanerLogger) -> dict[str, Any]:
    """Disable hibernation using the existing tweak engine."""
    return apply_tweak("disable_hibernation", logger)


def set_pagefile_system_managed(logger: CleanerLogger) -> dict[str, Any]:
    """Switch Windows page file management to automatic."""
    if not _is_windows():
        return {"ok": False, "message": "Windows only"}

    script = "Get-CimInstance Win32_ComputerSystem | Set-CimInstance -Property @{AutomaticManagedPagefile=$true} | Out-Null"
    return _run_powershell(logger, script, "pagefile_auto", "Set page file to system managed")


def set_pagefile_custom_size(size_mb: int, logger: CleanerLogger) -> dict[str, Any]:
    """Set a custom Windows page file size in MB."""
    if not _is_windows():
        return {"ok": False, "message": "Windows only"}
    if size_mb <= 0:
        return {"ok": False, "message": "Size must be greater than 0"}

    system_drive = os.environ.get("SystemDrive", "C:")
    script = (
        "$size = {size}; "
        "$cs = Get-CimInstance Win32_ComputerSystem; "
        "Set-CimInstance -InputObject $cs -Property @{AutomaticManagedPagefile=$false} | Out-Null; "
        "$settings = Get-CimInstance Win32_PageFileSetting; "
        "if (-not $settings) {{ "
        "  New-CimInstance -ClassName Win32_PageFileSetting -Property @{{Name='{drive}\\pagefile.sys'; InitialSize=$size; MaximumSize=$size}} | Out-Null "
        "}} else {{ "
        "  foreach ($setting in $settings) {{ Set-CimInstance -InputObject $setting -Property @{{InitialSize=$size; MaximumSize=$size}} | Out-Null }} "
        "}}"
    ).format(size=size_mb, drive=system_drive)
    return _run_powershell(logger, script, "pagefile_custom", f"Set page file size to {size_mb} MB")


def _run_powershell(logger: CleanerLogger, script: str, action: str, detail: str) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=120,
        )
        ok = proc.returncode == 0
        if logger:
            logger.log(action, "space_makers", detail, success=ok)
        return {
            "ok": ok,
            "message": proc.stdout.strip() or proc.stderr.strip(),
            "returncode": proc.returncode,
        }
    except Exception as exc:
        if logger:
            logger.error(f"{action} failed: {exc}")
        return {"ok": False, "message": str(exc), "returncode": -1}

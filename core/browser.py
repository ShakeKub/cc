"""Browser cleaning module - Chrome, Edge, Firefox cache/cookies/history."""

import os
import shutil
import sqlite3
from pathlib import Path
from typing import Any
from core.logger import CleanerLogger


# Browser profile paths (relative to user's LOCALAPPDATA / APPDATA)
BROWSER_PATHS = {
    "chrome": {
        "base": lambda: Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data",
        "cache_dirs": ["Cache", "Code Cache", "GPUCache"],
        "cookie_files": ["Cookies", "Cookies-journal"],
        "history_files": ["History", "History-journal"],
        "session_files": ["Current Session", "Current Tabs", "Last Session", "Last Tabs"],
    },
    "edge": {
        "base": lambda: Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "User Data",
        "cache_dirs": ["Cache", "Code Cache", "GPUCache"],
        "cookie_files": ["Cookies", "Cookies-journal"],
        "history_files": ["History", "History-journal"],
        "session_files": ["Current Session", "Current Tabs", "Last Session", "Last Tabs"],
    },
    "firefox": {
        "base": lambda: Path(os.environ.get("APPDATA", "")) / "Mozilla" / "Firefox" / "Profiles",
        "cache_dirs": ["cache2"],
        "cookie_files": ["cookies.sqlite", "cookies.sqlite-wal"],
        "history_files": ["places.sqlite", "places.sqlite-wal"],
        "session_files": ["sessionstore.jsonlz4", "sessionstore-backups"],
    },
}


def _get_profiles(browser: str) -> list[Path]:
    """Get all profile directories for a browser."""
    config = BROWSER_PATHS.get(browser)
    if not config:
        return []
    base = config["base"]()
    if not base.exists():
        return []
    if browser == "firefox":
        # Firefox profiles are subdirectories with random names
        return [p for p in base.iterdir() if p.is_dir()]
    else:
        # Chrome/Edge profiles are "Default", "Profile 1", "Profile 2", etc.
        profiles = []
        for item in base.iterdir():
            if item.is_dir() and (item.name == "Default" or item.name.startswith("Profile")):
                profiles.append(item)
        return profiles


def _safe_remove_path(path: Path, logger: CleanerLogger) -> int:
    """Remove a file or directory safely. Returns bytes freed."""
    try:
        if path.is_file():
            size = path.stat().st_size
            path.unlink()
            return size
        elif path.is_dir():
            size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
            shutil.rmtree(path, ignore_errors=True)
            return size
    except PermissionError:
        logger.warning(f"Browser file locked (browser may be open): {path}")
    except Exception as e:
        logger.error(f"Error removing {path}: {e}")
    return 0


def detect_installed_browsers() -> list[dict[str, Any]]:
    """Detect which supported browsers are installed."""
    browsers = []
    for name, config in BROWSER_PATHS.items():
        base = config["base"]()
        profiles = _get_profiles(name)
        if base.exists():
            total_size = 0
            for profile in profiles:
                for cache_dir in config["cache_dirs"]:
                    cache_path = profile / cache_dir
                    if cache_path.exists():
                        try:
                            total_size += sum(
                                f.stat().st_size for f in cache_path.rglob("*") if f.is_file()
                            )
                        except (PermissionError, OSError):
                            pass
            browsers.append({
                "name": name,
                "display_name": name.capitalize(),
                "installed": True,
                "profiles": len(profiles),
                "cache_size": total_size,
                "base_path": str(base),
            })
    return browsers


def scan_browser(browser: str, logger: CleanerLogger) -> dict[str, Any]:
    """Scan a browser for cleanable data."""
    config = BROWSER_PATHS.get(browser)
    if not config:
        return {"error": f"Unknown browser: {browser}"}

    profiles = _get_profiles(browser)
    result = {
        "browser": browser,
        "profiles": len(profiles),
        "cache": {"count": 0, "size": 0, "items": []},
        "cookies": {"count": 0, "size": 0, "items": []},
        "history": {"count": 0, "size": 0, "items": []},
        "sessions": {"count": 0, "size": 0, "items": []},
    }

    for profile in profiles:
        # Scan cache directories
        for cache_dir in config["cache_dirs"]:
            cache_path = profile / cache_dir
            if cache_path.exists():
                try:
                    size = sum(f.stat().st_size for f in cache_path.rglob("*") if f.is_file())
                    count = sum(1 for _ in cache_path.rglob("*") if _.is_file())
                    result["cache"]["count"] += count
                    result["cache"]["size"] += size
                    result["cache"]["items"].append(str(cache_path))
                except (PermissionError, OSError):
                    pass

        # Scan cookie files
        for cookie_file in config["cookie_files"]:
            cookie_path = profile / cookie_file
            if cookie_path.exists():
                try:
                    size = cookie_path.stat().st_size
                    result["cookies"]["count"] += 1
                    result["cookies"]["size"] += size
                    result["cookies"]["items"].append(str(cookie_path))
                except (PermissionError, OSError):
                    pass

        # Scan history files
        for history_file in config["history_files"]:
            history_path = profile / history_file
            if history_path.exists():
                try:
                    size = history_path.stat().st_size
                    result["history"]["count"] += 1
                    result["history"]["size"] += size
                    result["history"]["items"].append(str(history_path))
                except (PermissionError, OSError):
                    pass

        # Scan session files
        for session_file in config["session_files"]:
            session_path = profile / session_file
            if session_path.exists():
                try:
                    if session_path.is_file():
                        size = session_path.stat().st_size
                    else:
                        size = sum(f.stat().st_size for f in session_path.rglob("*") if f.is_file())
                    result["sessions"]["count"] += 1
                    result["sessions"]["size"] += size
                    result["sessions"]["items"].append(str(session_path))
                except (PermissionError, OSError):
                    pass

    total = sum(result[k]["size"] for k in ["cache", "cookies", "history", "sessions"])
    logger.info(f"Scanned {browser}: {total} bytes cleanable across {len(profiles)} profiles")
    return result


def clean_browser(browser: str, logger: CleanerLogger,
                  cache: bool = True, cookies: bool = False,
                  history: bool = False, sessions: bool = False) -> dict[str, int]:
    """Clean specified browser data. Returns bytes freed per category."""
    config = BROWSER_PATHS.get(browser)
    if not config:
        return {}

    profiles = _get_profiles(browser)
    freed = {"cache": 0, "cookies": 0, "history": 0, "sessions": 0}

    for profile in profiles:
        if cache:
            for cache_dir in config["cache_dirs"]:
                cache_path = profile / cache_dir
                if cache_path.exists():
                    freed["cache"] += _safe_remove_path(cache_path, logger)

        if cookies:
            for cookie_file in config["cookie_files"]:
                cookie_path = profile / cookie_file
                if cookie_path.exists():
                    freed["cookies"] += _safe_remove_path(cookie_path, logger)

        if history:
            for history_file in config["history_files"]:
                history_path = profile / history_file
                if history_path.exists():
                    freed["history"] += _safe_remove_path(history_path, logger)

        if sessions:
            for session_file in config["session_files"]:
                session_path = profile / session_file
                if session_path.exists():
                    freed["sessions"] += _safe_remove_path(session_path, logger)

    total = sum(freed.values())
    logger.log("clean_browser", "browser", f"Cleaned {browser}: freed {total} bytes", total)
    return freed


def clean_all_browsers(logger: CleanerLogger,
                       cache: bool = True, cookies: bool = False,
                       history: bool = False, sessions: bool = False) -> dict[str, dict[str, int]]:
    """Clean all detected browsers."""
    results = {}
    for browser_info in detect_installed_browsers():
        name = browser_info["name"]
        results[name] = clean_browser(name, logger, cache, cookies, history, sessions)
    return results

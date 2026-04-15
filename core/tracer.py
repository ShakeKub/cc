"""Deep Application Trace Analyzer - comprehensive app trace detection and removal."""

import os
import shutil
import subprocess
import winreg
from pathlib import Path
from typing import Any
from core.logger import CleanerLogger


class AppTracer:
    """Analyzes and removes all traces of a specific application."""

    def __init__(self, app_name: str, app_path: str = "", logger: CleanerLogger | None = None):
        self.app_name = app_name
        self.app_path = app_path
        self.logger = logger
        self.search_terms = self._generate_search_terms()
        self.traces: dict[str, list[dict[str, Any]]] = {
            "files": [],
            "registry": [],
            "services": [],
            "scheduled_tasks": [],
            "startup": [],
            "processes": [],
        }

    def _generate_search_terms(self) -> list[str]:
        """Generate heuristic search terms from app name."""
        terms = [self.app_name.lower()]
        # Remove common suffixes
        clean = self.app_name.lower().replace(".exe", "").replace(".msi", "")
        terms.append(clean)
        # Split camelCase or PascalCase
        import re
        split = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', clean).lower()
        if split != clean:
            terms.append(split)
        # Without spaces
        terms.append(clean.replace(" ", ""))
        terms.append(clean.replace(" ", "_"))
        terms.append(clean.replace(" ", "-"))
        # Deduplicate
        return list(set(terms))

    def scan_all(self, progress_callback=None) -> dict[str, list[dict]]:
        """Perform comprehensive trace scan."""
        steps = [
            ("Scanning files...", self._scan_files),
            ("Scanning registry...", self._scan_registry),
            ("Scanning services...", self._scan_services),
            ("Scanning scheduled tasks...", self._scan_scheduled_tasks),
            ("Scanning startup entries...", self._scan_startup),
            ("Scanning running processes...", self._scan_processes),
        ]

        for i, (desc, scanner) in enumerate(steps):
            if progress_callback:
                progress_callback(i, len(steps), desc)
            try:
                scanner()
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Trace scan error in {desc}: {e}")

        if progress_callback:
            progress_callback(len(steps), len(steps), "Scan complete")

        total = sum(len(items) for items in self.traces.values())
        if self.logger:
            self.logger.info(f"App trace scan for '{self.app_name}': {total} traces found")

        return self.traces

    def _scan_files(self):
        """Scan filesystem for application traces."""
        search_dirs = []

        # Common application data directories
        env_dirs = {
            "APPDATA": os.environ.get("APPDATA", ""),
            "LOCALAPPDATA": os.environ.get("LOCALAPPDATA", ""),
            "PROGRAMDATA": os.environ.get("PROGRAMDATA", ""),
            "PROGRAMFILES": os.environ.get("PROGRAMFILES", ""),
            "PROGRAMFILES_X86": os.environ.get("PROGRAMFILES(X86)", ""),
            "TEMP": os.environ.get("TEMP", ""),
            "USERPROFILE": os.environ.get("USERPROFILE", ""),
        }

        for env_name, env_path in env_dirs.items():
            if env_path:
                search_dirs.append((Path(env_path), env_name, 2))

        # Also check specific install location if provided
        if self.app_path and Path(self.app_path).exists():
            parent = Path(self.app_path).parent
            self.traces["files"].append({
                "path": str(parent),
                "type": "directory",
                "category": "Install Directory",
                "size": self._dir_size(parent),
                "risk": "low",
                "match_term": "direct path",
            })

        for base_dir, location, max_depth in search_dirs:
            if not base_dir.exists():
                continue
            self._search_directory(base_dir, location, max_depth)

    def _search_directory(self, base: Path, location: str, max_depth: int, depth: int = 0):
        """Recursively search a directory for matching items."""
        if depth > max_depth:
            return
        try:
            for item in base.iterdir():
                try:
                    name_lower = item.name.lower()
                    matched_term = None
                    for term in self.search_terms:
                        if term in name_lower:
                            matched_term = term
                            break

                    if matched_term:
                        size = 0
                        if item.is_file():
                            size = item.stat().st_size
                            item_type = "file"
                        elif item.is_dir():
                            size = self._dir_size(item)
                            item_type = "directory"
                        else:
                            continue

                        self.traces["files"].append({
                            "path": str(item),
                            "type": item_type,
                            "category": location,
                            "size": size,
                            "risk": "low",
                            "match_term": matched_term,
                        })

                    elif item.is_dir() and depth < max_depth:
                        self._search_directory(item, location, max_depth, depth + 1)

                except (PermissionError, OSError):
                    pass
        except PermissionError:
            pass

    def _dir_size(self, path: Path) -> int:
        """Calculate total directory size."""
        total = 0
        try:
            for f in path.rglob("*"):
                if f.is_file():
                    try:
                        total += f.stat().st_size
                    except (PermissionError, OSError):
                        pass
        except PermissionError:
            pass
        return total

    def _scan_registry(self):
        """Scan Windows registry for application traces."""
        # Key registry locations to check
        reg_locations = [
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE", "HKCU\\SOFTWARE"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE", "HKLM\\SOFTWARE"),
            (winreg.HKEY_CURRENT_USER,
             r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
             "HKCU\\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE,
             r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
             "HKLM\\Uninstall"),
            (winreg.HKEY_CLASSES_ROOT, "", "HKCR"),
        ]

        for hive, key_path, location in reg_locations:
            try:
                key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
                i = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        name_lower = subkey_name.lower()
                        for term in self.search_terms:
                            if term in name_lower:
                                full_path = f"{location}\\{subkey_name}"
                                self.traces["registry"].append({
                                    "path": full_path,
                                    "key_name": subkey_name,
                                    "category": "Registry Key",
                                    "risk": "medium",
                                    "match_term": term,
                                    "hive": hive,
                                    "full_key": f"{key_path}\\{subkey_name}",
                                })
                                break
                        i += 1
                    except OSError:
                        break
                winreg.CloseKey(key)
            except OSError:
                pass

    def _scan_services(self):
        """Scan Windows services for app-related entries."""
        try:
            result = subprocess.run(
                ["sc", "query", "type=", "service", "state=", "all"],
                capture_output=True, text=True, timeout=15,
            )
            current_service = {}
            for line in result.stdout.splitlines():
                if "SERVICE_NAME:" in line:
                    if current_service:
                        name_lower = (current_service.get("name", "") +
                                     current_service.get("display", "")).lower()
                        for term in self.search_terms:
                            if term in name_lower:
                                self.traces["services"].append({
                                    "name": current_service["name"],
                                    "display_name": current_service.get("display", ""),
                                    "status": current_service.get("status", "unknown"),
                                    "category": "Windows Service",
                                    "risk": "medium",
                                    "match_term": term,
                                })
                                break
                    current_service = {"name": line.split(":")[-1].strip()}
                elif "DISPLAY_NAME:" in line:
                    current_service["display"] = line.split(":")[-1].strip()
                elif "STATE" in line:
                    if "RUNNING" in line:
                        current_service["status"] = "running"
                    elif "STOPPED" in line:
                        current_service["status"] = "stopped"
        except Exception:
            pass

    def _scan_scheduled_tasks(self):
        """Scan Windows Task Scheduler for app-related tasks."""
        try:
            result = subprocess.run(
                ["schtasks", "/query", "/fo", "CSV", "/v"],
                capture_output=True, text=True, timeout=30,
            )
            for line in result.stdout.splitlines()[1:]:  # Skip header
                line_lower = line.lower()
                for term in self.search_terms:
                    if term in line_lower:
                        parts = line.split('","')
                        if len(parts) >= 2:
                            task_name = parts[1].strip('"') if len(parts) > 1 else line
                            self.traces["scheduled_tasks"].append({
                                "name": task_name,
                                "category": "Scheduled Task",
                                "risk": "medium",
                                "match_term": term,
                                "raw": line[:200],
                            })
                        break
        except Exception:
            pass

    def _scan_startup(self):
        """Scan startup entries for app-related items."""
        startup_keys = [
            (winreg.HKEY_CURRENT_USER,
             r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
            (winreg.HKEY_LOCAL_MACHINE,
             r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
        ]

        for hive, key_path in startup_keys:
            try:
                key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                        combined = (name + " " + str(value)).lower()
                        for term in self.search_terms:
                            if term in combined:
                                hive_name = "HKCU" if hive == winreg.HKEY_CURRENT_USER else "HKLM"
                                self.traces["startup"].append({
                                    "name": name,
                                    "command": value,
                                    "location": f"{hive_name}\\{key_path}",
                                    "category": "Startup Entry",
                                    "risk": "low",
                                    "match_term": term,
                                })
                                break
                        i += 1
                    except OSError:
                        break
                winreg.CloseKey(key)
            except OSError:
                pass

    def _scan_processes(self):
        """Scan running processes for app-related items."""
        import psutil
        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                info = proc.info
                combined = (
                    (info.get('name', '') or '') + " " +
                    (info.get('exe', '') or '')
                ).lower()
                for term in self.search_terms:
                    if term in combined:
                        self.traces["processes"].append({
                            "pid": info['pid'],
                            "name": info.get('name', ''),
                            "exe": info.get('exe', ''),
                            "category": "Running Process",
                            "risk": "low",
                            "match_term": term,
                        })
                        break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of all found traces."""
        total_size = sum(
            item.get("size", 0) for item in self.traces.get("files", [])
        )
        return {
            "app_name": self.app_name,
            "total_traces": sum(len(v) for v in self.traces.values()),
            "files": len(self.traces["files"]),
            "registry": len(self.traces["registry"]),
            "services": len(self.traces["services"]),
            "scheduled_tasks": len(self.traces["scheduled_tasks"]),
            "startup": len(self.traces["startup"]),
            "processes": len(self.traces["processes"]),
            "total_size": total_size,
        }

    def remove_trace(self, category: str, index: int) -> bool:
        """Remove a specific trace by category and index."""
        items = self.traces.get(category, [])
        if index >= len(items):
            return False

        item = items[index]
        success = False

        try:
            if category == "files":
                path = Path(item["path"])
                if path.is_file():
                    path.unlink()
                    success = True
                elif path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                    success = not path.exists()

            elif category == "registry":
                try:
                    winreg.DeleteKey(item["hive"], item["full_key"])
                    success = True
                except OSError:
                    # Try recursive delete for keys with subkeys
                    self._delete_reg_tree(item["hive"], item["full_key"])
                    success = True

            elif category == "services":
                result = subprocess.run(
                    ["sc", "delete", item["name"]],
                    capture_output=True, timeout=15,
                )
                success = result.returncode == 0

            elif category == "scheduled_tasks":
                result = subprocess.run(
                    ["schtasks", "/delete", "/tn", item["name"], "/f"],
                    capture_output=True, timeout=15,
                )
                success = result.returncode == 0

            elif category == "startup":
                loc = item.get("location", "")
                hive = winreg.HKEY_CURRENT_USER if "HKCU" in loc else winreg.HKEY_LOCAL_MACHINE
                key_path = loc.split("\\", 1)[1] if "\\" in loc else ""
                key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_WRITE)
                winreg.DeleteValue(key, item["name"])
                winreg.CloseKey(key)
                success = True

            elif category == "processes":
                import psutil
                try:
                    proc = psutil.Process(item["pid"])
                    proc.terminate()
                    proc.wait(timeout=5)
                    success = True
                except (psutil.NoSuchProcess, psutil.AccessDenied,
                        psutil.TimeoutExpired):
                    pass

        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to remove trace: {e}")

        if success:
            items.pop(index)
            if self.logger:
                self.logger.log("remove_trace", "tracer",
                              f"Removed {category} trace: {item.get('path', item.get('name', ''))}")

        return success

    def deep_clean(self, backup_registry: bool = True) -> dict[str, int]:
        """Perform complete removal of all detected traces."""
        results = {"removed": 0, "failed": 0, "skipped": 0}

        # Backup registry first if requested
        if backup_registry and self.traces["registry"]:
            from core.registry import backup_registry as reg_backup
            reg_backup(logger=self.logger)

        # Kill processes first
        for i in range(len(self.traces.get("processes", [])) - 1, -1, -1):
            if self.remove_trace("processes", i):
                results["removed"] += 1
            else:
                results["failed"] += 1

        # Remove in safe order: startup -> scheduled_tasks -> services -> files -> registry
        for category in ["startup", "scheduled_tasks", "services", "files", "registry"]:
            items = self.traces.get(category, [])
            for i in range(len(items) - 1, -1, -1):
                item = items[i]
                if item.get("risk") == "high":
                    results["skipped"] += 1
                    continue
                if self.remove_trace(category, i):
                    results["removed"] += 1
                else:
                    results["failed"] += 1

        if self.logger:
            self.logger.log("deep_clean", "tracer",
                          f"Deep clean for '{self.app_name}': "
                          f"{results['removed']} removed, {results['failed']} failed, "
                          f"{results['skipped']} skipped")
        return results

    def _delete_reg_tree(self, hive, key_path: str):
        """Recursively delete a registry key and all subkeys."""
        try:
            key = winreg.OpenKey(hive, key_path, 0,
                                winreg.KEY_READ | winreg.KEY_WRITE)
            # Delete subkeys first
            while True:
                try:
                    subkey_name = winreg.EnumKey(key, 0)
                    self._delete_reg_tree(hive, f"{key_path}\\{subkey_name}")
                except OSError:
                    break
            winreg.CloseKey(key)
            winreg.DeleteKey(hive, key_path)
        except OSError:
            pass

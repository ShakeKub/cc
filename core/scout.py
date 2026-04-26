"""Scout Mode - Deep application behavior monitoring.

Tracks file I/O, registry changes, network connections, downloads,
DLL loading, and child-process spawning for a specific target application.
All events are queued in real time and saved as structured JSON.
"""

import datetime
import json
import os
import queue
import socket
import threading
import time
from pathlib import Path

import psutil
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from core.logger import CleanerLogger


# ── helpers ─────────────────────────────────────────────────────────────────

def _ts() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]


def _snapshot_pids() -> dict[int, str]:
    result: dict[int, str] = {}
    for p in psutil.process_iter(["pid", "name"]):
        try:
            result[p.info["pid"]] = p.info["name"]
        except Exception:
            pass
    return result


def _get_modules(pid: int) -> set:
    """Return set of loaded DLL/module paths for a PID."""
    try:
        return {m.path.lower() for m in psutil.Process(pid).memory_maps() if m.path}
    except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
        return set()


def _reverse_dns(ip: str) -> str:
    """Best-effort reverse DNS lookup with a short timeout."""
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return ip


# ── registry snapshot helper (Windows only) ─────────────────────────────────

def _snapshot_reg_key(hive, key_path: str) -> dict[str, str]:
    """Return {value_name: str(value), '__KEY_subkey': subkey} for one registry key."""
    result: dict[str, str] = {}
    try:
        import winreg
        key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
        i = 0
        while True:
            try:
                name, value, _ = winreg.EnumValue(key, i)
                result[name] = str(value)[:500]
                i += 1
            except OSError:
                break
        i = 0
        while True:
            try:
                subkey = winreg.EnumKey(key, i)
                result[f"__KEY_{subkey}"] = subkey
                i += 1
            except OSError:
                break
        winreg.CloseKey(key)
    except Exception:
        pass
    return result


# ── ScoutSession ─────────────────────────────────────────────────────────────

class ScoutSession:
    """
    Deep behavior monitor for a specific application.

    Monitored categories
    --------------------
    file      — CREATE / MODIFY / DELETE / MOVE events (home + system dirs)
    registry  — REG_ADD / REG_MODIFY / REG_DELETE across all major hives
    network   — CONNECT events (new outbound/inbound connections + reverse DNS)
    process   — SPAWN / EXIT events; TARGET_FOUND when target appears
    dll       — new DLLs loaded into target process
    download  — files created/grown in the user's Downloads folder
    """

    # All important registry locations polled for changes (1-second interval)
    _REG_MONITOR = [
        # ── Startup / persistence ───────────────────────────────────────────
        ("HKCU\\Run",         "HKEY_CURRENT_USER",  r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
        ("HKCU\\RunOnce",     "HKEY_CURRENT_USER",  r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce"),
        ("HKLM\\Run",         "HKEY_LOCAL_MACHINE", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
        ("HKLM\\RunOnce",     "HKEY_LOCAL_MACHINE", r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce"),
        ("HKLM\\Run32",       "HKEY_LOCAL_MACHINE", r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"),
        # ── Installed software (top-level key detection) ────────────────────
        ("HKCU\\Software",    "HKEY_CURRENT_USER",  r"SOFTWARE"),
        ("HKLM\\Software",    "HKEY_LOCAL_MACHINE", r"SOFTWARE"),
        ("HKLM\\Software32",  "HKEY_LOCAL_MACHINE", r"SOFTWARE\WOW6432Node"),
        # ── Uninstall entries ───────────────────────────────────────────────
        ("HKLM\\Uninstall",   "HKEY_LOCAL_MACHINE", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        ("HKLM\\Uninst32",    "HKEY_LOCAL_MACHINE", r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        # ── Authentication / Winlogon hooks ─────────────────────────────────
        ("HKLM\\Winlogon",    "HKEY_LOCAL_MACHINE", r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"),
        ("HKLM\\LSA",         "HKEY_LOCAL_MACHINE", r"SYSTEM\CurrentControlSet\Control\Lsa"),
        # ── Services (detects new/removed services) ─────────────────────────
        ("HKLM\\Services",    "HKEY_LOCAL_MACHINE", r"SYSTEM\CurrentControlSet\Services"),
        # ── File associations / COM ─────────────────────────────────────────
        ("HKCU\\Classes",     "HKEY_CURRENT_USER",  r"SOFTWARE\Classes"),
        # ── Environment variables ───────────────────────────────────────────
        ("HKCU\\Env",         "HKEY_CURRENT_USER",  r"Environment"),
        ("HKLM\\SysEnv",      "HKEY_LOCAL_MACHINE", r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        # ── Browser helper objects ──────────────────────────────────────────
        ("HKLM\\BHO",         "HKEY_LOCAL_MACHINE", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Browser Helper Objects"),
        # ── Shell extensions / context menu handlers ────────────────────────
        ("HKLM\\ShellExec",   "HKEY_LOCAL_MACHINE", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Shell Extensions\Approved"),
        # ── Scheduled tasks registry cache ──────────────────────────────────
        ("HKLM\\TaskCache",   "HKEY_LOCAL_MACHINE", r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Schedule\TaskCache\Tasks"),
        # ── Group policy / restrictions ─────────────────────────────────────
        ("HKLM\\Policies",    "HKEY_LOCAL_MACHINE", r"SOFTWARE\Policies\Microsoft\Windows"),
        ("HKCU\\Policies",    "HKEY_CURRENT_USER",  r"SOFTWARE\Policies\Microsoft\Windows"),
        # ── Firewall ───────────────────────────────────────────────────────
        ("HKLM\\FWProfiles",  "HKEY_LOCAL_MACHINE", r"SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters\FirewallPolicy"),
        # ── AppInit DLLs (classic DLL injection vector) ─────────────────────
        ("HKLM\\AppInit",     "HKEY_LOCAL_MACHINE", r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Windows"),
        # ── Image File Execution Options (debugger hijack / IFEO) ───────────
        ("HKLM\\IFEO",        "HKEY_LOCAL_MACHINE", r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options"),
    ]

    # Extra watch directories beyond the user-specified path (Windows system paths)
    _SYSTEM_WATCH_DIRS = [
        r"C:\ProgramData",
        r"C:\Program Files",
        r"C:\Program Files (x86)",
    ]

    def __init__(self, app_name: str, profile_path: str, logger: CleanerLogger):
        self.app_name = app_name
        self.profile_path = profile_path
        self.logger = logger
        self.session_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_file = os.path.join(profile_path, f"scout_{self.session_id}.json")

        self.is_running = False
        self.event_queue: queue.Queue = queue.Queue()
        self.start_time: float | None = None

        # Per-category event lists
        self.file_events:     list[dict] = []
        self.registry_events: list[dict] = []
        self.network_events:  list[dict] = []
        self.process_events:  list[dict] = []
        self.download_events: list[dict] = []
        self.dll_events:      list[dict] = []

        self._threads:   list[threading.Thread] = []
        self._observer:  Observer | None = None

        self.watch_path       = os.path.expanduser("~")
        self.watch_paths:     list[str] = []          # populated in start()
        self.downloads_path   = str(Path.home() / "Downloads")
        self.target_process:  str | None = None
        self._target_pids:    set[int] = set()
        self._launched_process = None           # subprocess.Popen if we launched the exe
        self.file_access_events: list[dict] = []  # files opened by target process

    # ── public API ───────────────────────────────────────────────────────────

    def start(self, exe_path: str | None = None,
              watch_path: str | None = None,
              target_process: str | None = None) -> None:
        """Start monitoring.

        exe_path       — full path to the executable to launch. If given the
                         process is started automatically and its PID is
                         immediately added to the tracked set.
        watch_path     — explicit base directory for the file watcher. When
                         omitted the exe directory (or home) is used.
        target_process — process name to match (inferred from exe_path when
                         not supplied).
        """
        import subprocess

        # Resolve target process name
        if exe_path and not target_process:
            target_process = Path(exe_path).name
        if target_process:
            self.target_process = target_process.lower()

        # Resolve base watch path
        if watch_path:
            self.watch_path = watch_path
        elif exe_path:
            self.watch_path = str(Path(exe_path).parent)

        # Build deduplicated watch-path list
        candidates = [self.watch_path] + self._SYSTEM_WATCH_DIRS
        # Also add user env dirs that may be outside home (e.g. LOCALAPPDATA on some setups)
        for env_var in ("APPDATA", "LOCALAPPDATA", "TEMP", "TMP"):
            p = os.environ.get(env_var, "")
            if p:
                candidates.append(p)
        scheduled: list[str] = []
        for p in candidates:
            if not p or not os.path.isdir(p):
                continue
            norm = os.path.normcase(os.path.abspath(p))
            if any(norm.startswith(os.path.normcase(os.path.abspath(s)) + os.sep)
                   for s in scheduled):
                continue  # already covered by a parent watcher
            scheduled.append(p)
        self.watch_paths = scheduled

        self.is_running = True
        self.start_time = time.time()

        # Launch the exe before any monitoring starts so we can grab the PID
        if exe_path:
            try:
                self._launched_process = subprocess.Popen([exe_path])
                # Give the OS a moment, then pre-seed the target-PID set
                time.sleep(0.3)
                self._target_pids.add(self._launched_process.pid)
            except Exception as e:
                self.logger.error(f"Failed to launch '{exe_path}': {e}")

        self.logger.log("scout_start", "scout",
                        f"app='{self.app_name}' exe='{exe_path}' "
                        f"watch={self.watch_paths} "
                        f"target='{self.target_process}' id={self.session_id}")

        self._observer = Observer()
        self._start_file_watcher()
        self._start_download_watcher()
        self._observer.start()

        self._start_process_monitor()
        self._start_dll_monitor()
        self._start_open_files_monitor()
        self._start_network_monitor()
        self._start_registry_monitor()

    def stop(self) -> None:
        if not self.is_running:
            return
        self.is_running = False
        if self._observer:
            self._observer.stop()
            self._observer.join()
        self.logger.log("scout_stop", "scout", f"session_id={self.session_id}")
        self._save_session()

    # ── file system ──────────────────────────────────────────────────────────

    def _start_file_watcher(self) -> None:
        session = self

        class _Handler(FileSystemEventHandler):
            def _emit(self, etype: str, src: str, dest: str = "") -> None:
                ev: dict = {"type": etype, "path": src, "time": _ts(), "category": "file"}
                if dest:
                    ev["dest"] = dest
                session.file_events.append(ev)
                session.event_queue.put(ev)

            def on_created(self, e):
                if not e.is_directory:
                    self._emit("CREATE", e.src_path)

            def on_modified(self, e):
                if not e.is_directory:
                    self._emit("MODIFY", e.src_path)

            def on_deleted(self, e):
                if not e.is_directory:
                    self._emit("DELETE", e.src_path)

            def on_moved(self, e):
                self._emit("MOVE", e.src_path, e.dest_path)

        h = _Handler()
        for wp in self.watch_paths:
            self._observer.schedule(h, wp, recursive=True)

    # ── downloads watcher ────────────────────────────────────────────────────

    def _start_download_watcher(self) -> None:
        dl = self.downloads_path
        # Skip if Downloads is already covered by one of the scheduled watchers
        if not os.path.isdir(dl):
            return
        dl_norm = os.path.normcase(os.path.abspath(dl))
        for wp in self.watch_paths:
            wp_norm = os.path.normcase(os.path.abspath(wp))
            if dl_norm.startswith(wp_norm + os.sep) or dl_norm == wp_norm:
                return

        session = self

        class _DLHandler(FileSystemEventHandler):
            def on_created(self, e):
                if e.is_directory:
                    return
                ev = {"type": "DOWNLOAD", "path": e.src_path,
                      "time": _ts(), "category": "download", "size": 0}
                session.download_events.append(ev)
                session.event_queue.put(ev)

            def on_modified(self, e):
                if e.is_directory:
                    return
                try:
                    size = Path(e.src_path).stat().st_size
                except Exception:
                    size = 0
                ev = {"type": "DOWNLOAD_UPDATE", "path": e.src_path,
                      "time": _ts(), "category": "download", "size": size}
                session.download_events.append(ev)
                session.event_queue.put(ev)

        self._observer.schedule(_DLHandler(), dl, recursive=False)

    # ── process monitor ──────────────────────────────────────────────────────

    def _start_process_monitor(self) -> None:
        def run():
            prev_pids = _snapshot_pids()

            if self.target_process:
                for pid, name in prev_pids.items():
                    if name.lower() == self.target_process:
                        self._target_pids.add(pid)

            while self.is_running:
                time.sleep(0.5)
                try:
                    cur_pids = _snapshot_pids()

                    for pid, name in cur_pids.items():
                        if pid not in prev_pids:
                            parent_pid, cmdline, exe, cwd, username = None, "", "", "", ""
                            try:
                                p = psutil.Process(pid)
                                parent_pid = p.ppid()
                                cmdline    = " ".join(p.cmdline())
                                exe        = p.exe()
                                cwd        = p.cwd()
                                username   = p.username()
                            except Exception:
                                pass
                            ev = {
                                "type": "SPAWN", "path": name, "pid": pid,
                                "parent_pid": parent_pid, "cmdline": cmdline[:400],
                                "exe": exe, "cwd": cwd, "username": username,
                                "time": _ts(), "category": "process",
                            }
                            self.process_events.append(ev)
                            self.event_queue.put(ev)
                            if self.target_process and parent_pid in self._target_pids:
                                self._target_pids.add(pid)

                    for pid in list(prev_pids):
                        if pid not in cur_pids:
                            ev = {"type": "EXIT", "path": prev_pids[pid], "pid": pid,
                                  "time": _ts(), "category": "process"}
                            self.process_events.append(ev)
                            self.event_queue.put(ev)
                            self._target_pids.discard(pid)

                    if self.target_process and not self._target_pids:
                        for pid, name in cur_pids.items():
                            if name.lower() == self.target_process:
                                self._target_pids.add(pid)
                                ev = {"type": "TARGET_FOUND", "path": f"{name} (PID {pid})",
                                      "pid": pid, "time": _ts(), "category": "process"}
                                self.process_events.append(ev)
                                self.event_queue.put(ev)

                    prev_pids = cur_pids
                except Exception:
                    pass

        t = threading.Thread(target=run, daemon=True, name="ScoutProcMon")
        t.start()
        self._threads.append(t)

    # ── open-files monitor (per-process file access) ─────────────────────────

    def _start_open_files_monitor(self) -> None:
        """Poll open file handles of every tracked PID every 0.2 s.

        This gives us a process-filtered list of files the target application
        actually touched, independent of the broad watchdog observer.
        """
        session = self

        def run():
            seen: set[str] = set()
            while session.is_running:
                time.sleep(0.2)
                for pid in list(session._target_pids):
                    try:
                        for f in psutil.Process(pid).open_files():
                            norm = f.path.lower()
                            if norm not in seen:
                                seen.add(norm)
                                ev = {
                                    "type": "FILE_ACCESS",
                                    "path": f.path,
                                    "pid": pid,
                                    "time": _ts(),
                                    "category": "file_access",
                                }
                                session.file_access_events.append(ev)
                                session.event_queue.put(ev)
                    except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
                        pass

        t = threading.Thread(target=run, daemon=True, name="ScoutOpenFiles")
        t.start()
        self._threads.append(t)

    # ── DLL monitor ──────────────────────────────────────────────────────────

    def _start_dll_monitor(self) -> None:
        """Poll loaded modules of the target process (and its children) for new DLLs."""
        def run():
            # {pid: set_of_known_dll_paths}
            dll_snapshots: dict[int, set] = {}
            warned_no_access: set[int] = set()

            while self.is_running:
                time.sleep(1)
                try:
                    pids_to_watch = set(self._target_pids)
                    if not pids_to_watch:
                        continue

                    for pid in pids_to_watch:
                        cur_dlls = _get_modules(pid)
                        prev_dlls = dll_snapshots.get(pid)

                        if prev_dlls is None:
                            # First snapshot for this PID
                            dll_snapshots[pid] = cur_dlls
                            continue

                        if not cur_dlls and not prev_dlls and pid not in warned_no_access:
                            warned_no_access.add(pid)
                            ev = {
                                "type": "DLL_WARN",
                                "path": f"Cannot read modules for PID {pid} (run as admin)",
                                "pid": pid, "time": _ts(), "category": "dll",
                            }
                            self.dll_events.append(ev)
                            self.event_queue.put(ev)
                            continue

                        for dll in cur_dlls - prev_dlls:
                            ev = {
                                "type": "DLL_LOAD",
                                "path": dll, "pid": pid,
                                "time": _ts(), "category": "dll",
                            }
                            self.dll_events.append(ev)
                            self.event_queue.put(ev)

                        dll_snapshots[pid] = cur_dlls

                    # Clean up PIDs that are no longer tracked
                    for pid in list(dll_snapshots):
                        if pid not in pids_to_watch:
                            del dll_snapshots[pid]
                except Exception:
                    pass

        t = threading.Thread(target=run, daemon=True, name="ScoutDLLMon")
        t.start()
        self._threads.append(t)

    # ── network monitor ──────────────────────────────────────────────────────

    def _start_network_monitor(self) -> None:
        def run():
            def _conn_key(c):
                return (
                    c.laddr.ip if c.laddr else "",
                    c.laddr.port if c.laddr else 0,
                    c.raddr.ip if c.raddr else "",
                    c.raddr.port if c.raddr else 0,
                    c.pid or 0,
                )

            prev: set = set()
            try:
                prev = {_conn_key(c) for c in psutil.net_connections(kind="all") if c.raddr}
            except Exception:
                pass

            while self.is_running:
                time.sleep(1)
                try:
                    cur_conns = psutil.net_connections(kind="all")
                    cur: set = {_conn_key(c) for c in cur_conns if c.raddr}

                    for c in cur_conns:
                        if not c.raddr:
                            continue
                        key = _conn_key(c)
                        if key not in prev:
                            proc_name = ""
                            if c.pid:
                                try:
                                    proc_name = psutil.Process(c.pid).name()
                                except Exception:
                                    pass
                            remote_ip   = c.raddr.ip
                            remote_port = c.raddr.port
                            local_str   = f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else "?"
                            remote_str  = f"{remote_ip}:{remote_port}"
                            ev = {
                                "type": "CONNECT",
                                "path": f"{local_str} -> {remote_str}",
                                "local": local_str,
                                "remote": remote_str,
                                "remote_ip": remote_ip,
                                "remote_port": remote_port,
                                "remote_host": _reverse_dns(remote_ip),
                                "pid": c.pid or 0,
                                "process": proc_name,
                                "status": c.status,
                                "time": _ts(),
                                "category": "network",
                            }
                            self.network_events.append(ev)
                            self.event_queue.put(ev)

                    prev = cur
                except Exception:
                    pass

        t = threading.Thread(target=run, daemon=True, name="ScoutNetMon")
        t.start()
        self._threads.append(t)

    # ── registry monitor ─────────────────────────────────────────────────────

    def _start_registry_monitor(self) -> None:
        if os.name != "nt":
            return

        def run():
            try:
                import winreg
                hive_map = {
                    "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
                    "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
                }
            except ImportError:
                return

            prev_snaps: dict[str, dict] = {}
            for label, hive_name, key_path in self._REG_MONITOR:
                hive = hive_map.get(hive_name)
                if hive is not None:
                    prev_snaps[label] = _snapshot_reg_key(hive, key_path)

            while self.is_running:
                time.sleep(1)  # 1-second poll for fast detection
                for label, hive_name, key_path in self._REG_MONITOR:
                    hive = hive_map.get(hive_name)
                    if hive is None:
                        continue
                    cur  = _snapshot_reg_key(hive, key_path)
                    prev = prev_snaps.get(label, {})

                    for name, value in cur.items():
                        if name not in prev:
                            kind = "REG_ADD_KEY" if name.startswith("__KEY_") else "REG_ADD"
                            ev = {"type": kind,
                                  "path": f"{label}\\{value if name.startswith('__KEY_') else name}",
                                  "value": value, "time": _ts(), "category": "registry"}
                            self.registry_events.append(ev)
                            self.event_queue.put(ev)
                        elif prev[name] != value:
                            ev = {"type": "REG_MODIFY", "path": f"{label}\\{name}",
                                  "old_value": prev[name][:200], "new_value": value[:200],
                                  "time": _ts(), "category": "registry"}
                            self.registry_events.append(ev)
                            self.event_queue.put(ev)

                    for name in prev:
                        if name not in cur:
                            kind = "REG_DEL_KEY" if name.startswith("__KEY_") else "REG_DELETE"
                            ev = {"type": kind, "path": f"{label}\\{name}",
                                  "old_value": prev[name][:200],
                                  "time": _ts(), "category": "registry"}
                            self.registry_events.append(ev)
                            self.event_queue.put(ev)

                    prev_snaps[label] = cur

        t = threading.Thread(target=run, daemon=True, name="ScoutRegMon")
        t.start()
        self._threads.append(t)

    # ── persistence ──────────────────────────────────────────────────────────

    def get_summary(self) -> dict:
        duration = (time.time() - self.start_time) if self.start_time else 0
        return {
            "app_name":          self.app_name,
            "session_id":        self.session_id,
            "duration_s":        round(duration, 1),
            "file_events":       len(self.file_events),
            "file_access_events": len(self.file_access_events),
            "registry_events":   len(self.registry_events),
            "network_events":    len(self.network_events),
            "process_events":    len(self.process_events),
            "download_events":   len(self.download_events),
            "dll_events":        len(self.dll_events),
            "total_events":      (len(self.file_events) + len(self.file_access_events) +
                                  len(self.registry_events) + len(self.network_events) +
                                  len(self.process_events) + len(self.download_events) +
                                  len(self.dll_events)),
        }

    def _save_session(self) -> None:
        os.makedirs(self.profile_path, exist_ok=True)
        data = {
            "app_name":           self.app_name,
            "session_id":         self.session_id,
            "watch_paths":        self.watch_paths,
            "target_process":     self.target_process,
            "start_time":         self.start_time,
            "end_time":           time.time(),
            "summary":            self.get_summary(),
            "file_access_events": self.file_access_events,
            "file_events":        self.file_events,
            "registry_events":    self.registry_events,
            "network_events":     self.network_events,
            "process_events":     self.process_events,
            "download_events":    self.download_events,
            "dll_events":         self.dll_events,
        }
        with open(self.session_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _build_export_data(self) -> dict:
        return {
            "app_name":           self.app_name,
            "session_id":         self.session_id,
            "watch_paths":        self.watch_paths,
            "target_process":     self.target_process,
            "start_time":         self.start_time,
            "end_time":           time.time(),
            "summary":            self.get_summary(),
            "file_access_events": self.file_access_events,
            "file_events":        self.file_events,
            "registry_events":    self.registry_events,
            "network_events":     self.network_events,
            "process_events":     self.process_events,
            "download_events":    self.download_events,
            "dll_events":         self.dll_events,
        }

    def export_html(self, filepath: str | None = None) -> str:
        """Export session as a self-contained interactive HTML report."""
        import html as _html
        import datetime as _dt

        if filepath is None:
            filepath = os.path.join(
                self.profile_path, f"scout_export_{self.session_id}.html"
            )
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

        sm = self.get_summary()

        def esc(v: object) -> str:
            return _html.escape(str(v)) if v is not None else ""

        try:
            start_dt = _dt.datetime.fromtimestamp(self.start_time).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            start_dt = "?"

        TYPE_CLS = {
            "CREATE": "c-grn", "MODIFY": "c-yel", "DELETE": "c-red", "MOVE": "c-cyn",
            "FILE_ACCESS": "c-grn",
            "CONNECT": "c-cyn",
            "REG_ADD": "c-grn", "REG_ADD_KEY": "c-grn",
            "REG_MODIFY": "c-yel",
            "REG_DELETE": "c-red", "REG_DEL_KEY": "c-red",
            "SPAWN": "c-grn", "EXIT": "c-dim", "TARGET_FOUND": "c-yel",
            "DLL_LOAD": "c-cyn", "DLL_WARN": "c-yel",
            "DOWNLOAD": "c-grn", "DOWNLOAD_UPDATE": "c-yel",
        }

        def badge(etype: str) -> str:
            cls = TYPE_CLS.get(etype, "")
            return f'<span class="bdg {cls}">{esc(etype)}</span>'

        def td_trunc(value: object) -> str:
            return f'<td class="trunc">{esc(value)}</td>'

        def build_rows_file_access(evs: list) -> str:
            rows = []
            for ev in evs:
                rows.append(
                    f'<tr><td class="tm">{esc(ev.get("time",""))}</td>'
                    f'<td>{esc(ev.get("pid",""))}</td>'
                    f'{td_trunc(ev.get("path",""))}</tr>'
                )
            return "".join(rows)

        def build_rows_files(evs: list) -> str:
            rows = []
            for ev in evs:
                dest = ev.get("dest", "")
                rows.append(
                    f'<tr><td class="tm">{esc(ev.get("time",""))}</td>'
                    f'<td>{badge(ev.get("type",""))}</td>'
                    f'{td_trunc(ev.get("path",""))}'
                    f'{td_trunc(dest) if dest else "<td></td>"}</tr>'
                )
            return "".join(rows)

        def build_rows_registry(evs: list) -> str:
            rows = []
            for ev in evs:
                old_v = str(ev.get("old_value", ""))[:300]
                new_v = str(ev.get("new_value", ev.get("value", "")))[:300]
                rows.append(
                    f'<tr><td class="tm">{esc(ev.get("time",""))}</td>'
                    f'<td>{badge(ev.get("type",""))}</td>'
                    f'{td_trunc(ev.get("path",""))}'
                    f'{td_trunc(old_v)}'
                    f'{td_trunc(new_v)}</tr>'
                )
            return "".join(rows)

        def build_rows_network(evs: list) -> str:
            rows = []
            for ev in evs:
                rows.append(
                    f'<tr><td class="tm">{esc(ev.get("time",""))}</td>'
                    f'<td>{esc(ev.get("process",""))}</td>'
                    f'<td>{esc(ev.get("pid",""))}</td>'
                    f'<td class="mono">{esc(ev.get("local",""))}</td>'
                    f'<td class="mono">{esc(ev.get("remote",""))}</td>'
                    f'{td_trunc(ev.get("remote_host",""))}'
                    f'<td>{esc(ev.get("status",""))}</td></tr>'
                )
            return "".join(rows)

        def build_rows_process(evs: list) -> str:
            rows = []
            for ev in evs:
                rows.append(
                    f'<tr><td class="tm">{esc(ev.get("time",""))}</td>'
                    f'<td>{badge(ev.get("type",""))}</td>'
                    f'<td>{esc(ev.get("path",""))}</td>'
                    f'<td>{esc(ev.get("pid",""))}</td>'
                    f'<td>{esc(ev.get("parent_pid",""))}</td>'
                    f'{td_trunc(ev.get("exe",""))}'
                    f'{td_trunc(ev.get("cmdline",""))}'
                    f'<td>{esc(ev.get("username",""))}</td></tr>'
                )
            return "".join(rows)

        def build_rows_dll(evs: list) -> str:
            rows = []
            for ev in evs:
                rows.append(
                    f'<tr><td class="tm">{esc(ev.get("time",""))}</td>'
                    f'<td>{badge(ev.get("type",""))}</td>'
                    f'<td>{esc(ev.get("pid",""))}</td>'
                    f'{td_trunc(ev.get("path",""))}</tr>'
                )
            return "".join(rows)

        def build_rows_download(evs: list) -> str:
            rows = []
            for ev in evs:
                size = ev.get("size", 0)
                size_str = f"{size:,} B" if size else ""
                rows.append(
                    f'<tr><td class="tm">{esc(ev.get("time",""))}</td>'
                    f'<td>{badge(ev.get("type",""))}</td>'
                    f'{td_trunc(ev.get("path",""))}'
                    f'<td>{size_str}</td></tr>'
                )
            return "".join(rows)

        def panel_table(tab_id: str, headers: list, rows_html: str, count: int) -> str:
            if not rows_html:
                return '<div class="no-ev">Žádné události</div>'
            ths = "".join(
                f'<th onclick="sortTbl(this)">{h}</th>' for h in headers
            )
            return (
                f'<div class="cnt-info" id="ci-{tab_id}">{count} událostí</div>'
                f'<div class="tbl-wrap">'
                f'<table id="tbl-{tab_id}"><thead><tr>{ths}</tr></thead>'
                f'<tbody>{rows_html}</tbody></table></div>'
            )

        panels_data = [
            ("fopen", "Soubory (proces)",    sm.get("file_access_events", 0),
             panel_table("fopen", ["Čas", "PID", "Cesta"],
                         build_rows_file_access(self.file_access_events),
                         sm.get("file_access_events", 0))),
            ("files", "Změny souborů",       sm.get("file_events", 0),
             panel_table("files", ["Čas", "Typ", "Cesta", "Cíl"],
                         build_rows_files(self.file_events),
                         sm.get("file_events", 0))),
            ("reg",   "Registr",             sm.get("registry_events", 0),
             panel_table("reg", ["Čas", "Typ", "Klíč / Hodnota", "Stará data", "Nová data"],
                         build_rows_registry(self.registry_events),
                         sm.get("registry_events", 0))),
            ("net",   "Síť",                 sm.get("network_events", 0),
             panel_table("net", ["Čas", "Proces", "PID", "Local", "Remote", "Hostname", "Status"],
                         build_rows_network(self.network_events),
                         sm.get("network_events", 0))),
            ("proc",  "Procesy",             sm.get("process_events", 0),
             panel_table("proc", ["Čas", "Typ", "Název", "PID", "Parent", "Exe", "Cmdline", "User"],
                         build_rows_process(self.process_events),
                         sm.get("process_events", 0))),
            ("dll",   "DLL",                 sm.get("dll_events", 0),
             panel_table("dll", ["Čas", "Typ", "PID", "Cesta"],
                         build_rows_dll(self.dll_events),
                         sm.get("dll_events", 0))),
            ("dl",    "Downloady",           sm.get("download_events", 0),
             panel_table("dl", ["Čas", "Typ", "Cesta", "Velikost"],
                         build_rows_download(self.download_events),
                         sm.get("download_events", 0))),
        ]

        cards_html = "\n".join(
            f'<div class="card" onclick="switchTab(\'{tid}\')" style="cursor:pointer">'
            f'<div class="num" style="color:{color}">{sm.get(key, 0)}</div>'
            f'<div class="lbl">{label}</div></div>'
            for (tid, label, color, key) in [
                ("fopen", "Soubory (proces)",  "#3fb950", "file_access_events"),
                ("files", "Změny souborů",     "#d29922", "file_events"),
                ("reg",   "Registr",           "#79c0ff", "registry_events"),
                ("net",   "Síť",               "#79c0ff", "network_events"),
                ("proc",  "Procesy",           "#3fb950", "process_events"),
                ("dll",   "DLL",               "#79c0ff", "dll_events"),
                ("dl",    "Downloady",         "#3fb950", "download_events"),
            ]
        )

        tabs_html = "\n".join(
            f'<div class="tab{" active" if i == 0 else ""}" '
            f'id="tab-{tid}" onclick="switchTab(\'{tid}\')">'
            f'{label} <span class="tbdg">{count}</span></div>'
            for i, (tid, label, count, _) in enumerate(panels_data)
        )

        panels_html = "\n".join(
            f'<div class="panel{" active" if i == 0 else ""}" id="panel-{tid}">'
            f'<div class="srch-bar">'
            f'<input type="text" placeholder="Hledat v {label}…" '
            f'oninput="filterTbl(this,\'tbl-{tid}\',\'ci-{tid}\')">'
            f'</div>{content}</div>'
            for i, (tid, label, count, content) in enumerate(panels_data)
        )

        watch_str = esc(", ".join(self.watch_paths) if self.watch_paths else "—")

        doc = f"""<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Scout Report — {esc(self.app_name)}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0d1117;color:#c9d1d9;font-family:'Consolas','Courier New',monospace;font-size:13px;line-height:1.5}}
.hdr{{background:#161b22;border-bottom:1px solid #30363d;padding:18px 28px}}
.hdr h1{{color:#58a6ff;font-size:17px;font-weight:bold;letter-spacing:.3px}}
.hdr .meta{{color:#8b949e;margin-top:7px;font-size:11px;line-height:1.9}}
.hdr .meta b{{color:#c9d1d9}}
.hdr .paths{{color:#8b949e;font-size:10px;margin-top:4px;word-break:break-all}}
.cards{{display:flex;gap:10px;padding:14px 28px;flex-wrap:wrap;border-bottom:1px solid #21262d}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:12px 16px;min-width:105px;transition:border-color .15s}}
.card:hover{{border-color:#58a6ff}}
.card .num{{font-size:22px;font-weight:bold}}
.card .lbl{{color:#8b949e;font-size:10px;margin-top:3px;text-transform:uppercase;letter-spacing:.6px}}
.tabs{{display:flex;background:#0d1117;border-bottom:1px solid #30363d;padding:0 28px;overflow-x:auto}}
.tab{{padding:9px 15px;cursor:pointer;color:#8b949e;border-bottom:2px solid transparent;font-size:12px;white-space:nowrap;transition:color .12s}}
.tab:hover{{color:#c9d1d9}}
.tab.active{{color:#58a6ff;border-bottom-color:#58a6ff}}
.tbdg{{background:#21262d;border-radius:9px;padding:1px 6px;margin-left:4px;font-size:10px;color:#8b949e}}
.panel{{display:none}}.panel.active{{display:block}}
.srch-bar{{padding:12px 28px 8px}}
.srch-bar input{{background:#21262d;border:1px solid #30363d;color:#c9d1d9;padding:6px 12px;border-radius:6px;width:380px;font-family:inherit;font-size:12px;outline:none}}
.srch-bar input:focus{{border-color:#58a6ff;background:#161b22}}
.cnt-info{{color:#8b949e;font-size:11px;padding:0 28px 6px}}
.tbl-wrap{{padding:0 28px 32px;overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
thead{{position:sticky;top:0;z-index:1}}
th{{text-align:left;padding:8px 10px;color:#8b949e;border-bottom:1px solid #30363d;font-weight:normal;background:#0d1117;cursor:pointer;user-select:none;white-space:nowrap}}
th:hover{{color:#c9d1d9}}
th::after{{content:" ↕";opacity:.25;font-size:9px}}
th.asc::after{{content:" ↑";opacity:1}}th.desc::after{{content:" ↓";opacity:1}}
td{{padding:5px 10px;border-bottom:1px solid #161b22;vertical-align:top}}
tr:hover td{{background:#161b22}}
tr.hide{{display:none}}
.tm{{color:#8b949e;white-space:nowrap;font-size:11px}}
.mono{{font-family:'Consolas','Courier New',monospace}}
.trunc{{max-width:440px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer}}
.trunc:hover{{opacity:.8}}
.trunc.exp{{white-space:normal;word-break:break-all;max-width:none}}
.bdg{{display:inline-block;padding:1px 7px;border-radius:4px;font-size:11px;font-weight:bold;background:#21262d;letter-spacing:.2px}}
.c-grn{{color:#3fb950}}.c-yel{{color:#d29922}}.c-red{{color:#f85149}}
.c-cyn{{color:#79c0ff}}.c-dim{{color:#8b949e}}
.no-ev{{color:#8b949e;padding:50px 28px;text-align:center;font-size:13px}}
::-webkit-scrollbar{{width:6px;height:6px}}
::-webkit-scrollbar-track{{background:#0d1117}}
::-webkit-scrollbar-thumb{{background:#30363d;border-radius:3px}}
</style>
</head>
<body>

<div class="hdr">
  <h1>&#9670; Scout Report &mdash; {esc(self.app_name)}</h1>
  <div class="meta">
    Session: <b>{esc(self.session_id)}</b> &nbsp;&bull;&nbsp;
    Target: <b>{esc(self.target_process or "all processes")}</b> &nbsp;&bull;&nbsp;
    Délka: <b>{sm["duration_s"]} s</b> &nbsp;&bull;&nbsp;
    Spuštěno: <b>{start_dt}</b>
  </div>
  <div class="paths">Sledované cesty: {watch_str}</div>
</div>

<div class="cards">
{cards_html}
</div>

<div class="tabs">
{tabs_html}
</div>

{panels_html}

<script>
(function(){{
  function switchTab(id){{
    document.querySelectorAll('.tab').forEach(function(t){{t.classList.remove('active');}});
    document.querySelectorAll('.panel').forEach(function(p){{p.classList.remove('active');}});
    var tab=document.getElementById('tab-'+id);
    var panel=document.getElementById('panel-'+id);
    if(tab) tab.classList.add('active');
    if(panel) panel.classList.add('active');
  }}
  window.switchTab=switchTab;

  window.filterTbl=function(inp,tblId,ciId){{
    var q=inp.value.toLowerCase();
    var rows=document.querySelectorAll('#'+tblId+' tbody tr');
    var vis=0;
    rows.forEach(function(r){{
      var show=!q||r.textContent.toLowerCase().includes(q);
      r.classList.toggle('hide',!show);
      if(show) vis++;
    }});
    var ci=document.getElementById(ciId);
    if(ci){{
      var total=rows.length;
      ci.textContent=(vis<total?(vis+' / '+total):total)+' událostí';
    }}
  }};

  window.sortTbl=function(th){{
    var tbl=th.closest('table');
    var tbody=tbl.querySelector('tbody');
    var col=Array.from(th.parentNode.children).indexOf(th);
    var asc=th.classList.contains('asc');
    tbl.querySelectorAll('th').forEach(function(h){{h.classList.remove('asc','desc');}});
    th.classList.add(asc?'desc':'asc');
    var rows=Array.from(tbody.querySelectorAll('tr'));
    rows.sort(function(a,b){{
      var av=a.cells[col]?a.cells[col].textContent.trim():'';
      var bv=b.cells[col]?b.cells[col].textContent.trim():'';
      return(asc?-1:1)*av.localeCompare(bv,undefined,{{numeric:true,sensitivity:'base'}});
    }});
    rows.forEach(function(r){{tbody.appendChild(r);}});
  }};

  document.querySelectorAll('.trunc').forEach(function(el){{
    el.title='Kliknutím rozbalíte';
    el.addEventListener('click',function(){{el.classList.toggle('exp');}});
  }});
}})();
</script>
</body>
</html>"""

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(doc)
        return filepath

    def export_json(self, filepath: str | None = None) -> str:
        """Export the session to a JSON file and return the path."""
        if filepath is None:
            filepath = os.path.join(
                self.profile_path, f"scout_export_{self.session_id}.json"
            )
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self._build_export_data(), f, indent=2, ensure_ascii=False)
        return filepath

    def export_txt(self, filepath: str | None = None) -> str:
        """Export the session as a human-readable text report and return the path."""
        if filepath is None:
            filepath = os.path.join(
                self.profile_path, f"scout_export_{self.session_id}.txt"
            )
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        sm = self.get_summary()
        lines = [
            "=" * 72,
            "  SCOUT SESSION REPORT",
            "=" * 72,
            f"  Label          : {self.app_name}",
            f"  Session ID     : {self.session_id}",
            f"  Duration       : {sm['duration_s']} s",
            f"  Watch paths    : {', '.join(self.watch_paths)}",
            f"  Target process : {self.target_process or 'all'}",
            f"  Total events   : {sm['total_events']}",
            "=" * 72,
            "",
        ]

        sections = [
            ("FILES ACCESSED BY PROCESS", self.file_access_events,
             ["type", "path", "pid", "time"]),
            ("FILE SYSTEM CHANGES (all processes)", self.file_events,
             ["type", "path", "dest", "time"]),
            ("REGISTRY CHANGES",  self.registry_events,
             ["type", "path", "value", "old_value", "new_value", "time"]),
            ("NETWORK CONNECTIONS", self.network_events,
             ["type", "path", "remote_host", "process", "status", "time"]),
            ("PROCESSES",          self.process_events,
             ["type", "path", "pid", "parent_pid", "cmdline", "exe", "username", "time"]),
            ("DLLS LOADED",        self.dll_events,
             ["type", "path", "pid", "time"]),
            ("DOWNLOADS",          self.download_events,
             ["type", "path", "size", "time"]),
        ]

        for title, events, fields in sections:
            if not events:
                continue
            lines.append("─" * 72)
            lines.append(f"  {title}  ({len(events)})")
            lines.append("─" * 72)
            for ev in events:
                parts = []
                for field in fields:
                    v = ev.get(field)
                    if v is not None and v != "":
                        parts.append(f"{field}={str(v)[:120]}")
                lines.append("  " + "  ".join(parts))
            lines.append("")

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return filepath

    @staticmethod
    def load_sessions(profile_path: str) -> list[dict]:
        sessions: list[dict] = []
        if not os.path.exists(profile_path):
            return sessions
        for filename in sorted(os.listdir(profile_path), reverse=True):
            if filename.startswith("scout_") and filename.endswith(".json"):
                path = os.path.join(profile_path, filename)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        sessions.append(json.load(f))
                except Exception:
                    pass
        return sessions

"""Scout Mode - Deep application behavior monitoring.

Tracks file I/O, registry changes, network connections, downloads,
DLL loading, and child-process spawning for a specific target application.
All events are queued in real time and saved as structured JSON.
"""

import datetime
import hashlib
import json
import os
import queue
import re
import socket
import subprocess
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


def _parse_dns_cache() -> set[str]:
    """Return set of hostnames currently in the Windows DNS resolver cache."""
    entries: set[str] = set()
    try:
        out = subprocess.run(
            ["ipconfig", "/displaydns"],
            capture_output=True, text=True,
            encoding="utf-8", errors="ignore", timeout=6,
        ).stdout
        for line in out.splitlines():
            m = re.search(r"Record Name[\s.]+:\s+(.+)", line)
            if m:
                hostname = m.group(1).strip().rstrip(".").lower()
                if hostname:
                    entries.add(hostname)
    except Exception:
        pass
    return entries


def _list_named_pipes() -> set[str]:
    """Return set of currently existing named pipe names (Windows only)."""
    try:
        return set(os.listdir(r"\\.\pipe\\"))
    except Exception:
        return set()


def _sha256(path: str) -> str | None:
    """Compute SHA-256 of a file; returns None on error or if file > 200 MB."""
    try:
        if os.path.getsize(path) > 200 * 1024 * 1024:
            return "skipped:too_large"
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


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
        self.watch_paths:     list[str] = []
        self.downloads_path   = str(Path.home() / "Downloads")
        self.target_process:  str | None = None
        self._target_pids:    set[int] = set()
        self._launched_process = None
        self.file_access_events: list[dict] = []

        # Extended monitoring
        self.dns_events:   list[dict] = []
        self.pipe_events:  list[dict] = []
        self.file_hashes:  dict[str, str] = {}
        self.risk_flags:   list[dict] = []

        # Control flags
        self.is_paused:             bool = False
        self._auto_stop_requested:  bool = False

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
        self._start_dns_monitor()
        self._start_pipe_monitor()

    def stop(self) -> None:
        if not self.is_running:
            return
        self.is_running = False
        self.is_paused = False
        if self._observer:
            self._observer.stop()
            self._observer.join()
        self._hash_accessed_files()
        self.risk_flags = self._analyze_risks()
        self.logger.log(
            "scout_stop", "scout",
            f"session_id={self.session_id} risk_score={self.get_risk_score()}",
        )
        self._save_session()

    def pause(self) -> None:
        """Pause all monitors without stopping the session."""
        self.is_paused = True

    def resume(self) -> None:
        """Resume a paused session."""
        self.is_paused = False

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
            had_targets = False

            if self.target_process:
                for pid, name in prev_pids.items():
                    if name.lower() == self.target_process:
                        self._target_pids.add(pid)
                        had_targets = True

            while self.is_running:
                if self.is_paused:
                    time.sleep(0.2)
                    continue
                time.sleep(0.5)
                try:
                    cur_pids = _snapshot_pids()

                    for pid, name in cur_pids.items():
                        if pid not in prev_pids:
                            parent_pid, cmdline, exe, cwd, username, environ_snap = (
                                None, "", "", "", "", {}
                            )
                            try:
                                p = psutil.Process(pid)
                                parent_pid = p.ppid()
                                cmdline    = " ".join(p.cmdline())
                                exe        = p.exe()
                                cwd        = p.cwd()
                                username   = p.username()
                                # Only capture a handful of relevant env vars
                                full_env   = p.environ()
                                environ_snap = {
                                    k: full_env[k] for k in (
                                        "PATH", "APPDATA", "LOCALAPPDATA",
                                        "TEMP", "USERNAME", "COMPUTERNAME",
                                        "SYSTEMROOT",
                                    ) if k in full_env
                                }
                            except Exception:
                                pass
                            ev = {
                                "type": "SPAWN", "path": name, "pid": pid,
                                "parent_pid": parent_pid, "cmdline": cmdline[:400],
                                "exe": exe, "cwd": cwd, "username": username,
                                "environ": environ_snap,
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
                                had_targets = True
                                ev = {"type": "TARGET_FOUND",
                                      "path": f"{name} (PID {pid})",
                                      "pid": pid, "time": _ts(), "category": "process"}
                                self.process_events.append(ev)
                                self.event_queue.put(ev)

                    # Auto-stop: tracked process and all its children have exited
                    if had_targets and not self._target_pids and not self._auto_stop_requested:
                        self._auto_stop_requested = True
                        ev = {"type": "AUTO_STOP",
                              "path": "Sledovaný proces (a všechny podprocesy) skončil",
                              "time": _ts(), "category": "system"}
                        self.event_queue.put(ev)

                    if self._target_pids:
                        had_targets = True

                    prev_pids = cur_pids
                except Exception:
                    pass

        t = threading.Thread(target=run, daemon=True, name="ScoutProcMon")
        t.start()
        self._threads.append(t)

    # ── open-files monitor (per-process file access) ─────────────────────────

    def _start_open_files_monitor(self) -> None:
        """Poll open file handles of every tracked PID every 0.2 s."""
        session = self

        def run():
            seen: set[str] = set()
            while session.is_running:
                if session.is_paused:
                    time.sleep(0.2)
                    continue
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
                if self.is_paused:
                    time.sleep(0.2)
                    continue
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
                if self.is_paused:
                    time.sleep(0.2)
                    continue
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
                if self.is_paused:
                    time.sleep(0.2)
                    continue
                time.sleep(1)
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

    # ── DNS monitor ──────────────────────────────────────────────────────────

    def _start_dns_monitor(self) -> None:
        """Poll Windows DNS resolver cache every 3 s for new hostname lookups."""
        if os.name != "nt":
            return

        def run():
            seen = _parse_dns_cache()
            while self.is_running:
                if self.is_paused:
                    time.sleep(0.2)
                    continue
                time.sleep(3)
                try:
                    cur = _parse_dns_cache()
                    for host in cur - seen:
                        ev = {
                            "type": "DNS_QUERY",
                            "path": host,
                            "time": _ts(),
                            "category": "dns",
                        }
                        self.dns_events.append(ev)
                        self.event_queue.put(ev)
                    seen = cur
                except Exception:
                    pass

        t = threading.Thread(target=run, daemon=True, name="ScoutDNSMon")
        t.start()
        self._threads.append(t)

    # ── named-pipe monitor ───────────────────────────────────────────────────

    def _start_pipe_monitor(self) -> None:
        """Detect new named pipes every 2 s (Windows only)."""
        if os.name != "nt":
            return

        def run():
            seen = _list_named_pipes()
            while self.is_running:
                if self.is_paused:
                    time.sleep(0.2)
                    continue
                time.sleep(2)
                try:
                    cur = _list_named_pipes()
                    for pipe in cur - seen:
                        ev = {
                            "type": "PIPE_NEW",
                            "path": f"\\\\.\\pipe\\{pipe}",
                            "time": _ts(),
                            "category": "pipe",
                        }
                        self.pipe_events.append(ev)
                        self.event_queue.put(ev)
                    seen = cur
                except Exception:
                    pass

        t = threading.Thread(target=run, daemon=True, name="ScoutPipeMon")
        t.start()
        self._threads.append(t)

    # ── post-session analysis ────────────────────────────────────────────────

    def _hash_accessed_files(self) -> None:
        """SHA-256 all files touched by the target process (skips missing/huge)."""
        paths: set[str] = set()
        for ev in self.file_access_events:
            p = ev.get("path", "")
            if p:
                paths.add(p)
        for ev in self.file_events:
            if ev.get("type") in ("CREATE", "MODIFY"):
                p = ev.get("path", "")
                if p:
                    paths.add(p)
        for path in paths:
            if not os.path.isfile(path):
                continue
            digest = _sha256(path)
            if digest:
                self.file_hashes[path] = digest

    def _analyze_risks(self) -> list[dict]:
        """Scan collected events and return a list of risk-flag dicts."""
        flags: list[dict] = []

        def flag(severity: str, category: str, desc: str, time: str = "") -> None:
            flags.append({
                "severity": severity, "category": category,
                "desc": desc, "time": time,
            })

        # ── Registry checks ──────────────────────────────────────────────────
        for ev in self.registry_events:
            path  = ev.get("path", "").lower()
            etype = ev.get("type", "")
            t     = ev.get("time", "")
            if etype in ("REG_ADD", "REG_MODIFY"):
                if "\\run" in path or "\\runonce" in path:
                    flag("HIGH",     "Persistence",     f"Zápis do Run klíče: {ev['path']}", t)
                if "ifeo" in path:
                    flag("CRITICAL", "DLL Injection",   f"Modifikace IFEO (debugger hijack): {ev['path']}", t)
                if "appinit" in path:
                    flag("CRITICAL", "DLL Injection",   f"Modifikace AppInit DLLs: {ev['path']}", t)
                if "winlogon" in path and "microsoft" in path:
                    flag("HIGH",     "Auth Hook",       f"Modifikace Winlogon: {ev['path']}", t)
                if "\\lsa" in path:
                    flag("CRITICAL", "Auth Hook",       f"Modifikace LSA (credential theft vector): {ev['path']}", t)
                if "firewall" in path:
                    flag("MEDIUM",   "Firewall Bypass", f"Modifikace firewall pravidel: {ev['path']}", t)
                if "\\services" in path and "\\run" not in path:
                    flag("MEDIUM",   "Service Install", f"Změna v Services: {ev['path']}", t)
                if "taskcache" in path or "schedule" in path:
                    flag("MEDIUM",   "Persistence",     f"Modifikace naplánovaných úloh: {ev['path']}", t)
                if "policies" in path:
                    flag("MEDIUM",   "Policy Change",   f"Modifikace Group Policy: {ev['path']}", t)

        # ── Process checks ───────────────────────────────────────────────────
        _SUSPICIOUS_PROCS = {
            "cmd.exe", "powershell.exe", "pwsh.exe", "wscript.exe", "cscript.exe",
            "mshta.exe", "regsvr32.exe", "rundll32.exe", "msiexec.exe",
            "certutil.exe", "bitsadmin.exe", "schtasks.exe",
            "net.exe", "net1.exe", "sc.exe", "reg.exe", "regasm.exe",
            "installutil.exe", "wmic.exe",
        }
        for ev in self.process_events:
            if ev.get("type") == "SPAWN":
                name = ev.get("path", "").lower()
                t    = ev.get("time", "")
                if name in _SUSPICIOUS_PROCS:
                    flag("MEDIUM", "Shell Spawn",
                         f"Spuštěn podezřelý proces: {ev['path']} (PID {ev.get('pid','')})"
                         + (f" ← {ev.get('cmdline','')[:80]}" if ev.get("cmdline") else ""), t)

        # ── DLL checks ───────────────────────────────────────────────────────
        _SUSPICIOUS_DIRS = [d.lower() for d in [
            os.environ.get("TEMP", ""), os.environ.get("TMP", ""),
            os.environ.get("APPDATA", ""), os.environ.get("LOCALAPPDATA", ""),
        ] if d]
        for ev in self.dll_events:
            dll = ev.get("path", "").lower()
            t   = ev.get("time", "")
            for d in _SUSPICIOUS_DIRS:
                if d and dll.startswith(d):
                    flag("HIGH", "Suspicious DLL",
                         f"DLL načtena z dočasné složky: {ev['path']}", t)
                    break

        # ── File checks ──────────────────────────────────────────────────────
        for ev in self.file_events:
            path  = ev.get("path", "").lower()
            etype = ev.get("type", "")
            t     = ev.get("time", "")
            if etype in ("CREATE", "MODIFY") and "system32" in path:
                flag("HIGH", "System Tamper", f"Zápis do System32: {ev['path']}", t)
            if etype in ("CREATE", "MODIFY") and path.endswith((".exe", ".dll", ".bat", ".ps1", ".vbs")):
                flag("LOW", "Executable Write", f"Vytvoření spustitelného souboru: {ev['path']}", t)

        # ── Network checks ───────────────────────────────────────────────────
        _LOCAL_PREFIXES = ("127.", "192.168.", "10.", "172.16.", "172.17.",
                           "172.18.", "172.19.", "172.20.", "172.21.", "172.22.",
                           "172.23.", "172.24.", "172.25.", "172.26.", "172.27.",
                           "172.28.", "172.29.", "172.30.", "172.31.", "::1", "0.0.0.0")
        seen_ext: set[str] = set()
        for ev in self.network_events:
            ip = ev.get("remote_ip", "")
            t  = ev.get("time", "")
            if ip and not any(ip.startswith(p) for p in _LOCAL_PREFIXES):
                key = f"{ip}:{ev.get('remote_port','')}"
                if key not in seen_ext:
                    seen_ext.add(key)
                    host = ev.get("remote_host", ip)
                    flag("INFO", "External Network",
                         f"Spojení na {host} ({key}) přes {ev.get('process','?')}", t)
            port = ev.get("remote_port", 0)
            if port and port not in (80, 443, 53, 8080, 8443, 22, 21, 25, 587, 993, 995):
                flag("LOW", "Unusual Port",
                     f"Spojení na nestandardním portu {port} → {ev.get('remote_host', ip)}", t)

        # ── DNS checks ───────────────────────────────────────────────────────
        for ev in self.dns_events:
            host = ev.get("path", "").lower()
            t    = ev.get("time", "")
            # Flag raw-IP lookups or suspicious TLDs (basic heuristic)
            if re.match(r"^\d+\.\d+\.\d+\.\d+$", host):
                flag("LOW", "Reverse DNS", f"Reverse DNS lookup na IP: {host}", t)

        # Sort by severity
        _SEV_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
        flags.sort(key=lambda f: _SEV_ORDER.get(f["severity"], 9))
        return flags

    def get_risk_score(self) -> int:
        """Return 0–100 risk score based on current risk_flags."""
        _WEIGHTS = {"CRITICAL": 40, "HIGH": 20, "MEDIUM": 10, "LOW": 4, "INFO": 1}
        return min(sum(_WEIGHTS.get(f["severity"], 0) for f in self.risk_flags), 100)

    # ── persistence ──────────────────────────────────────────────────────────

    def get_summary(self) -> dict:
        duration = (time.time() - self.start_time) if self.start_time else 0
        return {
            "app_name":           self.app_name,
            "session_id":         self.session_id,
            "duration_s":         round(duration, 1),
            "file_access_events": len(self.file_access_events),
            "file_events":        len(self.file_events),
            "registry_events":    len(self.registry_events),
            "network_events":     len(self.network_events),
            "process_events":     len(self.process_events),
            "download_events":    len(self.download_events),
            "dll_events":         len(self.dll_events),
            "dns_events":         len(self.dns_events),
            "pipe_events":        len(self.pipe_events),
            "risk_flags":         len(self.risk_flags),
            "risk_score":         self.get_risk_score(),
            "total_events":       (len(self.file_access_events) + len(self.file_events) +
                                   len(self.registry_events) + len(self.network_events) +
                                   len(self.process_events) + len(self.download_events) +
                                   len(self.dll_events) + len(self.dns_events) +
                                   len(self.pipe_events)),
        }

    def _all_data(self) -> dict:
        return {
            "app_name":           self.app_name,
            "session_id":         self.session_id,
            "watch_paths":        self.watch_paths,
            "target_process":     self.target_process,
            "start_time":         self.start_time,
            "end_time":           time.time(),
            "summary":            self.get_summary(),
            "risk_flags":         self.risk_flags,
            "file_hashes":        self.file_hashes,
            "file_access_events": self.file_access_events,
            "file_events":        self.file_events,
            "registry_events":    self.registry_events,
            "network_events":     self.network_events,
            "process_events":     self.process_events,
            "download_events":    self.download_events,
            "dll_events":         self.dll_events,
            "dns_events":         self.dns_events,
            "pipe_events":        self.pipe_events,
        }

    def _save_session(self) -> None:
        os.makedirs(self.profile_path, exist_ok=True)
        with open(self.session_file, "w", encoding="utf-8") as f:
            json.dump(self._all_data(), f, indent=2)

    def _build_export_data(self) -> dict:
        return self._all_data()

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
        risk_score = self.get_risk_score()
        data = self._all_data()

        def esc(v: object) -> str:
            return _html.escape(str(v)) if v is not None else ""

        # risk score color
        if risk_score >= 50:
            dial_color = "#e74c3c"
        elif risk_score >= 20:
            dial_color = "#f39c12"
        else:
            dial_color = "#27ae60"

        def fmt_bytes(b):
            try:
                b = int(b)
            except Exception:
                return esc(b)
            for u in ["B","KB","MB","GB"]:
                if b < 1024:
                    return f"{b:.1f} {u}"
                b /= 1024
            return f"{b:.1f} TB"

        # --- row builders ---
        def r_fopen(ev):
            sha = esc(ev.get("sha256",""))
            sha_disp = f'<span class="trunc" title="{sha}">{sha[:12]}…</span>' if sha else ""
            return (f"<tr><td>{esc(ev.get('time',''))}</td>"
                    f"<td>{esc(ev.get('pid',''))}</td>"
                    f"<td><span class='trunc' title='{esc(ev.get('path',''))}'>{esc(ev.get('path',''))}</span></td>"
                    f"<td>{sha_disp}</td></tr>")

        def r_files(ev):
            sha = esc(ev.get("sha256",""))
            sha_disp = f'<span class="trunc" title="{sha}">{sha[:12]}…</span>' if sha else ""
            return (f"<tr><td>{esc(ev.get('time',''))}</td>"
                    f"<td>{esc(ev.get('type',''))}</td>"
                    f"<td><span class='trunc' title='{esc(ev.get('path',''))}'>{esc(ev.get('path',''))}</span></td>"
                    f"<td><span class='trunc' title='{esc(ev.get('dest',''))}'>{esc(ev.get('dest',''))}</span></td>"
                    f"<td>{sha_disp}</td></tr>")

        def r_registry(ev):
            old = esc(ev.get("old_data",""))
            new = esc(ev.get("new_data",""))
            return (f"<tr><td>{esc(ev.get('time',''))}</td>"
                    f"<td>{esc(ev.get('type',''))}</td>"
                    f"<td><span class='trunc' title='{esc(ev.get('key',''))}'>{esc(ev.get('key',''))}</span></td>"
                    f"<td><span class='trunc' title='{old}'>{old[:40]}…</span></td>"
                    f"<td><span class='trunc' title='{new}'>{new[:40]}…</span></td></tr>")

        def r_network(ev):
            return (f"<tr><td>{esc(ev.get('time',''))}</td>"
                    f"<td>{esc(ev.get('process',''))}</td>"
                    f"<td>{esc(ev.get('pid',''))}</td>"
                    f"<td>{esc(ev.get('local',''))}</td>"
                    f"<td>{esc(ev.get('remote',''))}</td>"
                    f"<td>{esc(ev.get('hostname',''))}</td>"
                    f"<td>{esc(ev.get('status',''))}</td></tr>")

        def r_process(ev):
            env = ev.get("environ") or {}
            env_str = "; ".join(f"{k}={v}" for k, v in list(env.items())[:10])
            return (f"<tr><td>{esc(ev.get('time',''))}</td>"
                    f"<td>{esc(ev.get('type',''))}</td>"
                    f"<td>{esc(ev.get('name',''))}</td>"
                    f"<td>{esc(ev.get('pid',''))}</td>"
                    f"<td>{esc(ev.get('parent_pid',''))}</td>"
                    f"<td><span class='trunc' title='{esc(ev.get('exe',''))}'>{esc(ev.get('exe',''))}</span></td>"
                    f"<td><span class='trunc' title='{esc(ev.get('cmdline',''))}'>{esc(ev.get('cmdline',''))}</span></td>"
                    f"<td>{esc(ev.get('username',''))}</td>"
                    f"<td><span class='trunc' title='{esc(env_str)}'>{esc(env_str[:40])}…</span></td></tr>")

        def r_dll(ev):
            return (f"<tr><td>{esc(ev.get('time',''))}</td>"
                    f"<td>{esc(ev.get('type',''))}</td>"
                    f"<td>{esc(ev.get('pid',''))}</td>"
                    f"<td><span class='trunc' title='{esc(ev.get('path',''))}'>{esc(ev.get('path',''))}</span></td></tr>")

        def r_download(ev):
            return (f"<tr><td>{esc(ev.get('time',''))}</td>"
                    f"<td>{esc(ev.get('type',''))}</td>"
                    f"<td><span class='trunc' title='{esc(ev.get('path',''))}'>{esc(ev.get('path',''))}</span></td>"
                    f"<td>{fmt_bytes(ev.get('size',0))}</td></tr>")

        def r_dns(ev):
            sev_cls = "badge-high" if ev.get("type") == "DNS_QUERY" else "badge-info"
            return (f"<tr><td>{esc(ev.get('time',''))}</td>"
                    f"<td><span class='badge {sev_cls}'>{esc(ev.get('type',''))}</span></td>"
                    f"<td>{esc(ev.get('hostname',''))}</td></tr>")

        def r_pipes(ev):
            return (f"<tr><td>{esc(ev.get('time',''))}</td>"
                    f"<td>{esc(ev.get('type',''))}</td>"
                    f"<td><span class='trunc' title='{esc(ev.get('path',''))}'>{esc(ev.get('path',''))}</span></td></tr>")

        SEV_CLASS = {
            "CRITICAL": "badge-critical",
            "HIGH": "badge-high",
            "MEDIUM": "badge-medium",
            "LOW": "badge-low",
            "INFO": "badge-info",
        }

        def r_risk(ev):
            sev = str(ev.get("severity","INFO")).upper()
            cls = SEV_CLASS.get(sev, "badge-info")
            return (f"<tr><td>{esc(ev.get('time',''))}</td>"
                    f"<td><span class='badge {cls}'>{esc(sev)}</span></td>"
                    f"<td>{esc(ev.get('category',''))}</td>"
                    f"<td>{esc(ev.get('description',''))}</td></tr>")

        # build timeline: merge all events
        _timeline = []
        for ev in data.get("file_access_events", []):
            _timeline.append({"time": ev.get("time",""), "cat": "FILE_ACCESS", "type": "FOPEN",
                               "desc": ev.get("path","")})
        for ev in data.get("file_events", []):
            _timeline.append({"time": ev.get("time",""), "cat": "FILE", "type": ev.get("type",""),
                               "desc": ev.get("path","")})
        for ev in data.get("registry_events", []):
            _timeline.append({"time": ev.get("time",""), "cat": "REGISTRY", "type": ev.get("type",""),
                               "desc": ev.get("key","")})
        for ev in data.get("network_events", []):
            _timeline.append({"time": ev.get("time",""), "cat": "NETWORK", "type": "NET",
                               "desc": f"{ev.get('local','')} → {ev.get('remote','')}"})
        for ev in data.get("process_events", []):
            _timeline.append({"time": ev.get("time",""), "cat": "PROCESS", "type": ev.get("type",""),
                               "desc": f"{ev.get('name','')} (PID {ev.get('pid','')})"})
        for ev in data.get("dll_events", []):
            _timeline.append({"time": ev.get("time",""), "cat": "DLL", "type": ev.get("type",""),
                               "desc": ev.get("path","")})
        for ev in data.get("dns_events", []):
            _timeline.append({"time": ev.get("time",""), "cat": "DNS", "type": "DNS_QUERY",
                               "desc": ev.get("hostname","")})
        for ev in data.get("pipe_events", []):
            _timeline.append({"time": ev.get("time",""), "cat": "PIPE", "type": ev.get("type",""),
                               "desc": ev.get("path","")})
        for ev in data.get("risk_flags", []):
            _timeline.append({"time": ev.get("time",""), "cat": "RISK", "type": ev.get("severity",""),
                               "desc": ev.get("description","")})
        _timeline.sort(key=lambda x: x["time"])

        def r_timeline(ev):
            return (f"<tr><td>{esc(ev.get('time',''))}</td>"
                    f"<td>{esc(ev.get('cat',''))}</td>"
                    f"<td>{esc(ev.get('type',''))}</td>"
                    f"<td><span class='trunc' title='{esc(ev.get('desc',''))}'>{esc(ev.get('desc',''))}</span></td></tr>")

        def build_rows(evlist, builder):
            if not evlist:
                return "<tr><td colspan='99' style=\'text-align:center;opacity:.5\'>Žádné záznamy</td></tr>"
            return "\n".join(builder(e) for e in evlist)

        # generate HTML
        gen_time = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        app_name = esc(data.get("app_name", ""))
        exe_path = esc(data.get("exe_path", ""))
        watch_path = esc(data.get("watch_path", ""))
        session_id = esc(data.get("session_id", ""))
        duration = data.get("duration_seconds", 0)
        dur_str = f"{int(duration//60)}m {int(duration%60)}s" if duration else "—"

        rows_fopen    = build_rows(data.get("file_access_events", []), r_fopen)
        rows_files    = build_rows(data.get("file_events", []), r_files)
        rows_registry = build_rows(data.get("registry_events", []), r_registry)
        rows_network  = build_rows(data.get("network_events", []), r_network)
        rows_process  = build_rows(data.get("process_events", []), r_process)
        rows_dll      = build_rows(data.get("dll_events", []), r_dll)
        rows_download = build_rows(data.get("downloads", []), r_download)
        rows_dns      = build_rows(data.get("dns_events", []), r_dns)
        rows_pipes    = build_rows(data.get("pipe_events", []), r_pipes)
        rows_risk     = build_rows(data.get("risk_flags", []), r_risk)
        rows_timeline = build_rows(_timeline, r_timeline)

        doc = f"""<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Scout Report – {app_name}</title>
<style>
:root{{--bg:#0d1117;--surface:#161b22;--border:#30363d;--text:#c9d1d9;--accent:#58a6ff;
      --green:#3fb950;--yellow:#d29922;--red:#f85149;--muted:#8b949e}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;font-size:13px;min-height:100vh}}
a{{color:var(--accent);text-decoration:none}}
/* header */
.header{{padding:20px 28px;background:var(--surface);border-bottom:1px solid var(--border);
         display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:16px}}
.header-left h1{{font-size:22px;font-weight:700;color:var(--accent)}}
.header-left .meta{{margin-top:8px;color:var(--muted);line-height:1.7;font-size:12px}}
.header-left .meta b{{color:var(--text)}}
/* risk dial */
.dial-wrap{{text-align:center;cursor:pointer}}
.dial{{width:96px;height:96px;border-radius:50%;border:5px solid {dial_color};
       display:flex;flex-direction:column;align-items:center;justify-content:center;
       background:rgba(0,0,0,.3);transition:.2s}}
.dial:hover{{transform:scale(1.05)}}
.dial .score{{font-size:30px;font-weight:700;color:{dial_color}}}
.dial .lbl{{font-size:10px;color:var(--muted);margin-top:2px}}
/* cards */
.cards{{display:flex;flex-wrap:wrap;gap:10px;padding:16px 28px}}
.card{{background:var(--surface);border:1px solid var(--border);border-radius:8px;
       padding:12px 18px;min-width:130px;flex:1}}
.card .n{{font-size:26px;font-weight:700;color:var(--accent)}}
.card .k{{font-size:11px;color:var(--muted);margin-top:2px}}
/* tabs */
.tabs{{display:flex;flex-wrap:wrap;gap:4px;padding:0 28px;border-bottom:1px solid var(--border);background:var(--surface)}}
.tab{{padding:8px 14px;border:none;background:none;color:var(--muted);cursor:pointer;
      font-size:13px;border-bottom:2px solid transparent;transition:.15s}}
.tab:hover{{color:var(--text)}}
.tab.active{{color:var(--accent);border-bottom-color:var(--accent)}}
/* panels */
.panel{{display:none;padding:20px 28px}}
.panel.active{{display:block}}
/* filter bar */
.filter-bar{{display:flex;align-items:center;gap:8px;margin-bottom:12px;flex-wrap:wrap}}
.filter-bar input{{background:var(--surface);border:1px solid var(--border);border-radius:6px;
                   color:var(--text);padding:5px 10px;font-size:12px;width:260px}}
.filter-bar input:focus{{outline:none;border-color:var(--accent)}}
.count{{color:var(--muted);font-size:12px}}
/* table */
.tbl-wrap{{overflow-x:auto;border-radius:6px;border:1px solid var(--border)}}
table{{width:100%;border-collapse:collapse}}
th{{background:#1c2128;color:var(--muted);font-weight:600;padding:8px 10px;
    text-align:left;font-size:11px;cursor:pointer;user-select:none;white-space:nowrap}}
th:hover{{color:var(--text)}}
td{{padding:6px 10px;border-top:1px solid var(--border);vertical-align:top;word-break:break-all}}
tr:hover td{{background:rgba(88,166,255,.04)}}
.trunc{{display:inline-block;max-width:320px;overflow:hidden;white-space:nowrap;
        text-overflow:ellipsis;vertical-align:bottom;cursor:pointer}}
.trunc.expanded{{max-width:none;white-space:normal;word-break:break-all}}
/* badges */
.badge{{display:inline-block;padding:2px 7px;border-radius:10px;font-size:10px;font-weight:700;text-transform:uppercase}}
.badge-critical{{background:#5a0000;color:#ff8080}}
.badge-high{{background:#5a3000;color:#ffb347}}
.badge-medium{{background:#4a4000;color:#ffe080}}
.badge-low{{background:#003a20;color:#7fff90}}
.badge-info{{background:#003060;color:#80c0ff}}
/* footer */
.footer{{text-align:center;padding:16px;color:var(--muted);font-size:11px;border-top:1px solid var(--border)}}
</style>
</head>
<body>
<div class="header">
  <div class="header-left">
    <h1>Scout Report — {app_name}</h1>
    <div class="meta">
      <b>Session ID:</b> {session_id}<br>
      <b>Exe:</b> {exe_path}<br>
      <b>Watch path:</b> {watch_path}<br>
      <b>Duration:</b> {dur_str} &nbsp;|&nbsp; <b>Generated:</b> {gen_time}
    </div>
  </div>
  <div class="dial-wrap" onclick="switchTab('risk')" title="Kliknutím zobrazíš rizika">
    <div class="dial">
      <span class="score">{risk_score}</span>
      <span class="lbl">RISK</span>
    </div>
    <div style="font-size:11px;color:var(--muted);margin-top:4px">klikni pro detail</div>
  </div>
</div>

<div class="cards">
  <div class="card"><div class="n" style="color:{dial_color}">{risk_score}</div><div class="k">Risk Score</div></div>
  <div class="card"><div class="n">{sm.get("file_access_events",0)}</div><div class="k">Soubory (proces)</div></div>
  <div class="card"><div class="n">{sm.get("file_events",0)}</div><div class="k">Změny souborů</div></div>
  <div class="card"><div class="n">{sm.get("registry_events",0)}</div><div class="k">Registr</div></div>
  <div class="card"><div class="n">{sm.get("network_events",0)}</div><div class="k">Síť</div></div>
  <div class="card"><div class="n">{sm.get("process_events",0)}</div><div class="k">Procesy</div></div>
  <div class="card"><div class="n">{sm.get("dll_events",0)}</div><div class="k">DLL</div></div>
  <div class="card"><div class="n">{sm.get("dns_events",0)}</div><div class="k">DNS</div></div>
  <div class="card"><div class="n">{sm.get("pipe_events",0)}</div><div class="k">Named Pipes</div></div>
</div>

<div class="tabs">
  <button class="tab active" onclick="switchTab('risk')">⚠ Rizika</button>
  <button class="tab" onclick="switchTab('timeline')">⏱ Timeline</button>
  <button class="tab" onclick="switchTab('fopen')">Soubory (proces)</button>
  <button class="tab" onclick="switchTab('files')">Změny souborů</button>
  <button class="tab" onclick="switchTab('reg')">Registr</button>
  <button class="tab" onclick="switchTab('net')">Síť</button>
  <button class="tab" onclick="switchTab('proc')">Procesy</button>
  <button class="tab" onclick="switchTab('dll')">DLL</button>
  <button class="tab" onclick="switchTab('dns')">DNS</button>
  <button class="tab" onclick="switchTab('pipe')">Named Pipes</button>
  <button class="tab" onclick="switchTab('dl')">Downloady</button>
</div>

<!-- RISK -->
<div id="panel-risk" class="panel active">
  <div class="filter-bar">
    <input type="text" placeholder="Filtr…" oninput="filterTbl('tbl-risk',this.value)">
    <span class="count" id="cnt-risk"></span>
  </div>
  <div class="tbl-wrap"><table id="tbl-risk">
    <thead><tr><th onclick="sortTbl('tbl-risk',0)">Čas</th><th onclick="sortTbl('tbl-risk',1)">Závažnost</th>
    <th onclick="sortTbl('tbl-risk',2)">Kategorie</th><th onclick="sortTbl('tbl-risk',3)">Popis</th></tr></thead>
    <tbody>{rows_risk}</tbody>
  </table></div>
</div>

<!-- TIMELINE -->
<div id="panel-timeline" class="panel">
  <div class="filter-bar">
    <input type="text" placeholder="Filtr…" oninput="filterTbl('tbl-timeline',this.value)">
    <span class="count" id="cnt-timeline"></span>
  </div>
  <div class="tbl-wrap"><table id="tbl-timeline">
    <thead><tr><th onclick="sortTbl('tbl-timeline',0)">Čas</th><th onclick="sortTbl('tbl-timeline',1)">Kategorie</th>
    <th onclick="sortTbl('tbl-timeline',2)">Typ</th><th onclick="sortTbl('tbl-timeline',3)">Popis</th></tr></thead>
    <tbody>{rows_timeline}</tbody>
  </table></div>
</div>

<!-- FILE OPEN (per-process) -->
<div id="panel-fopen" class="panel">
  <div class="filter-bar">
    <input type="text" placeholder="Filtr…" oninput="filterTbl('tbl-fopen',this.value)">
    <span class="count" id="cnt-fopen"></span>
  </div>
  <div class="tbl-wrap"><table id="tbl-fopen">
    <thead><tr><th onclick="sortTbl('tbl-fopen',0)">Čas</th><th onclick="sortTbl('tbl-fopen',1)">PID</th>
    <th onclick="sortTbl('tbl-fopen',2)">Cesta</th><th onclick="sortTbl('tbl-fopen',3)">SHA-256</th></tr></thead>
    <tbody>{rows_fopen}</tbody>
  </table></div>
</div>

<!-- FILE EVENTS -->
<div id="panel-files" class="panel">
  <div class="filter-bar">
    <input type="text" placeholder="Filtr…" oninput="filterTbl('tbl-files',this.value)">
    <span class="count" id="cnt-files"></span>
  </div>
  <div class="tbl-wrap"><table id="tbl-files">
    <thead><tr><th onclick="sortTbl('tbl-files',0)">Čas</th><th onclick="sortTbl('tbl-files',1)">Typ</th>
    <th onclick="sortTbl('tbl-files',2)">Cesta</th><th onclick="sortTbl('tbl-files',3)">Cíl</th>
    <th onclick="sortTbl('tbl-files',4)">SHA-256</th></tr></thead>
    <tbody>{rows_files}</tbody>
  </table></div>
</div>

<!-- REGISTRY -->
<div id="panel-reg" class="panel">
  <div class="filter-bar">
    <input type="text" placeholder="Filtr…" oninput="filterTbl('tbl-reg',this.value)">
    <span class="count" id="cnt-reg"></span>
  </div>
  <div class="tbl-wrap"><table id="tbl-reg">
    <thead><tr><th onclick="sortTbl('tbl-reg',0)">Čas</th><th onclick="sortTbl('tbl-reg',1)">Typ</th>
    <th onclick="sortTbl('tbl-reg',2)">Klíč</th><th onclick="sortTbl('tbl-reg',3)">Stará data</th>
    <th onclick="sortTbl('tbl-reg',4)">Nová data</th></tr></thead>
    <tbody>{rows_registry}</tbody>
  </table></div>
</div>

<!-- NETWORK -->
<div id="panel-net" class="panel">
  <div class="filter-bar">
    <input type="text" placeholder="Filtr…" oninput="filterTbl('tbl-net',this.value)">
    <span class="count" id="cnt-net"></span>
  </div>
  <div class="tbl-wrap"><table id="tbl-net">
    <thead><tr><th onclick="sortTbl('tbl-net',0)">Čas</th><th onclick="sortTbl('tbl-net',1)">Proces</th>
    <th onclick="sortTbl('tbl-net',2)">PID</th><th onclick="sortTbl('tbl-net',3)">Local</th>
    <th onclick="sortTbl('tbl-net',4)">Remote</th><th onclick="sortTbl('tbl-net',5)">Hostname</th>
    <th onclick="sortTbl('tbl-net',6)">Status</th></tr></thead>
    <tbody>{rows_network}</tbody>
  </table></div>
</div>

<!-- PROCESSES -->
<div id="panel-proc" class="panel">
  <div class="filter-bar">
    <input type="text" placeholder="Filtr…" oninput="filterTbl('tbl-proc',this.value)">
    <span class="count" id="cnt-proc"></span>
  </div>
  <div class="tbl-wrap"><table id="tbl-proc">
    <thead><tr><th onclick="sortTbl('tbl-proc',0)">Čas</th><th onclick="sortTbl('tbl-proc',1)">Typ</th>
    <th onclick="sortTbl('tbl-proc',2)">Název</th><th onclick="sortTbl('tbl-proc',3)">PID</th>
    <th onclick="sortTbl('tbl-proc',4)">Parent</th><th onclick="sortTbl('tbl-proc',5)">Exe</th>
    <th onclick="sortTbl('tbl-proc',6)">Cmdline</th><th onclick="sortTbl('tbl-proc',7)">User</th>
    <th onclick="sortTbl('tbl-proc',8)">Env vars</th></tr></thead>
    <tbody>{rows_process}</tbody>
  </table></div>
</div>

<!-- DLL -->
<div id="panel-dll" class="panel">
  <div class="filter-bar">
    <input type="text" placeholder="Filtr…" oninput="filterTbl('tbl-dll',this.value)">
    <span class="count" id="cnt-dll"></span>
  </div>
  <div class="tbl-wrap"><table id="tbl-dll">
    <thead><tr><th onclick="sortTbl('tbl-dll',0)">Čas</th><th onclick="sortTbl('tbl-dll',1)">Typ</th>
    <th onclick="sortTbl('tbl-dll',2)">PID</th><th onclick="sortTbl('tbl-dll',3)">Cesta</th></tr></thead>
    <tbody>{rows_dll}</tbody>
  </table></div>
</div>

<!-- DNS -->
<div id="panel-dns" class="panel">
  <div class="filter-bar">
    <input type="text" placeholder="Filtr…" oninput="filterTbl('tbl-dns',this.value)">
    <span class="count" id="cnt-dns"></span>
  </div>
  <div class="tbl-wrap"><table id="tbl-dns">
    <thead><tr><th onclick="sortTbl('tbl-dns',0)">Čas</th><th onclick="sortTbl('tbl-dns',1)">Typ</th>
    <th onclick="sortTbl('tbl-dns',2)">Hostname</th></tr></thead>
    <tbody>{rows_dns}</tbody>
  </table></div>
</div>

<!-- NAMED PIPES -->
<div id="panel-pipe" class="panel">
  <div class="filter-bar">
    <input type="text" placeholder="Filtr…" oninput="filterTbl('tbl-pipe',this.value)">
    <span class="count" id="cnt-pipe"></span>
  </div>
  <div class="tbl-wrap"><table id="tbl-pipe">
    <thead><tr><th onclick="sortTbl('tbl-pipe',0)">Čas</th><th onclick="sortTbl('tbl-pipe',1)">Typ</th>
    <th onclick="sortTbl('tbl-pipe',2)">Cesta</th></tr></thead>
    <tbody>{rows_pipes}</tbody>
  </table></div>
</div>

<!-- DOWNLOADS -->
<div id="panel-dl" class="panel">
  <div class="filter-bar">
    <input type="text" placeholder="Filtr…" oninput="filterTbl('tbl-dl',this.value)">
    <span class="count" id="cnt-dl"></span>
  </div>
  <div class="tbl-wrap"><table id="tbl-dl">
    <thead><tr><th onclick="sortTbl('tbl-dl',0)">Čas</th><th onclick="sortTbl('tbl-dl',1)">Typ</th>
    <th onclick="sortTbl('tbl-dl',2)">Cesta</th><th onclick="sortTbl('tbl-dl',3)">Velikost</th></tr></thead>
    <tbody>{rows_download}</tbody>
  </table></div>
</div>

<div class="footer">Scout Report &mdash; generated {gen_time}</div>

<script>
const TAB_IDS = ['risk','timeline','fopen','files','reg','net','proc','dll','dns','pipe','dl'];
function switchTab(id) {{
  document.querySelectorAll('.tab').forEach((b,i) => b.classList.toggle('active', TAB_IDS[i] === id));
  document.querySelectorAll('.panel').forEach(p => p.classList.toggle('active', p.id === 'panel-'+id));
  updateCount(id);
}}
function filterTbl(tid, q) {{
  const rows = document.querySelectorAll('#'+tid+' tbody tr');
  q = q.toLowerCase();
  rows.forEach(r => r.style.display = (!q || r.textContent.toLowerCase().includes(q)) ? '' : 'none');
  const id = tid.replace('tbl-','');
  const cnt = document.getElementById('cnt-'+id);
  if (cnt) cnt.textContent = [...rows].filter(r => r.style.display !== 'none').length + ' / ' + rows.length;
}}
function sortTbl(tid, col) {{
  const tb = document.querySelector('#'+tid+' tbody');
  const rows = [...tb.querySelectorAll('tr')];
  let asc = tb.dataset.sortCol == col && tb.dataset.sortDir == '1';
  rows.sort((a, b) => {{
    const av = a.cells[col]?.textContent.trim() ?? '';
    const bv = b.cells[col]?.textContent.trim() ?? '';
    return asc ? bv.localeCompare(av, undefined, {{numeric:true}}) : av.localeCompare(bv, undefined, {{numeric:true}});
  }});
  rows.forEach(r => tb.appendChild(r));
  tb.dataset.sortCol = col; tb.dataset.sortDir = asc ? '0' : '1';
}}
function updateCount(id) {{
  const t = document.getElementById('tbl-'+id);
  if (!t) return;
  const rows = t.querySelectorAll('tbody tr');
  const cnt = document.getElementById('cnt-'+id);
  if (cnt) cnt.textContent = rows.length + ' záznamů';
}}
document.querySelectorAll('.trunc').forEach(el => el.addEventListener('click', () => el.classList.toggle('expanded')));
TAB_IDS.forEach(updateCount);
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

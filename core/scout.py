"""Scout Mode - Deep application behavior monitoring.

Tracks file I/O, registry changes, network connections, downloads,
and child-process spawning for a specific target application.
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
    file      — CREATE / MODIFY / DELETE / MOVE events in watch_path
    registry  — REG_ADD / REG_MODIFY / REG_DELETE in key monitored hives
    network   — CONNECT events (new outbound/inbound connections)
    process   — SPAWN / EXIT events; TARGET_FOUND when target appears
    download  — files created/grown in the user's Downloads folder
    """

    # Registry hives/keys that are polled for changes
    _REG_MONITOR = [
        ("HKCU\\Run",      "HKEY_CURRENT_USER",   r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
        ("HKLM\\Run",      "HKEY_LOCAL_MACHINE",   r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
        ("HKCU\\Software", "HKEY_CURRENT_USER",    r"SOFTWARE"),
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

        self._threads:   list[threading.Thread] = []
        self._observer:  Observer | None = None

        self.watch_path     = os.path.expanduser("~")
        self.downloads_path = str(Path.home() / "Downloads")
        self.target_process: str | None = None
        self._target_pids:   set[int] = set()

    # ── public API ───────────────────────────────────────────────────────────

    def start(self, watch_path: str | None = None, target_process: str | None = None) -> None:
        if watch_path:
            self.watch_path = watch_path
        if target_process:
            self.target_process = target_process.lower()

        self.is_running = True
        self.start_time = time.time()
        self.logger.log("scout_start", "scout",
                        f"app='{self.app_name}' watch='{self.watch_path}' "
                        f"target='{self.target_process}' id={self.session_id}")

        self._observer = Observer()
        self._start_file_watcher()
        self._start_download_watcher()
        self._observer.start()

        self._start_process_monitor()
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

        self._observer.schedule(_Handler(), self.watch_path, recursive=True)

    # ── downloads watcher ────────────────────────────────────────────────────

    def _start_download_watcher(self) -> None:
        dl = self.downloads_path
        if not os.path.isdir(dl) or dl == self.watch_path:
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
                            parent_pid, cmdline = None, ""
                            try:
                                p = psutil.Process(pid)
                                parent_pid = p.ppid()
                                cmdline = " ".join(p.cmdline())
                            except Exception:
                                pass
                            ev = {"type": "SPAWN", "path": name, "pid": pid,
                                  "parent_pid": parent_pid, "cmdline": cmdline[:300],
                                  "time": _ts(), "category": "process"}
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
                time.sleep(2)
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
            "app_name":       self.app_name,
            "session_id":     self.session_id,
            "duration_s":     round(duration, 1),
            "file_events":    len(self.file_events),
            "registry_events": len(self.registry_events),
            "network_events": len(self.network_events),
            "process_events": len(self.process_events),
            "download_events": len(self.download_events),
            "total_events":   (len(self.file_events) + len(self.registry_events) +
                               len(self.network_events) + len(self.process_events) +
                               len(self.download_events)),
        }

    def _save_session(self) -> None:
        os.makedirs(self.profile_path, exist_ok=True)
        data = {
            "app_name":       self.app_name,
            "session_id":     self.session_id,
            "watch_path":     self.watch_path,
            "target_process": self.target_process,
            "start_time":     self.start_time,
            "end_time":       time.time(),
            "summary":        self.get_summary(),
            "file_events":    self.file_events,
            "registry_events": self.registry_events,
            "network_events": self.network_events,
            "process_events": self.process_events,
            "download_events": self.download_events,
        }
        with open(self.session_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

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

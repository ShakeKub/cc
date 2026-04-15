"""TracerSession — monitors file system, processes, DLL injection and network."""

import datetime
import json
import os
import queue
import threading
import time
from pathlib import Path

import psutil
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


# ── helpers ─────────────────────────────────────────────────

def _ts():
    return datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]


def _snapshot_pids():
    """Return {pid: name} for all running processes."""
    result = {}
    for p in psutil.process_iter(["pid", "name"]):
        try:
            result[p.info["pid"]] = p.info["name"]
        except Exception:
            pass
    return result


def _get_modules(pid: int) -> set:
    """Return set of loaded DLL/module paths for a PID."""
    try:
        proc = psutil.Process(pid)
        return {m.path.lower() for m in proc.memory_maps()}
    except Exception:
        return set()


def _get_connections(pid: int | None = None) -> set:
    """Return set of (laddr, raddr, status) tuples. If pid given, only that process."""
    result = set()
    try:
        conns = psutil.net_connections(kind="all") if pid is None else psutil.Process(pid).net_connections()
        for c in conns:
            raddr = f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else ""
            laddr = f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else ""
            result.add((laddr, raddr, c.status))
    except Exception:
        pass
    return result


# ── session ─────────────────────────────────────────────────

class TracerSession:
    """
    Monitors:
      FILE — file system events in watch_path
      PROC — new processes spawned
      KILL — processes that died
      DLL  — new DLLs loaded into target_process
      NET  — new network connections (optionally filtered to target)
    """

    def __init__(self, app_name: str, profile_path: str, logger):
        self.app_name = app_name
        self.profile_path = profile_path
        self.logger = logger
        self.session_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_file = os.path.join(profile_path, f"trace_{self.session_id}.json")

        self.watch_path = os.path.expanduser("~")
        self.target_process: str | None = None   # e.g. "game.exe"

        self.is_running = False
        self.event_queue: queue.Queue = queue.Queue()

        # Collected artefacts
        self.created_files:  set = set()
        self.modified_files: set = set()
        self.deleted_files:  set = set()
        self.new_processes:  list = []
        self.killed_processes: list = []
        self.injected_dlls:  list = []
        self.new_connections: list = []

        self._threads: list[threading.Thread] = []
        self._observer = None
        self.start_time: float | None = None

    # ── public API ──────────────────────────────────────────

    def start(self, watch_path: str | None = None, target_process: str | None = None):
        if watch_path:
            self.watch_path = watch_path
        if target_process:
            self.target_process = target_process.lower()

        self.is_running = True
        self.start_time = time.time()
        self.logger.log(
            f"Tracer started: app='{self.app_name}' watch='{self.watch_path}' "
            f"target='{self.target_process}' id={self.session_id}",
            category="tracer",
        )

        self._start_file_watcher()
        self._start_process_monitor()
        self._start_network_monitor()

    def stop(self):
        if not self.is_running:
            return
        self.is_running = False
        if self._observer:
            self._observer.stop()
            self._observer.join()
        # threads are daemon — they die automatically
        self.logger.log(f"Tracer stopped: {self.session_id}", category="tracer")
        self._save_session()

    # ── file system ─────────────────────────────────────────

    def _start_file_watcher(self):
        session = self

        class Handler(FileSystemEventHandler):
            def _put(self, etype, path):
                session.event_queue.put({"type": etype, "path": path, "time": _ts()})

            def on_created(self, e):
                if not e.is_directory:
                    session.created_files.add(e.src_path)
                    self._put("FILE+", e.src_path)

            def on_modified(self, e):
                if not e.is_directory:
                    session.modified_files.add(e.src_path)
                    self._put("FILE~", e.src_path)

            def on_deleted(self, e):
                if not e.is_directory:
                    session.deleted_files.add(e.src_path)
                    self._put("FILE-", e.src_path)

            def on_moved(self, e):
                session.event_queue.put({
                    "type": "MOVE ",
                    "path": f"{e.src_path}  →  {e.dest_path}",
                    "time": _ts(),
                })

        self._observer = Observer()
        self._observer.schedule(Handler(), self.watch_path, recursive=True)
        self._observer.start()

    # ── process + DLL monitor ───────────────────────────────

    def _start_process_monitor(self):
        def run():
            prev_pids = _snapshot_pids()
            # DLL snapshot for target process
            target_pid: int | None = None
            prev_dlls: set = set()

            if self.target_process:
                for pid, name in prev_pids.items():
                    if name.lower() == self.target_process:
                        target_pid = pid
                        prev_dlls = _get_modules(pid)
                        break

            while self.is_running:
                time.sleep(0.5)
                try:
                    cur_pids = _snapshot_pids()

                    # new processes
                    for pid, name in cur_pids.items():
                        if pid not in prev_pids:
                            entry = {"pid": pid, "name": name, "time": _ts()}
                            self.new_processes.append(entry)
                            self.event_queue.put({"type": "PROC+", "path": f"{name} (PID {pid})", "time": entry["time"]})

                    # killed processes
                    for pid, name in prev_pids.items():
                        if pid not in cur_pids:
                            entry = {"pid": pid, "name": name, "time": _ts()}
                            self.killed_processes.append(entry)
                            self.event_queue.put({"type": "PROC-", "path": f"{name} (PID {pid})", "time": entry["time"]})

                    # find / re-find target process
                    if self.target_process:
                        if target_pid and target_pid not in cur_pids:
                            target_pid = None   # process died
                        if not target_pid:
                            for pid, name in cur_pids.items():
                                if name.lower() == self.target_process:
                                    target_pid = pid
                                    prev_dlls = _get_modules(pid)
                                    self.event_queue.put({
                                        "type": "TARGET",
                                        "path": f"Target process found: {name} (PID {pid})",
                                        "time": _ts(),
                                    })
                                    break

                        # DLL injection check
                        if target_pid:
                            cur_dlls = _get_modules(target_pid)
                            new_dlls = cur_dlls - prev_dlls
                            for dll in new_dlls:
                                entry = {"pid": target_pid, "dll": dll, "time": _ts()}
                                self.injected_dlls.append(entry)
                                self.event_queue.put({
                                    "type": "DLL  ",
                                    "path": dll,
                                    "time": entry["time"],
                                })
                            prev_dlls = cur_dlls

                    prev_pids = cur_pids
                except Exception:
                    pass

        t = threading.Thread(target=run, daemon=True)
        t.start()
        self._threads.append(t)

    # ── network monitor ─────────────────────────────────────

    def _start_network_monitor(self):
        def run():
            prev = _get_connections()
            while self.is_running:
                time.sleep(1)
                try:
                    cur = _get_connections()
                    for conn in cur - prev:
                        laddr, raddr, status = conn
                        if not raddr:
                            continue
                        entry = {"local": laddr, "remote": raddr, "status": status, "time": _ts()}
                        self.new_connections.append(entry)
                        self.event_queue.put({
                            "type": "NET  ",
                            "path": f"{laddr}  →  {raddr}  [{status}]",
                            "time": entry["time"],
                        })
                    prev = cur
                except Exception:
                    pass

        t = threading.Thread(target=run, daemon=True)
        t.start()
        self._threads.append(t)

    # ── save ────────────────────────────────────────────────

    def _save_session(self):
        data = {
            "app_name": self.app_name,
            "session_id": self.session_id,
            "watch_path": self.watch_path,
            "target_process": self.target_process,
            "start_time": self.start_time,
            "end_time": time.time(),
            "created_files":   list(self.created_files),
            "modified_files":  list(self.modified_files),
            "deleted_files":   list(self.deleted_files),
            "new_processes":   self.new_processes,
            "killed_processes": self.killed_processes,
            "injected_dlls":   self.injected_dlls,
            "new_connections": self.new_connections,
        }
        with open(self.session_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        self.logger.log(f"Session saved: {self.session_file}", category="tracer")

    def get_created_files(self):
        return self.created_files

    # ── load saved sessions ─────────────────────────────────

    @staticmethod
    def load_sessions(profile_path: str) -> list:
        sessions = []
        if not os.path.exists(profile_path):
            return sessions
        for filename in sorted(os.listdir(profile_path), reverse=True):
            if filename.startswith("trace_") and filename.endswith(".json"):
                path = os.path.join(profile_path, filename)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        sessions.append(json.load(f))
                except Exception:
                    pass
        return sessions

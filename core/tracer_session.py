import datetime
import json
import os
import threading
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class TracerSession:
    def __init__(self, app_name, profile_path, logger):
        self.app_name = app_name
        self.profile_path = profile_path
        self.logger = logger
        self.session_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_file = os.path.join(self.profile_path, f"trace_{self.session_id}.json")
        self.observer = None
        self.created_files = set()
        self.is_running = False
        self.handler = None

    def start(self):
        self.is_running = True
        self.logger.log(f"Starting tracer session for {self.app_name} (ID: {self.session_id})")
        self.handler = self._get_handler()
        self.observer = Observer()
        # This should be configurable or more intelligently determined
        watch_path = os.path.expanduser("~") 
        self.observer.schedule(self.handler, watch_path, recursive=True)
        self.observer.start()
        
        # Run observer in a separate thread
        self.thread = threading.Thread(target=self._run_observer)
        self.thread.start()

    def _run_observer(self):
        try:
            while self.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
        self.observer.join()

    def stop(self):
        if self.is_running:
            self.is_running = False
            if self.observer.is_alive():
                self.observer.stop()
                self.observer.join()
            self.logger.log(f"Stopping tracer session {self.session_id}")
            self._save_session()

    def _get_handler(self):
        class Handler(FileSystemEventHandler):
            def __init__(self, session):
                self.session = session

            def on_created(self, event):
                if not event.is_directory:
                    self.session.created_files.add(event.src_path)
                    self.session.logger.log(f"File created: {event.src_path}", "DEBUG")
        
        return Handler(self)

    def _save_session(self):
        session_data = {
            "app_name": self.app_name,
            "session_id": self.session_id,
            "start_time": self.observer.started_event.wait(1),
            "end_time": time.time(),
            "created_files": list(self.created_files)
        }
        with open(self.session_file, 'w') as f:
            json.dump(session_data, f, indent=4)
        self.logger.log(f"Tracer session data saved to {self.session_file}")

    def get_created_files(self):
        return self.created_files

    @staticmethod
    def load_sessions(profile_path):
        sessions = []
        if not os.path.exists(profile_path):
            return sessions
        for filename in os.listdir(profile_path):
            if filename.startswith("trace_") and filename.endswith(".json"):
                with open(os.path.join(profile_path, filename), 'r') as f:
                    sessions.append(json.load(f))
        return sessions

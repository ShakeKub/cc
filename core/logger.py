"""Logging system with TXT/JSON export and cleaning reports."""

import itertools
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

_INSTANCE_COUNTER = itertools.count()


class CleanerLogger:
    """Full logging system with export and reporting capabilities."""

    def __init__(self, log_dir: str = "logs", log_format: str = "json", max_files: int = 50):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.log_format = log_format
        self.max_files = max_files
        self.session_log: list[dict[str, Any]] = []
        self.session_start = datetime.now()

        # Use a unique logger name per session to avoid duplicate handlers
        # when CleanerLogger is instantiated more than once in the same process.
        logger_name = f"SystemCleaner.{self.session_start.strftime('%Y%m%d_%H%M%S')}.{next(_INSTANCE_COUNTER)}"
        self._logger = logging.getLogger(logger_name)
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False
        handler = logging.FileHandler(
            self.log_dir / f"cleaner_{self.session_start.strftime('%Y%m%d_%H%M%S')}.log"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        self._logger.addHandler(handler)

        self._rotate_old_logs()

    def _rotate_old_logs(self):
        """Remove oldest log files if over max_files limit."""
        logs = sorted(self.log_dir.glob("cleaner_*.log"), key=lambda p: p.stat().st_mtime)
        while len(logs) > self.max_files:
            logs[0].unlink()
            logs.pop(0)

    def log(self, action: str, category: str, details: str = "",
            freed_bytes: int = 0, risk_level: str = "safe", success: bool = True):
        """Log an action with structured metadata."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "category": category,
            "details": details,
            "freed_bytes": freed_bytes,
            "risk_level": risk_level,
            "success": success,
        }
        self.session_log.append(entry)
        level = logging.INFO if success else logging.ERROR
        self._logger.log(level, f"[{category}] {action}: {details} (freed: {freed_bytes}B)")

    def info(self, message: str):
        self._logger.info(message)
        self.session_log.append({
            "timestamp": datetime.now().isoformat(),
            "action": "info",
            "category": "system",
            "details": message,
            "freed_bytes": 0,
            "risk_level": "safe",
            "success": True,
        })

    def warning(self, message: str):
        self._logger.warning(message)

    def error(self, message: str):
        self._logger.error(message)

    def get_session_stats(self) -> dict[str, Any]:
        """Get summary statistics for current session."""
        total_freed = sum(e["freed_bytes"] for e in self.session_log)
        actions_taken = len([e for e in self.session_log if e["action"] != "info"])
        errors = len([e for e in self.session_log if not e["success"]])
        categories = {}
        for entry in self.session_log:
            cat = entry["category"]
            if cat not in categories:
                categories[cat] = {"count": 0, "freed": 0}
            categories[cat]["count"] += 1
            categories[cat]["freed"] += entry["freed_bytes"]

        return {
            "session_start": self.session_start.isoformat(),
            "duration_seconds": (datetime.now() - self.session_start).total_seconds(),
            "total_freed_bytes": total_freed,
            "total_freed_readable": self._format_bytes(total_freed),
            "actions_taken": actions_taken,
            "errors": errors,
            "categories": categories,
        }

    def export_txt(self, filepath: str | None = None) -> str:
        """Export session log as TXT."""
        if filepath is None:
            filepath = str(self.log_dir / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        stats = self.get_session_stats()
        lines = [
            "=" * 70,
            "  SYSTEM CLEANER - CLEANING REPORT",
            "=" * 70,
            f"  Session Start : {stats['session_start']}",
            f"  Duration      : {stats['duration_seconds']:.1f} seconds",
            f"  Space Freed   : {stats['total_freed_readable']}",
            f"  Actions Taken : {stats['actions_taken']}",
            f"  Errors        : {stats['errors']}",
            "=" * 70,
            "",
            "DETAILED LOG:",
            "-" * 70,
        ]
        for entry in self.session_log:
            status = "OK" if entry["success"] else "FAIL"
            freed = self._format_bytes(entry["freed_bytes"]) if entry["freed_bytes"] else ""
            lines.append(
                f"[{entry['timestamp']}] [{status}] [{entry['category']}] "
                f"{entry['action']}: {entry['details']} {freed}"
            )
        lines.append("-" * 70)
        content = "\n".join(lines)
        Path(filepath).write_text(content, encoding="utf-8")
        return filepath

    def export_json(self, filepath: str | None = None) -> str:
        """Export session log as JSON."""
        if filepath is None:
            filepath = str(self.log_dir / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        data = {
            "stats": self.get_session_stats(),
            "entries": self.session_log,
        }
        Path(filepath).write_text(json.dumps(data, indent=2), encoding="utf-8")
        return filepath

    @staticmethod
    def _format_bytes(b: int) -> str:
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if b < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} PB"

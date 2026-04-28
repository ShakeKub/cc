"""Logging system with TXT/JSON export, audit trail, and reporting."""

import itertools
import json
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

_INSTANCE_COUNTER = itertools.count()
_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


def _read_config() -> dict[str, Any]:
    try:
        if _CONFIG_PATH.exists():
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


class CleanerLogger:
    """Full logging system with export and reporting capabilities."""

    def __init__(self, log_dir: str = "logs", log_format: str = "json", max_files: int = 50):
        cfg = _read_config()
        log_dir = cfg.get("log_dir", log_dir)
        log_format = cfg.get("log_format", log_format)
        max_files = cfg.get("max_log_files", max_files)
        level_name = str(cfg.get("log_level", "INFO")).upper()

        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.log_format = log_format
        self.max_files = max_files
        self.session_log: list[dict[str, Any]] = []
        self.session_start = datetime.now()
        self.session_id = f"{self.session_start.strftime('%Y%m%d_%H%M%S')}_{next(_INSTANCE_COUNTER)}"
        self.audit_file = self.log_dir / "audit_trail.jsonl"
        self.audit_file.touch(exist_ok=True)

        # Use a unique logger name per session to avoid duplicate handlers
        # when CleanerLogger is instantiated more than once in the same process.
        logger_name = f"ByteSweep.{self.session_id}"
        self._logger = logging.getLogger(logger_name)
        self._logger.setLevel(getattr(logging, level_name, logging.INFO))
        self._logger.propagate = False
        handler = logging.FileHandler(
            self.log_dir / f"cleaner_{self.session_start.strftime('%Y%m%d_%H%M%S')}.log"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        self._logger.addHandler(handler)

        self._rotate_old_logs()
        self._trim_audit_trail(max_lines=30000, keep_lines=15000)
        self.audit_event(
            event="session_start",
            category="system",
            details="Session started",
            success=True,
            severity="info",
            metadata={"session_start": self.session_start.isoformat()},
        )

    def _rotate_old_logs(self):
        """Remove oldest log files if over max_files limit."""
        logs = sorted(self.log_dir.glob("cleaner_*.log"), key=lambda p: p.stat().st_mtime)
        while len(logs) > self.max_files:
            logs[0].unlink()
            logs.pop(0)

    def _trim_audit_trail(self, max_lines: int = 30000, keep_lines: int = 15000):
        """Trim audit trail file when it grows too large."""
        try:
            lines = self.audit_file.read_text(encoding="utf-8").splitlines()
            if len(lines) > max_lines:
                self.audit_file.write_text("\n".join(lines[-keep_lines:]) + "\n", encoding="utf-8")
        except Exception:
            pass

    def _append_session_entry(self, entry: dict[str, Any]):
        self.session_log.append(entry)

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
        self._append_session_entry(entry)
        level = logging.INFO if success else logging.ERROR
        self._logger.log(level, f"[{category}] {action}: {details} (freed: {freed_bytes}B)")
        self.audit_event(
            event=action,
            category=category,
            details=details,
            success=success,
            severity="info" if success else "error",
            metadata={"freed_bytes": freed_bytes, "risk_level": risk_level},
        )

    def log_action(
        self,
        action: str,
        details: str = "",
        category: str = "system",
        success: bool = True,
        risk_level: str = "safe",
    ):
        """Backward-compatible helper used by older modules."""
        self.log(action, category, details, freed_bytes=0, risk_level=risk_level, success=success)

    def info(self, message: str):
        self._logger.info(message)
        self._append_session_entry({
            "timestamp": datetime.now().isoformat(),
            "action": "info",
            "category": "system",
            "details": message,
            "freed_bytes": 0,
            "risk_level": "safe",
            "success": True,
        })
        self.audit_event("info", "system", message, success=True, severity="info")

    def warning(self, message: str):
        self._logger.warning(message)
        self._append_session_entry({
            "timestamp": datetime.now().isoformat(),
            "action": "warning",
            "category": "system",
            "details": message,
            "freed_bytes": 0,
            "risk_level": "safe",
            "success": True,
        })
        self.audit_event("warning", "system", message, success=True, severity="warning")

    def error(self, message: str):
        self._logger.error(message)
        self._append_session_entry({
            "timestamp": datetime.now().isoformat(),
            "action": "error",
            "category": "system",
            "details": message,
            "freed_bytes": 0,
            "risk_level": "safe",
            "success": False,
        })
        self.audit_event("error", "system", message, success=False, severity="error")

    def audit_event(
        self,
        event: str,
        category: str,
        details: str,
        success: bool = True,
        severity: str = "info",
        metadata: dict[str, Any] | None = None,
    ):
        """Write a persistent audit event to JSONL trail."""
        record = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "event": event,
            "category": category,
            "details": details,
            "success": success,
            "severity": severity,
            "metadata": metadata or {},
        }
        try:
            with self.audit_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _read_audit_entries(self, limit: int | None = None) -> list[dict[str, Any]]:
        try:
            lines = self.audit_file.read_text(encoding="utf-8").splitlines()
        except Exception:
            return []

        if limit is not None and limit > 0:
            lines = lines[-limit:]

        items: list[dict[str, Any]] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    items.append(obj)
            except json.JSONDecodeError:
                continue
        return items

    def tail_audit(self, limit: int = 25) -> list[dict[str, Any]]:
        return self._read_audit_entries(limit=max(1, limit))

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
            "  BYTESWEEP - CLEANING REPORT",
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
            "session_id": self.session_id,
            "stats": self.get_session_stats(),
            "entries": self.session_log,
        }
        Path(filepath).write_text(json.dumps(data, indent=2), encoding="utf-8")
        return filepath

    def _audit_summary(self, entries: list[dict[str, Any]]) -> dict[str, Any]:
        by_category: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "success": 0, "failed": 0})
        for e in entries:
            cat = str(e.get("category", "unknown"))
            ok = bool(e.get("success", False))
            by_category[cat]["total"] += 1
            if ok:
                by_category[cat]["success"] += 1
            else:
                by_category[cat]["failed"] += 1

        return {
            "total": len(entries),
            "success": sum(1 for e in entries if e.get("success")),
            "failed": sum(1 for e in entries if not e.get("success")),
            "categories": dict(by_category),
        }

    def export_audit_json(self, filepath: str | None = None, limit: int = 5000) -> str:
        """Export persistent audit trail summary and entries as JSON."""
        if filepath is None:
            filepath = str(self.log_dir / f"audit_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        entries = self._read_audit_entries(limit=max(1, limit))
        data = {
            "generated_at": datetime.now().isoformat(),
            "current_session_id": self.session_id,
            "summary": self._audit_summary(entries),
            "entries": entries,
        }
        Path(filepath).write_text(json.dumps(data, indent=2), encoding="utf-8")
        return filepath

    def export_audit_txt(self, filepath: str | None = None, limit: int = 5000) -> str:
        """Export persistent audit trail summary and entries as TXT."""
        if filepath is None:
            filepath = str(self.log_dir / f"audit_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")

        entries = self._read_audit_entries(limit=max(1, limit))
        summary = self._audit_summary(entries)

        lines = [
            "=" * 78,
            "  BYTESWEEP - AUDIT REPORT",
            "=" * 78,
            f"  Generated      : {datetime.now().isoformat()}",
            f"  Session ID     : {self.session_id}",
            f"  Events         : {summary['total']}",
            f"  Success        : {summary['success']}",
            f"  Failed         : {summary['failed']}",
            "=" * 78,
            "",
            "By Category:",
            "-" * 78,
        ]

        for cat, stat in sorted(summary["categories"].items(), key=lambda x: x[0]):
            lines.append(
                f"  {cat:<18} total={stat['total']:<4} success={stat['success']:<4} failed={stat['failed']:<4}"
            )

        lines.extend([
            "",
            "Audit Entries:",
            "-" * 78,
        ])

        for e in entries:
            status = "OK" if e.get("success") else "FAIL"
            ts = str(e.get("timestamp", ""))
            cat = str(e.get("category", ""))
            evt = str(e.get("event", ""))
            details = str(e.get("details", "")).replace("\n", " ")
            lines.append(f"[{ts}] [{status}] [{cat}] {evt}: {details}")

        lines.append("-" * 78)
        Path(filepath).write_text("\n".join(lines), encoding="utf-8")
        return filepath

    @staticmethod
    def _format_bytes(b: int) -> str:
        size = float(b)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

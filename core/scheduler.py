"""Scheduler - automated cleaning, custom profiles, background mode."""

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
from core.logger import CleanerLogger


TASK_PREFIX = "SystemCleaner_"
CONFIG_FILE = "config.json"


def _load_config() -> dict:
    """Load the configuration file."""
    config_path = Path(__file__).parent.parent / CONFIG_FILE
    if config_path.exists():
        return json.loads(config_path.read_text(encoding="utf-8"))
    return {}


def _save_config(config: dict):
    """Save configuration."""
    config_path = Path(__file__).parent.parent / CONFIG_FILE
    config_path.write_text(json.dumps(config, indent=4), encoding="utf-8")


def create_scheduled_task(name: str, schedule: str, profile: str,
                          logger: CleanerLogger) -> bool:
    """Create a Windows scheduled task for automatic cleaning.

    Args:
        name: Task name
        schedule: Schedule type - "daily", "weekly", "monthly", or "hourly"
        profile: Cleaning profile name (from config)
    """
    task_name = f"{TASK_PREFIX}{name}"
    # Get path to our script
    script_path = Path(__file__).parent.parent / "main.py"

    # Build the schtasks command
    schedule_map = {
        "hourly": "HOURLY",
        "daily": "DAILY",
        "weekly": "WEEKLY",
        "monthly": "MONTHLY",
    }

    sched = schedule_map.get(schedule, "DAILY")
    python_exe = os.sys.executable

    try:
        cmd = [
            "schtasks", "/create",
            "/tn", task_name,
            "/tr", f'"{python_exe}" "{script_path}" --silent --profile {profile}',
            "/sc", sched,
            "/st", "03:00",  # Default 3 AM
            "/f",  # Force overwrite
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        success = result.returncode == 0

        if success:
            # Save to config
            config = _load_config()
            if "scheduled_tasks" not in config:
                config["scheduled_tasks"] = []
            config["scheduled_tasks"].append({
                "name": name,
                "task_name": task_name,
                "schedule": schedule,
                "profile": profile,
                "created": datetime.now().isoformat(),
                "enabled": True,
            })
            _save_config(config)
            logger.log("create_schedule", "scheduler",
                      f"Created scheduled task: {name} ({schedule})")
        else:
            logger.error(f"Failed to create task: {result.stderr}")
        return success
    except Exception as e:
        logger.error(f"Scheduler error: {e}")
        return False


def delete_scheduled_task(name: str, logger: CleanerLogger) -> bool:
    """Delete a scheduled cleaning task."""
    task_name = f"{TASK_PREFIX}{name}"
    try:
        result = subprocess.run(
            ["schtasks", "/delete", "/tn", task_name, "/f"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            # Remove from config
            config = _load_config()
            config["scheduled_tasks"] = [
                t for t in config.get("scheduled_tasks", [])
                if t.get("name") != name
            ]
            _save_config(config)
            logger.log("delete_schedule", "scheduler",
                      f"Deleted scheduled task: {name}")
            return True
        return False
    except Exception as e:
        logger.error(f"Delete task error: {e}")
        return False


def list_scheduled_tasks(logger: CleanerLogger) -> list[dict[str, Any]]:
    """List all System Cleaner scheduled tasks."""
    tasks = []
    config = _load_config()

    for task in config.get("scheduled_tasks", []):
        # Check if task still exists in Windows scheduler
        task_name = task.get("task_name", f"{TASK_PREFIX}{task['name']}")
        try:
            result = subprocess.run(
                ["schtasks", "/query", "/tn", task_name],
                capture_output=True, text=True, timeout=10,
            )
            task["exists_in_scheduler"] = result.returncode == 0
        except Exception:
            task["exists_in_scheduler"] = False

        tasks.append(task)

    return tasks


def toggle_scheduled_task(name: str, enable: bool,
                          logger: CleanerLogger) -> bool:
    """Enable or disable a scheduled task."""
    task_name = f"{TASK_PREFIX}{name}"
    action = "/enable" if enable else "/disable"
    try:
        result = subprocess.run(
            ["schtasks", "/change", "/tn", task_name, action],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            config = _load_config()
            for task in config.get("scheduled_tasks", []):
                if task.get("name") == name:
                    task["enabled"] = enable
            _save_config(config)
            logger.log("toggle_schedule", "scheduler",
                      f"{'Enabled' if enable else 'Disabled'} task: {name}")
            return True
        return False
    except Exception as e:
        logger.error(f"Toggle task error: {e}")
        return False


def get_cleaning_profiles() -> dict[str, dict]:
    """Get available cleaning profiles from config."""
    config = _load_config()
    return config.get("cleaning_profiles", {})


def save_cleaning_profile(name: str, settings: dict, logger: CleanerLogger):
    """Save a custom cleaning profile."""
    config = _load_config()
    if "cleaning_profiles" not in config:
        config["cleaning_profiles"] = {}
    config["cleaning_profiles"][name] = settings
    _save_config(config)
    logger.log("save_profile", "scheduler", f"Saved cleaning profile: {name}")


def delete_cleaning_profile(name: str, logger: CleanerLogger) -> bool:
    """Delete a cleaning profile (cannot delete built-in ones)."""
    builtin = {"quick", "standard", "deep"}
    if name in builtin:
        logger.warning(f"Cannot delete built-in profile: {name}")
        return False
    config = _load_config()
    if name in config.get("cleaning_profiles", {}):
        del config["cleaning_profiles"][name]
        _save_config(config)
        logger.log("delete_profile", "scheduler", f"Deleted profile: {name}")
        return True
    return False

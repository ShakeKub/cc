"""System Health Score — composite score based on CPU, RAM, disk, temps, startup."""

import os
import time
from typing import Any

import psutil

from core.logger import CleanerLogger


def _score_cpu(usage: float) -> tuple[int, str]:
    if usage < 30:
        return 100, "Excellent"
    if usage < 60:
        return 70, "Good"
    if usage < 85:
        return 40, "Fair"
    return 10, "Poor"


def _score_ram(percent: float) -> tuple[int, str]:
    if percent < 50:
        return 100, "Excellent"
    if percent < 70:
        return 75, "Good"
    if percent < 85:
        return 45, "Fair"
    return 10, "Poor"


def _score_disk(percent: float) -> tuple[int, str]:
    free_pct = 100 - percent
    if free_pct > 30:
        return 100, "Excellent"
    if free_pct > 15:
        return 70, "Good"
    if free_pct > 5:
        return 35, "Low"
    return 5, "Critical"


def _score_temp_files(temp_count: int) -> tuple[int, str]:
    if temp_count < 50:
        return 100, "Clean"
    if temp_count < 200:
        return 75, "Moderate"
    if temp_count < 500:
        return 45, "Heavy"
    return 15, "Overloaded"


def _score_startup(entry_count: int) -> tuple[int, str]:
    if entry_count < 5:
        return 100, "Lean"
    if entry_count < 12:
        return 75, "Normal"
    if entry_count < 20:
        return 45, "Crowded"
    return 20, "Overloaded"


def _score_uptime(uptime_hours: float) -> tuple[int, str]:
    if uptime_hours < 24:
        return 100, "Fresh"
    if uptime_hours < 72:
        return 80, "Good"
    if uptime_hours < 168:
        return 55, "Needs restart"
    return 25, "Stale"


def get_health_score(logger: CleanerLogger) -> dict[str, Any]:
    """
    Compute a 0-100 overall system health score from multiple indicators.

    Returns a dict with:
        overall_score  — weighted average (0-100)
        grade          — A / B / C / D / F
        indicators     — list of per-indicator detail dicts
        recommendations — list of actionable suggestion strings
    """
    indicators: list[dict[str, Any]] = []
    recommendations: list[str] = []

    # ── CPU ──────────────────────────────────────────────────────────────────
    cpu_usage = psutil.cpu_percent(interval=1)
    cpu_score, cpu_label = _score_cpu(cpu_usage)
    indicators.append({
        "name": "CPU Usage",
        "value": f"{cpu_usage:.1f}%",
        "score": cpu_score,
        "status": cpu_label,
    })
    if cpu_score < 50:
        recommendations.append("High CPU usage detected — check Process Manager for resource hogs.")

    # ── RAM ──────────────────────────────────────────────────────────────────
    mem = psutil.virtual_memory()
    ram_score, ram_label = _score_ram(mem.percent)
    indicators.append({
        "name": "RAM Usage",
        "value": f"{mem.percent:.1f}%  ({mem.used // 1024 ** 2} MB / {mem.total // 1024 ** 2} MB)",
        "score": ram_score,
        "status": ram_label,
    })
    if ram_score < 50:
        recommendations.append("RAM is heavily loaded — consider closing unused applications or using Optimizer > RAM.")

    # ── Disk ─────────────────────────────────────────────────────────────────
    disk_root = "C:\\" if os.name == "nt" else "/"
    try:
        disk = psutil.disk_usage(disk_root)
        disk_score, disk_label = _score_disk(disk.percent)
        indicators.append({
            "name": "Disk Free Space",
            "value": f"{100 - disk.percent:.1f}% free  ({disk.free // 1024 ** 3} GB / {disk.total // 1024 ** 3} GB)",
            "score": disk_score,
            "status": disk_label,
        })
        if disk_score < 40:
            recommendations.append("Low disk space — run a Deep Clean or use Disk Tools to find large files.")
    except Exception:
        disk_score = 50

    # ── Temp files ───────────────────────────────────────────────────────────
    try:
        import tempfile
        temp_dir = tempfile.gettempdir()
        temp_count = sum(1 for _ in os.scandir(temp_dir))
    except Exception:
        temp_count = 0
    temp_score, temp_label = _score_temp_files(temp_count)
    indicators.append({
        "name": "Temp File Clutter",
        "value": f"{temp_count} items in temp dir",
        "score": temp_score,
        "status": temp_label,
    })
    if temp_score < 50:
        recommendations.append("Many temporary files found — run a Quick Clean to reclaim space.")

    # ── Startup items ────────────────────────────────────────────────────────
    startup_count = 0
    try:
        from core.startup import get_startup_entries
        startup_count = len(get_startup_entries(logger))
    except Exception:
        pass
    startup_score, startup_label = _score_startup(startup_count)
    indicators.append({
        "name": "Startup Programs",
        "value": f"{startup_count} entries",
        "score": startup_score,
        "status": startup_label,
    })
    if startup_score < 50:
        recommendations.append("Too many startup programs — use Startup Manager to disable unnecessary entries.")

    # ── Uptime ───────────────────────────────────────────────────────────────
    uptime_seconds = time.time() - psutil.boot_time()
    uptime_hours   = uptime_seconds / 3600
    uptime_score, uptime_label = _score_uptime(uptime_hours)
    uptime_str = (
        f"{int(uptime_hours // 24)}d {int(uptime_hours % 24)}h"
        if uptime_hours >= 24
        else f"{int(uptime_hours)}h {int((uptime_hours % 1) * 60)}m"
    )
    indicators.append({
        "name": "System Uptime",
        "value": uptime_str,
        "score": uptime_score,
        "status": uptime_label,
    })
    if uptime_score < 50:
        recommendations.append("System has been running for a long time — a restart can improve stability.")

    # ── Overall score ────────────────────────────────────────────────────────
    weights = [0.20, 0.20, 0.20, 0.15, 0.15, 0.10]
    scores  = [cpu_score, ram_score, disk_score, temp_score, startup_score, uptime_score]
    overall = int(sum(s * w for s, w in zip(scores, weights)))

    if overall >= 85:
        grade = "A"
    elif overall >= 70:
        grade = "B"
    elif overall >= 55:
        grade = "C"
    elif overall >= 35:
        grade = "D"
    else:
        grade = "F"

    if not recommendations:
        recommendations.append("System is in great shape — no immediate action required.")

    logger.info(f"Health score computed: {overall}/100 (grade {grade})")
    return {
        "overall_score":   overall,
        "grade":           grade,
        "indicators":      indicators,
        "recommendations": recommendations,
    }

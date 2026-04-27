"""System monitor — live dashboard, port listing, temperatures, battery."""

import os
import time
import psutil


def snapshot() -> dict:
    """One-shot system snapshot for dashboard."""
    cpu = psutil.cpu_percent(interval=0.5)
    cpu_per = psutil.cpu_percent(interval=0, percpu=True)
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    disks = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append({
                "device":  part.device,
                "mount":   part.mountpoint,
                "fstype":  part.fstype,
                "total":   usage.total,
                "used":    usage.used,
                "free":    usage.free,
                "percent": usage.percent,
            })
        except (PermissionError, OSError):
            pass

    net = psutil.net_io_counters()

    freq = psutil.cpu_freq()
    uptime = time.time() - psutil.boot_time()

    return {
        "cpu_percent":  cpu,
        "cpu_per_core": cpu_per,
        "cpu_count":    psutil.cpu_count(logical=True),
        "cpu_freq_mhz": round(freq.current) if freq else None,
        "mem_total":    mem.total,
        "mem_used":     mem.used,
        "mem_percent":  mem.percent,
        "swap_used":    swap.used,
        "swap_percent": swap.percent,
        "disks":        disks,
        "net_sent":     net.bytes_sent,
        "net_recv":     net.bytes_recv,
        "uptime_s":     uptime,
    }


def list_ports() -> list[dict]:
    """All network connections with owning process."""
    try:
        conns = psutil.net_connections(kind="inet")
    except (psutil.AccessDenied, PermissionError):
        try:
            conns = psutil.net_connections(kind="inet4")
        except Exception:
            return []

    pid_cache: dict[int, str] = {}
    results: list[dict] = []

    for c in conns:
        if not c.laddr:
            continue
        pid = c.pid or 0
        if pid and pid not in pid_cache:
            try:
                pid_cache[pid] = psutil.Process(pid).name()
            except Exception:
                pid_cache[pid] = "?"
        try:
            proto = "TCP" if c.type.name == "SOCK_STREAM" else "UDP"
        except Exception:
            proto = "?"
        results.append({
            "proto":       proto,
            "local":       f"{c.laddr.ip}:{c.laddr.port}",
            "remote":      f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else "",
            "status":      c.status or "",
            "pid":         pid,
            "process":     pid_cache.get(pid, "?"),
        })

    return sorted(results, key=lambda x: (x["status"], x["local"]))


def temperatures() -> dict[str, list[dict]]:
    """CPU/GPU temperatures. Returns {} if unavailable (e.g. macOS without sudo)."""
    try:
        raw = psutil.sensors_temperatures()
        if not raw:
            return {}
        return {
            name: [
                {"label": e.label or name, "current": e.current,
                 "high": e.high, "critical": e.critical}
                for e in entries
            ]
            for name, entries in raw.items()
        }
    except (AttributeError, Exception):
        return {}


def battery() -> dict | None:
    """Battery info. Returns None if no battery present."""
    try:
        b = psutil.sensors_battery()
        if b is None:
            return None
        secs = b.secsleft
        if secs in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN, -1, -2):
            secs = None
        return {
            "percent": round(b.percent, 1),
            "plugged": b.power_plugged,
            "secs_left": secs,
        }
    except (AttributeError, Exception):
        return None


def fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def fmt_uptime(secs: float) -> str:
    s = int(secs)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    if d:
        return f"{d}d {h:02d}:{m:02d}:{s:02d}"
    return f"{h:02d}:{m:02d}:{s:02d}"

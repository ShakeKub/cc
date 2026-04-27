"""Log analyzer — parse system/auth logs and flag anomalies."""

import os
import platform
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


# ── Anomaly patterns ──────────────────────────────────────────────────────────

_PATTERNS = {
    "failed_login":    re.compile(r"(failed|failure|invalid|error|wrong).{0,30}(password|login|auth|credential)", re.I),
    "brute_force":     re.compile(r"(authentication failure|Failed password for|Invalid user)", re.I),
    "privilege_esc":   re.compile(r"(sudo|su:|COMMAND=|ROOT COMMAND|privilege|escalat)", re.I),
    "new_user":        re.compile(r"(useradd|adduser|new user|user .{0,20} created)", re.I),
    "service_change":  re.compile(r"(service .{0,30} (started|stopped|failed|crashed)|systemd)", re.I),
    "kernel_error":    re.compile(r"(kernel|panic|oops|BUG:|NULL pointer|segfault)", re.I),
    "network_anomaly": re.compile(r"(connection refused|port scan|nmap|network unreachable)", re.I),
    "ssh_event":       re.compile(r"(sshd|Accepted|Disconnected from|publickey|keyboard-interactive)", re.I),
}


def _flag_line(line: str) -> list[str]:
    flags = []
    for name, pat in _PATTERNS.items():
        if pat.search(line):
            flags.append(name)
    return flags


# ── Linux / macOS log sources ─────────────────────────────────────────────────

_LINUX_LOGS = [
    "/var/log/auth.log",
    "/var/log/secure",
    "/var/log/syslog",
    "/var/log/messages",
    "/var/log/kern.log",
]


def _read_file_tail(path: str, lines: int = 2000) -> list[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        return all_lines[-lines:]
    except PermissionError:
        return [f"[Permission denied: {path}]"]
    except FileNotFoundError:
        return []
    except Exception as exc:
        return [f"[Error reading {path}: {exc}]"]


def _macos_log(hours: int = 6, limit: int = 2000) -> list[str]:
    """Use macOS `log show` to read recent system log."""
    try:
        r = subprocess.run(
            ["log", "show", "--last", f"{hours}h",
             "--style", "syslog", "--info"],
            capture_output=True, text=True, timeout=30,
        )
        return r.stdout.splitlines()[-limit:]
    except Exception:
        return []


def _windows_log(log_name: str = "Security", count: int = 500) -> list[str]:
    """Use wevtutil to read Windows event log."""
    try:
        r = subprocess.run(
            ["wevtutil", "qe", log_name, f"/c:{count}", "/rd:true", "/f:text"],
            capture_output=True, text=True, timeout=30,
        )
        return r.stdout.splitlines()
    except Exception:
        return []


def collect_lines(hours: int = 24, max_lines: int = 5000) -> list[tuple[str, str]]:
    """Return [(source, line), ...] from platform-appropriate logs."""
    plat = platform.system()
    pairs: list[tuple[str, str]] = []

    if plat == "Linux":
        for path in _LINUX_LOGS:
            for line in _read_file_tail(path, max_lines // len(_LINUX_LOGS)):
                pairs.append((path, line.rstrip()))

    elif plat == "Darwin":
        for line in _macos_log(hours=hours, limit=max_lines):
            pairs.append(("log show", line))
        # Also try common log files
        for path in ["/var/log/system.log", "/var/log/auth.log"]:
            for line in _read_file_tail(path, 500):
                pairs.append((path, line.rstrip()))

    elif plat == "Windows":
        for log_name in ("Security", "System", "Application"):
            for line in _windows_log(log_name, max_lines // 3):
                pairs.append((log_name, line))

    return pairs


# ── Main analysis ─────────────────────────────────────────────────────────────

def analyze(hours: int = 24, max_lines: int = 5000) -> dict:
    """Analyze system logs and return flagged events grouped by type."""
    pairs = collect_lines(hours=hours, max_lines=max_lines)

    events_by_type: dict[str, list[dict]] = defaultdict(list)
    total_lines = len(pairs)
    flagged     = 0

    # IP extraction
    _ip_re = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")

    for source, line in pairs:
        flags = _flag_line(line)
        if not flags:
            continue
        flagged += 1
        ips = _ip_re.findall(line)
        entry = {
            "source": source,
            "line":   line[:300],
            "ips":    list(set(ips)),
        }
        for f in flags:
            events_by_type[f].append(entry)

    # Top IPs involved in brute-force events
    bf_ips: dict[str, int] = defaultdict(int)
    for entry in events_by_type.get("brute_force", []):
        for ip in entry["ips"]:
            bf_ips[ip] += 1
    top_ips = sorted(bf_ips.items(), key=lambda x: -x[1])[:10]

    return {
        "platform":          platform.system(),
        "hours_analyzed":    hours,
        "total_lines":       total_lines,
        "flagged_lines":     flagged,
        "events":            {k: v for k, v in events_by_type.items()},
        "event_counts":      {k: len(v) for k, v in events_by_type.items()},
        "top_brute_ips":     top_ips,
        "sources_read":      list({s for s, _ in pairs}),
    }


def summary_lines(result: dict) -> list[str]:
    """Format an analyze() result into printable lines."""
    lines = [
        f"Platform      : {result['platform']}",
        f"Log hours     : {result['hours_analyzed']}",
        f"Lines scanned : {result['total_lines']:,}",
        f"Flagged lines : {result['flagged_lines']:,}",
        "",
        "Event counts:",
    ]
    counts = result.get("event_counts", {})
    if not counts:
        lines.append("  No anomalies detected.")
    else:
        for etype, n in sorted(counts.items(), key=lambda x: -x[1]):
            lines.append(f"  {etype:<22} {n:>4}")

    top = result.get("top_brute_ips", [])
    if top:
        lines += ["", "Top IPs (brute-force):"]
        for ip, n in top:
            lines.append(f"  {ip:<20} {n} events")

    return lines

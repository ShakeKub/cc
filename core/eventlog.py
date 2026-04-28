"""Event log viewer — Windows/Linux/macOS."""
import platform, re, subprocess
from datetime import datetime, timedelta

LEVELS = {"critical": 1, "error": 2, "warning": 3, "information": 4}

def _run(cmd, timeout=20):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, errors="replace")
        return r.returncode, r.stdout, r.stderr
    except Exception as e:
        return -1, "", str(e)

def query(log: str = "System", level: str = "error",
          hours: int = 24, max_events: int = 100) -> list[dict]:
    sys = platform.system()
    if sys == "Windows":   return _query_win(log, level, hours, max_events)
    if sys == "Darwin":    return _query_mac(level, hours, max_events)
    return _query_linux(level, hours, max_events)

def available_logs() -> list[str]:
    if platform.system() == "Windows":
        rc, out, _ = _run(["wevtutil", "el"])
        return [l.strip() for l in out.splitlines() if l.strip()][:50]
    return ["System", "Application", "Security"]

def _query_win(log, level, hours, max_events) -> list[dict]:
    level_map = {"critical": "1", "error": "2", "warning": "3",
                 "information": "4", "all": "0"}
    lv = level_map.get(level.lower(), "2")
    since = (datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S")
    query_str = f"*[System[(Level<={lv}) and TimeCreated[@SystemTime>='{since}']]]"
    rc, out, err = _run([
        "wevtutil", "qe", log,
        f"/query:{query_str}",
        f"/count:{max_events}",
        "/format:text",
        "/rd:true",
    ], timeout=30)
    events = []
    cur: dict = {}
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("Event["):
            if cur: events.append(cur)
            cur = {}
        elif "Date:" in line:
            cur["time"] = line.split("Date:",1)[1].strip()
        elif "Level:" in line:
            cur["level"] = line.split("Level:",1)[1].strip()
        elif "Source:" in line:
            cur["source"] = line.split("Source:",1)[1].strip()
        elif "Event ID:" in line or "EventID:" in line:
            cur["event_id"] = line.split(":",1)[1].strip()
        elif "Description:" in line:
            cur["message"] = line.split("Description:",1)[1].strip()[:200]
    if cur: events.append(cur)
    return events

def _query_mac(level, hours, max_events) -> list[dict]:
    pred = ""
    if level in ("error", "critical"):
        pred = "--predicate eventType == logEventType AND messageType >= 16"
    rc, out, _ = _run(["log", "show", "--last", f"{hours}h",
                        "--style", "syslog", "--info"] +
                       (pred.split() if pred else []), timeout=30)
    events = []
    for line in out.splitlines()[-max_events:]:
        if not line.strip(): continue
        parts = line.split(None, 3)
        if len(parts) >= 4:
            events.append({"time": f"{parts[0]} {parts[1]}", "source": parts[2],
                           "level": "info", "message": parts[3][:200]})
    return events

def _query_linux(level, hours, max_events) -> list[dict]:
    since = f"{hours}h ago"
    prio_map = {"critical": "0..2", "error": "0..3", "warning": "0..4", "all": "0..7"}
    prio = prio_map.get(level.lower(), "0..3")
    rc, out, _ = _run(["journalctl", f"--since={since}", f"-p{prio}",
                        "-n", str(max_events), "--no-pager", "-o", "short"], timeout=20)
    events = []
    for line in out.splitlines():
        parts = line.split(None, 4)
        if len(parts) >= 5:
            events.append({"time": f"{parts[0]} {parts[1]}", "source": parts[2],
                           "level": level, "message": " ".join(parts[3:])[:200]})
    return events

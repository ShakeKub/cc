"""DNS tools — flush DNS cache, view/edit hosts file."""

import os
import re
import subprocess
from pathlib import Path
from core.logger import CleanerLogger

HOSTS_PATH = Path(r"C:\Windows\System32\drivers\etc\hosts")
MARKER_START = "# == System Cleaner Hosts Block Start =="
MARKER_END   = "# == System Cleaner Hosts Block End =="


def flush_dns(logger: CleanerLogger) -> bool:
    """Run ipconfig /flushdns. Returns True on success."""
    try:
        r = subprocess.run(["ipconfig", "/flushdns"],
                           capture_output=True, text=True, timeout=15)
        ok = r.returncode == 0
        logger.log("flush_dns", "dnstools",
                   "DNS cache flushed" if ok else f"Flush failed: {r.stderr}")
        return ok
    except Exception as e:
        logger.error(f"flush_dns error: {e}")
        return False


def get_dns_servers() -> list[str]:
    """Return list of active DNS server addresses."""
    try:
        r = subprocess.run(["netsh", "dns", "show", "state"],
                           capture_output=True, text=True, timeout=10)
        servers = re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", r.stdout)
        return list(dict.fromkeys(servers))  # deduplicate, preserve order
    except Exception:
        return []


def read_hosts(logger: CleanerLogger) -> list[dict]:
    """Parse hosts file. Returns list of {ip, host, comment, line_no, is_blocker}."""
    entries = []
    if not HOSTS_PATH.exists():
        return entries
    try:
        lines = HOSTS_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
        in_block = False
        for i, line in enumerate(lines):
            if line.strip() == MARKER_START:
                in_block = True
                continue
            if line.strip() == MARKER_END:
                in_block = False
                continue
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split()
            if len(parts) >= 2:
                ip = parts[0]
                host = parts[1]
                comment = " ".join(parts[2:]).lstrip("#").strip() if len(parts) > 2 else ""
                entries.append({
                    "ip": ip, "host": host, "comment": comment,
                    "line_no": i + 1, "is_blocker": in_block,
                })
    except Exception as e:
        logger.error(f"read_hosts error: {e}")
    return entries


def add_hosts_entry(ip: str, host: str, logger: CleanerLogger) -> bool:
    """Append a new entry to the hosts file."""
    try:
        with HOSTS_PATH.open("a", encoding="utf-8") as f:
            f.write(f"\n{ip}\t{host}")
        logger.log("add_hosts", "dnstools", f"Added hosts entry: {ip} {host}")
        return True
    except Exception as e:
        logger.error(f"add_hosts error: {e}")
        return False


def delete_hosts_entry(host: str, logger: CleanerLogger) -> bool:
    """Remove all lines containing the given hostname."""
    try:
        text = HOSTS_PATH.read_text(encoding="utf-8", errors="replace")
        lines = [l for l in text.splitlines()
                 if not (not l.strip().startswith("#") and host in l.split())]
        HOSTS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        logger.log("del_hosts", "dnstools", f"Removed hosts entry: {host}")
        return True
    except Exception as e:
        logger.error(f"del_hosts error: {e}")
        return False


def display_dns_cache(logger: CleanerLogger) -> list[dict]:
    """Return local DNS cache entries via ipconfig /displaydns."""
    try:
        r = subprocess.run(["ipconfig", "/displaydns"],
                           capture_output=True, text=True, timeout=15)
        entries = []
        current = {}
        for line in r.stdout.splitlines():
            line = line.strip()
            if "Record Name" in line:
                if current:
                    entries.append(current)
                current = {"name": line.split(":", 1)[-1].strip()}
            elif "Record Type" in line:
                current["type"] = line.split(":", 1)[-1].strip()
            elif "Data" in line and "A (Host)" not in line:
                current["data"] = line.split(":", 1)[-1].strip()
        if current:
            entries.append(current)
        return entries
    except Exception as e:
        logger.error(f"display_dns_cache error: {e}")
        return []

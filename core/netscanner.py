"""Network scanner — TCP port scan, banner grab, ping sweep, DNS."""

import concurrent.futures
import os
import re
import socket
import subprocess
import time
from typing import Callable

# Mapping of well-known port → service name
COMMON_PORTS: dict[int, str] = {
    21: "FTP",      22: "SSH",       23: "Telnet",     25: "SMTP",
    53: "DNS",      67: "DHCP",      69: "TFTP",       80: "HTTP",
    110: "POP3",    111: "RPC",      119: "NNTP",      135: "MSRPC",
    137: "NetBIOS", 139: "NetBIOS",  143: "IMAP",      161: "SNMP",
    389: "LDAP",    443: "HTTPS",    445: "SMB",       465: "SMTPS",
    500: "IKE",     587: "SMTP",     631: "IPP",       636: "LDAPS",
    993: "IMAPS",   995: "POP3S",   1080: "SOCKS",    1194: "OpenVPN",
    1433: "MSSQL", 1521: "Oracle",  1723: "PPTP",     2049: "NFS",
    2181: "Zookeeper", 3000: "Dev", 3306: "MySQL",   3389: "RDP",
    4444: "Shell",  5000: "Dev",    5432: "Postgres", 5601: "Kibana",
    5672: "AMQP",   5900: "VNC",    6379: "Redis",    6443: "K8s",
    7077: "Spark",  8080: "HTTP",   8443: "HTTPS",    8888: "Jupyter",
    9000: "Dev",    9200: "ES",     9300: "ES",      11211: "Memcached",
    27017: "MongoDB", 27018: "MongoDB", 50070: "HDFS",
}

TOP_100_PORTS = sorted(COMMON_PORTS.keys())


def _tcp_probe(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def grab_banner(host: str, port: int, timeout: float = 3.0) -> str | None:
    """Try to read a service banner after connecting."""
    probes = {
        80: b"HEAD / HTTP/1.0\r\n\r\n",
        443: b"HEAD / HTTP/1.0\r\n\r\n",
        21: None, 22: None, 25: None,  # server sends first
    }
    probe = probes.get(port, b"\r\n")
    try:
        with socket.create_connection((host, port), timeout=timeout) as s:
            if probe:
                try:
                    s.sendall(probe)
                except Exception:
                    pass
            try:
                data = s.recv(1024)
                return data.decode("utf-8", errors="replace").strip()[:300]
            except Exception:
                return None
    except Exception:
        return None


def scan_ports(
    host: str,
    ports: list[int],
    timeout: float = 0.5,
    max_workers: int = 150,
    grab_banners: bool = False,
    progress_cb: Callable | None = None,
    stop_event=None,
) -> list[dict]:
    """TCP connect scan. Returns only open ports, sorted."""
    done = [0]

    class _NE:
        def is_set(self): return False

    _stop = stop_event or _NE()
    open_ports: list[dict] = []

    def _one(port: int) -> dict | None:
        done[0] += 1
        if progress_cb:
            progress_cb(done[0], len(ports), port)
        if _stop.is_set():
            return None
        if not _tcp_probe(host, port, timeout):
            return None
        entry = {
            "port":    port,
            "service": COMMON_PORTS.get(port, ""),
            "banner":  None,
        }
        if grab_banners:
            entry["banner"] = grab_banner(host, port)
        return entry

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(max_workers, len(ports) or 1)) as ex:
        for result in ex.map(_one, ports):
            if result:
                open_ports.append(result)

    return sorted(open_ports, key=lambda x: x["port"])


def ping_host(host: str, count: int = 1, timeout_s: int = 2) -> dict:
    """ICMP ping using the system ping binary."""
    flag_c = "-n" if os.name == "nt" else "-c"
    flag_w = "-w" if os.name == "nt" else "-W"
    try:
        t0 = time.time()
        r = subprocess.run(
            ["ping", flag_c, str(count), flag_w, str(timeout_s), host],
            capture_output=True, timeout=timeout_s + 3, text=True,
        )
        rtt_ms = (time.time() - t0) * 1000
        alive  = r.returncode == 0
        ttl: int | None = None
        m = re.search(r"ttl=(\d+)", r.stdout, re.IGNORECASE)
        if m:
            ttl = int(m.group(1))
        return {"alive": alive, "rtt_ms": round(rtt_ms, 1) if alive else None, "ttl": ttl}
    except Exception:
        return {"alive": False, "rtt_ms": None, "ttl": None}


def guess_os_from_ttl(ttl: int | None) -> str:
    if ttl is None:
        return "unknown"
    if ttl <= 64:
        return "Linux / macOS / Android"
    if ttl <= 128:
        return "Windows"
    if ttl <= 255:
        return "Cisco / Network device"
    return "unknown"


def ping_sweep(
    base_ip: str,
    start: int = 1,
    end: int = 254,
    max_workers: int = 64,
    progress_cb: Callable | None = None,
    stop_event=None,
) -> list[dict]:
    """Ping every host in *base_ip*.start–end. Returns alive hosts."""
    hosts = [f"{base_ip}.{i}" for i in range(start, end + 1)]
    done  = [0]

    class _NE:
        def is_set(self): return False

    _stop = stop_event or _NE()
    alive: list[dict] = []

    def _check(host: str) -> dict | None:
        done[0] += 1
        if progress_cb:
            progress_cb(done[0], len(hosts), host)
        if _stop.is_set():
            return None
        r = ping_host(host)
        if r["alive"]:
            rdns = _reverse(host)
            return {"host": host, "rdns": rdns, **r,
                    "os_guess": guess_os_from_ttl(r["ttl"])}
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        for r in ex.map(_check, hosts):
            if r:
                alive.append(r)

    return alive


def resolve(hostname: str) -> str | None:
    try:
        return socket.gethostbyname(hostname)
    except Exception:
        return None


def _reverse(ip: str) -> str | None:
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return None


def traceroute(host: str, max_hops: int = 30, timeout_s: int = 3) -> list[dict]:
    """Run system traceroute/tracert. Returns [{hop, ip, rtt_ms, rdns}, ...]."""
    import sys
    cmd = (["tracert", "-h", str(max_hops), "-w", str(timeout_s * 1000), host]
           if os.name == "nt"
           else ["traceroute", "-m", str(max_hops), "-w", str(timeout_s), host])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=max_hops * timeout_s + 10)
        output = r.stdout + r.stderr
    except FileNotFoundError:
        return [{"hop": 0, "ip": None, "rtt_ms": None, "rdns": None,
                 "error": "traceroute binary not found. Install traceroute."}]
    except Exception as exc:
        return [{"hop": 0, "ip": None, "rtt_ms": None, "rdns": None, "error": str(exc)}]

    hops: list[dict] = []
    ip_re  = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")
    rtt_re = re.compile(r"(\d+(?:\.\d+)?)\s*ms")

    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        # Match hop number at line start
        m_hop = re.match(r"^\s*(\d+)", line)
        if not m_hop:
            continue
        hop_num = int(m_hop.group(1))
        ips  = ip_re.findall(line)
        rtts = rtt_re.findall(line)
        ip   = ips[0] if ips else None
        rtt  = float(rtts[0]) if rtts else None
        rdns = _reverse(ip) if ip else None
        if rdns == ip:
            rdns = None
        hops.append({"hop": hop_num, "ip": ip, "rtt_ms": rtt, "rdns": rdns})

    return hops


def whois(host: str, timeout: int = 10) -> str:
    """WHOIS lookup via system binary or direct socket to whois.iana.org."""
    # Try system binary first
    try:
        r = subprocess.run(["whois", host], capture_output=True, text=True,
                           timeout=timeout)
        if r.stdout.strip():
            return r.stdout.strip()
    except FileNotFoundError:
        pass
    except Exception:
        pass

    # Fallback: raw socket to IANA WHOIS
    try:
        with socket.create_connection(("whois.iana.org", 43), timeout=timeout) as s:
            s.sendall((host + "\r\n").encode())
            data = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
            raw = data.decode("utf-8", errors="replace")
        # If IANA refers to another server, follow one redirect
        for line in raw.splitlines():
            if line.lower().startswith("refer:"):
                refer_host = line.split(":", 1)[1].strip()
                try:
                    with socket.create_connection((refer_host, 43), timeout=timeout) as s2:
                        s2.sendall((host + "\r\n").encode())
                        data2 = b""
                        while True:
                            chunk = s2.recv(4096)
                            if not chunk:
                                break
                            data2 += chunk
                        return data2.decode("utf-8", errors="replace")
                except Exception:
                    break
        return raw
    except Exception as exc:
        return f"WHOIS error: {exc}"


def parse_port_range(spec: str) -> list[int]:
    """Parse '22,80,443,1000-2000' → sorted list of ints."""
    ports: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            ports.update(range(int(lo), int(hi) + 1))
        elif part.isdigit():
            ports.add(int(part))
    return sorted(p for p in ports if 1 <= p <= 65535)

"""Network Speed Test — latency, DNS timing, and download speed."""

import os
import socket
import subprocess
import time
import urllib.request
from core.logger import CleanerLogger

# 10 MB test file from Cloudflare's speed test infrastructure
TEST_URL = "https://speed.cloudflare.com/__down?bytes=10000000"
PING_HOSTS = ["8.8.8.8", "1.1.1.1", "208.67.222.222"]
DNS_HOSTS  = ["google.com", "cloudflare.com", "microsoft.com"]


def ping_latency(host: str = "8.8.8.8", count: int = 4) -> dict:
    """Return avg/min/max latency in ms by running system ping."""
    try:
        if os.name == "nt":
            r = subprocess.run(
                ["ping", "-n", str(count), host],
                capture_output=True, text=True, timeout=20,
            )
        else:
            r = subprocess.run(
                ["ping", "-c", str(count), host],
                capture_output=True, text=True, timeout=20,
            )
        out = r.stdout
        # Parse "Average = XXms" (Windows) or "rtt min/avg/max" (Unix)
        avg = mn = mx = 0.0
        if os.name == "nt":
            import re
            m = re.search(r"Average = (\d+)ms", out)
            if m:
                avg = float(m.group(1))
            m2 = re.search(r"Minimum = (\d+)ms", out)
            if m2:
                mn = float(m2.group(1))
            m3 = re.search(r"Maximum = (\d+)ms", out)
            if m3:
                mx = float(m3.group(1))
        else:
            import re
            m = re.search(r"(\d+\.?\d*)/(\d+\.?\d*)/(\d+\.?\d*)", out)
            if m:
                mn, avg, mx = float(m.group(1)), float(m.group(2)), float(m.group(3))
        return {"host": host, "avg_ms": avg, "min_ms": mn, "max_ms": mx,
                "success": avg > 0}
    except Exception as e:
        return {"host": host, "avg_ms": 0, "min_ms": 0, "max_ms": 0,
                "success": False, "error": str(e)}


def dns_resolution_time(hostname: str) -> dict:
    """Measure DNS resolution time in milliseconds."""
    t0 = time.perf_counter()
    try:
        socket.getaddrinfo(hostname, None)
        elapsed = (time.perf_counter() - t0) * 1000
        return {"host": hostname, "ms": round(elapsed, 1), "success": True}
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        return {"host": hostname, "ms": round(elapsed, 1), "success": False, "error": str(e)}


def download_speed(url: str = TEST_URL, timeout: int = 30) -> dict:
    """Download from url, return speed in Mbps."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ByteSweep/1.0"})
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        elapsed = time.perf_counter() - t0
        bytes_recv = len(data)
        mbps = (bytes_recv * 8) / (elapsed * 1_000_000) if elapsed > 0 else 0
        return {
            "bytes": bytes_recv,
            "elapsed_s": round(elapsed, 2),
            "mbps": round(mbps, 2),
            "success": True,
        }
    except Exception as e:
        return {"bytes": 0, "elapsed_s": 0, "mbps": 0, "success": False, "error": str(e)}


def run_full_test(logger: CleanerLogger) -> dict:
    """Run complete latency + DNS + download test. Returns combined results."""
    results: dict = {}

    results["ping"] = [ping_latency(h) for h in PING_HOSTS]
    results["dns"]  = [dns_resolution_time(h) for h in DNS_HOSTS]
    results["download"] = download_speed()

    avg_ping = [p["avg_ms"] for p in results["ping"] if p["success"]]
    results["summary"] = {
        "avg_ping_ms":   round(sum(avg_ping) / len(avg_ping), 1) if avg_ping else 0,
        "download_mbps": results["download"].get("mbps", 0),
    }

    logger.log("netspeed_test", "netspeed",
               f"Speed test: {results['summary']['download_mbps']} Mbps, "
               f"ping {results['summary']['avg_ping_ms']} ms")
    return results

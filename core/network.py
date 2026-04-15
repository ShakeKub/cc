"""Network tools - connections, DNS, diagnostics, IP info, ping."""

import socket
import subprocess
from typing import Any
import psutil
from core.logger import CleanerLogger


def get_active_connections(logger: CleanerLogger | None = None) -> list[dict[str, Any]]:
    """List all active network connections."""
    connections = []
    for conn in psutil.net_connections(kind='inet'):
        try:
            # Get process name
            proc_name = ""
            if conn.pid:
                try:
                    proc_name = psutil.Process(conn.pid).name()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    proc_name = f"PID:{conn.pid}"

            local = f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else "N/A"
            remote = f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else "N/A"

            connections.append({
                "pid": conn.pid or 0,
                "process": proc_name,
                "local_address": local,
                "remote_address": remote,
                "status": conn.status,
                "type": "TCP" if conn.type == socket.SOCK_STREAM else "UDP",
                "family": "IPv4" if conn.family == socket.AF_INET else "IPv6",
            })
        except Exception:
            pass

    if logger:
        logger.info(f"Found {len(connections)} active connections")
    return connections


def flush_dns(logger: CleanerLogger) -> bool:
    """Flush the DNS resolver cache."""
    try:
        result = subprocess.run(
            ["ipconfig", "/flushdns"],
            capture_output=True, text=True, timeout=15,
        )
        success = result.returncode == 0
        logger.log("flush_dns", "network", "DNS cache flushed", success=success)
        return success
    except Exception as e:
        logger.error(f"DNS flush failed: {e}")
        return False


def get_ip_info(logger: CleanerLogger | None = None) -> dict[str, Any]:
    """Get local network interface information."""
    info = {
        "hostname": socket.gethostname(),
        "interfaces": [],
    }

    try:
        # Get all network interfaces
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()

        for iface_name, iface_addrs in addrs.items():
            iface_info = {
                "name": iface_name,
                "is_up": stats.get(iface_name, None) and stats[iface_name].isup,
                "speed": stats.get(iface_name, None) and stats[iface_name].speed,
                "addresses": [],
            }
            for addr in iface_addrs:
                addr_info = {
                    "address": addr.address,
                    "netmask": addr.netmask,
                    "family": str(addr.family),
                }
                if addr.family == socket.AF_INET:
                    addr_info["type"] = "IPv4"
                elif addr.family == socket.AF_INET6:
                    addr_info["type"] = "IPv6"
                else:
                    addr_info["type"] = "MAC"
                iface_info["addresses"].append(addr_info)
            info["interfaces"].append(iface_info)
    except Exception as e:
        if logger:
            logger.error(f"Failed to get IP info: {e}")

    # Try to get default gateway
    try:
        result = subprocess.run(
            ["ipconfig"],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.splitlines():
            if "Default Gateway" in line and ":" in line:
                gw = line.split(":")[-1].strip()
                if gw:
                    info["default_gateway"] = gw
                    break
    except Exception:
        pass

    return info


def ping(host: str, count: int = 4,
         logger: CleanerLogger | None = None) -> dict[str, Any]:
    """Ping a host and return results."""
    try:
        result = subprocess.run(
            ["ping", "-n", str(count), host],
            capture_output=True, text=True, timeout=30,
        )
        output = result.stdout

        # Parse results
        ping_result = {
            "host": host,
            "success": result.returncode == 0,
            "output": output,
            "packets_sent": count,
            "packets_received": 0,
            "avg_latency_ms": 0,
        }

        # Parse packet stats
        for line in output.splitlines():
            if "Received" in line:
                parts = line.split(",")
                for part in parts:
                    if "Received" in part:
                        try:
                            ping_result["packets_received"] = int(
                                part.strip().split("=")[1].strip().split()[0]
                            )
                        except (ValueError, IndexError):
                            pass
            if "Average" in line:
                try:
                    avg = line.split("Average")[-1].strip().strip("=").strip().replace("ms", "")
                    ping_result["avg_latency_ms"] = float(avg)
                except (ValueError, IndexError):
                    pass

        if logger:
            logger.info(f"Ping {host}: {'success' if ping_result['success'] else 'failed'}")
        return ping_result
    except subprocess.TimeoutExpired:
        return {"host": host, "success": False, "output": "Ping timed out"}
    except Exception as e:
        return {"host": host, "success": False, "output": str(e)}


def run_diagnostics(logger: CleanerLogger) -> list[dict[str, Any]]:
    """Run basic network diagnostics."""
    tests = []

    # Test 1: DNS resolution
    try:
        ip = socket.gethostbyname("www.google.com")
        tests.append({
            "test": "DNS Resolution",
            "target": "www.google.com",
            "result": f"Resolved to {ip}",
            "status": "pass",
        })
    except socket.gaierror:
        tests.append({
            "test": "DNS Resolution",
            "target": "www.google.com",
            "result": "Failed to resolve",
            "status": "fail",
        })

    # Test 2: Gateway ping
    ip_info = get_ip_info()
    gw = ip_info.get("default_gateway", "")
    if gw:
        ping_result = ping(gw, count=2, logger=logger)
        tests.append({
            "test": "Gateway Ping",
            "target": gw,
            "result": f"{'OK' if ping_result['success'] else 'Failed'} "
                      f"({ping_result.get('avg_latency_ms', 'N/A')}ms)",
            "status": "pass" if ping_result["success"] else "fail",
        })

    # Test 3: Internet connectivity
    ping_result = ping("8.8.8.8", count=2, logger=logger)
    tests.append({
        "test": "Internet Connectivity",
        "target": "8.8.8.8 (Google DNS)",
        "result": f"{'OK' if ping_result['success'] else 'Failed'} "
                  f"({ping_result.get('avg_latency_ms', 'N/A')}ms)",
        "status": "pass" if ping_result["success"] else "fail",
    })

    # Test 4: Check for active adapters
    active_adapters = sum(
        1 for iface in ip_info.get("interfaces", [])
        if iface.get("is_up")
    )
    tests.append({
        "test": "Network Adapters",
        "target": "Local",
        "result": f"{active_adapters} active adapter(s)",
        "status": "pass" if active_adapters > 0 else "fail",
    })

    logger.info(f"Network diagnostics: {sum(1 for t in tests if t['status'] == 'pass')}/{len(tests)} passed")
    return tests


def get_network_stats() -> dict[str, Any]:
    """Get network I/O statistics."""
    counters = psutil.net_io_counters()
    return {
        "bytes_sent": counters.bytes_sent,
        "bytes_recv": counters.bytes_recv,
        "packets_sent": counters.packets_sent,
        "packets_recv": counters.packets_recv,
        "errors_in": counters.errin,
        "errors_out": counters.errout,
        "drop_in": counters.dropin,
        "drop_out": counters.dropout,
    }

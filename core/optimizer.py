"""System optimization - services, RAM, CPU, power plans."""

import subprocess
from typing import Any
from core.logger import CleanerLogger


# Services that are generally safe to disable for performance
OPTIONAL_SERVICES = {
    "DiagTrack": {
        "display": "Connected User Experiences and Telemetry",
        "description": "Windows telemetry data collection",
        "category": "telemetry",
        "impact": "low",
        "safe_to_disable": True,
    },
    "dmwappushservice": {
        "display": "Device Management WAP Push",
        "description": "WAP push message routing",
        "category": "telemetry",
        "impact": "low",
        "safe_to_disable": True,
    },
    "SysMain": {
        "display": "SysMain (Superfetch)",
        "description": "Maintains and improves system performance (uses RAM/disk)",
        "category": "performance",
        "impact": "medium",
        "safe_to_disable": True,
    },
    "WSearch": {
        "display": "Windows Search",
        "description": "Content indexing and search (high disk usage)",
        "category": "performance",
        "impact": "high",
        "safe_to_disable": True,
    },
    "Fax": {
        "display": "Fax",
        "description": "Fax sending and receiving",
        "category": "unused",
        "impact": "low",
        "safe_to_disable": True,
    },
    "MapsBroker": {
        "display": "Downloaded Maps Manager",
        "description": "Windows Maps data access",
        "category": "unused",
        "impact": "low",
        "safe_to_disable": True,
    },
    "lfsvc": {
        "display": "Geolocation Service",
        "description": "Monitors device location",
        "category": "privacy",
        "impact": "low",
        "safe_to_disable": True,
    },
    "RetailDemo": {
        "display": "Retail Demo Service",
        "description": "Retail demo mode management",
        "category": "unused",
        "impact": "low",
        "safe_to_disable": True,
    },
    "wisvc": {
        "display": "Windows Insider Service",
        "description": "Windows Insider Program infrastructure",
        "category": "unused",
        "impact": "low",
        "safe_to_disable": True,
    },
    "XblAuthManager": {
        "display": "Xbox Live Auth Manager",
        "description": "Xbox Live authentication",
        "category": "gaming",
        "impact": "low",
        "safe_to_disable": True,
    },
    "XblGameSave": {
        "display": "Xbox Live Game Save",
        "description": "Xbox Live game save sync",
        "category": "gaming",
        "impact": "low",
        "safe_to_disable": True,
    },
}

# Critical services that must never be disabled
CRITICAL_SERVICES = {
    "RpcSs", "DcomLaunch", "BrokerInfrastructure", "LSM",
    "EventLog", "PlugPlay", "Power", "Winmgmt", "Schedule",
    "SENS", "SystemEventsBroker", "WinDefend", "mpssvc",
    "BFE", "CryptSvc", "Dhcp", "Dnscache", "LanmanWorkstation",
    "nsi", "Themes", "AudioSrv", "AudioEndpointBuilder",
}


def get_service_status(service_name: str) -> dict[str, str]:
    """Get the current status of a Windows service."""
    try:
        result = subprocess.run(
            ["sc", "query", service_name],
            capture_output=True, text=True, timeout=10,
        )
        status = "unknown"
        start_type = "unknown"
        if "RUNNING" in result.stdout:
            status = "running"
        elif "STOPPED" in result.stdout:
            status = "stopped"

        result2 = subprocess.run(
            ["sc", "qc", service_name],
            capture_output=True, text=True, timeout=10,
        )
        if "AUTO_START" in result2.stdout:
            start_type = "automatic"
        elif "DEMAND_START" in result2.stdout:
            start_type = "manual"
        elif "DISABLED" in result2.stdout:
            start_type = "disabled"

        return {"status": status, "start_type": start_type}
    except Exception:
        return {"status": "error", "start_type": "unknown"}


def list_optimizable_services(logger: CleanerLogger) -> list[dict[str, Any]]:
    """List services that can be optimized with their current status."""
    services = []
    for name, info in OPTIONAL_SERVICES.items():
        status = get_service_status(name)
        services.append({
            "name": name,
            "display_name": info["display"],
            "description": info["description"],
            "category": info["category"],
            "impact": info["impact"],
            "status": status["status"],
            "start_type": status["start_type"],
            "safe_to_disable": info["safe_to_disable"],
        })
    logger.info(f"Found {len(services)} optimizable services")
    return services


def disable_service(service_name: str, logger: CleanerLogger) -> bool:
    """Disable a Windows service (set to manual start and stop it)."""
    if service_name in CRITICAL_SERVICES:
        logger.error(f"Refused to disable critical service: {service_name}")
        return False
    try:
        # Set to disabled
        subprocess.run(["sc", "config", service_name, "start=", "disabled"],
                       capture_output=True, timeout=15)
        # Stop it
        subprocess.run(["sc", "stop", service_name],
                       capture_output=True, timeout=15)
        logger.log("disable_service", "optimizer", f"Disabled service: {service_name}")
        return True
    except Exception as e:
        logger.error(f"Failed to disable {service_name}: {e}")
        return False


def enable_service(service_name: str, logger: CleanerLogger) -> bool:
    """Re-enable a Windows service."""
    try:
        subprocess.run(["sc", "config", service_name, "start=", "auto"],
                       capture_output=True, timeout=15)
        subprocess.run(["sc", "start", service_name],
                       capture_output=True, timeout=15)
        logger.log("enable_service", "optimizer", f"Enabled service: {service_name}")
        return True
    except Exception as e:
        logger.error(f"Failed to enable {service_name}: {e}")
        return False


def get_power_plans(logger: CleanerLogger) -> list[dict[str, str]]:
    """List available power plans."""
    plans = []
    try:
        result = subprocess.run(
            ["powercfg", "/list"],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.splitlines():
            if "GUID" in line:
                parts = line.strip().split(":")
                if len(parts) >= 2:
                    guid_part = parts[1].strip()
                    guid = guid_part.split(" ")[0].strip()
                    name = ""
                    if "(" in line and ")" in line:
                        name = line[line.index("(") + 1:line.index(")")]
                    active = "*" in line
                    plans.append({
                        "guid": guid,
                        "name": name,
                        "active": active,
                    })
    except Exception as e:
        logger.error(f"Failed to list power plans: {e}")
    return plans


def set_power_plan(guid: str, logger: CleanerLogger) -> bool:
    """Switch to a specific power plan."""
    try:
        result = subprocess.run(
            ["powercfg", "/setactive", guid],
            capture_output=True, text=True, timeout=10,
        )
        success = result.returncode == 0
        if success:
            logger.log("set_power_plan", "optimizer", f"Switched power plan to: {guid}")
        return success
    except Exception as e:
        logger.error(f"Failed to set power plan: {e}")
        return False


def get_system_stats() -> dict[str, Any]:
    """Get current CPU, RAM, and disk usage statistics."""
    import os
    import psutil
    cpu_percent = psutil.cpu_percent(interval=0.5)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("C:\\") if os.name == "nt" else psutil.disk_usage("/")
    return {
        "cpu_percent": cpu_percent,
        "cpu_count": psutil.cpu_count(),
        "cpu_freq": psutil.cpu_freq()._asdict() if psutil.cpu_freq() else {},
        "ram_total": memory.total,
        "ram_used": memory.used,
        "ram_available": memory.available,
        "ram_percent": memory.percent,
        "disk_total": disk.total,
        "disk_used": disk.used,
        "disk_free": disk.free,
        "disk_percent": disk.percent,
    }


def optimize_ram(logger: CleanerLogger) -> dict[str, Any]:
    """
    Trim the working set of every accessible process.
    This asks Windows to page out idle memory pages, lowering reported RAM usage.
    Requires admin for best results; non-admin processes are skipped silently.
    """
    import gc
    import os
    import psutil

    before = psutil.virtual_memory()
    gc.collect()

    trimmed = 0
    skipped = 0

    if os.name == "nt":
        try:
            import ctypes
            kernel32  = ctypes.windll.kernel32
            PROCESS_SET_QUOTA = 0x0100
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            access = PROCESS_SET_QUOTA | PROCESS_QUERY_LIMITED_INFORMATION

            for proc in psutil.process_iter(["pid"]):
                pid = proc.info["pid"]
                if pid == 0:
                    continue
                handle = kernel32.OpenProcess(access, False, pid)
                if handle:
                    # SetProcessWorkingSetSize(-1, -1) = "trim to minimum"
                    kernel32.SetProcessWorkingSetSize(handle, -1, -1)
                    kernel32.CloseHandle(handle)
                    trimmed += 1
                else:
                    skipped += 1
        except Exception as e:
            logger.error(f"RAM optimization error: {e}")

    after = psutil.virtual_memory()
    freed = max(0, before.used - after.used)

    logger.log("optimize_ram", "optimizer",
               f"Trimmed {trimmed} processes, freed ~{freed} bytes", freed)
    return {
        "before_used":    before.used,
        "after_used":     after.used,
        "freed":          freed,
        "before_percent": before.percent,
        "after_percent":  after.percent,
        "trimmed_procs":  trimmed,
        "skipped_procs":  skipped,
    }

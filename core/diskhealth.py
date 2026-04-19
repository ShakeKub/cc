"""Disk health — physical disk info and SMART data via PowerShell/WMI."""

import json
import subprocess


def _ps(cmd: str, timeout: int = 20) -> str:
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=timeout,
        )
        return r.stdout.strip()
    except Exception:
        return ""


def get_physical_disks(logger=None) -> list[dict]:
    """Return basic info for every physical disk: model, type, health, size, bus."""
    raw = _ps(
        "Get-PhysicalDisk | "
        "Select-Object FriendlyName,MediaType,HealthStatus,OperationalStatus,Size,BusType | "
        "ConvertTo-Json -Compress"
    )
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        return [
            {
                "model":      d.get("FriendlyName", "Unknown"),
                "media_type": d.get("MediaType", "Unknown"),    # HDD / SSD / NVMe / Unspecified
                "health":     d.get("HealthStatus", "Unknown"), # Healthy / Warning / Unhealthy
                "status":     d.get("OperationalStatus", ""),
                "size":       int(d.get("Size") or 0),
                "bus":        d.get("BusType", ""),
            }
            for d in data
        ]
    except (json.JSONDecodeError, TypeError):
        return []


def get_smart_counters(logger=None) -> list[dict]:
    """
    Return SMART reliability counters per disk.
    Requires Storage cmdlets (Windows 8+).
    Fields: temperature (°C), wear (%), read/write errors, power-on hours.
    """
    raw = _ps(
        "Get-PhysicalDisk | Get-StorageReliabilityCounter -ErrorAction SilentlyContinue | "
        "Select-Object DeviceId,Temperature,Wear,"
        "ReadErrorsTotal,ReadErrorsCorrected,WriteErrorsTotal,"
        "PowerOnHours,StartStopCycleCount,LoadUnloadCycleCount | "
        "ConvertTo-Json -Compress",
        timeout=25,
    )
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        result = []
        for d in data:
            result.append({
                "device_id":     d.get("DeviceId", ""),
                "temperature":   d.get("Temperature"),          # °C, None if unavailable
                "wear":          d.get("Wear"),                 # 0-100 %, None if unavailable
                "read_errors":   int(d.get("ReadErrorsTotal") or 0),
                "read_corrected":int(d.get("ReadErrorsCorrected") or 0),
                "write_errors":  int(d.get("WriteErrorsTotal") or 0),
                "power_hours":   int(d.get("PowerOnHours") or 0),
                "start_stop":    int(d.get("StartStopCycleCount") or 0),
                "load_unload":   int(d.get("LoadUnloadCycleCount") or 0),
            })
        return result
    except (json.JSONDecodeError, TypeError):
        return []


def get_disk_partitions(logger=None) -> list[dict]:
    """Return logical disk (partition) info: drive letter, label, FS, free space."""
    raw = _ps(
        "Get-PSDrive -PSProvider FileSystem | "
        "Select-Object Name,Description,Used,Free | "
        "ConvertTo-Json -Compress"
    )
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        parts = []
        for d in data:
            used = int(d.get("Used") or 0)
            free = int(d.get("Free") or 0)
            total = used + free
            parts.append({
                "letter": d.get("Name", ""),
                "label":  d.get("Description", ""),
                "used":   used,
                "free":   free,
                "total":  total,
                "pct":    round(used / total * 100, 1) if total else 0,
            })
        return parts
    except (json.JSONDecodeError, TypeError):
        return []

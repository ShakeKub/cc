"""System Info Snapshot — collect hardware/OS details and export to file."""

import os
import platform
import subprocess
from datetime import datetime
from pathlib import Path
from core.logger import CleanerLogger


def _ps(script: str, timeout: int = 15) -> str:
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=timeout,
        )
        return r.stdout.strip()
    except Exception:
        return ""


def collect(logger: CleanerLogger) -> dict:
    """Gather a full system snapshot. Returns nested dict."""
    info: dict = {}

    # OS
    info["os"] = {
        "name":     platform.system(),
        "version":  platform.version(),
        "release":  platform.release(),
        "machine":  platform.machine(),
        "hostname": platform.node(),
        "username": os.environ.get("USERNAME", ""),
    }

    if os.name == "nt":
        info["os"]["edition"] = _ps(
            "(Get-WmiObject Win32_OperatingSystem).Caption"
        )
        info["os"]["build"] = _ps(
            "(Get-WmiObject Win32_OperatingSystem).BuildNumber"
        )
        info["os"]["install_date"] = _ps(
            "$d=(Get-WmiObject Win32_OperatingSystem).InstallDate; "
            "[Management.ManagementDateTimeConverter]::ToDateTime($d).ToString('yyyy-MM-dd')"
        )
        info["os"]["last_boot"] = _ps(
            "$d=(Get-WmiObject Win32_OperatingSystem).LastBootUpTime; "
            "[Management.ManagementDateTimeConverter]::ToDateTime($d).ToString('yyyy-MM-dd HH:mm')"
        )

    # CPU
    try:
        import psutil
        info["cpu"] = {
            "name":          _ps("(Get-WmiObject Win32_Processor).Name") if os.name == "nt" else platform.processor(),
            "physical_cores": psutil.cpu_count(logical=False),
            "logical_cores":  psutil.cpu_count(logical=True),
            "freq_mhz":      round(psutil.cpu_freq().current) if psutil.cpu_freq() else 0,
            "usage_pct":     psutil.cpu_percent(interval=1),
        }
    except Exception as e:
        info["cpu"] = {"error": str(e)}

    # RAM
    try:
        import psutil
        mem = psutil.virtual_memory()
        info["ram"] = {
            "total_gb":     round(mem.total / 1024**3, 1),
            "available_gb": round(mem.available / 1024**3, 1),
            "used_pct":     mem.percent,
        }
    except Exception as e:
        info["ram"] = {"error": str(e)}

    # GPU
    if os.name == "nt":
        gpu_out = _ps(
            "Get-WmiObject Win32_VideoController | "
            "Select-Object Name, AdapterRAM, DriverVersion | ConvertTo-Json -Compress"
        )
        try:
            import json
            gpus = json.loads(gpu_out)
            if isinstance(gpus, dict):
                gpus = [gpus]
            info["gpu"] = [
                {
                    "name":        g.get("Name", ""),
                    "vram_mb":     int(g.get("AdapterRAM") or 0) // 1024 // 1024,
                    "driver":      g.get("DriverVersion", ""),
                }
                for g in (gpus or [])
            ]
        except Exception:
            info["gpu"] = []

    # Disks
    try:
        import psutil
        disks = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disks.append({
                    "device":    part.device,
                    "mountpoint": part.mountpoint,
                    "fstype":    part.fstype,
                    "total_gb":  round(usage.total / 1024**3, 1),
                    "used_gb":   round(usage.used / 1024**3, 1),
                    "free_gb":   round(usage.free / 1024**3, 1),
                    "pct":       usage.percent,
                })
            except Exception:
                pass
        info["disks"] = disks
    except Exception as e:
        info["disks"] = [{"error": str(e)}]

    # Network adapters
    try:
        import psutil
        addrs = psutil.net_if_addrs()
        nets = []
        for iface, addr_list in addrs.items():
            ips = [a.address for a in addr_list if a.family.name in ("AF_INET", "AF_INET6")]
            if ips:
                nets.append({"interface": iface, "addresses": ips})
        info["network"] = nets
    except Exception as e:
        info["network"] = [{"error": str(e)}]

    # Installed RAM sticks (WMI)
    if os.name == "nt":
        sticks_out = _ps(
            "Get-WmiObject Win32_PhysicalMemory | "
            "Select-Object Manufacturer, Capacity, Speed | ConvertTo-Json -Compress"
        )
        try:
            import json
            sticks = json.loads(sticks_out)
            if isinstance(sticks, dict):
                sticks = [sticks]
            info["ram_sticks"] = [
                {
                    "manufacturer": s.get("Manufacturer", "").strip(),
                    "capacity_gb":  int(s.get("Capacity") or 0) // 1024**3,
                    "speed_mhz":    s.get("Speed", 0),
                }
                for s in (sticks or [])
            ]
        except Exception:
            info["ram_sticks"] = []

    logger.log("collect_sysinfo", "sysinfo", "System snapshot collected")
    return info


def export_to_file(info: dict, output_dir: str = ".", logger: CleanerLogger | None = None) -> str:
    """Write system info as a formatted text report. Returns file path."""
    lines = [
        f"System Info Snapshot — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
    ]

    def section(title: str, data: dict | list):
        lines.append(f"\n[{title}]")
        if isinstance(data, dict):
            for k, v in data.items():
                lines.append(f"  {k:<20} {v}")
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    lines.append("  " + "  |  ".join(f"{k}: {v}" for k, v in item.items()))
                else:
                    lines.append(f"  {item}")

    section("Operating System", info.get("os", {}))
    section("CPU", info.get("cpu", {}))
    section("RAM", info.get("ram", {}))
    if "ram_sticks" in info:
        section("RAM Modules", info["ram_sticks"])
    if "gpu" in info:
        section("GPU", info["gpu"])
    section("Disks", info.get("disks", []))
    section("Network", info.get("network", []))

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(output_dir) / f"sysinfo_{ts}.txt"
    try:
        out_path.write_text("\n".join(lines), encoding="utf-8")
        if logger:
            logger.log("export_sysinfo", "sysinfo", f"Exported to: {out_path}")
    except Exception as e:
        if logger:
            logger.error(f"export_to_file error: {e}")
    return str(out_path)

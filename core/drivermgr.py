"""Driver Manager — driverquery + WMI PnP signed driver listing."""

from __future__ import annotations
import subprocess
import csv
import io
from typing import Any


def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
        return r.returncode, r.stdout, r.stderr
    except FileNotFoundError:
        return -1, "", "command not found"
    except subprocess.TimeoutExpired:
        return -2, "", "timeout"
    except Exception as e:
        return -3, "", str(e)


def get_kernel_drivers(logger=None) -> list[dict[str, str]]:
    """Return kernel drivers via driverquery /FO CSV /V."""
    code, out, _ = _run(["driverquery", "/FO", "CSV", "/V"], timeout=30)
    if code != 0:
        return []
    results = []
    try:
        reader = csv.DictReader(io.StringIO(out))
        for row in reader:
            name = row.get("Module Name", row.get("Display Name", "")).strip()
            if not name:
                continue
            results.append({
                "name": name,
                "display": row.get("Display Name", "").strip(),
                "type": row.get("Driver Type", row.get("Type", "")).strip(),
                "state": row.get("State", "").strip(),
                "path": row.get("Link Date", "").strip(),
                "start": row.get("Start Mode", "").strip(),
            })
    except Exception:
        pass
    return results


def get_pnp_drivers(logger=None) -> list[dict[str, Any]]:
    """Return PnP signed drivers via WMI Win32_PnPSignedDriver."""
    try:
        import wmi
        c = wmi.WMI()
        results = []
        for drv in c.Win32_PnPSignedDriver():
            try:
                name = drv.DeviceName or drv.FriendlyName or ""
                if not name:
                    continue
                results.append({
                    "name": name.strip(),
                    "manufacturer": (drv.Manufacturer or "").strip(),
                    "driver_name": (drv.DriverName or "").strip(),
                    "driver_version": (drv.DriverVersion or "").strip(),
                    "driver_date": str(drv.DriverDate or "").strip()[:10],
                    "signed": bool(drv.IsSigned),
                    "inf_name": (drv.InfName or "").strip(),
                    "device_class": (drv.DeviceClass or "").strip(),
                })
            except Exception:
                continue
        results.sort(key=lambda d: d["name"].lower())
        return results
    except ImportError:
        return []
    except Exception:
        return []


def get_unsigned_drivers(logger=None) -> list[dict[str, Any]]:
    drivers = get_pnp_drivers(logger)
    return [d for d in drivers if not d.get("signed", True)]


def open_device_manager() -> bool:
    try:
        subprocess.Popen(["devmgmt.msc"], shell=True)
        return True
    except Exception:
        return False


def wmi_available() -> bool:
    try:
        import wmi
        return True
    except ImportError:
        return False

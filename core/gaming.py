"""MTA San Andreas spoofer — serial, cachechecksum, full HWID via WMI + registry."""

import hashlib
import json
import os
import re
import secrets
import shutil
import string
import subprocess
import uuid
from pathlib import Path
from typing import Any
from core.logger import CleanerLogger

# ── registry paths ────────────────────────────────────────────────────────────

_REG_SERIAL_PATHS = [
    ("HKCU Common", "HKCU", r"Software\Multi Theft Auto: San Andreas All\Common"),
    ("HKLM Common", "HKLM", r"SOFTWARE\Multi Theft Auto: San Andreas All\Common"),
    ("HKLM WOW64",  "HKLM", r"SOFTWARE\Wow6432Node\Multi Theft Auto: San Andreas All\Common"),
]
_SERIAL_VALUE = "Serial"

_REG_CHECKSUM_PATHS = [
    r"SOFTWARE\WOW6432Node\Multi Theft Auto: San Andreas All\1.6\Settings\general",
    r"SOFTWARE\WOW6432Node\Multi Theft Auto: San Andreas All\1.5\Settings\general",
    r"SOFTWARE\WOW6432Node\Multi Theft Auto: San Andreas All\1.4\Settings\general",
    r"SOFTWARE\Multi Theft Auto: San Andreas All\1.6\Settings\general",
    r"SOFTWARE\Multi Theft Auto: San Andreas All\1.5\Settings\general",
]
_CHECKSUM_VALUE = "cachechecksum"

_MTA_REG_BASE = r"Software\Multi Theft Auto: San Andreas All"

_GTA_SA_SERIAL_PATHS = [
    (r"SOFTWARE\WOW6432Node\Rockstar Games\GTA San Andreas", "Serial"),
    (r"SOFTWARE\Rockstar Games\GTA San Andreas",             "Serial"),
]

# AppData / install paths
_MTA_APPDATA_ROOT  = Path(os.environ.get("APPDATA",      "")) / "MTA San Andreas All"
_MTA_LOCAL_ROOT    = Path(os.environ.get("LOCALAPPDATA", "")) / "MTA San Andreas All"
_MTA_PROGDATA_ROOT = Path(os.environ.get("PROGRAMDATA",  r"C:\ProgramData")) / "MTA San Andreas All"
_MTA_INSTALL_PATHS = [
    Path(r"C:\Program Files\MTA San Andreas 1.6"),
    Path(r"C:\Program Files (x86)\MTA San Andreas 1.6"),
    Path(r"C:\Program Files\MTA San Andreas"),
    Path(r"C:\Program Files (x86)\MTA San Andreas"),
]

_SERIAL_BACKUP_FILE = Path(__file__).parent.parent / "mta_serial_backup.json"
_HWID_BACKUP_FILE   = Path(__file__).parent.parent / "mta_hwid_backup.json"

# Fake value pools used when spoofing system info
_FAKE_MANUFACTURERS = [
    "Dell Inc.", "HP", "Lenovo", "ASUS", "Acer",
    "MSI", "Gigabyte Technology Co., Ltd.", "ASRock",
]
_FAKE_BIOS_VENDORS = [
    "American Megatrends Inc.",
    "Phoenix Technologies Ltd.",
    "Award Software International, Inc.",
    "Insyde Corp.",
]
_FAKE_PRODUCTS = [
    "Inspiron 15 3000", "Pavilion Gaming 15", "IdeaPad 5",
    "ROG Strix G15", "Aspire 5", "MAG B550 TOMAHAWK",
    "B450 AORUS M", "Fatal1ty B450 Gaming K4",
]


def _wr():
    import winreg as _w
    return _w


def _wmi():
    import wmi as _wmi_mod
    return _wmi_mod.WMI()


# ── hardware info (WMI) ───────────────────────────────────────────────────────

def get_hardware_info() -> dict[str, Any]:
    """
    Read all hardware identifiers via WMI.
    Returns a nested dict with disks, bios, motherboard, cpu, gpu, system.
    Falls back gracefully if wmi is not installed.
    """
    info: dict[str, Any] = {}
    try:
        c = _wmi()

        # Disks
        info["disks"] = []
        for disk in c.Win32_DiskDrive():
            info["disks"].append({
                "model":      (disk.Model or "").strip(),
                "serial":     (disk.SerialNumber or "").strip(),
                "size_gb":    round(int(disk.Size or 0) / 1_073_741_824, 1),
                "interface":  (disk.InterfaceType or "").strip(),
            })

        # BIOS
        for bios in c.Win32_BIOS():
            info["bios"] = {
                "manufacturer":  (bios.Manufacturer or "").strip(),
                "version":       (bios.Version or "").strip(),
                "serial":        (bios.SerialNumber or "").strip(),
                "release_date":  (bios.ReleaseDate or "").strip(),
            }
            break

        # Motherboard / baseboard
        for mb in c.Win32_BaseBoard():
            info["motherboard"] = {
                "manufacturer": (mb.Manufacturer or "").strip(),
                "product":      (mb.Product or "").strip(),
                "serial":       (mb.SerialNumber or "").strip(),
                "version":      (mb.Version or "").strip(),
            }
            break

        # CPU
        for cpu in c.Win32_Processor():
            info["cpu"] = {
                "name":          (cpu.Name or "").strip(),
                "processor_id":  (cpu.ProcessorId or "").strip(),
                "cores":         cpu.NumberOfCores,
                "manufacturer":  (cpu.Manufacturer or "").strip(),
            }
            break

        # GPU(s)
        info["gpus"] = []
        for gpu in c.Win32_VideoController():
            info["gpus"].append({
                "name":           (gpu.Name or "").strip(),
                "driver_version": (gpu.DriverVersion or "").strip(),
                "adapter_ram":    gpu.AdapterRAM,
            })

        # System product (UUID, vendor)
        for sp in c.Win32_ComputerSystemProduct():
            info["system_product"] = {
                "uuid":               (sp.UUID or "").strip(),
                "vendor":             (sp.Vendor or "").strip(),
                "name":               (sp.Name or "").strip(),
                "identifying_number": (sp.IdentifyingNumber or "").strip(),
            }
            break

        # Network adapters (MAC addresses)
        info["network_adapters"] = []
        for nic in c.Win32_NetworkAdapter(PhysicalAdapter=True):
            info["network_adapters"].append({
                "name":        (nic.Name or "").strip(),
                "mac_address": (nic.MACAddress or "").strip(),
                "adapter_type":(nic.AdapterType or "").strip(),
            })

    except ImportError:
        info["error"] = "wmi library not installed — run: pip install wmi pywin32"
    except Exception as e:
        info["error"] = str(e)

    return info


# ── process / install discovery ──────────────────────────────────────────────

def kill_mta_processes() -> list[dict]:
    """Kill all running MTA / GTA processes before writing registry. Returns killed list."""
    try:
        import psutil
    except ImportError:
        return []
    killed = []
    keywords = ("mta", "multi theft auto", "gta_sa", "gta-sa", "gta san andreas")
    for proc in psutil.process_iter(["pid", "name", "exe"]):
        try:
            name = proc.info["name"] or ""
            exe  = proc.info["exe"]  or ""
            if any(k in name.lower() or k in exe.lower() for k in keywords):
                proc.kill()
                killed.append({"pid": proc.info["pid"], "name": name})
        except Exception:
            pass
    return killed


def find_mta_processes() -> list[dict]:
    try:
        import psutil
    except ImportError:
        return []
    procs = []
    keywords = ("mta", "multi theft auto", "gta_sa", "gta-sa")
    for proc in psutil.process_iter(["pid", "name", "exe"]):
        try:
            name = proc.info["name"] or ""
            exe  = proc.info["exe"]  or ""
            if any(k in name.lower() or k in exe.lower() for k in keywords):
                procs.append({"pid": proc.info["pid"], "name": name, "exe": exe})
        except Exception:
            pass
    return procs


def get_mta_install_dir() -> str:
    for p in _MTA_INSTALL_PATHS:
        if p.is_dir():
            return str(p)
    return ""


# ── cachechecksum (primary MTA serial mechanism) ──────────────────────────────
#
# Research source: wiki.multitheftauto.com/wiki/Serial + cheater forum post.
#
# MTA stores a "cachechecksum" in:
#   HKLM\SOFTWARE\WOW6432Node\MTA San Andreas All\{ver}\Settings\general
# Format of the stored value:
#   MD5(checksum)[:16]  +  checksum  +  MD5(checksum)[16:]
# Checksum structure:
#   8 chars  +  ":"  +  17 chars  +  ":"  +  5 chars
#   chars from {1-9, B-G}   (decrement by 1 → valid hex 0-8, A-F; ":" → "9")
# Visible serial = each char decremented by 1, ":" replaced by "9".

_CHECKSUM_CHARSET = "123456789BCDEFG"


def _checksum_to_serial(checksum: str) -> str:
    return "".join("9" if c == ":" else chr(ord(c) - 1) for c in checksum)


def generate_cachechecksum() -> tuple[str, str, str]:
    """Returns (checksum, derived_serial, full_registry_value)."""
    def _rand(n: int) -> str:
        return "".join(secrets.choice(_CHECKSUM_CHARSET) for _ in range(n))
    checksum = _rand(8) + ":" + _rand(17) + ":" + _rand(5)
    serial   = _checksum_to_serial(checksum)
    md5      = hashlib.md5(checksum.encode()).hexdigest().upper()
    return checksum, serial, md5[:16] + checksum + md5[16:]


def read_cachechecksum() -> dict[str, str]:
    if os.name != "nt":
        return {}
    w = _wr()
    results: dict[str, str] = {}
    for path in _REG_CHECKSUM_PATHS:
        try:
            with w.OpenKey(w.HKEY_LOCAL_MACHINE, path) as key:
                val, _ = w.QueryValueEx(key, _CHECKSUM_VALUE)
                results[path.split("\\")[4]] = str(val)
        except OSError:
            pass
    return results


def write_cachechecksum(full_value: str, logger: CleanerLogger) -> dict[str, bool]:
    if os.name != "nt":
        return {}
    w = _wr()
    results: dict[str, bool] = {}
    for path in _REG_CHECKSUM_PATHS:
        label = path.split("\\")[4]
        try:
            with w.CreateKey(w.HKEY_LOCAL_MACHINE, path) as key:
                w.SetValueEx(key, _CHECKSUM_VALUE, 0, w.REG_SZ, full_value)
            results[label] = True
        except OSError as e:
            results[label] = False
            logger.error(f"write_cachechecksum {label}: {e}")
    return results


def delete_cachechecksum(logger: CleanerLogger) -> list[str]:
    if os.name != "nt":
        return []
    w = _wr()
    deleted = []
    for path in _REG_CHECKSUM_PATHS:
        try:
            with w.OpenKey(w.HKEY_LOCAL_MACHINE, path, 0, w.KEY_SET_VALUE) as key:
                w.DeleteValue(key, _CHECKSUM_VALUE)
            deleted.append(path.split("\\")[4])
        except OSError:
            pass
    return deleted


# ── direct serial read / write ────────────────────────────────────────────────

def read_serial_registry() -> dict[str, str]:
    if os.name != "nt":
        return {}
    w = _wr()
    results: dict[str, str] = {}
    for label, hive_str, path in _REG_SERIAL_PATHS:
        hive = w.HKEY_CURRENT_USER if hive_str == "HKCU" else w.HKEY_LOCAL_MACHINE
        try:
            with w.OpenKey(hive, path) as key:
                val, _ = w.QueryValueEx(key, _SERIAL_VALUE)
                results[label] = str(val)
        except OSError:
            results[label] = "(not found)"
    return results


def write_serial_registry(serial: str, logger: CleanerLogger) -> dict[str, bool]:
    if os.name != "nt":
        return {}
    w = _wr()
    results: dict[str, bool] = {}
    for label, hive_str, path in _REG_SERIAL_PATHS:
        hive = w.HKEY_CURRENT_USER if hive_str == "HKCU" else w.HKEY_LOCAL_MACHINE
        try:
            with w.CreateKey(hive, path) as key:
                w.SetValueEx(key, _SERIAL_VALUE, 0, w.REG_SZ, serial)
            results[label] = True
            logger.log("mta_serial_write", "gaming", f"{label} → {serial}")
        except OSError as e:
            results[label] = False
            logger.error(f"write_serial_registry {label}: {e}")
    return results


def backup_serial(logger: CleanerLogger) -> bool:
    current = read_serial_registry()
    try:
        _SERIAL_BACKUP_FILE.write_text(json.dumps(current, indent=2), encoding="utf-8")
        return True
    except OSError as e:
        logger.error(f"backup_serial: {e}"); return False


def restore_serial(logger: CleanerLogger) -> dict[str, Any]:
    if not _SERIAL_BACKUP_FILE.exists():
        return {"ok": False, "error": "No backup file found."}
    try:
        saved = json.loads(_SERIAL_BACKUP_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return {"ok": False, "error": str(e)}
    if os.name != "nt":
        return {"ok": False, "error": "Windows only."}
    w = _wr()
    restored, errors = [], []
    for label, hive_str, path in _REG_SERIAL_PATHS:
        serial = saved.get(label)
        if not serial or serial == "(not found)":
            continue
        hive = w.HKEY_CURRENT_USER if hive_str == "HKCU" else w.HKEY_LOCAL_MACHINE
        try:
            with w.CreateKey(hive, path) as key:
                w.SetValueEx(key, _SERIAL_VALUE, 0, w.REG_SZ, serial)
            restored.append(f"{label} → {serial}")
        except OSError as e:
            errors.append(f"{label}: {e}")
    return {"ok": bool(restored), "restored": restored, "errors": errors}


def serial_backup_exists() -> bool:
    return _SERIAL_BACKUP_FILE.exists()


def generate_mta_serial() -> str:
    return secrets.token_hex(16).upper()


def read_gta_sa_serial() -> dict[str, str]:
    """Read GTA:SA CD key from registry."""
    if os.name != "nt":
        return {}
    w = _wr()
    results: dict[str, str] = {}
    for path, value in _GTA_SA_SERIAL_PATHS:
        label = path.split("\\")[-1]
        try:
            with w.OpenKey(w.HKEY_LOCAL_MACHINE, path) as key:
                val, _ = w.QueryValueEx(key, value)
                results[label] = str(val)
        except OSError:
            results[label] = "(not found)"
    return results


def _spoof_gta_sa_serial(w, logger: CleanerLogger) -> dict[str, Any]:
    """Write a random 32-char hex serial to GTA:SA registry keys."""
    new_serial = secrets.token_hex(16).upper()
    changed: dict[str, str] = {}
    original: dict[str, str] = {}
    for path, value in _GTA_SA_SERIAL_PATHS:
        label = path.split("\\")[-1]
        try:
            with w.OpenKey(w.HKEY_LOCAL_MACHINE, path) as rk:
                try:
                    old_val, _ = w.QueryValueEx(rk, value)
                    original[label] = str(old_val)
                except OSError:
                    original[label] = "(not found)"
        except OSError:
            original[label] = "(key missing)"
        try:
            with w.OpenKey(w.HKEY_LOCAL_MACHINE, path, 0, w.KEY_SET_VALUE) as wk:
                w.SetValueEx(wk, value, 0, w.REG_SZ, new_serial)
            changed[label] = new_serial
            logger.log("gta_sa_serial", "gaming", f"GTA:SA Serial → {new_serial}")
        except OSError:
            pass   # key absent = GTA:SA not installed; silently skip
    return {"new": new_serial, "changed": changed, "original": original}


def spoof_serial(logger: CleanerLogger) -> dict[str, Any]:
    """Kill MTA/GTA → generate new cachechecksum → write → derive + write Serial."""
    killed        = kill_mta_processes()
    old_serials   = read_serial_registry()
    checksum, serial, full_val = generate_cachechecksum()
    backup_serial(logger)
    checksum_results = write_cachechecksum(full_val, logger)
    serial_results   = write_serial_registry(serial, logger)
    logger.log("mta_spoof", "gaming", f"New serial: {serial}")
    return {
        "killed":           killed,
        "old_serials":      old_serials,
        "checksum":         checksum,
        "serial":           serial,
        "full_value":       full_val,
        "checksum_results": checksum_results,
        "serial_results":   serial_results,
    }


# ── individual HWID spoof helpers ─────────────────────────────────────────────

def _spoof_os_identifiers(w, logger: CleanerLogger) -> dict[str, str]:
    """Change MachineGuid, HwProfileGuid, MachineId, ProductId."""
    changed: dict[str, str] = {}
    writes = [
        (r"SOFTWARE\Microsoft\Cryptography",
         "MachineGuid",   str(uuid.uuid4()),
         w.KEY_SET_VALUE | w.KEY_WOW64_64KEY),
        (r"SYSTEM\CurrentControlSet\Control\IDConfigDB\Hardware Profiles\0001",
         "HwProfileGuid", "{" + str(uuid.uuid4()).upper() + "}",
         w.KEY_SET_VALUE),
        (r"SOFTWARE\Microsoft\SQMClient",
         "MachineId",     "{" + str(uuid.uuid4()).upper() + "}",
         w.KEY_SET_VALUE),
        (r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
         "ProductId",     "-".join(
             "".join(str(secrets.randbelow(10)) for _ in range(5))
             for _ in range(4)),
         w.KEY_SET_VALUE),
    ]
    for key_path, value_name, new_val, flags in writes:
        try:
            with w.OpenKey(w.HKEY_LOCAL_MACHINE, key_path, 0, flags) as key:
                w.SetValueEx(key, value_name, 0, w.REG_SZ, new_val)
            changed[value_name] = new_val
            logger.log("skimo_os_id", "gaming", f"{value_name} → {new_val}")
        except OSError as e:
            logger.error(f"_spoof_os_identifiers {value_name}: {e}")
    return changed


def _spoof_bios_system_info(w, logger: CleanerLogger) -> dict[str, str]:
    """
    Randomise BIOS / system-info strings in the SystemInformation registry key.
    This is what many applications read as "motherboard / BIOS manufacturer".
    """
    changed: dict[str, str] = {}
    mfr     = secrets.choice(_FAKE_MANUFACTURERS)
    bios_v  = secrets.choice(_FAKE_BIOS_VENDORS)
    product = secrets.choice(_FAKE_PRODUCTS)
    ver_num = f"F{secrets.randbelow(30) + 1:02d}"

    sys_info_path = r"SYSTEM\CurrentControlSet\Control\SystemInformation"
    writes = {
        "SystemManufacturer":  mfr,
        "SystemProductName":   product,
        "SystemFamily":        "To Be Filled By O.E.M.",
        "SystemVersion":       "To Be Filled By O.E.M.",
        "SystemSKU":           "To Be Filled By O.E.M.",
        "BIOSVendor":          bios_v,
        "BIOSVersion":         ver_num,
        "BIOSReleaseDate":     f"{''.join(str(secrets.randbelow(10)) for _ in range(8))}",
    }
    try:
        with w.OpenKey(w.HKEY_LOCAL_MACHINE, sys_info_path, 0, w.KEY_SET_VALUE) as key:
            for name, val in writes.items():
                try:
                    w.SetValueEx(key, name, 0, w.REG_SZ, val)
                    changed[name] = val
                except OSError as e:
                    logger.error(f"_spoof_bios_system_info {name}: {e}")
    except OSError as e:
        logger.error(f"_spoof_bios_system_info: {e}")
    return changed


def _spoof_computer_name(w, logger: CleanerLogger) -> str:
    """Change computer name in registry (takes effect after reboot)."""
    prefix   = secrets.choice(["DESKTOP", "LAPTOP", "PC", "WORKSTATION"])
    suffix   = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(7))
    new_name = f"{prefix}-{suffix}"
    for path in (
        r"SYSTEM\CurrentControlSet\Control\ComputerName\ComputerName",
        r"SYSTEM\CurrentControlSet\Control\ComputerName\ActiveComputerName",
    ):
        try:
            with w.OpenKey(w.HKEY_LOCAL_MACHINE, path, 0, w.KEY_SET_VALUE) as key:
                w.SetValueEx(key, "ComputerName", 0, w.REG_SZ, new_name)
        except OSError as e:
            logger.error(f"_spoof_computer_name {path}: {e}")
    logger.log("skimo_name", "gaming", f"ComputerName → {new_name}")
    return new_name


def _spoof_gpu_driver_desc(w, logger: CleanerLogger) -> dict[str, str]:
    """
    Randomise GPU driver description strings in display driver registry keys.
    Changes what software reads as GPU name via registry (not DXGI/WMI hardware query).
    """
    changed: dict[str, str] = {}
    fake_gpus = [
        "NVIDIA GeForce GTX 1660 Super",
        "NVIDIA GeForce RTX 2060",
        "NVIDIA GeForce RTX 3060 Ti",
        "AMD Radeon RX 5700 XT",
        "AMD Radeon RX 6600",
        "Intel(R) UHD Graphics 630",
    ]
    new_gpu = secrets.choice(fake_gpus)
    video_base = r"SYSTEM\CurrentControlSet\Control\Class\{4D36E968-E325-11CE-BFC1-08002BE10318}"
    try:
        with w.OpenKey(w.HKEY_LOCAL_MACHINE, video_base) as base:
            i = 0
            while True:
                try:
                    sub = w.EnumKey(base, i); i += 1
                    if not sub.isdigit():
                        continue
                    sub_path = f"{video_base}\\{sub}"
                    with w.OpenKey(w.HKEY_LOCAL_MACHINE, sub_path, 0, w.KEY_SET_VALUE) as sk:
                        for field in ("DriverDesc", "Device Description"):
                            try:
                                w.SetValueEx(sk, field, 0, w.REG_SZ, new_gpu)
                                changed[f"GPU[{sub}].{field}"] = new_gpu
                            except OSError:
                                pass
                except OSError:
                    break
    except OSError as e:
        logger.error(f"_spoof_gpu_driver_desc: {e}")
    logger.log("skimo_gpu", "gaming", f"GPU desc → {new_gpu}")
    return changed


def _spoof_mac_addresses(w, logger: CleanerLogger) -> dict[str, str]:
    """Write random locally-administered MAC addresses to all NIC driver keys."""
    changed: dict[str, str] = {}
    nic_base = r"SYSTEM\CurrentControlSet\Control\Class\{4D36E972-E325-11CE-BFC1-08002BE10318}"

    def _rand_mac() -> str:
        raw = [secrets.randbelow(256) for _ in range(6)]
        raw[0] = (raw[0] & 0xFE) | 0x02   # locally administered, unicast
        return "".join(f"{b:02X}" for b in raw)

    try:
        with w.OpenKey(w.HKEY_LOCAL_MACHINE, nic_base) as base:
            i = 0
            while True:
                try:
                    sub = w.EnumKey(base, i); i += 1
                    if not sub.isdigit():
                        continue
                    mac = _rand_mac()
                    with w.OpenKey(w.HKEY_LOCAL_MACHINE, f"{nic_base}\\{sub}",
                                   0, w.KEY_SET_VALUE) as sk:
                        w.SetValueEx(sk, "NetworkAddress", 0, w.REG_SZ, mac)
                    changed[sub] = mac
                    logger.log("skimo_mac", "gaming", f"NIC {sub} → {mac}")
                except OSError:
                    break
    except OSError as e:
        logger.error(f"_spoof_mac_addresses: {e}")
    return changed


def _spoof_install_id(w, logger: CleanerLogger) -> dict[str, str]:
    """Randomise additional Windows install / telemetry identifiers."""
    changed: dict[str, str] = {}
    rand_guid = "{" + str(uuid.uuid4()).upper() + "}"
    rand_hex  = secrets.token_hex(16).upper()

    targets = [
        (r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
         "InstallDate", str(secrets.randbelow(2**31)), w.REG_DWORD),
        (r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\DigitalProductId",
         None, None, None),   # skip — binary blob, too risky to corrupt
        (r"SOFTWARE\Microsoft\Provisioning\OMADM\Logger",
         "DeviceClientId", rand_guid, w.REG_SZ),
        (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Diagnostics\DiagTrack",
         "DiagTrackLocalDeviceId", rand_guid, w.REG_SZ),
    ]
    for key_path, value_name, new_val, reg_type in targets:
        if value_name is None:
            continue
        try:
            with w.OpenKey(w.HKEY_LOCAL_MACHINE, key_path, 0, w.KEY_SET_VALUE) as key:
                w.SetValueEx(key, value_name, 0, reg_type, new_val)
            changed[value_name] = str(new_val)
            logger.log("skimo_install_id", "gaming", f"{value_name} → {new_val}")
        except OSError:
            pass   # key may not exist on all systems
    return changed


# ── backup helpers ────────────────────────────────────────────────────────────

def _read_os_originals(w) -> dict[str, str]:
    originals: dict[str, str] = {}
    reads = [
        (r"SOFTWARE\Microsoft\Cryptography",          "MachineGuid",   w.KEY_READ | w.KEY_WOW64_64KEY),
        (r"SYSTEM\CurrentControlSet\Control\IDConfigDB\Hardware Profiles\0001",
                                                       "HwProfileGuid", w.KEY_READ),
        (r"SOFTWARE\Microsoft\SQMClient",             "MachineId",     w.KEY_READ),
        (r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "ProductId", w.KEY_READ),
        (r"SYSTEM\CurrentControlSet\Control\SystemInformation", "SystemManufacturer", w.KEY_READ),
        (r"SYSTEM\CurrentControlSet\Control\SystemInformation", "SystemProductName",  w.KEY_READ),
        (r"SYSTEM\CurrentControlSet\Control\SystemInformation", "BIOSVendor",         w.KEY_READ),
        (r"SYSTEM\CurrentControlSet\Control\SystemInformation", "BIOSVersion",        w.KEY_READ),
        (r"SYSTEM\CurrentControlSet\Control\ComputerName\ComputerName", "ComputerName", w.KEY_READ),
    ]
    for key_path, value_name, flags in reads:
        try:
            with w.OpenKey(w.HKEY_LOCAL_MACHINE, key_path, 0, flags) as key:
                val, _ = w.QueryValueEx(key, value_name)
                originals[value_name] = str(val)
        except OSError:
            pass
    return originals


def _read_mac_originals(w) -> dict[str, str]:
    originals: dict[str, str] = {}
    nic_base = r"SYSTEM\CurrentControlSet\Control\Class\{4D36E972-E325-11CE-BFC1-08002BE10318}"
    try:
        with w.OpenKey(w.HKEY_LOCAL_MACHINE, nic_base) as base:
            i = 0
            while True:
                try:
                    sub = w.EnumKey(base, i); i += 1
                    if not sub.isdigit():
                        continue
                    with w.OpenKey(w.HKEY_LOCAL_MACHINE, f"{nic_base}\\{sub}") as sk:
                        try:
                            val, _ = w.QueryValueEx(sk, "NetworkAddress")
                            originals[sub] = str(val)
                        except OSError:
                            originals[sub] = ""
                except OSError:
                    break
    except OSError:
        pass
    return originals


# ── HrajemeSkimoRP — full identity reset ─────────────────────────────────────

def hrajeme_skimo_rp(logger: CleanerLogger) -> dict[str, Any]:
    """
    Full identity reset using only Python built-ins + wmi (no kernel drivers):

    Registry-based (winreg):
      MachineGuid, HwProfileGuid, MachineId, ProductId,
      BIOS / system info strings (SystemManufacturer, BIOSVendor, …),
      Computer name, GPU driver description strings,
      MAC addresses (NIC NetworkAddress), install/telemetry IDs

    MTA-specific:
      cachechecksum → derived Serial in all Common keys

    Cleanup:
      MTA cache + logs, DNS flush, Winsock reset
    """
    if os.name != "nt":
        return {"ok": False, "error": "Windows only."}

    # ── kill MTA/GTA before touching any registry values ─────────────────────
    killed = kill_mta_processes()

    w = _wr()
    report: dict[str, Any] = {
        "killed":      killed,
        "os_ids":      {},
        "bios_info":   {},
        "computer":    "",
        "gpu":         {},
        "mac":         {},
        "install_ids": {},
        "gta_sa":      {},
        "serial":      {},
        "cache":       {},
        "network":     [],
        "errors":      [],
    }

    # ── back up everything first ──────────────────────────────────────────────
    backup = _read_os_originals(w)
    backup["_mac"]        = _read_mac_originals(w)
    backup["_serial"]     = read_serial_registry()
    backup["_gta_serial"] = read_gta_sa_serial()
    try:
        _HWID_BACKUP_FILE.write_text(json.dumps(backup, indent=2), encoding="utf-8")
        report["backup_saved"] = True
        logger.log("skimo_backup", "gaming", f"Backup saved to {_HWID_BACKUP_FILE}")
    except OSError as e:
        report["backup_saved"] = False
        report["errors"].append(f"backup write: {e}")

    # ── spoof each layer ──────────────────────────────────────────────────────
    report["os_ids"]      = _spoof_os_identifiers(w, logger)
    report["bios_info"]   = _spoof_bios_system_info(w, logger)
    report["computer"]    = _spoof_computer_name(w, logger)
    report["gpu"]         = _spoof_gpu_driver_desc(w, logger)
    report["mac"]         = _spoof_mac_addresses(w, logger)
    report["install_ids"] = _spoof_install_id(w, logger)
    report["gta_sa"]      = _spoof_gta_sa_serial(w, logger)

    # ── MTA serial via cachechecksum ──────────────────────────────────────────
    spoof = spoof_serial(logger)
    report["serial"] = {
        "serial":   spoof["serial"],
        "checksum": spoof["checksum"],
        "written":  spoof["serial_results"],
    }

    # ── clean MTA cache + network ─────────────────────────────────────────────
    report["cache"]   = clean_mta_cache(logger)
    report["network"] = reset_network({"dns": True, "winsock": True}, logger)

    logger.log("skimo_done", "gaming", "HrajemeSkimoRP complete")
    return report


def hrajeme_backup_exists() -> bool:
    return _HWID_BACKUP_FILE.exists()


def restore_hrajeme(logger: CleanerLogger) -> dict[str, Any]:
    """Restore all values backed up by hrajeme_skimo_rp."""
    if not _HWID_BACKUP_FILE.exists():
        return {"ok": False, "error": "No backup found."}
    try:
        saved = json.loads(_HWID_BACKUP_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return {"ok": False, "error": str(e)}
    if os.name != "nt":
        return {"ok": False, "error": "Windows only."}

    w = _wr()
    restored, errors = [], []

    # OS identifiers
    os_restore = [
        (r"SOFTWARE\Microsoft\Cryptography",          "MachineGuid",   w.KEY_SET_VALUE | w.KEY_WOW64_64KEY),
        (r"SYSTEM\CurrentControlSet\Control\IDConfigDB\Hardware Profiles\0001",
                                                       "HwProfileGuid", w.KEY_SET_VALUE),
        (r"SOFTWARE\Microsoft\SQMClient",             "MachineId",     w.KEY_SET_VALUE),
        (r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "ProductId", w.KEY_SET_VALUE),
    ]
    for key_path, value_name, flags in os_restore:
        val = saved.get(value_name)
        if not val:
            continue
        try:
            with w.OpenKey(w.HKEY_LOCAL_MACHINE, key_path, 0, flags) as key:
                w.SetValueEx(key, value_name, 0, w.REG_SZ, val)
            restored.append(f"{value_name} restored")
        except OSError as e:
            errors.append(f"{value_name}: {e}")

    # BIOS / system info
    sys_info_path = r"SYSTEM\CurrentControlSet\Control\SystemInformation"
    for field in ("SystemManufacturer", "SystemProductName", "BIOSVendor", "BIOSVersion"):
        val = saved.get(field)
        if not val:
            continue
        try:
            with w.OpenKey(w.HKEY_LOCAL_MACHINE, sys_info_path, 0, w.KEY_SET_VALUE) as key:
                w.SetValueEx(key, field, 0, w.REG_SZ, val)
            restored.append(f"{field} restored")
        except OSError as e:
            errors.append(f"{field}: {e}")

    # Computer name
    cn = saved.get("ComputerName")
    if cn:
        for path in (
            r"SYSTEM\CurrentControlSet\Control\ComputerName\ComputerName",
            r"SYSTEM\CurrentControlSet\Control\ComputerName\ActiveComputerName",
        ):
            try:
                with w.OpenKey(w.HKEY_LOCAL_MACHINE, path, 0, w.KEY_SET_VALUE) as key:
                    w.SetValueEx(key, "ComputerName", 0, w.REG_SZ, cn)
            except OSError:
                pass
        restored.append(f"ComputerName → {cn}")

    # MAC addresses
    nic_base = r"SYSTEM\CurrentControlSet\Control\Class\{4D36E972-E325-11CE-BFC1-08002BE10318}"
    for sub, original_mac in saved.get("_mac", {}).items():
        try:
            with w.OpenKey(w.HKEY_LOCAL_MACHINE, f"{nic_base}\\{sub}",
                           0, w.KEY_SET_VALUE) as sk:
                if original_mac:
                    w.SetValueEx(sk, "NetworkAddress", 0, w.REG_SZ, original_mac)
                else:
                    try: w.DeleteValue(sk, "NetworkAddress")
                    except OSError: pass
            restored.append(f"NIC {sub} MAC restored")
        except OSError as e:
            errors.append(f"NIC {sub}: {e}")

    # GTA:SA serial
    for path, value in _GTA_SA_SERIAL_PATHS:
        label = path.split("\\")[-1]
        orig = saved.get("_gta_serial", {}).get(label, "")
        if not orig or orig.startswith("("):
            continue
        try:
            with w.OpenKey(w.HKEY_LOCAL_MACHINE, path, 0, w.KEY_SET_VALUE) as key:
                w.SetValueEx(key, value, 0, w.REG_SZ, orig)
            restored.append(f"GTA:SA Serial restored → {orig}")
        except OSError as e:
            errors.append(f"GTA:SA Serial {label}: {e}")

    # MTA serial
    serial_result = restore_serial(logger)
    if serial_result.get("ok"):
        restored.extend(serial_result.get("restored", []))

    return {"ok": bool(restored), "restored": restored, "errors": errors}


# ── MTA cache cleaning ────────────────────────────────────────────────────────

def get_mta_cache_targets() -> list[tuple[str, str]]:
    targets: list[tuple[str, str]] = []

    def _scan(root: Path, label: str):
        if not root.exists():
            return
        for version_dir in sorted(root.iterdir()):
            if not version_dir.is_dir():
                continue
            vname = version_dir.name
            for sub in ("logs", "report", "resource-cache", "http-client-files", "cache"):
                p = version_dir / sub
                if p.is_dir():
                    targets.append((f"{label} {sub} ({vname})", str(p)))
            # config dir — stores server history, coreconfig, guiconfig (identity info)
            config_dir = version_dir / "config"
            if config_dir.is_dir():
                targets.append((f"{label} config ({vname})", str(config_dir)))
            # root-level .set and .xml identity files
            for fname in version_dir.iterdir():
                if fname.is_file() and fname.suffix in (".set", ".xml", ".db"):
                    targets.append((f"{label} {fname.name} ({vname})", str(fname)))
            gta_dir = version_dir / "GTA San Andreas"
            if gta_dir.is_dir():
                for fname in ("gta_sa.set", "gta_sa.sav"):
                    fp = gta_dir / fname
                    if fp.is_file():
                        targets.append((f"GTA SA {fname} ({vname})", str(fp)))

    _scan(_MTA_APPDATA_ROOT, "AppData")
    _scan(_MTA_LOCAL_ROOT,   "LocalAppData")
    install = get_mta_install_dir()
    if install:
        for rel in (r"MTA\logs", r"server\logs", r"server\mods\deathmatch\logs"):
            p = Path(install) / rel
            if p.is_dir():
                targets.append((f"Install {rel}", str(p)))
    return targets


def clean_mta_cache(logger: CleanerLogger) -> dict[str, Any]:
    targets = get_mta_cache_targets()
    cleaned = skipped = 0
    errors: list[str] = []
    for desc, path in targets:
        p = Path(path)
        if not p.exists():
            skipped += 1; continue
        try:
            shutil.rmtree(p) if p.is_dir() else p.unlink()
            cleaned += 1
            logger.log("mta_cache_clean", "gaming", f"Removed: {path}")
        except OSError as e:
            errors.append(f"{desc}: {e}")
    return {"targets": len(targets), "cleaned": cleaned, "skipped": skipped, "errors": errors}


# ── network reset ─────────────────────────────────────────────────────────────

def reset_network(options: dict, logger: CleanerLogger) -> list[tuple[str, bool, str]]:
    cmds = []
    if options.get("dns"):     cmds.append(("Flush DNS",     "ipconfig /flushdns"))
    if options.get("winsock"): cmds.append(("Reset Winsock", "netsh winsock reset"))
    if options.get("tcpip"):   cmds.append(("Reset TCP/IP",  "netsh int ip reset"))
    results = []
    for desc, cmd in cmds:
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
            out = (r.stdout + r.stderr).strip()
            results.append((desc, r.returncode == 0, out))
            logger.log("mta_net_reset", "gaming", f"{desc}: {'ok' if r.returncode==0 else 'fail'}")
        except Exception as e:
            results.append((desc, False, str(e)))
    return results


# ── all-in-one (serial + cache + DNS) ────────────────────────────────────────

def full_reset(logger: CleanerLogger) -> dict[str, Any]:
    spoof   = spoof_serial(logger)
    cache   = clean_mta_cache(logger)
    network = reset_network({"dns": True}, logger)
    return {"serial": spoof["serial"], "spoof": spoof, "cache": cache, "network": network}


# ── diagnostics ──────────────────────────────────────────────────────────────

def mta_diagnostics() -> dict[str, Any]:
    diag: dict[str, Any] = {}
    diag["serial_registry"] = read_serial_registry()
    diag["cachechecksum"]   = read_cachechecksum()
    diag["hardware"]        = get_hardware_info()
    diag["registry"] = {}
    if os.name == "nt":
        w = _wr()

        def _dump(hive, path: str) -> dict:
            res: dict[str, Any] = {"_values": {}, "_subkeys": {}}
            for flags in (w.KEY_READ, w.KEY_READ | w.KEY_WOW64_32KEY):
                try:
                    key = w.OpenKey(hive, path, 0, flags)
                except OSError:
                    continue
                vi = 0
                while True:
                    try:
                        vn, vd, _ = w.EnumValue(key, vi); vi += 1
                        res["_values"][vn] = str(vd)
                    except OSError:
                        break
                ki = 0
                while True:
                    try:
                        sub = w.EnumKey(key, ki); ki += 1
                        res["_subkeys"][sub] = _dump(hive, f"{path}\\{sub}")
                    except OSError:
                        break
                w.CloseKey(key)
                break
            return res

        for hive, hname in ((w.HKEY_CURRENT_USER, "HKCU"),
                            (w.HKEY_LOCAL_MACHINE, "HKLM")):
            try:
                w.OpenKey(hive, _MTA_REG_BASE, 0, w.KEY_READ)
                diag["registry"][f"{hname}\\{_MTA_REG_BASE}"] = _dump(hive, _MTA_REG_BASE)
            except OSError:
                diag["registry"][f"{hname}\\{_MTA_REG_BASE}"] = "(not found)"

    diag["cache_targets"] = get_mta_cache_targets()
    return diag

"""History Manager — selective deletion of system activity records.

Covers three categories (Windows-only):
  - Network / internet connection history  (NetworkList registry)
  - USB & external storage device history  (USBSTOR registry)
  - Application launch history             (UserAssist, RecentDocs, RunMRU)

All public functions return plain dicts so the TUI can display and act on them
without any coupling to the Windows API beyond this module.
"""

import os
import struct
import subprocess
from datetime import datetime, timezone, timedelta
from typing import Any

from core.logger import CleanerLogger


# ── helpers ──────────────────────────────────────────────────────────────────

def _winreg():
    """Lazily import winreg so the module can be imported on non-Windows."""
    import winreg as _wr
    return _wr


def _filetime_to_dt(ft_bytes: bytes) -> str:
    """Convert an 8-byte Windows FILETIME to a readable UTC string."""
    try:
        val = struct.unpack("<Q", ft_bytes[:8])[0]
        if val == 0:
            return ""
        # FILETIME: 100-ns intervals since 1601-01-01
        EPOCH_DIFF = 116444736000000000
        ts = (val - EPOCH_DIFF) / 10_000_000
        dt = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=ts)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


def _rot13(s: str) -> str:
    result = []
    for ch in s:
        if "a" <= ch <= "z":
            result.append(chr((ord(ch) - ord("a") + 13) % 26 + ord("a")))
        elif "A" <= ch <= "Z":
            result.append(chr((ord(ch) - ord("A") + 13) % 26 + ord("A")))
        else:
            result.append(ch)
    return "".join(result)


def _read_str(key, name: str, default: str = "") -> str:
    wr = _winreg()
    try:
        val, _ = wr.QueryValueEx(key, name)
        return str(val)
    except OSError:
        return default


def _read_binary(key, name: str) -> bytes:
    wr = _winreg()
    try:
        val, _ = wr.QueryValueEx(key, name)
        return bytes(val) if val else b""
    except OSError:
        return b""


# ── 1. Network / Internet History ────────────────────────────────────────────

_NET_PROFILES_KEY = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\NetworkList\Profiles"
_NET_SIGNATURES_KEY = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\NetworkList\Signatures\Unmanaged"


def get_network_history(logger: CleanerLogger) -> list[dict[str, Any]]:
    """
    Return stored Wi-Fi and wired network profiles from the registry.

    Each entry:
        guid           — registry key name (GUID string)
        name           — display name (SSID or description)
        description    — longer description
        conn_type      — 'wireless', 'wired', 'dialup', or 'unknown'
        date_created   — human-readable UTC string or ""
        date_last_conn — human-readable UTC string or ""
    """
    if os.name != "nt":
        return []
    wr = _winreg()
    profiles: list[dict[str, Any]] = []
    conn_types = {0: "wired", 1: "wireless", 2: "dialup"}

    try:
        key = wr.OpenKey(wr.HKEY_LOCAL_MACHINE, _NET_PROFILES_KEY, 0, wr.KEY_READ)
    except OSError:
        logger.warning("Cannot open NetworkList\\Profiles — requires admin?")
        return []

    try:
        i = 0
        while True:
            try:
                guid = wr.EnumKey(key, i)
                i += 1
            except OSError:
                break
            try:
                sub = wr.OpenKey(key, guid, 0, wr.KEY_READ)
                name = _read_str(sub, "ProfileName")
                desc = _read_str(sub, "Description")
                cat_raw = _read_binary(sub, "Category")
                cat = struct.unpack("<I", cat_raw[:4])[0] if len(cat_raw) >= 4 else 255
                conn_type = conn_types.get(cat, "unknown")

                # DateCreated / DateLastConnected are stored as 8-byte binary FILETIME
                created   = _filetime_to_dt(_read_binary(sub, "DateCreated"))
                last_conn = _filetime_to_dt(_read_binary(sub, "DateLastConnected"))

                wr.CloseKey(sub)
                profiles.append({
                    "guid":           guid,
                    "name":           name or guid,
                    "description":    desc,
                    "conn_type":      conn_type,
                    "date_created":   created,
                    "date_last_conn": last_conn,
                })
            except OSError:
                pass
    finally:
        wr.CloseKey(key)

    profiles.sort(key=lambda p: p["date_last_conn"] or "", reverse=True)
    logger.info(f"Network history: {len(profiles)} profiles found")
    return profiles


def delete_network_profile(guid: str, logger: CleanerLogger) -> bool:
    """Delete a single network profile by its registry GUID key."""
    if os.name != "nt":
        return False
    wr = _winreg()
    deleted = 0
    for base_path in (_NET_PROFILES_KEY,):
        try:
            key = wr.OpenKey(wr.HKEY_LOCAL_MACHINE, base_path, 0,
                             wr.KEY_READ | wr.KEY_WRITE)
            wr.DeleteKey(key, guid)
            wr.CloseKey(key)
            deleted += 1
        except OSError:
            pass

    # Also remove from Signatures if present
    try:
        sig_key = wr.OpenKey(wr.HKEY_LOCAL_MACHINE, _NET_SIGNATURES_KEY,
                             0, wr.KEY_READ | wr.KEY_WRITE)
        si = 0
        to_delete = []
        while True:
            try:
                subname = wr.EnumKey(sig_key, si)
                si += 1
                sub = wr.OpenKey(sig_key, subname, 0, wr.KEY_READ)
                profile_guid = _read_str(sub, "ProfileGuid")
                wr.CloseKey(sub)
                if profile_guid == guid:
                    to_delete.append(subname)
            except OSError:
                break
        for name in to_delete:
            try:
                wr.DeleteKey(sig_key, name)
            except OSError:
                pass
        wr.CloseKey(sig_key)
    except OSError:
        pass

    success = deleted > 0
    logger.log("del_net_profile", "history",
               f"{'Deleted' if success else 'Failed to delete'} network profile: {guid}",
               success=success)
    return success


def clear_all_network_history(logger: CleanerLogger) -> int:
    """Delete every stored network profile. Returns number deleted."""
    profiles = get_network_history(logger)
    count = sum(1 for p in profiles if delete_network_profile(p["guid"], logger))
    logger.log("clear_net_history", "history", f"Cleared {count} network profiles")
    return count


# ── 2. USB & External Storage History ────────────────────────────────────────

_USBSTOR_KEY  = r"SYSTEM\CurrentControlSet\Enum\USBSTOR"
_MOUNTPTS_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\MountPoints2"


def get_usb_history(logger: CleanerLogger) -> list[dict[str, Any]]:
    """
    Return USB mass storage devices that have ever been connected.

    Each entry:
        device_type  — e.g. "Disk&Ven_SanDisk&Prod_Ultra&Rev_1.00"
        serial       — device serial / instance ID
        friendly     — friendly name (e.g. "SanDisk Ultra USB Device")
        vendor       — parsed vendor string
        model        — parsed model string
        reg_key      — full subkey path for deletion
    """
    if os.name != "nt":
        return []
    wr = _winreg()
    devices: list[dict[str, Any]] = []

    try:
        root = wr.OpenKey(wr.HKEY_LOCAL_MACHINE, _USBSTOR_KEY, 0, wr.KEY_READ)
    except OSError:
        logger.warning("Cannot open USBSTOR — requires admin?")
        return []

    try:
        di = 0
        while True:
            try:
                dev_type = wr.EnumKey(root, di)
                di += 1
            except OSError:
                break

            vendor = model = ""
            parts = dev_type.split("&")
            for part in parts:
                if part.startswith("Ven_"):
                    vendor = part[4:]
                elif part.startswith("Prod_"):
                    model = part[5:]

            try:
                dev_key = wr.OpenKey(root, dev_type, 0, wr.KEY_READ)
                si = 0
                while True:
                    try:
                        serial = wr.EnumKey(dev_key, si)
                        si += 1
                    except OSError:
                        break

                    friendly = ""
                    try:
                        inst_key = wr.OpenKey(dev_key, serial, 0, wr.KEY_READ)
                        friendly = _read_str(inst_key, "FriendlyName")
                        wr.CloseKey(inst_key)
                    except OSError:
                        pass

                    devices.append({
                        "device_type": dev_type,
                        "serial":      serial,
                        "friendly":    friendly or f"{vendor} {model}".strip() or dev_type,
                        "vendor":      vendor,
                        "model":       model,
                        "reg_key":     f"{_USBSTOR_KEY}\\{dev_type}\\{serial}",
                        "_dev_type":   dev_type,  # for deletion
                    })
                wr.CloseKey(dev_key)
            except OSError:
                pass
    finally:
        wr.CloseKey(root)

    logger.info(f"USB history: {len(devices)} device entries found")
    return devices


def delete_usb_entry(device: dict, logger: CleanerLogger) -> bool:
    """Delete a single USB device entry from USBSTOR."""
    if os.name != "nt":
        return False
    wr = _winreg()
    dev_type = device.get("_dev_type", "")
    serial   = device.get("serial", "")
    if not dev_type or not serial:
        return False

    try:
        key = wr.OpenKey(wr.HKEY_LOCAL_MACHINE, f"{_USBSTOR_KEY}\\{dev_type}",
                         0, wr.KEY_READ | wr.KEY_WRITE)
        wr.DeleteKey(key, serial)
        wr.CloseKey(key)
        logger.log("del_usb_entry", "history", f"Deleted USB entry: {dev_type}\\{serial}")
        return True
    except OSError as e:
        logger.warning(f"Cannot delete USB entry {serial}: {e}")
        return False


def clear_all_usb_history(logger: CleanerLogger) -> int:
    """Delete all USB device entries. Returns count deleted."""
    devices = get_usb_history(logger)
    count = sum(1 for d in devices if delete_usb_entry(d, logger))

    # Also clear MountPoints2 (drive-letter mount history)
    try:
        wr = _winreg()
        mp_key = wr.OpenKey(wr.HKEY_CURRENT_USER, _MOUNTPTS_KEY,
                            0, wr.KEY_READ | wr.KEY_WRITE)
        mounts: list[str] = []
        i = 0
        while True:
            try:
                mounts.append(wr.EnumKey(mp_key, i))
                i += 1
            except OSError:
                break
        for m in mounts:
            try:
                wr.DeleteKey(mp_key, m)
                count += 1
            except OSError:
                pass
        wr.CloseKey(mp_key)
    except OSError:
        pass

    logger.log("clear_usb_history", "history", f"Cleared {count} USB/mount entries")
    return count


# ── 3. Application Launch History ────────────────────────────────────────────

# UserAssist GUIDs (may vary by Windows version)
_UA_GUIDS = [
    "{CEBFF5CD-ACE2-4F4F-9178-9926F41749EA}",   # applications
    "{F4E57C4B-2036-45F0-A9AB-443BCFE33D9F}",   # shortcut links
    "{CAA59E3C-4792-41A5-9909-6A6A8D32490E}",   # internet explorer entries
]
_UA_BASE  = r"Software\Microsoft\Windows\CurrentVersion\Explorer\UserAssist"
_RECENT_KEY  = r"Software\Microsoft\Windows\CurrentVersion\Explorer\RecentDocs"
_RUNMRU_KEY  = r"Software\Microsoft\Windows\CurrentVersion\Explorer\RunMRU"


def _parse_userassist_data(raw: bytes) -> tuple[int, str]:
    """Return (run_count, last_run_str) from raw UserAssist binary value."""
    try:
        if len(raw) >= 72:
            run_count = struct.unpack_from("<I", raw, 4)[0]
            if run_count == 0xFFFFFFFF:
                run_count = 0
            ft_bytes = raw[60:68]
            last_run = _filetime_to_dt(ft_bytes)
            return run_count, last_run
    except Exception:
        pass
    return 0, ""


def get_app_launch_history(logger: CleanerLogger) -> dict[str, list[dict[str, Any]]]:
    """
    Return application launch records from three registry sources.

    Returns a dict with keys:
        "userassist"  — list of {name, run_count, last_run, guid, value_name}
        "recent_docs" — list of {name, extension, reg_key}
        "run_mru"     — list of {name, command, order_index}
    """
    result: dict[str, list[dict[str, Any]]] = {
        "userassist":  [],
        "recent_docs": [],
        "run_mru":     [],
    }

    if os.name != "nt":
        return result

    wr = _winreg()

    # ── UserAssist ────────────────────────────────────────────
    for guid in _UA_GUIDS:
        count_path = f"{_UA_BASE}\\{guid}\\Count"
        try:
            key = wr.OpenKey(wr.HKEY_CURRENT_USER, count_path, 0, wr.KEY_READ)
            vi = 0
            while True:
                try:
                    val_name, raw_data, _ = wr.EnumValue(key, vi)
                    vi += 1
                except OSError:
                    break
                decoded = _rot13(val_name)
                # Skip internal counters
                if decoded.startswith("UEME_"):
                    continue
                run_count, last_run = _parse_userassist_data(
                    bytes(raw_data) if raw_data else b""
                )
                # Shorten long paths for display
                display = decoded
                if "\\" in display:
                    display = display.split("\\")[-1]
                if display.endswith(".lnk"):
                    display = display[:-4]
                result["userassist"].append({
                    "name":       display,
                    "full_path":  decoded,
                    "run_count":  run_count,
                    "last_run":   last_run,
                    "guid":       guid,
                    "value_name": val_name,
                })
            wr.CloseKey(key)
        except OSError:
            pass

    # Deduplicate by name, keeping highest run_count
    seen: dict[str, int] = {}
    deduped: list[dict] = []
    for entry in sorted(result["userassist"], key=lambda x: x["run_count"], reverse=True):
        key_str = entry["name"].lower()
        if key_str not in seen:
            seen[key_str] = 1
            deduped.append(entry)
    result["userassist"] = deduped

    # ── RecentDocs ────────────────────────────────────────────
    try:
        rd_key = wr.OpenKey(wr.HKEY_CURRENT_USER, _RECENT_KEY, 0, wr.KEY_READ)
        ext_i = 0
        while True:
            try:
                ext = wr.EnumKey(rd_key, ext_i)
                ext_i += 1
            except OSError:
                break
            try:
                ext_key = wr.OpenKey(rd_key, ext, 0, wr.KEY_READ)
                vi = 0
                while True:
                    try:
                        val_name, raw_data, vtype = wr.EnumValue(ext_key, vi)
                        vi += 1
                    except OSError:
                        break
                    if val_name == "MRUListEx":
                        continue
                    # The value is a NUL-terminated UTF-16LE filename
                    try:
                        raw_bytes = bytes(raw_data) if raw_data else b""
                        name = raw_bytes.decode("utf-16-le").rstrip("\x00").split("\x00")[0]
                    except Exception:
                        name = str(val_name)
                    result["recent_docs"].append({
                        "name":      name,
                        "extension": ext,
                        "reg_key":   f"{_RECENT_KEY}\\{ext}",
                        "val_name":  val_name,
                    })
                wr.CloseKey(ext_key)
            except OSError:
                pass
        wr.CloseKey(rd_key)
    except OSError:
        pass

    # ── RunMRU ────────────────────────────────────────────────
    try:
        run_key = wr.OpenKey(wr.HKEY_CURRENT_USER, _RUNMRU_KEY, 0, wr.KEY_READ)
        vi = 0
        order = []
        while True:
            try:
                val_name, val_data, _ = wr.EnumValue(run_key, vi)
                vi += 1
            except OSError:
                break
            if val_name == "MRUList":
                order = list(str(val_data))
                continue
            result["run_mru"].append({
                "name":        val_name,
                "command":     str(val_data).rstrip("\\1"),
                "order_index": order.index(val_name) if val_name in order else 99,
            })
        wr.CloseKey(run_key)
        result["run_mru"].sort(key=lambda x: x["order_index"])
    except OSError:
        pass

    logger.info(
        f"App history: {len(result['userassist'])} UserAssist, "
        f"{len(result['recent_docs'])} RecentDocs, "
        f"{len(result['run_mru'])} RunMRU entries"
    )
    return result


def delete_app_launch_entry(entry: dict, logger: CleanerLogger) -> bool:
    """
    Delete a single UserAssist, RecentDocs, or RunMRU entry.
    The entry must be exactly as returned by get_app_launch_history().
    """
    if os.name != "nt":
        return False
    wr = _winreg()

    source = entry.get("_source", "")
    try:
        if "guid" in entry:  # UserAssist
            count_path = f"{_UA_BASE}\\{entry['guid']}\\Count"
            key = wr.OpenKey(wr.HKEY_CURRENT_USER, count_path,
                             0, wr.KEY_READ | wr.KEY_WRITE)
            wr.DeleteValue(key, entry["value_name"])
            wr.CloseKey(key)

        elif "extension" in entry:  # RecentDocs
            key = wr.OpenKey(wr.HKEY_CURRENT_USER, entry["reg_key"],
                             0, wr.KEY_READ | wr.KEY_WRITE)
            wr.DeleteValue(key, entry["val_name"])
            wr.CloseKey(key)

        elif "command" in entry:  # RunMRU
            key = wr.OpenKey(wr.HKEY_CURRENT_USER, _RUNMRU_KEY,
                             0, wr.KEY_READ | wr.KEY_WRITE)
            wr.DeleteValue(key, entry["name"])
            wr.CloseKey(key)

        else:
            return False

        logger.log("del_app_entry", "history",
                   f"Deleted app history entry: {entry.get('name', '?')}")
        return True
    except OSError as e:
        logger.warning(f"Cannot delete app history entry: {e}")
        return False


def clear_app_launch_history(logger: CleanerLogger) -> dict[str, int]:
    """
    Clear all app launch history records.
    Returns dict with counts: {userassist, recent_docs, run_mru, prefetch}.
    """
    if os.name != "nt":
        return {}

    wr = _winreg()
    counts: dict[str, int] = {"userassist": 0, "recent_docs": 0,
                               "run_mru": 0, "prefetch": 0}

    # ── UserAssist ────────────────────────────────────────────
    for guid in _UA_GUIDS:
        count_path = f"{_UA_BASE}\\{guid}\\Count"
        try:
            key = wr.OpenKey(wr.HKEY_CURRENT_USER, count_path,
                             0, wr.KEY_READ | wr.KEY_WRITE)
            vals: list[str] = []
            vi = 0
            while True:
                try:
                    vn, _, _ = wr.EnumValue(key, vi)
                    vi += 1
                    vals.append(vn)
                except OSError:
                    break
            for vn in vals:
                try:
                    wr.DeleteValue(key, vn)
                    counts["userassist"] += 1
                except OSError:
                    pass
            wr.CloseKey(key)
        except OSError:
            pass

    # ── RecentDocs ────────────────────────────────────────────
    try:
        rd_key = wr.OpenKey(wr.HKEY_CURRENT_USER, _RECENT_KEY,
                            0, wr.KEY_READ | wr.KEY_WRITE)
        ext_names: list[str] = []
        ei = 0
        while True:
            try:
                ext_names.append(wr.EnumKey(rd_key, ei))
                ei += 1
            except OSError:
                break
        for ext in ext_names:
            try:
                ext_key = wr.OpenKey(rd_key, ext, 0, wr.KEY_READ | wr.KEY_WRITE)
                vals_ext: list[str] = []
                vi = 0
                while True:
                    try:
                        vn, _, _ = wr.EnumValue(ext_key, vi)
                        vi += 1
                        vals_ext.append(vn)
                    except OSError:
                        break
                for vn in vals_ext:
                    try:
                        wr.DeleteValue(ext_key, vn)
                        counts["recent_docs"] += 1
                    except OSError:
                        pass
                wr.CloseKey(ext_key)
            except OSError:
                pass
        wr.CloseKey(rd_key)
    except OSError:
        pass

    # ── RunMRU ────────────────────────────────────────────────
    try:
        run_key = wr.OpenKey(wr.HKEY_CURRENT_USER, _RUNMRU_KEY,
                             0, wr.KEY_READ | wr.KEY_WRITE)
        vals_run: list[str] = []
        vi = 0
        while True:
            try:
                vn, _, _ = wr.EnumValue(run_key, vi)
                vi += 1
                vals_run.append(vn)
            except OSError:
                break
        for vn in vals_run:
            try:
                wr.DeleteValue(run_key, vn)
                counts["run_mru"] += 1
            except OSError:
                pass
        wr.CloseKey(run_key)
    except OSError:
        pass

    # ── Prefetch files ────────────────────────────────────────
    import shutil
    prefetch_dir = os.path.join(
        os.environ.get("WINDIR", r"C:\Windows"), "Prefetch"
    )
    try:
        for f in os.scandir(prefetch_dir):
            if f.name.upper().endswith(".PF"):
                try:
                    os.unlink(f.path)
                    counts["prefetch"] += 1
                except OSError:
                    pass
    except (PermissionError, OSError):
        pass

    logger.log("clear_app_history", "history",
               f"Cleared: UserAssist={counts['userassist']}, "
               f"RecentDocs={counts['recent_docs']}, "
               f"RunMRU={counts['run_mru']}, "
               f"Prefetch={counts['prefetch']}")
    return counts

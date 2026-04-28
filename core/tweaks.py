"""Windows tweak center - essential, advanced, preferences, and performance tweaks."""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, cast

if os.name == "nt":
    import winreg as _winreg

    winreg = cast(Any, _winreg)
else:
    winreg = cast(Any, None)


ULTIMATE_PERF_GUID = "e9a42b02-d5df-448d-aa00-03f14749eb61"
_STATE_FILE = Path("logs") / "tweaks_state.json"
_PROFILE_DIR = Path("profiles") / "tweak_profiles"
_MAX_HISTORY = 200

_STATE_CACHE: dict[str, Any] | None = None
_EXEC_CTX_STACK: list[dict[str, Any]] = []


@dataclass
class TweakDef:
    key: str
    label: str
    group: str
    kind: str = "action"  # action | toggle
    caution: bool = False
    action_fn: Callable[[Any], tuple[bool, str]] | None = None
    set_fn: Callable[[bool, Any], tuple[bool, str]] | None = None
    probe_fn: Callable[[], bool | None] | None = None


def _now_iso() -> str:
    return datetime.now().isoformat()


def _default_state() -> dict[str, Any]:
    return {
        "version": 1,
        "next_change_id": 1,
        "next_batch_id": 1,
        "changes": [],
        "batches": [],
        "favorites": [],
        "pending_restart": [],
    }


def _load_state() -> dict[str, Any]:
    global _STATE_CACHE
    if _STATE_CACHE is not None:
        return _STATE_CACHE

    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        if _STATE_FILE.exists():
            data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                state = _default_state()
                state.update(data)
                _STATE_CACHE = state
                return _STATE_CACHE
    except Exception:
        pass

    _STATE_CACHE = _default_state()
    return _STATE_CACHE


def _save_state():
    state = _load_state()
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


def _trim_history(state: dict[str, Any]):
    changes = state.get("changes", [])
    batches = state.get("batches", [])
    if len(changes) > _MAX_HISTORY:
        state["changes"] = changes[-_MAX_HISTORY:]
    if len(batches) > _MAX_HISTORY:
        state["batches"] = batches[-_MAX_HISTORY:]


def _begin_exec_context(tweak_key: str, label: str, dry_run: bool = False):
    _EXEC_CTX_STACK.append({
        "tweak_key": tweak_key,
        "label": label,
        "dry_run": dry_run,
        "undo_ops": [],
        "plan_ops": [],
    })


def _end_exec_context() -> dict[str, Any]:
    if not _EXEC_CTX_STACK:
        return {"dry_run": False, "undo_ops": [], "plan_ops": []}
    return _EXEC_CTX_STACK.pop()


def _ctx() -> dict[str, Any] | None:
    if not _EXEC_CTX_STACK:
        return None
    return _EXEC_CTX_STACK[-1]


def _is_dry_run() -> bool:
    c = _ctx()
    return bool(c and c.get("dry_run"))


def _record_plan(op: dict[str, Any]):
    c = _ctx()
    if not c:
        return
    c["plan_ops"].append(op)


def _record_undo(op: dict[str, Any]):
    c = _ctx()
    if not c:
        return
    c["undo_ops"].append(op)


def _hive_to_name(hive) -> str:
    if not _is_windows():
        return ""
    if hive == winreg.HKEY_LOCAL_MACHINE:
        return "HKLM"
    if hive == winreg.HKEY_CURRENT_USER:
        return "HKCU"
    if hive == winreg.HKEY_USERS:
        return "HKU"
    return ""


def _name_to_hive(name: str):
    if not _is_windows():
        return None
    n = name.upper().strip()
    if n == "HKLM":
        return winreg.HKEY_LOCAL_MACHINE
    if n == "HKCU":
        return winreg.HKEY_CURRENT_USER
    if n == "HKU":
        return winreg.HKEY_USERS
    return None


def _serialize_reg_value(value: Any, value_type: Any) -> Any:
    if isinstance(value, bytes):
        return {"__bytes_hex__": value.hex(), "__type__": int(value_type)}
    return value


def _deserialize_reg_value(value: Any) -> Any:
    if isinstance(value, dict) and "__bytes_hex__" in value:
        try:
            return bytes.fromhex(str(value.get("__bytes_hex__", "")))
        except Exception:
            return b""
    return value


def _is_restart_sensitive_command(args: list[str]) -> bool:
    cmd = " ".join(args).lower()
    return (
        "winsock reset" in cmd
        or "int ip reset" in cmd
        or "/delete" in cmd and "powercfg" in cmd
        or "/setactive" in cmd and "powercfg" in cmd
        or "/hibernate" in cmd
    )


def _command_requires_admin(args: list[str]) -> bool:
    if not args:
        return False
    head = args[0].lower()
    return head in {"sc", "netsh", "dism", "winget", "cleanmgr", "taskkill", "powercfg"}


def _platform_info() -> dict[str, Any]:
    info = {
        "is_windows": _is_windows(),
        "release": "",
        "version": "",
        "build": 0,
    }
    try:
        info["release"] = platform.release()
        info["version"] = platform.version()
        parts = re.findall(r"\d+", str(info["version"]))
        if parts:
            info["build"] = int(parts[-1])
    except Exception:
        pass
    return info


_GROUPS = {
    "essential":   "Essential Tweaks",
    "advanced":    "Advanced Tweaks (Caution)",
    "preferences": "Customize Preferences",
    "performance": "Performance Tweaks",
    "privacy":     "Privacy Tweaks",
    "gaming":      "Gaming Tweaks",
    "security":    "Security Hardening",
}


def _is_windows() -> bool:
    return os.name == "nt" and winreg is not None


def _result(ok: bool, message: str) -> tuple[bool, str]:
    return ok, message


def _log(logger, action: str, details: str, success: bool = True):
    if not logger:
        return
    try:
        logger.log(action, "tweaks", details, success=success)
    except Exception:
        pass


def _run(args: list[str], timeout: int = 45, mutating: bool = True) -> tuple[int, str, str]:
    if mutating and _is_dry_run():
        _record_plan(
            {
                "kind": "command",
                "command": " ".join(args),
                "requires_admin": _command_requires_admin(args),
                "restart_required": _is_restart_sensitive_command(args),
                "dry_run": True,
            }
        )
        return 0, "", "dry-run"
    try:
        r = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except FileNotFoundError:
        return -1, "", f"command not found: {args[0]}"
    except subprocess.TimeoutExpired:
        return -2, "", "timeout"
    except Exception as e:
        return -3, "", str(e)


def _run_ps(script: str, timeout: int = 45, mutating: bool = True) -> tuple[int, str, str]:
    return _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], timeout=timeout, mutating=mutating)


def _read_reg_ex(hive, key_path: str, value_name: str) -> tuple[bool, Any, Any]:
    if not _is_windows():
        return False, None, None
    try:
        with winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ) as k:
            val, reg_type = winreg.QueryValueEx(k, value_name)
            return True, val, reg_type
    except OSError:
        return False, None, None


def _set_reg(
    hive,
    key_path: str,
    value_name: str,
    value: Any,
    value_type,
    capture: bool = True,
) -> bool:
    if not _is_windows():
        return False

    exists, old_val, old_type = _read_reg_ex(hive, key_path, value_name)
    _record_plan(
        {
            "kind": "registry_set",
            "hive": _hive_to_name(hive),
            "key_path": key_path,
            "value_name": value_name,
            "old_value": _serialize_reg_value(old_val, old_type) if exists else None,
            "new_value": _serialize_reg_value(value, value_type),
            "value_type": int(value_type),
            "requires_admin": _hive_to_name(hive) == "HKLM",
            "restart_required": False,
            "dry_run": _is_dry_run(),
        }
    )

    if _is_dry_run():
        return True

    try:
        with winreg.CreateKeyEx(hive, key_path, 0, winreg.KEY_WRITE) as k:
            winreg.SetValueEx(k, value_name, 0, value_type, value)

        if capture:
            if exists:
                _record_undo(
                    {
                        "kind": "registry_set",
                        "hive": _hive_to_name(hive),
                        "key_path": key_path,
                        "value_name": value_name,
                        "value": _serialize_reg_value(old_val, old_type),
                        "value_type": int(old_type),
                    }
                )
            else:
                _record_undo(
                    {
                        "kind": "registry_delete",
                        "hive": _hive_to_name(hive),
                        "key_path": key_path,
                        "value_name": value_name,
                    }
                )
        return True
    except OSError:
        return False


def _delete_reg(hive, key_path: str, value_name: str, capture: bool = True) -> bool:
    if not _is_windows():
        return False

    exists, old_val, old_type = _read_reg_ex(hive, key_path, value_name)
    _record_plan(
        {
            "kind": "registry_delete",
            "hive": _hive_to_name(hive),
            "key_path": key_path,
            "value_name": value_name,
            "old_value": _serialize_reg_value(old_val, old_type) if exists else None,
            "requires_admin": _hive_to_name(hive) == "HKLM",
            "restart_required": False,
            "dry_run": _is_dry_run(),
        }
    )

    if _is_dry_run():
        return True

    try:
        with winreg.OpenKey(hive, key_path, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, value_name)

        if capture and exists:
            _record_undo(
                {
                    "kind": "registry_set",
                    "hive": _hive_to_name(hive),
                    "key_path": key_path,
                    "value_name": value_name,
                    "value": _serialize_reg_value(old_val, old_type),
                    "value_type": int(old_type),
                }
            )
        return True
    except OSError:
        return False


def _read_reg(hive, key_path: str, value_name: str) -> Any | None:
    if not _is_windows():
        return None
    try:
        with winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ) as k:
            val, _ = winreg.QueryValueEx(k, value_name)
            return val
    except OSError:
        return None


def _get_service_start_mode(service_name: str) -> str | None:
    rc, out, _ = _run(["sc", "qc", service_name], timeout=20, mutating=False)
    if rc != 0:
        return None
    txt = out.lower()
    if "auto_start" in txt:
        return "auto"
    if "demand_start" in txt:
        return "demand"
    if "disabled" in txt:
        return "disabled"
    return None


def _set_service_start(service_name: str, mode: str, capture: bool = True) -> bool:
    # mode: auto | demand | disabled
    old_mode = _get_service_start_mode(service_name)
    _record_plan(
        {
            "kind": "service_start",
            "service_name": service_name,
            "old_mode": old_mode,
            "new_mode": mode,
            "requires_admin": True,
            "restart_required": False,
            "dry_run": _is_dry_run(),
        }
    )

    rc, _, _ = _run(["sc", "config", service_name, "start=", mode], timeout=20)
    ok = rc == 0
    if ok and capture and old_mode and old_mode != mode:
        _record_undo(
            {
                "kind": "service_start",
                "service_name": service_name,
                "mode": old_mode,
            }
        )
    return ok


def _stop_service(service_name: str) -> bool:
    rc, _, _ = _run(["sc", "stop", service_name], timeout=20)
    return rc in (0, 1062)


def _disable_services(names: list[str]) -> tuple[int, int]:
    ok_count = 0
    fail_count = 0
    for name in names:
        ok_cfg = _set_service_start(name, "disabled")
        ok_stop = _stop_service(name)
        if ok_cfg or ok_stop:
            ok_count += 1
        else:
            fail_count += 1
    return ok_count, fail_count


def _set_services_manual(names: list[str]) -> tuple[int, int]:
    ok_count = 0
    fail_count = 0
    for name in names:
        if _set_service_start(name, "demand"):
            ok_count += 1
        else:
            fail_count += 1
    return ok_count, fail_count


def _parse_power_list(text: str) -> list[dict[str, Any]]:
    schemes: list[dict[str, Any]] = []
    pat = re.compile(r"Power Scheme GUID:\s*([a-fA-F0-9\-]+)\s*\((.*?)\)\s*(\*)?")
    for line in text.splitlines():
        m = pat.search(line)
        if m:
            schemes.append(
                {
                    "guid": m.group(1).lower(),
                    "name": m.group(2).strip(),
                    "active": bool(m.group(3)),
                }
            )
    return schemes


def _get_power_schemes() -> list[dict[str, Any]]:
    rc, out, _ = _run(["powercfg", "/list"], timeout=15, mutating=False)
    if rc != 0:
        return []
    return _parse_power_list(out)


def _get_active_power_scheme_guid() -> str | None:
    schemes = _get_power_schemes()
    active = next((s for s in schemes if s.get("active")), None)
    if not active:
        return None
    return str(active.get("guid", "")).strip().lower() or None


def _set_power_scheme(guid: str, capture: bool = True) -> bool:
    old_guid = _get_active_power_scheme_guid()
    _record_plan(
        {
            "kind": "power_scheme",
            "old_guid": old_guid,
            "new_guid": guid,
            "requires_admin": True,
            "restart_required": False,
            "dry_run": _is_dry_run(),
        }
    )
    rc, _, _ = _run(["powercfg", "/setactive", guid], timeout=15)
    ok = rc == 0
    if ok and capture and old_guid and old_guid != guid.lower():
        _record_undo(
            {
                "kind": "power_scheme",
                "guid": old_guid,
            }
        )
    return ok


# ---------------------------------------------------------------------------
# Essential tweaks
# ---------------------------------------------------------------------------

def _tw_create_restore_point(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    if _is_dry_run():
        _record_plan(
            {
                "kind": "restore_point",
                "description": "Create restore checkpoint",
                "requires_admin": True,
                "restart_required": False,
                "dry_run": True,
            }
        )
        return _result(True, "Dry-run: restore point would be created")
    try:
        from core.restore import create_restore_point

        desc = f"SystemCleaner Tweak Checkpoint {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        ok = create_restore_point(desc, logger)
        _log(logger, "tweak_restore_point", desc, success=ok)
        return _result(ok, "Restore point created" if ok else "Restore point creation failed")
    except Exception as e:
        return _result(False, str(e))


def _tw_delete_temp_files(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    if _is_dry_run():
        _record_plan(
            {
                "kind": "cleanup",
                "description": "Delete temporary files",
                "requires_admin": False,
                "restart_required": False,
                "dry_run": True,
            }
        )
        return _result(True, "Dry-run: temporary file cleanup would run")
    try:
        from core.cleaner import clean_temp_files

        freed = clean_temp_files(logger)
        _log(logger, "tweak_delete_temp", f"freed={freed}", success=True)
        return _result(True, f"Temporary files cleaned ({freed} bytes)")
    except Exception as e:
        return _result(False, str(e))


def _tw_disable_consumer_features(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok1 = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Policies\Microsoft\Windows\CloudContent",
        "DisableWindowsConsumerFeatures",
        1,
        winreg.REG_DWORD,
    )
    ok2 = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Policies\Microsoft\Windows\CloudContent",
        "DisableSoftLanding",
        1,
        winreg.REG_DWORD,
    )
    ok = ok1 or ok2
    _log(logger, "tweak_consumer_features", "Disabled consumer features", success=ok)
    return _result(ok, "Consumer features policy updated")


def _tw_disable_telemetry(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    if _is_dry_run():
        _record_plan(
            {
                "kind": "privacy",
                "description": "Disable telemetry policies and diagnostic services",
                "requires_admin": True,
                "restart_required": True,
                "dry_run": True,
            }
        )
        return _result(True, "Dry-run: telemetry policies/services would be disabled")
    try:
        from core.privacy import disable_all_telemetry

        t = disable_all_telemetry(logger)
        ok_t = all(bool(v) for v in t.values()) if t else False
    except Exception:
        ok_t = False
    ok_s, fail_s = _disable_services(["DiagTrack", "dmwappushservice"])
    ok = ok_t or ok_s > 0
    _log(logger, "tweak_disable_telemetry", f"telemetry={ok_t} services_ok={ok_s} services_fail={fail_s}", success=ok)
    return _result(ok, f"Telemetry disabled. Services ok={ok_s}, fail={fail_s}")


def _tw_disable_activity_history(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    keys_ok = []
    keys_ok.append(
        _set_reg(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Policies\Microsoft\Windows\System",
            "EnableActivityFeed",
            0,
            winreg.REG_DWORD,
        )
    )
    keys_ok.append(
        _set_reg(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Policies\Microsoft\Windows\System",
            "PublishUserActivities",
            0,
            winreg.REG_DWORD,
        )
    )
    keys_ok.append(
        _set_reg(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Policies\Microsoft\Windows\System",
            "UploadUserActivities",
            0,
            winreg.REG_DWORD,
        )
    )
    ok = any(keys_ok)
    _log(logger, "tweak_activity_history", "Disabled Activity History", success=ok)
    return _result(ok, "Activity History policy updated")


def _tw_disable_explorer_folder_discovery(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\Bags\AllFolders\Shell",
        "FolderType",
        "NotSpecified",
        winreg.REG_SZ,
    )
    _log(logger, "tweak_folder_discovery", "Disabled Explorer automatic folder discovery", success=ok)
    return _result(ok, "Explorer folder type auto-discovery disabled")


def _tw_disable_game_dvr(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok1 = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\GameDVR",
        "AppCaptureEnabled",
        0,
        winreg.REG_DWORD,
    )
    ok2 = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"System\GameConfigStore",
        "GameDVR_Enabled",
        0,
        winreg.REG_DWORD,
    )
    ok3 = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Policies\Microsoft\Windows\GameDVR",
        "AllowGameDVR",
        0,
        winreg.REG_DWORD,
    )
    ok = ok1 or ok2 or ok3
    _log(logger, "tweak_game_dvr", "Disabled GameDVR", success=ok)
    return _result(ok, "GameDVR disabled")


def _tw_disable_hibernation(logger) -> tuple[bool, str]:
    rc, _, err = _run(["powercfg", "/hibernate", "off"], timeout=20)
    ok = rc == 0
    _log(logger, "tweak_hibernation_off", "powercfg /hibernate off", success=ok)
    return _result(ok, "Hibernation disabled" if ok else f"Failed: {err}")


def _tw_disable_homegroup(logger) -> tuple[bool, str]:
    ok, fail = _disable_services(["HomeGroupListener", "HomeGroupProvider"])
    success = ok > 0
    _log(logger, "tweak_homegroup", f"disabled_ok={ok} disabled_fail={fail}", success=success)
    return _result(success, f"HomeGroup services disabled ok={ok} fail={fail}")


def _tw_disable_location_tracking(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok1 = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\location",
        "Value",
        "Deny",
        winreg.REG_SZ,
    )
    ok2 = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Policies\Microsoft\Windows\LocationAndSensors",
        "DisableLocation",
        1,
        winreg.REG_DWORD,
    )
    ok = ok1 or ok2
    _log(logger, "tweak_location", "Disabled location tracking", success=ok)
    return _result(ok, "Location tracking disabled")


def _tw_disable_storage_sense(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\StorageSense\Parameters\StoragePolicy",
        "01",
        0,
        winreg.REG_DWORD,
    )
    _log(logger, "tweak_storage_sense", "Disabled Storage Sense", success=ok)
    return _result(ok, "Storage Sense disabled")


def _tw_disable_wifi_sense(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok1 = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Microsoft\WcmSvc\wifinetworkmanager\config",
        "AutoConnectAllowedOEM",
        0,
        winreg.REG_DWORD,
    )
    ok2 = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Microsoft\WcmSvc\wifinetworkmanager\config",
        "WiFISenseAllowed",
        0,
        winreg.REG_DWORD,
    )
    ok = ok1 or ok2
    _log(logger, "tweak_wifi_sense", "Disabled Wi-Fi Sense", success=ok)
    return _result(ok, "Wi-Fi Sense disabled")


def _tw_enable_end_task_taskbar(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced\TaskbarDeveloperSettings",
        "TaskbarEndTask",
        1,
        winreg.REG_DWORD,
    )
    if not ok:
        # fallback path used by some builds
        ok = _set_reg(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
            "TaskbarEndTask",
            1,
            winreg.REG_DWORD,
        )
    _log(logger, "tweak_end_task_menu", "Enabled End Task in taskbar menu", success=ok)
    return _result(ok, "End Task option enabled in taskbar right-click menu")


def _tw_run_disk_cleanup(logger) -> tuple[bool, str]:
    rc, out, err = _run(["cleanmgr", "/VERYLOWDISK"], timeout=180)
    ok = rc == 0
    if not ok:
        # fallback to Windows component cleanup
        rc2, _, err2 = _run(["dism", "/online", "/Cleanup-Image", "/StartComponentCleanup"], timeout=300)
        ok = rc2 == 0
        err = err2 if not ok else ""
    _log(logger, "tweak_disk_cleanup", "Ran disk cleanup", success=ok)
    return _result(ok, "Disk cleanup executed" if ok else f"Disk cleanup failed: {err or out}")


def _tw_set_terminal_pwsh7_default(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    if _is_dry_run():
        _record_plan(
            {
                "kind": "file_write",
                "description": "Set Windows Terminal default profile to PowerShell 7",
                "requires_admin": False,
                "restart_required": False,
                "dry_run": True,
            }
        )
        return _result(True, "Dry-run: Windows Terminal default profile would be updated")

    local = Path(os.environ.get("LOCALAPPDATA", ""))
    candidates = [
        local / "Packages" / "Microsoft.WindowsTerminal_8wekyb3d8bbwe" / "LocalState" / "settings.json",
        local / "Packages" / "Microsoft.WindowsTerminalPreview_8wekyb3d8bbwe" / "LocalState" / "settings.json",
    ]

    for cfg in candidates:
        if not cfg.exists():
            continue
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
        except Exception:
            continue

        profiles = data.get("profiles", {}).get("list", [])
        target_guid = ""
        for p in profiles:
            cmd = str(p.get("commandline", "")).lower()
            name = str(p.get("name", "")).lower()
            if "pwsh" in cmd or "powershell 7" in name:
                target_guid = str(p.get("guid", "")).strip()
                break

        if not target_guid:
            continue

        data["defaultProfile"] = target_guid
        try:
            cfg.write_text(json.dumps(data, indent=2), encoding="utf-8")
            _log(logger, "tweak_terminal_pwsh7", f"Set defaultProfile={target_guid}", success=True)
            return _result(True, "Windows Terminal default profile switched to PowerShell 7")
        except Exception as e:
            return _result(False, f"Could not write Windows Terminal settings: {e}")

    return _result(False, "PowerShell 7 profile not found in Windows Terminal settings")


def _tw_disable_pwsh7_telemetry(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok_user = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"Environment",
        "POWERSHELL_TELEMETRY_OPTOUT",
        "1",
        winreg.REG_SZ,
    )
    ok_machine = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        "POWERSHELL_TELEMETRY_OPTOUT",
        "1",
        winreg.REG_SZ,
    )
    ok = ok_user or ok_machine
    _log(logger, "tweak_pwsh_telemetry", "Set POWERSHELL_TELEMETRY_OPTOUT=1", success=ok)
    return _result(ok, "PowerShell telemetry opt-out applied")


def _tw_disable_recall(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    keys = [
        _set_reg(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Policies\Microsoft\Windows\WindowsAI",
            "DisableAIDataAnalysis",
            1,
            winreg.REG_DWORD,
        ),
        _set_reg(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Policies\Microsoft\Windows\WindowsAI",
            "TurnOffSavingSnapshots",
            1,
            winreg.REG_DWORD,
        ),
        _set_reg(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Policies\Microsoft\Windows\WindowsAI",
            "DisableRecall",
            1,
            winreg.REG_DWORD,
        ),
    ]
    ok = any(keys)
    _log(logger, "tweak_disable_recall", "Disabled Recall policies", success=ok)
    return _result(ok, "Recall policy keys updated")


def _tw_set_hibernation_default_laptop(logger) -> tuple[bool, str]:
    cmds = [
        ["powercfg", "/hibernate", "on"],
        ["powercfg", "/setacvalueindex", "SCHEME_CURRENT", "SUB_BUTTONS", "LIDACTION", "2"],
        ["powercfg", "/setdcvalueindex", "SCHEME_CURRENT", "SUB_BUTTONS", "LIDACTION", "2"],
        ["powercfg", "/setactive", "SCHEME_CURRENT"],
    ]
    ok = 0
    for cmd in cmds:
        rc, _, _ = _run(cmd, timeout=20)
        if rc == 0:
            ok += 1
    success = ok >= 2
    _log(logger, "tweak_hibernate_laptop", f"commands_ok={ok}", success=success)
    return _result(success, f"Hibernate-preferred laptop setup applied ({ok}/{len(cmds)} commands)")


def _tw_set_services_manual(logger) -> tuple[bool, str]:
    try:
        from core.optimizer import OPTIONAL_SERVICES

        names = sorted(OPTIONAL_SERVICES.keys())
    except Exception:
        names = ["DiagTrack", "dmwappushservice", "SysMain", "WSearch", "MapsBroker", "lfsvc"]

    ok, fail = _set_services_manual(names)
    success = ok > 0
    _log(logger, "tweak_services_manual", f"ok={ok} fail={fail}", success=success)
    return _result(success, f"Services set to manual: ok={ok}, fail={fail}")


def _tw_debloat_edge(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")

    writes = [
        _set_reg(
            winreg.HKEY_CURRENT_USER,
            r"Software\Policies\Microsoft\Edge",
            "StartupBoostEnabled",
            0,
            winreg.REG_DWORD,
        ),
        _set_reg(
            winreg.HKEY_CURRENT_USER,
            r"Software\Policies\Microsoft\Edge",
            "BackgroundModeEnabled",
            0,
            winreg.REG_DWORD,
        ),
        _set_reg(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Policies\Microsoft\Edge",
            "StartupBoostEnabled",
            0,
            winreg.REG_DWORD,
        ),
        _set_reg(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Policies\Microsoft\Edge",
            "BackgroundModeEnabled",
            0,
            winreg.REG_DWORD,
        ),
    ]
    ok_s, fail_s = _disable_services(["edgeupdate", "edgeupdatem"])
    ok = any(writes) or ok_s > 0
    _log(logger, "tweak_edge_debloat", f"writes={sum(1 for x in writes if x)} svc_ok={ok_s} svc_fail={fail_s}", success=ok)
    return _result(ok, f"Edge background tweaks applied (services ok={ok_s}, fail={fail_s})")


# ---------------------------------------------------------------------------
# Advanced tweaks
# ---------------------------------------------------------------------------

def _find_adobe_executables() -> list[Path]:
    roots = [
        Path(os.environ.get("ProgramFiles", "")),
        Path(os.environ.get("ProgramFiles(x86)", "")),
        Path(os.environ.get("CommonProgramFiles", "")),
        Path(os.environ.get("CommonProgramFiles(x86)", "")),
    ]
    known = {
        "creative cloud.exe",
        "ccxprocess.exe",
        "adobeipcbroker.exe",
        "adobe desktop service.exe",
        "adobe gc client.exe",
        "armsvc.exe",
    }

    found: list[Path] = []
    for root in roots:
        if not root or not root.exists():
            continue
        for base in [root / "Adobe", root / "Common Files" / "Adobe"]:
            if not base.exists():
                continue
            try:
                for p in base.rglob("*.exe"):
                    if p.name.lower() in known:
                        found.append(p)
            except Exception:
                continue
    return sorted(set(found))


def _tw_adobe_network_block(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")

    exes = _find_adobe_executables()
    if not exes:
        return _result(False, "No Adobe executables found")

    ok = 0
    for exe in exes:
        rule = f"SC_ADOBE_BLOCK_{exe.stem}"[:60]
        rc, _, _ = _run(
            [
                "netsh",
                "advfirewall",
                "firewall",
                "add",
                "rule",
                f"name={rule}",
                "dir=out",
                "action=block",
                f"program={str(exe)}",
                "enable=yes",
            ],
            timeout=25,
        )
        if rc == 0:
            ok += 1

    success = ok > 0
    _log(logger, "tweak_adobe_block", f"rules_created={ok}", success=success)
    return _result(success, f"Adobe outbound firewall rules created: {ok}")


def _tw_adobe_debloat(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    if _is_dry_run():
        _record_plan(
            {
                "kind": "debloat",
                "description": "Disable Adobe startup/services and remove Adobe logs",
                "requires_admin": True,
                "restart_required": False,
                "dry_run": True,
            }
        )
        return _result(True, "Dry-run: Adobe debloat actions would be executed")

    startup_ok = 0
    try:
        from core.startup import disable_startup_entry, get_startup_entries

        entries = get_startup_entries(logger)
        targets = [e for e in entries if "adobe" in (e.get("name", "") + " " + e.get("command", "")).lower()]
        for e in targets:
            if disable_startup_entry(e, logger):
                startup_ok += 1
    except Exception:
        pass

    svc_ok, _ = _disable_services(["AdobeARMservice", "AGMService", "AGSService", "AdobeUpdateService"])

    removed = 0
    for p in [
        Path(os.environ.get("APPDATA", "")) / "Adobe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Adobe",
    ]:
        if p.exists():
            try:
                for item in p.glob("*.log"):
                    item.unlink(missing_ok=True)
                    removed += 1
            except Exception:
                pass

    success = startup_ok > 0 or svc_ok > 0 or removed > 0
    _log(logger, "tweak_adobe_debloat", f"startup={startup_ok} services={svc_ok} logs_removed={removed}", success=success)
    return _result(success, f"Adobe debloat done (startup={startup_ok}, services={svc_ok}, logs={removed})")


def _tw_disable_ipv6(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters",
        "DisabledComponents",
        0xFF,
        winreg.REG_DWORD,
    )
    _log(logger, "tweak_disable_ipv6", "Set DisabledComponents=0xFF", success=ok)
    return _result(ok, "IPv6 disabled (reboot required)")


def _tw_prefer_ipv4(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters",
        "DisabledComponents",
        0x20,
        winreg.REG_DWORD,
    )
    _log(logger, "tweak_prefer_ipv4", "Set DisabledComponents=0x20", success=ok)
    return _result(ok, "IPv4 preference over IPv6 applied (reboot required)")


def _tw_disable_teredo(logger) -> tuple[bool, str]:
    cmds = [
        ["netsh", "interface", "teredo", "set", "state", "disabled"],
        ["netsh", "interface", "6to4", "set", "state", "disabled"],
        ["netsh", "interface", "isatap", "set", "state", "disabled"],
    ]
    ok = 0
    for cmd in cmds:
        rc, _, _ = _run(cmd, timeout=20)
        if rc == 0:
            ok += 1
    success = ok > 0
    _log(logger, "tweak_disable_teredo", f"commands_ok={ok}", success=success)
    return _result(success, f"Teredo/6to4/ISATAP disable commands ok={ok}")


def _tw_disable_background_apps(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications",
        "GlobalUserDisabled",
        1,
        winreg.REG_DWORD,
    )
    _log(logger, "tweak_background_apps", "Disabled background apps", success=ok)
    return _result(ok, "Background apps disabled")


def _tw_disable_fullscreen_optimizations(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    writes = [
        _set_reg(
            winreg.HKEY_CURRENT_USER,
            r"System\GameConfigStore",
            "GameDVR_FSEBehaviorMode",
            2,
            winreg.REG_DWORD,
        ),
        _set_reg(
            winreg.HKEY_CURRENT_USER,
            r"System\GameConfigStore",
            "GameDVR_HonorUserFSEBehaviorMode",
            1,
            winreg.REG_DWORD,
        ),
    ]
    ok = any(writes)
    _log(logger, "tweak_fullscreen_opt", "Disabled fullscreen optimizations", success=ok)
    return _result(ok, "Fullscreen optimization policy updated")


def _tw_disable_copilot(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    writes = [
        _set_reg(
            winreg.HKEY_CURRENT_USER,
            r"Software\Policies\Microsoft\Windows\WindowsCopilot",
            "TurnOffWindowsCopilot",
            1,
            winreg.REG_DWORD,
        ),
        _set_reg(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Policies\Microsoft\Windows\WindowsCopilot",
            "TurnOffWindowsCopilot",
            1,
            winreg.REG_DWORD,
        ),
        _set_reg(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
            "ShowCopilotButton",
            0,
            winreg.REG_DWORD,
        ),
    ]
    ok = any(writes)
    _log(logger, "tweak_disable_copilot", "Disabled Windows Copilot", success=ok)
    return _result(ok, "Copilot disabled")


def _tw_disable_intel_lms(logger) -> tuple[bool, str]:
    ok, fail = _disable_services(["LMS"])
    success = ok > 0
    _log(logger, "tweak_disable_lms", f"ok={ok} fail={fail}", success=success)
    return _result(success, "Intel LMS service disabled" if success else "Intel LMS service not found or access denied")


def _tw_disable_notification_center(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Policies\Microsoft\Windows\Explorer",
        "DisableNotificationCenter",
        1,
        winreg.REG_DWORD,
    )
    _log(logger, "tweak_disable_notifications", "Disabled notification center", success=ok)
    return _result(ok, "Notification center disabled")


def _tw_disable_wpbt(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SYSTEM\CurrentControlSet\Control\Session Manager",
        "DisableWpbtExecution",
        1,
        winreg.REG_DWORD,
    )
    _log(logger, "tweak_disable_wpbt", "Set DisableWpbtExecution=1", success=ok)
    return _result(ok, "WPBT execution disabled via policy key")


def _tw_set_display_performance(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    if _is_dry_run():
        _record_plan(
            {
                "kind": "visual_effects",
                "description": "Set Windows visual effects for performance",
                "requires_admin": False,
                "restart_required": False,
                "dry_run": True,
            }
        )
        return _result(True, "Dry-run: display performance settings would be applied")
    try:
        from core.perfboost import disable_visual_effects

        ok = disable_visual_effects(logger)
        _log(logger, "tweak_display_perf", "Set display for performance", success=ok)
        return _result(ok, "Display effects tuned for performance")
    except Exception as e:
        return _result(False, str(e))


def _tw_set_classic_context_menu(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}\InprocServer32",
        "",
        "",
        winreg.REG_SZ,
    )
    _log(logger, "tweak_classic_menu", "Enabled classic right-click menu", success=ok)
    return _result(ok, "Classic right-click menu enabled (restart Explorer)")


def _tw_set_utc_dual_boot(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SYSTEM\CurrentControlSet\Control\TimeZoneInformation",
        "RealTimeIsUniversal",
        1,
        winreg.REG_DWORD,
    )
    _log(logger, "tweak_utc_time", "Set RealTimeIsUniversal=1", success=ok)
    return _result(ok, "Hardware clock set to UTC mode")


def _tw_remove_all_store_apps(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")

    script = (
        "Get-AppxPackage -AllUsers | Remove-AppxPackage -AllUsers -ErrorAction SilentlyContinue; "
        "Get-AppxProvisionedPackage -Online | Remove-AppxProvisionedPackage -Online -ErrorAction SilentlyContinue"
    )
    rc, out, err = _run_ps(script, timeout=600)
    ok = rc == 0
    _log(logger, "tweak_remove_store_apps", "Removed all MS Store apps", success=ok)
    if ok:
        return _result(True, "All MS Store apps removal command completed")
    return _result(False, f"Command failed: {err or out}")


def _tw_remove_edge(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")

    success = False
    attempts = 0

    # Attempt 1: winget uninstall
    rc, _, _ = _run(
        [
            "winget",
            "uninstall",
            "--id",
            "Microsoft.Edge",
            "--accept-source-agreements",
            "--disable-interactivity",
        ],
        timeout=300,
    )
    attempts += 1
    if rc == 0:
        success = True

    # Attempt 2: setup.exe uninstall
    roots = [
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft" / "Edge" / "Application",
        Path(os.environ.get("ProgramFiles", "")) / "Microsoft" / "Edge" / "Application",
    ]
    for root in roots:
        if not root.exists():
            continue
        for setup in sorted(root.glob("*/Installer/setup.exe"), reverse=True):
            cmd = [
                str(setup),
                "--uninstall",
                "--system-level",
                "--force-uninstall",
                "--verbose-logging",
            ]
            rc2, _, _ = _run(cmd, timeout=300)
            attempts += 1
            if rc2 == 0:
                success = True
                break

    _log(logger, "tweak_remove_edge", f"attempts={attempts}", success=success)
    return _result(success, "Microsoft Edge uninstall attempted" if success else "Edge uninstall failed")


def _tw_remove_home_gallery_explorer(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    writes = [
        _set_reg(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
            "LaunchTo",
            1,
            winreg.REG_DWORD,
        ),
        _set_reg(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
            "ShowRecent",
            0,
            winreg.REG_DWORD,
        ),
        _set_reg(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
            "ShowFrequent",
            0,
            winreg.REG_DWORD,
        ),
        _set_reg(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
            "ShowGallery",
            0,
            winreg.REG_DWORD,
        ),
    ]
    ok = any(writes)
    _log(logger, "tweak_explorer_home_gallery", "Removed Home/Gallery from Explorer", success=ok)
    return _result(ok, "Explorer Home/Gallery visibility reduced")


def _tw_remove_onedrive(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    _run(["taskkill", "/f", "/im", "OneDrive.exe"], timeout=15)

    setups = [
        Path(os.environ.get("SystemRoot", r"C:\Windows")) / "SysWOW64" / "OneDriveSetup.exe",
        Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "OneDriveSetup.exe",
    ]

    ok_cmd = False
    for exe in setups:
        if exe.exists():
            rc, _, _ = _run([str(exe), "/uninstall"], timeout=180)
            if rc == 0:
                ok_cmd = True

    ok_policy = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Policies\Microsoft\Windows\OneDrive",
        "DisableFileSyncNGSC",
        1,
        winreg.REG_DWORD,
    )

    ok = ok_cmd or ok_policy
    _log(logger, "tweak_remove_onedrive", f"cmd={ok_cmd} policy={ok_policy}", success=ok)
    return _result(ok, "OneDrive uninstall/disable applied")


def _write_hosts_section(tag: str, domains: list[str]) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    if _is_dry_run():
        _record_plan(
            {
                "kind": "hosts_write",
                "description": f"Write hosts block section '{tag}'",
                "domains": domains,
                "requires_admin": True,
                "restart_required": False,
                "dry_run": True,
            }
        )
        return _result(True, f"Dry-run: hosts section '{tag}' would be written")

    hosts = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "drivers" / "etc" / "hosts"
    if not hosts.exists():
        return _result(False, "hosts file not found")

    start = f"# >>> {tag} START >>>"
    end = f"# <<< {tag} END <<<"

    lines = hosts.read_text(encoding="utf-8", errors="replace").splitlines()
    out: list[str] = []
    inside = False
    for line in lines:
        if line.strip() == start:
            inside = True
            continue
        if line.strip() == end:
            inside = False
            continue
        if not inside:
            out.append(line)

    out.append("")
    out.append(start)
    for d in domains:
        out.append(f"0.0.0.0 {d}")
    out.append(end)

    try:
        hosts.write_text("\n".join(out) + "\n", encoding="utf-8")
        return _result(True, f"hosts section '{tag}' written")
    except Exception as e:
        return _result(False, f"hosts update failed: {e}")


def _tw_block_razer_installs(logger) -> tuple[bool, str]:
    domains = [
        "api.razer.com",
        "rzr.to",
        "drivers.razer.com",
        "assets.razerzone.com",
        "updates.razer.com",
    ]
    ok, msg = _write_hosts_section("SC_RAZER_BLOCK", domains)
    _log(logger, "tweak_razer_block", msg, success=ok)
    return _result(ok, msg)


def _tw_run_ooshutup10(logger) -> tuple[bool, str]:
    if _is_dry_run():
        _record_plan(
            {
                "kind": "launch_app",
                "description": "Launch OOSU10.exe",
                "requires_admin": False,
                "restart_required": False,
                "dry_run": True,
            }
        )
        return _result(True, "Dry-run: OOSU10 would be launched")

    candidates = [
        Path.cwd() / "OOSU10.exe",
        Path.cwd() / "tools" / "OOSU10.exe",
        Path.cwd() / "downloads" / "OOSU10.exe",
        Path.home() / "Downloads" / "OOSU10.exe",
        Path.home() / "Desktop" / "OOSU10.exe",
    ]

    exe = next((p for p in candidates if p.exists()), None)
    if not exe:
        return _result(False, "OOSU10.exe not found (place it in project/tools or Downloads)")

    try:
        subprocess.Popen([str(exe)])
        _log(logger, "tweak_ooshutup10", f"Started {exe}", success=True)
        return _result(True, f"Started {exe}")
    except Exception as e:
        _log(logger, "tweak_ooshutup10", str(e), success=False)
        return _result(False, str(e))


# ---------------------------------------------------------------------------
# Preference toggles
# ---------------------------------------------------------------------------

def _toggle_dark_theme(enable: bool, logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    val = 0 if enable else 1
    ok1 = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        "AppsUseLightTheme",
        val,
        winreg.REG_DWORD,
    )
    ok2 = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        "SystemUsesLightTheme",
        val,
        winreg.REG_DWORD,
    )
    ok = ok1 or ok2
    _log(logger, "pref_dark_theme", f"enable={enable}", success=ok)
    return _result(ok, "Dark theme enabled" if enable else "Light theme enabled")


def _probe_dark_theme() -> bool | None:
    if not _is_windows():
        return None
    v = _read_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        "AppsUseLightTheme",
    )
    if v is None:
        return None
    return int(v) == 0


def _toggle_bing_start(enable: bool, logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    # policy key is inverted: 1 means disabled
    value = 0 if enable else 1
    ok = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"SOFTWARE\Policies\Microsoft\Windows\Explorer",
        "DisableSearchBoxSuggestions",
        value,
        winreg.REG_DWORD,
    )
    _log(logger, "pref_bing_start", f"enable={enable}", success=ok)
    return _result(ok, "Bing search enabled in Start" if enable else "Bing search disabled in Start")


def _probe_bing_start() -> bool | None:
    if not _is_windows():
        return None
    v = _read_reg(
        winreg.HKEY_CURRENT_USER,
        r"SOFTWARE\Policies\Microsoft\Windows\Explorer",
        "DisableSearchBoxSuggestions",
    )
    if v is None:
        return True
    return int(v) == 0


def _toggle_numlock(enable: bool, logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    val = "2" if enable else "0"
    ok1 = _set_reg(
        winreg.HKEY_USERS,
        r".DEFAULT\Control Panel\Keyboard",
        "InitialKeyboardIndicators",
        val,
        winreg.REG_SZ,
    )
    ok2 = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"Control Panel\Keyboard",
        "InitialKeyboardIndicators",
        val,
        winreg.REG_SZ,
    )
    ok = ok1 or ok2
    _log(logger, "pref_numlock", f"enable={enable}", success=ok)
    return _result(ok, "NumLock startup behavior updated")


def _probe_numlock() -> bool | None:
    if not _is_windows():
        return None
    v = _read_reg(
        winreg.HKEY_USERS,
        r".DEFAULT\Control Panel\Keyboard",
        "InitialKeyboardIndicators",
    )
    if v is None:
        return None
    return str(v).startswith("2")


def _toggle_verbose_logon(enable: bool, logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    val = 1 if enable else 0
    ok = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System",
        "VerboseStatus",
        val,
        winreg.REG_DWORD,
    )
    _log(logger, "pref_verbose_logon", f"enable={enable}", success=ok)
    return _result(ok, "Verbose logon messages updated")


def _probe_verbose_logon() -> bool | None:
    if not _is_windows():
        return None
    v = _read_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System",
        "VerboseStatus",
    )
    if v is None:
        return None
    return int(v) == 1


def _toggle_start_recommendations(enable: bool, logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    val = 1 if enable else 0
    ok = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
        "Start_IrisRecommendations",
        val,
        winreg.REG_DWORD,
    )
    _log(logger, "pref_start_recommendations", f"enable={enable}", success=ok)
    return _result(ok, "Start recommendations updated")


def _probe_start_recommendations() -> bool | None:
    if not _is_windows():
        return None
    v = _read_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
        "Start_IrisRecommendations",
    )
    if v is None:
        return None
    return int(v) == 1


def _toggle_settings_home_removed(enable: bool, logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    if enable:
        ok = _set_reg(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer",
            "SettingsPageVisibility",
            "hide:home",
            winreg.REG_SZ,
        )
    else:
        ok = _delete_reg(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer",
            "SettingsPageVisibility",
        )
    _log(logger, "pref_settings_home", f"remove_home={enable}", success=ok)
    return _result(ok, "Settings home page preference updated")


def _probe_settings_home_removed() -> bool | None:
    if not _is_windows():
        return None
    v = _read_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer",
        "SettingsPageVisibility",
    )
    if v is None:
        return False
    return "hide:home" in str(v).lower()


def _toggle_snap_window(enable: bool, logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"Control Panel\Desktop",
        "WindowArrangementActive",
        "1" if enable else "0",
        winreg.REG_SZ,
    )
    _log(logger, "pref_snap_window", f"enable={enable}", success=ok)
    return _result(ok, "Snap Window updated")


def _probe_snap_window() -> bool | None:
    if not _is_windows():
        return None
    v = _read_reg(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop", "WindowArrangementActive")
    if v is None:
        return None
    return str(v) == "1"


def _toggle_snap_flyout(enable: bool, logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
        "EnableSnapAssistFlyout",
        1 if enable else 0,
        winreg.REG_DWORD,
    )
    _log(logger, "pref_snap_flyout", f"enable={enable}", success=ok)
    return _result(ok, "Snap Assist flyout updated")


def _probe_snap_flyout() -> bool | None:
    if not _is_windows():
        return None
    v = _read_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
        "EnableSnapAssistFlyout",
    )
    if v is None:
        return None
    return int(v) == 1


def _toggle_snap_suggestion(enable: bool, logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
        "SnapAssist",
        1 if enable else 0,
        winreg.REG_DWORD,
    )
    _log(logger, "pref_snap_suggestion", f"enable={enable}", success=ok)
    return _result(ok, "Snap Assist suggestion updated")


def _probe_snap_suggestion() -> bool | None:
    if not _is_windows():
        return None
    v = _read_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
        "SnapAssist",
    )
    if v is None:
        return None
    return int(v) == 1


def _toggle_mouse_accel(enable: bool, logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    speed = "1" if enable else "0"
    thr1 = "6" if enable else "0"
    thr2 = "10" if enable else "0"
    ok = all(
        [
            _set_reg(winreg.HKEY_CURRENT_USER, r"Control Panel\Mouse", "MouseSpeed", speed, winreg.REG_SZ),
            _set_reg(winreg.HKEY_CURRENT_USER, r"Control Panel\Mouse", "MouseThreshold1", thr1, winreg.REG_SZ),
            _set_reg(winreg.HKEY_CURRENT_USER, r"Control Panel\Mouse", "MouseThreshold2", thr2, winreg.REG_SZ),
        ]
    )
    _log(logger, "pref_mouse_accel", f"enable={enable}", success=ok)
    return _result(ok, "Mouse acceleration updated")


def _probe_mouse_accel() -> bool | None:
    if not _is_windows():
        return None
    v = _read_reg(winreg.HKEY_CURRENT_USER, r"Control Panel\Mouse", "MouseSpeed")
    if v is None:
        return None
    return str(v) == "1"


def _toggle_sticky_keys(enable: bool, logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    # Common Flags values used by accessibility toggles.
    val = "510" if enable else "58"
    ok = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"Control Panel\Accessibility\StickyKeys",
        "Flags",
        val,
        winreg.REG_SZ,
    )
    _log(logger, "pref_sticky_keys", f"enable={enable}", success=ok)
    return _result(ok, "Sticky Keys updated")


def _probe_sticky_keys() -> bool | None:
    if not _is_windows():
        return None
    v = _read_reg(winreg.HKEY_CURRENT_USER, r"Control Panel\Accessibility\StickyKeys", "Flags")
    if v is None:
        return None
    try:
        return int(str(v)) >= 500
    except Exception:
        return None


def _toggle_hidden_files(enable: bool, logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
        "Hidden",
        1 if enable else 2,
        winreg.REG_DWORD,
    )
    _log(logger, "pref_hidden_files", f"enable={enable}", success=ok)
    return _result(ok, "Hidden files visibility updated")


def _probe_hidden_files() -> bool | None:
    if not _is_windows():
        return None
    v = _read_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
        "Hidden",
    )
    if v is None:
        return None
    return int(v) == 1


def _toggle_file_ext(enable: bool, logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
        "HideFileExt",
        0 if enable else 1,
        winreg.REG_DWORD,
    )
    _log(logger, "pref_file_extensions", f"show={enable}", success=ok)
    return _result(ok, "File extension visibility updated")


def _probe_file_ext() -> bool | None:
    if not _is_windows():
        return None
    v = _read_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
        "HideFileExt",
    )
    if v is None:
        return None
    return int(v) == 0


def _toggle_search_button(enable: bool, logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Search",
        "SearchboxTaskbarMode",
        1 if enable else 0,
        winreg.REG_DWORD,
    )
    _log(logger, "pref_search_button", f"enable={enable}", success=ok)
    return _result(ok, "Taskbar search button updated")


def _probe_search_button() -> bool | None:
    if not _is_windows():
        return None
    v = _read_reg(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Search", "SearchboxTaskbarMode")
    if v is None:
        return None
    return int(v) != 0


def _toggle_task_view(enable: bool, logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
        "ShowTaskViewButton",
        1 if enable else 0,
        winreg.REG_DWORD,
    )
    _log(logger, "pref_task_view", f"enable={enable}", success=ok)
    return _result(ok, "Task View button updated")


def _probe_task_view() -> bool | None:
    if not _is_windows():
        return None
    v = _read_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
        "ShowTaskViewButton",
    )
    if v is None:
        return None
    return int(v) == 1


def _toggle_taskbar_center(enable: bool, logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
        "TaskbarAl",
        1 if enable else 0,
        winreg.REG_DWORD,
    )
    _log(logger, "pref_taskbar_center", f"enable={enable}", success=ok)
    return _result(ok, "Taskbar alignment updated")


def _probe_taskbar_center() -> bool | None:
    if not _is_windows():
        return None
    v = _read_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
        "TaskbarAl",
    )
    if v is None:
        return None
    return int(v) == 1


def _toggle_widgets(enable: bool, logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
        "TaskbarDa",
        1 if enable else 0,
        winreg.REG_DWORD,
    )
    _log(logger, "pref_widgets", f"enable={enable}", success=ok)
    return _result(ok, "Widgets button updated")


def _probe_widgets() -> bool | None:
    if not _is_windows():
        return None
    v = _read_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
        "TaskbarDa",
    )
    if v is None:
        return None
    return int(v) == 1


def _toggle_detailed_bsod(enable: bool, logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SYSTEM\CurrentControlSet\Control\CrashControl",
        "DisplayParameters",
        1 if enable else 0,
        winreg.REG_DWORD,
    )
    _log(logger, "pref_detailed_bsod", f"enable={enable}", success=ok)
    return _result(ok, "Detailed BSOD setting updated")


def _probe_detailed_bsod() -> bool | None:
    if not _is_windows():
        return None
    v = _read_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SYSTEM\CurrentControlSet\Control\CrashControl",
        "DisplayParameters",
    )
    if v is None:
        return None
    return int(v) == 1


# ---------------------------------------------------------------------------
# Performance plan actions
# ---------------------------------------------------------------------------

def _tw_add_activate_ultimate_perf(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")

    schemes = _get_power_schemes()
    ultimate = [s for s in schemes if "ultimate" in s["name"].lower() and "performance" in s["name"].lower()]

    if not ultimate:
        _run(["powercfg", "-duplicatescheme", ULTIMATE_PERF_GUID], timeout=20)
        schemes = _get_power_schemes()
        ultimate = [s for s in schemes if "ultimate" in s["name"].lower() and "performance" in s["name"].lower()]

    if not ultimate:
        # fallback try direct setactive on known guid
        ok = _set_power_scheme(ULTIMATE_PERF_GUID)
        _log(logger, "tweak_ultimate_add", "Set active by static GUID", success=ok)
        return _result(ok, "Ultimate Performance profile activated" if ok else "Could not create/activate Ultimate Performance")

    ok = _set_power_scheme(ultimate[0]["guid"])
    _log(logger, "tweak_ultimate_add", f"guid={ultimate[0]['guid']}", success=ok)
    return _result(ok, f"Ultimate Performance activated ({ultimate[0]['guid']})")


def _tw_remove_ultimate_perf(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")

    schemes = _get_power_schemes()
    ultimate = [s for s in schemes if "ultimate" in s["name"].lower() and "performance" in s["name"].lower()]

    if not ultimate:
        return _result(True, "No Ultimate Performance profile found")

    # if active, switch to balanced first
    active = next((s for s in schemes if s.get("active")), None)
    if active and active in ultimate:
        balanced = next((s for s in schemes if "balanced" in s["name"].lower()), None)
        if balanced:
            _set_power_scheme(balanced["guid"])

    deleted = 0
    for s in ultimate:
        rc, _, _ = _run(["powercfg", "/delete", s["guid"]], timeout=15)
        if rc == 0:
            deleted += 1

    ok = deleted > 0
    _log(logger, "tweak_ultimate_remove", f"deleted={deleted}", success=ok)
    return _result(ok, f"Removed Ultimate Performance profiles: {deleted}")


# ---------------------------------------------------------------------------
# New tweaks — Essential additions
# ---------------------------------------------------------------------------

def _tw_disable_sysmain(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok_cfg = _set_service_start("SysMain", "disabled")
    ok_stop = _stop_service("SysMain")
    ok = ok_cfg or ok_stop
    _log(logger, "tweak_sysmain", "Disabled SysMain (Superfetch)", success=ok)
    return _result(ok, "SysMain (Superfetch) disabled")


def _tw_disable_search_indexing(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok_cfg = _set_service_start("WSearch", "disabled")
    ok_stop = _stop_service("WSearch")
    ok = ok_cfg or ok_stop
    _log(logger, "tweak_wsearch", "Disabled WSearch indexing", success=ok)
    return _result(ok, "Windows Search Indexing disabled")


def _tw_disable_fast_startup(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SYSTEM\CurrentControlSet\Control\Session Manager\Power",
        "HiberbootEnabled", 0, winreg.REG_DWORD,
    )
    _log(logger, "tweak_fast_startup", "Disabled Fast Startup", success=ok)
    return _result(ok, "Fast Startup disabled")


def _tw_enable_long_paths(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SYSTEM\CurrentControlSet\Control\FileSystem",
        "LongPathsEnabled", 1, winreg.REG_DWORD,
    )
    _log(logger, "tweak_long_paths", "Enabled long file paths", success=ok)
    return _result(ok, "Long file paths (>260 chars) enabled")


def _tw_disable_startup_delay(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok1 = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\Serialize",
        "StartupDelayInMSec", 0, winreg.REG_DWORD,
    )
    ok2 = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon",
        "AutoRestartShell", 1, winreg.REG_DWORD,
    )
    ok = ok1 or ok2
    _log(logger, "tweak_startup_delay", "Disabled startup delay", success=ok)
    return _result(ok, "Startup app delay removed")


def _tw_disable_error_reporting(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok1 = _set_service_start("WerSvc", "disabled")
    _stop_service("WerSvc")
    ok2 = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Microsoft\Windows\Windows Error Reporting",
        "Disabled", 1, winreg.REG_DWORD,
    )
    ok = ok1 or ok2
    _log(logger, "tweak_wer", "Disabled Windows Error Reporting", success=ok)
    return _result(ok, "Windows Error Reporting disabled")


def _tw_disable_remote_assistance(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok1 = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SYSTEM\CurrentControlSet\Control\Remote Assistance",
        "fAllowToGetHelp", 0, winreg.REG_DWORD,
    )
    ok2 = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Policies\Microsoft\Windows NT\Terminal Services",
        "fAllowToGetHelp", 0, winreg.REG_DWORD,
    )
    ok = ok1 or ok2
    _log(logger, "tweak_remote_assistance", "Disabled Remote Assistance", success=ok)
    return _result(ok, "Remote Assistance disabled")


# ---------------------------------------------------------------------------
# New tweaks — Performance
# ---------------------------------------------------------------------------

def _tw_perf_ntfs_timestamps(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    rc, _, _ = _run(["fsutil", "behavior", "set", "disablelastaccess", "1"], timeout=15)
    ok = rc == 0
    _log(logger, "tweak_ntfs_ts", "Disabled NTFS last access timestamps", success=ok)
    return _result(ok, "NTFS last-access timestamp updates disabled")


def _tw_perf_disable_83names(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    rc, _, _ = _run(["fsutil", "behavior", "set", "disable8dot3", "1"], timeout=15)
    ok = rc == 0
    _log(logger, "tweak_8dot3", "Disabled 8.3 filename creation", success=ok)
    return _result(ok, "8.3 filename creation disabled")


def _tw_perf_hags(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers",
        "HwSchMode", 2, winreg.REG_DWORD,
    )
    _log(logger, "tweak_hags", "Enabled HAGS", success=ok)
    return _result(ok, "Hardware-Accelerated GPU Scheduling (HAGS) enabled — restart required")


def _tw_perf_visual_effects(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects",
        "VisualFXSetting", 2, winreg.REG_DWORD,
    )
    # Also disable specific animations
    _set_reg(winreg.HKEY_CURRENT_USER,
             r"Control Panel\Desktop\WindowMetrics", "MinAnimate", "0", winreg.REG_SZ)
    _log(logger, "tweak_visual_effects", "Set visual effects to performance", success=ok)
    return _result(ok, "Visual effects set to best performance")


def _tw_perf_network_throttling(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile",
        "NetworkThrottlingIndex", 0xFFFFFFFF, winreg.REG_DWORD,
    )
    _log(logger, "tweak_net_throttle", "Disabled network throttling", success=ok)
    return _result(ok, "Network throttling index disabled")


def _tw_perf_disable_dynamic_tick(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    rc, _, _ = _run(["bcdedit", "/set", "disabledynamictick", "yes"], timeout=15)
    ok = rc == 0
    _log(logger, "tweak_dynamic_tick", "Disabled dynamic tick", success=ok)
    return _result(ok, "Dynamic tick disabled — restart required")


def _tw_perf_timer_resolution(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile",
        "SystemResponsiveness", 0, winreg.REG_DWORD,
    )
    _log(logger, "tweak_timer_res", "Set system responsiveness hint", success=ok)
    return _result(ok, "System timer responsiveness hint set to 0 (games/audio priority)")


# ---------------------------------------------------------------------------
# New tweaks — Privacy
# ---------------------------------------------------------------------------

def _tw_priv_advertising_id(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo",
        "Enabled", 0, winreg.REG_DWORD,
    )
    _log(logger, "tweak_adv_id", "Disabled advertising ID", success=ok)
    return _result(ok, "Advertising ID disabled")


def _tw_priv_tailored_experiences(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok1 = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Privacy",
        "TailoredExperiencesWithDiagnosticDataEnabled", 0, winreg.REG_DWORD,
    )
    ok2 = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Policies\Microsoft\Windows\CloudContent",
        "DisableTailoredExperiencesWithDiagnosticData", 1, winreg.REG_DWORD,
    )
    ok = ok1 or ok2
    _log(logger, "tweak_tailored", "Disabled tailored experiences", success=ok)
    return _result(ok, "Tailored experiences disabled")


def _tw_priv_lockscreen_ads(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    keys = [
        _set_reg(winreg.HKEY_CURRENT_USER,
                 r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager",
                 "RotatingLockScreenEnabled", 0, winreg.REG_DWORD),
        _set_reg(winreg.HKEY_CURRENT_USER,
                 r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager",
                 "RotatingLockScreenOverlayEnabled", 0, winreg.REG_DWORD),
        _set_reg(winreg.HKEY_CURRENT_USER,
                 r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager",
                 "SubscribedContent-338387Enabled", 0, winreg.REG_DWORD),
    ]
    ok = any(keys)
    _log(logger, "tweak_lockscreen_ads", "Disabled lock screen ads", success=ok)
    return _result(ok, "Lock screen ads/tips disabled")


def _tw_priv_start_ads(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    vals = {
        "ContentDeliveryAllowed": 0,
        "OemPreInstalledAppsEnabled": 0,
        "PreInstalledAppsEnabled": 0,
        "PreInstalledAppsEverEnabled": 0,
        "SilentInstalledAppsEnabled": 0,
        "SubscribedContent-338388Enabled": 0,
        "SubscribedContent-310093Enabled": 0,
        "SystemPaneSuggestionsEnabled": 0,
    }
    ok = False
    for name, val in vals.items():
        if _set_reg(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager",
                    name, val, winreg.REG_DWORD):
            ok = True
    _log(logger, "tweak_start_ads", "Disabled Start Menu ads", success=ok)
    return _result(ok, "Start Menu suggested/promoted apps disabled")


def _tw_priv_feedback(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok1 = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Siuf\Rules",
        "NumberOfSIUFInPeriod", 0, winreg.REG_DWORD,
    )
    ok2 = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Policies\Microsoft\Windows\DataCollection",
        "DoNotShowFeedbackNotifications", 1, winreg.REG_DWORD,
    )
    ok = ok1 or ok2
    _log(logger, "tweak_feedback", "Disabled feedback notifications", success=ok)
    return _result(ok, "Feedback notifications disabled")


def _tw_priv_maps_download(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok1 = _set_service_start("MapsBroker", "disabled")
    _stop_service("MapsBroker")
    ok2 = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Policies\Microsoft\Windows\Maps",
        "AutoDownloadAndUpdateMapData", 0, winreg.REG_DWORD,
    )
    ok = ok1 or ok2
    _log(logger, "tweak_maps", "Disabled maps auto-download", success=ok)
    return _result(ok, "Maps auto-download disabled")


def _tw_priv_cortana(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok1 = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Policies\Microsoft\Windows\Windows Search",
        "AllowCortana", 0, winreg.REG_DWORD,
    )
    ok2 = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Search",
        "CortanaEnabled", 0, winreg.REG_DWORD,
    )
    ok = ok1 or ok2
    _log(logger, "tweak_cortana", "Disabled Cortana", success=ok)
    return _result(ok, "Cortana disabled")


def _tw_priv_recent_clear(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok1 = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer",
        "ClearRecentDocsOnExit", 1, winreg.REG_DWORD,
    )
    ok2 = _set_reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer",
        "NoRecentDocsHistory", 1, winreg.REG_DWORD,
    )
    ok = ok1 or ok2
    _log(logger, "tweak_recent_clear", "Enabled clear recent on exit", success=ok)
    return _result(ok, "Recent files/docs cleared on logout")


def _tw_priv_clipboard_history(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Policies\Microsoft\Windows\System",
        "AllowClipboardHistory", 0, winreg.REG_DWORD,
    )
    _log(logger, "tweak_clipboard_hist", "Disabled clipboard history", success=ok)
    return _result(ok, "Clipboard history (Win+V) disabled")


# ---------------------------------------------------------------------------
# New tweaks — Gaming
# ---------------------------------------------------------------------------

def _tw_game_disable_gamebar(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    keys = [
        _set_reg(winreg.HKEY_CURRENT_USER,
                 r"Software\Microsoft\Windows\CurrentVersion\GameDVR",
                 "AppCaptureEnabled", 0, winreg.REG_DWORD),
        _set_reg(winreg.HKEY_LOCAL_MACHINE,
                 r"SOFTWARE\Policies\Microsoft\Windows\GameDVR",
                 "AllowGameDVR", 0, winreg.REG_DWORD),
        _set_reg(winreg.HKEY_CURRENT_USER,
                 r"System\GameConfigStore",
                 "GameDVR_Enabled", 0, winreg.REG_DWORD),
        _set_reg(winreg.HKEY_CURRENT_USER,
                 r"Software\Microsoft\GameBar",
                 "UseNexusForGameBarEnabled", 0, winreg.REG_DWORD),
        _set_reg(winreg.HKEY_CURRENT_USER,
                 r"Software\Microsoft\GameBar",
                 "AutoGameModeEnabled", 0, winreg.REG_DWORD),
    ]
    ok = any(keys)
    _log(logger, "tweak_gamebar", "Disabled Xbox Game Bar", success=ok)
    return _result(ok, "Xbox Game Bar disabled")


def _probe_game_mode() -> bool | None:
    if not _is_windows():
        return None
    val = _read_reg(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\GameBar", "AutoGameModeEnabled")
    return val == 1


def _toggle_game_mode(enable: bool, logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(winreg.HKEY_CURRENT_USER,
                  r"Software\Microsoft\GameBar",
                  "AutoGameModeEnabled", 1 if enable else 0, winreg.REG_DWORD)
    _log(logger, "tweak_game_mode", f"Game Mode={'on' if enable else 'off'}", success=ok)
    return _result(ok, f"Game Mode {'enabled' if enable else 'disabled'}")


def _tw_game_gpu_high_perf(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers",
        "TdrLevel", 0, winreg.REG_DWORD,
    )
    ok2 = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games",
        "GPU Priority", 8, winreg.REG_DWORD,
    )
    ok3 = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games",
        "Priority", 6, winreg.REG_DWORD,
    )
    ok4 = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games",
        "Scheduling Category", "High", winreg.REG_SZ,
    )
    result_ok = ok or ok2 or ok3 or ok4
    _log(logger, "tweak_gpu_perf", "Set GPU high performance hints", success=result_ok)
    return _result(result_ok, "GPU/game scheduler priority set to High")


# ---------------------------------------------------------------------------
# New tweaks — Security
# ---------------------------------------------------------------------------

def _tw_sec_disable_smbv1(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    rc1, _, _ = _run(
        ["powershell", "-NoProfile", "-Command",
         "Set-SmbServerConfiguration -EnableSMB1Protocol $false -Force"],
        timeout=30,
    )
    rc2, _, _ = _run(
        ["powershell", "-NoProfile", "-Command",
         "Disable-WindowsOptionalFeature -Online -FeatureName SMB1Protocol -NoRestart"],
        timeout=60,
    )
    ok = rc1 == 0 or rc2 == 0
    _log(logger, "tweak_smbv1", "Disabled SMBv1", success=ok)
    return _result(ok, "SMBv1 disabled — restart may be required")


def _tw_sec_disable_autorun(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok1 = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer",
        "NoDriveTypeAutoRun", 0xFF, winreg.REG_DWORD,
    )
    ok2 = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Policies\Microsoft\Windows\Explorer",
        "NoAutoplayfornonVolume", 1, winreg.REG_DWORD,
    )
    ok = ok1 or ok2
    _log(logger, "tweak_autorun", "Disabled AutoRun/AutoPlay", success=ok)
    return _result(ok, "AutoRun/AutoPlay disabled for all drives")


def _tw_sec_disable_llmnr(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Policies\Microsoft\Windows NT\DNSClient",
        "EnableMulticast", 0, winreg.REG_DWORD,
    )
    _log(logger, "tweak_llmnr", "Disabled LLMNR", success=ok)
    return _result(ok, "LLMNR disabled — reduces MitM attack surface")


def _tw_sec_disable_netbios(logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(
        winreg.HKEY_LOCAL_MACHINE,
        r"SYSTEM\CurrentControlSet\Services\NetBT\Parameters",
        "NetbiosOptions", 2, winreg.REG_DWORD,
    )
    _log(logger, "tweak_netbios", "Disabled NetBIOS over TCP/IP", success=ok)
    return _result(ok, "NetBIOS over TCP/IP disabled")


# ---------------------------------------------------------------------------
# New tweaks — UI/UX preference toggles
# ---------------------------------------------------------------------------

def _probe_clock_seconds() -> bool | None:
    if not _is_windows():
        return None
    val = _read_reg(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
                    "ShowSecondsInSystemClock")
    return val == 1


def _toggle_clock_seconds(enable: bool, logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(winreg.HKEY_CURRENT_USER,
                  r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
                  "ShowSecondsInSystemClock", 1 if enable else 0, winreg.REG_DWORD)
    _log(logger, "tweak_clock_sec", f"clock_seconds={'on' if enable else 'off'}", success=ok)
    return _result(ok, f"Clock seconds {'shown' if enable else 'hidden'}")


def _probe_transparency() -> bool | None:
    if not _is_windows():
        return None
    val = _read_reg(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                    "EnableTransparency")
    return val == 1


def _toggle_transparency(enable: bool, logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(winreg.HKEY_CURRENT_USER,
                  r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                  "EnableTransparency", 1 if enable else 0, winreg.REG_DWORD)
    _log(logger, "tweak_transparency", f"transparency={'on' if enable else 'off'}", success=ok)
    return _result(ok, f"Transparency effects {'enabled' if enable else 'disabled'}")


def _probe_animations() -> bool | None:
    if not _is_windows():
        return None
    val = _read_reg(winreg.HKEY_CURRENT_USER,
                    r"Control Panel\Desktop\WindowMetrics",
                    "MinAnimate")
    return val != "0"


def _toggle_animations(enable: bool, logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(winreg.HKEY_CURRENT_USER,
                  r"Control Panel\Desktop\WindowMetrics",
                  "MinAnimate", "1" if enable else "0", winreg.REG_SZ)
    _log(logger, "tweak_animations", f"animations={'on' if enable else 'off'}", success=ok)
    return _result(ok, f"Window animations {'enabled' if enable else 'disabled'}")


def _probe_compact_explorer() -> bool | None:
    if not _is_windows():
        return None
    val = _read_reg(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
                    "UseCompactMode")
    return val == 1


def _toggle_compact_explorer(enable: bool, logger) -> tuple[bool, str]:
    if not _is_windows():
        return _result(False, "Windows only")
    ok = _set_reg(winreg.HKEY_CURRENT_USER,
                  r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
                  "UseCompactMode", 1 if enable else 0, winreg.REG_DWORD)
    _log(logger, "tweak_compact", f"compact_mode={'on' if enable else 'off'}", success=ok)
    return _result(ok, f"Explorer compact mode {'enabled' if enable else 'disabled'}")


# ---------------------------------------------------------------------------
# Definitions
# ---------------------------------------------------------------------------

_TWEAKS: list[TweakDef] = [
    # Essential
    TweakDef("create_restore_point", "Create Restore Point", "essential", action_fn=_tw_create_restore_point),
    TweakDef("delete_temporary_files", "Delete Temporary Files", "essential", action_fn=_tw_delete_temp_files),
    TweakDef("disable_consumer_features", "Disable ConsumerFeatures", "essential", action_fn=_tw_disable_consumer_features),
    TweakDef("disable_telemetry", "Disable Telemetry", "essential", action_fn=_tw_disable_telemetry),
    TweakDef("disable_activity_history", "Disable Activity History", "essential", action_fn=_tw_disable_activity_history),
    TweakDef("disable_explorer_folder_discovery", "Disable Explorer Automatic Folder Discovery", "essential", action_fn=_tw_disable_explorer_folder_discovery),
    TweakDef("disable_game_dvr", "Disable GameDVR", "essential", action_fn=_tw_disable_game_dvr),
    TweakDef("disable_hibernation", "Disable Hibernation", "essential", action_fn=_tw_disable_hibernation),
    TweakDef("disable_homegroup", "Disable Homegroup", "essential", action_fn=_tw_disable_homegroup),
    TweakDef("disable_location_tracking", "Disable Location Tracking", "essential", action_fn=_tw_disable_location_tracking),
    TweakDef("disable_storage_sense", "Disable Storage Sense", "essential", action_fn=_tw_disable_storage_sense),
    TweakDef("disable_wifi_sense", "Disable Wifi-Sense", "essential", action_fn=_tw_disable_wifi_sense),
    TweakDef("enable_end_task_right_click", "Enable End Task With Right Click", "essential", action_fn=_tw_enable_end_task_taskbar),
    TweakDef("run_disk_cleanup", "Run Disk Cleanup", "essential", action_fn=_tw_run_disk_cleanup),
    TweakDef("terminal_default_pwsh7", "Change Windows Terminal default (PowerShell 7)", "essential", action_fn=_tw_set_terminal_pwsh7_default),
    TweakDef("disable_pwsh7_telemetry", "Disable PowerShell 7 Telemetry", "essential", action_fn=_tw_disable_pwsh7_telemetry),
    TweakDef("disable_recall", "Disable Recall", "essential", action_fn=_tw_disable_recall, caution=True),
    TweakDef("set_hibernation_default", "Set Hibernation as default (laptops)", "essential", action_fn=_tw_set_hibernation_default_laptop),
    TweakDef("set_services_manual", "Set Services to Manual", "essential", action_fn=_tw_set_services_manual),
    TweakDef("debloat_edge", "Debloat Edge", "essential", action_fn=_tw_debloat_edge, caution=True),

    # Advanced
    TweakDef("adobe_network_block", "Adobe Network Block", "advanced", action_fn=_tw_adobe_network_block, caution=True),
    TweakDef("adobe_debloat", "Adobe Debloat", "advanced", action_fn=_tw_adobe_debloat, caution=True),
    TweakDef("disable_ipv6", "Disable IPv6", "advanced", action_fn=_tw_disable_ipv6, caution=True),
    TweakDef("prefer_ipv4", "Prefer IPv4 over IPv6", "advanced", action_fn=_tw_prefer_ipv4),
    TweakDef("disable_teredo", "Disable Teredo", "advanced", action_fn=_tw_disable_teredo),
    TweakDef("disable_background_apps", "Disable Background Apps", "advanced", action_fn=_tw_disable_background_apps),
    TweakDef("disable_fullscreen_opt", "Disable Fullscreen Optimizations", "advanced", action_fn=_tw_disable_fullscreen_optimizations),
    TweakDef("disable_copilot", "Disable Microsoft Copilot", "advanced", action_fn=_tw_disable_copilot),
    TweakDef("disable_intel_lms", "Disable Intel MM (vPro LMS)", "advanced", action_fn=_tw_disable_intel_lms),
    TweakDef("disable_notification_center", "Disable Notification Tray/Calendar", "advanced", action_fn=_tw_disable_notification_center),
    TweakDef("disable_wpbt", "Disable Windows Platform Binary Table (WPBT)", "advanced", action_fn=_tw_disable_wpbt, caution=True),
    TweakDef("set_display_performance", "Set Display for Performance", "advanced", action_fn=_tw_set_display_performance),
    TweakDef("classic_right_click", "Set Classic Right-Click Menu", "advanced", action_fn=_tw_set_classic_context_menu),
    TweakDef("set_time_utc", "Set Time to UTC (Dual Boot)", "advanced", action_fn=_tw_set_utc_dual_boot),
    TweakDef("remove_all_store_apps", "Remove ALL MS Store Apps", "advanced", action_fn=_tw_remove_all_store_apps, caution=True),
    TweakDef("remove_edge", "Remove Microsoft Edge", "advanced", action_fn=_tw_remove_edge, caution=True),
    TweakDef("remove_home_gallery", "Remove Home and Gallery from Explorer", "advanced", action_fn=_tw_remove_home_gallery_explorer),
    TweakDef("remove_onedrive", "Remove OneDrive", "advanced", action_fn=_tw_remove_onedrive, caution=True),
    TweakDef("block_razer_installs", "Block Razer Software Installs", "advanced", action_fn=_tw_block_razer_installs),
    TweakDef("run_ooshutup10", "Run O&O Shutup10", "advanced", action_fn=_tw_run_ooshutup10, caution=True),

    # Preferences toggles
    TweakDef("pref_dark_theme", "Dark Theme for Windows", "preferences", kind="toggle", set_fn=_toggle_dark_theme, probe_fn=_probe_dark_theme),
    TweakDef("pref_bing_start", "Bing Search in Start Menu", "preferences", kind="toggle", set_fn=_toggle_bing_start, probe_fn=_probe_bing_start),
    TweakDef("pref_numlock", "NumLock on Startup", "preferences", kind="toggle", set_fn=_toggle_numlock, probe_fn=_probe_numlock),
    TweakDef("pref_verbose_logon", "Verbose Messages During Logon", "preferences", kind="toggle", set_fn=_toggle_verbose_logon, probe_fn=_probe_verbose_logon),
    TweakDef("pref_start_recommendations", "Recommendations in Start Menu", "preferences", kind="toggle", set_fn=_toggle_start_recommendations, probe_fn=_probe_start_recommendations),
    TweakDef("pref_settings_home", "Remove Settings Home Page", "preferences", kind="toggle", set_fn=_toggle_settings_home_removed, probe_fn=_probe_settings_home_removed),
    TweakDef("pref_snap_window", "Snap Window", "preferences", kind="toggle", set_fn=_toggle_snap_window, probe_fn=_probe_snap_window),
    TweakDef("pref_snap_flyout", "Snap Assist Flyout", "preferences", kind="toggle", set_fn=_toggle_snap_flyout, probe_fn=_probe_snap_flyout),
    TweakDef("pref_snap_suggestion", "Snap Assist Suggestion", "preferences", kind="toggle", set_fn=_toggle_snap_suggestion, probe_fn=_probe_snap_suggestion),
    TweakDef("pref_mouse_accel", "Mouse Acceleration", "preferences", kind="toggle", set_fn=_toggle_mouse_accel, probe_fn=_probe_mouse_accel),
    TweakDef("pref_sticky_keys", "Sticky Keys", "preferences", kind="toggle", set_fn=_toggle_sticky_keys, probe_fn=_probe_sticky_keys),
    TweakDef("pref_hidden_files", "Show Hidden Files", "preferences", kind="toggle", set_fn=_toggle_hidden_files, probe_fn=_probe_hidden_files),
    TweakDef("pref_file_ext", "Show File Extensions", "preferences", kind="toggle", set_fn=_toggle_file_ext, probe_fn=_probe_file_ext),
    TweakDef("pref_search_btn", "Search Button in Taskbar", "preferences", kind="toggle", set_fn=_toggle_search_button, probe_fn=_probe_search_button),
    TweakDef("pref_task_view", "Task View Button in Taskbar", "preferences", kind="toggle", set_fn=_toggle_task_view, probe_fn=_probe_task_view),
    TweakDef("pref_taskbar_center", "Center Taskbar Items", "preferences", kind="toggle", set_fn=_toggle_taskbar_center, probe_fn=_probe_taskbar_center),
    TweakDef("pref_widgets", "Widgets Button in Taskbar", "preferences", kind="toggle", set_fn=_toggle_widgets, probe_fn=_probe_widgets),
    TweakDef("pref_detailed_bsod", "Detailed BSoD", "preferences", kind="toggle", set_fn=_toggle_detailed_bsod, probe_fn=_probe_detailed_bsod),

    # Essential — additions
    TweakDef("disable_sysmain",         "Disable SysMain / Superfetch",          "essential", action_fn=_tw_disable_sysmain),
    TweakDef("disable_search_indexing", "Disable Windows Search Indexing",        "essential", action_fn=_tw_disable_search_indexing),
    TweakDef("disable_fast_startup",    "Disable Fast Startup",                   "essential", action_fn=_tw_disable_fast_startup),
    TweakDef("enable_long_paths",       "Enable Long File Paths (>260 chars)",    "essential", action_fn=_tw_enable_long_paths),
    TweakDef("disable_startup_delay",   "Remove Startup App Delay",               "essential", action_fn=_tw_disable_startup_delay),
    TweakDef("disable_error_reporting", "Disable Windows Error Reporting",        "essential", action_fn=_tw_disable_error_reporting),
    TweakDef("disable_remote_assist",   "Disable Remote Assistance",              "essential", action_fn=_tw_disable_remote_assistance),

    # Performance
    TweakDef("add_activate_ultimate_perf", "Add and Activate Ultimate Performance Profile", "performance", action_fn=_tw_add_activate_ultimate_perf),
    TweakDef("remove_ultimate_perf",       "Remove Ultimate Performance Profile",           "performance", action_fn=_tw_remove_ultimate_perf, caution=True),
    TweakDef("perf_ntfs_timestamps",       "Disable NTFS Last-Access Timestamps",           "performance", action_fn=_tw_perf_ntfs_timestamps),
    TweakDef("perf_disable_83names",       "Disable 8.3 Filename Creation",                 "performance", action_fn=_tw_perf_disable_83names),
    TweakDef("perf_hags",                  "Enable Hardware-Accelerated GPU Scheduling",     "performance", action_fn=_tw_perf_hags),
    TweakDef("perf_visual_effects",        "Set Visual Effects to Best Performance",         "performance", action_fn=_tw_perf_visual_effects),
    TweakDef("perf_network_throttling",    "Disable Network Throttling Index",               "performance", action_fn=_tw_perf_network_throttling),
    TweakDef("perf_disable_dynamic_tick",  "Disable Dynamic Tick",                           "performance", action_fn=_tw_perf_disable_dynamic_tick, caution=True),
    TweakDef("perf_timer_resolution",      "Set System Timer Responsiveness (games/audio)",  "performance", action_fn=_tw_perf_timer_resolution),

    # Privacy
    TweakDef("priv_advertising_id",        "Disable Advertising ID",                        "privacy", action_fn=_tw_priv_advertising_id),
    TweakDef("priv_tailored_experiences",  "Disable Tailored Experiences",                  "privacy", action_fn=_tw_priv_tailored_experiences),
    TweakDef("priv_lockscreen_ads",        "Disable Lock Screen Ads / Tips",                "privacy", action_fn=_tw_priv_lockscreen_ads),
    TweakDef("priv_start_ads",             "Disable Start Menu Ads / Suggested Apps",       "privacy", action_fn=_tw_priv_start_ads),
    TweakDef("priv_feedback",              "Disable Feedback Notifications",                "privacy", action_fn=_tw_priv_feedback),
    TweakDef("priv_maps_download",         "Disable Maps Auto-Download",                    "privacy", action_fn=_tw_priv_maps_download),
    TweakDef("priv_cortana",               "Disable Cortana",                               "privacy", action_fn=_tw_priv_cortana),
    TweakDef("priv_recent_clear",          "Clear Recent Files/Docs on Logout",             "privacy", action_fn=_tw_priv_recent_clear),
    TweakDef("priv_clipboard_history",     "Disable Clipboard History (Win+V)",             "privacy", action_fn=_tw_priv_clipboard_history),

    # Gaming
    TweakDef("game_disable_gamebar",  "Disable Xbox Game Bar",                             "gaming", action_fn=_tw_game_disable_gamebar),
    TweakDef("game_mode",             "Windows Game Mode",                                  "gaming", kind="toggle", set_fn=_toggle_game_mode, probe_fn=_probe_game_mode),
    TweakDef("game_gpu_high_perf",    "GPU & Game Scheduler High Priority",                 "gaming", action_fn=_tw_game_gpu_high_perf),

    # Security
    TweakDef("sec_disable_smbv1",    "Disable SMBv1",                                      "security", action_fn=_tw_sec_disable_smbv1, caution=True),
    TweakDef("sec_disable_autorun",  "Disable AutoRun / AutoPlay",                          "security", action_fn=_tw_sec_disable_autorun),
    TweakDef("sec_disable_llmnr",    "Disable LLMNR (MitM prevention)",                    "security", action_fn=_tw_sec_disable_llmnr),
    TweakDef("sec_disable_netbios",  "Disable NetBIOS over TCP/IP",                         "security", action_fn=_tw_sec_disable_netbios),

    # UI/UX preference toggles — additions
    TweakDef("pref_clock_seconds",    "Show Seconds in Taskbar Clock",    "preferences", kind="toggle", set_fn=_toggle_clock_seconds,    probe_fn=_probe_clock_seconds),
    TweakDef("pref_transparency",     "Transparency Effects",             "preferences", kind="toggle", set_fn=_toggle_transparency,     probe_fn=_probe_transparency),
    TweakDef("pref_animations",       "Window Animation Effects",         "preferences", kind="toggle", set_fn=_toggle_animations,       probe_fn=_probe_animations),
    TweakDef("pref_compact_explorer", "Compact Mode in File Explorer",    "preferences", kind="toggle", set_fn=_toggle_compact_explorer, probe_fn=_probe_compact_explorer),
]

_TWEAK_MAP = {t.key: t for t in _TWEAKS}

_TWEAK_META: dict[str, dict[str, Any]] = {
    "create_restore_point": {"requires_admin": True},
    "disable_telemetry": {"requires_admin": True, "restart_required": True},
    "disable_hibernation": {"requires_admin": True},
    "set_hibernation_default": {"requires_admin": True},
    "set_services_manual": {"requires_admin": True},
    "disable_ipv6": {"requires_admin": True, "restart_required": True},
    "prefer_ipv4": {"requires_admin": True, "restart_required": True},
    "remove_edge": {"requires_admin": True, "restart_required": True},
    "remove_onedrive": {"requires_admin": True, "restart_required": True},
    "remove_all_store_apps": {"requires_admin": True, "restart_required": True},
    "set_time_utc": {"requires_admin": True, "restart_required": True},
    "disable_recall": {"requires_admin": True, "restart_required": True, "min_build": 26100},
    "enable_end_task_right_click": {"min_build": 22621},
    "disable_copilot": {"min_build": 22621},
    "pref_taskbar_center": {"min_build": 22000},
    "pref_widgets": {"min_build": 22000},
    "remove_home_gallery": {"min_build": 22621},
    "pref_verbose_logon": {"restart_required": True},
    "pref_numlock": {"restart_required": True},
    "pref_detailed_bsod": {"restart_required": True},
}

_CONFLICT_RULES = [
    {
        "keys": ("disable_ipv6", "prefer_ipv4"),
        "message": "Disable IPv6 and Prefer IPv4 change the same stack policy and conflict.",
    },
    {
        "keys": ("disable_hibernation", "set_hibernation_default"),
        "message": "Disable Hibernation conflicts with setting hibernation as default action.",
    },
    {
        "keys": ("add_activate_ultimate_perf", "remove_ultimate_perf"),
        "message": "Add/Activate Ultimate Performance conflicts with removing that profile.",
    },
]


def _meta_for(key: str) -> dict[str, Any]:
    m = {
        "requires_admin": False,
        "restart_required": False,
        "min_build": 0,
        "max_build": 0,
        "tags": [],
    }
    m.update(_TWEAK_META.get(key, {}))
    return m


def _compatibility_for_key(key: str) -> dict[str, Any]:
    p = _platform_info()
    if not p.get("is_windows"):
        return {
            "compatible": False,
            "reason": "This tweak is available on Windows only.",
            "build": int(p.get("build") or 0),
        }

    meta = _meta_for(key)
    build = int(p.get("build") or 0)
    min_build = int(meta.get("min_build") or 0)
    max_build = int(meta.get("max_build") or 0)

    if min_build and build and build < min_build:
        return {
            "compatible": False,
            "reason": f"Requires Windows build {min_build} or newer.",
            "build": build,
        }
    if max_build and build and build > max_build:
        return {
            "compatible": False,
            "reason": f"Supports up to Windows build {max_build}.",
            "build": build,
        }

    return {"compatible": True, "reason": "", "build": build}


def _allocate_batch_id() -> int:
    state = _load_state()
    batch_id = int(state.get("next_batch_id", 1))
    state["next_batch_id"] = batch_id + 1
    _save_state()
    return batch_id


def _record_batch(batch_id: int, keys: list[str], labels: list[str], change_ids: list[int], success: bool):
    state = _load_state()
    state.setdefault("batches", []).append(
        {
            "id": batch_id,
            "timestamp": _now_iso(),
            "keys": keys,
            "labels": labels,
            "change_ids": change_ids,
            "success": bool(success),
            "undone": False,
            "undone_at": "",
        }
    )
    _trim_history(state)
    _save_state()


def _record_change(
    key: str,
    label: str,
    ops: list[dict[str, Any]],
    reversible: bool,
    batch_id: int | None,
    requires_admin: bool,
    restart_required: bool,
) -> int:
    state = _load_state()
    cid = int(state.get("next_change_id", 1))
    state["next_change_id"] = cid + 1
    state.setdefault("changes", []).append(
        {
            "id": cid,
            "timestamp": _now_iso(),
            "key": key,
            "label": label,
            "batch_id": batch_id,
            "reversible": bool(reversible),
            "ops": ops,
            "undone": False,
            "undone_at": "",
            "requires_admin": bool(requires_admin),
            "restart_required": bool(restart_required),
        }
    )
    _trim_history(state)
    _save_state()
    return cid


def _add_pending_restart(key: str, label: str, batch_id: int | None):
    state = _load_state()
    pending = state.setdefault("pending_restart", [])
    pending = [p for p in pending if p.get("key") != key]
    pending.append(
        {
            "id": str(uuid.uuid4()),
            "timestamp": _now_iso(),
            "key": key,
            "label": label,
            "batch_id": batch_id,
        }
    )
    state["pending_restart"] = pending
    _save_state()


def _remove_pending_restart_for_key(key: str):
    state = _load_state()
    state["pending_restart"] = [p for p in state.get("pending_restart", []) if p.get("key") != key]
    _save_state()


def get_pending_restart() -> dict[str, Any]:
    state = _load_state()
    rows = list(state.get("pending_restart", []))
    rows.sort(key=lambda x: str(x.get("timestamp", "")), reverse=True)
    return {"count": len(rows), "items": rows}


def clear_pending_restart() -> dict[str, Any]:
    state = _load_state()
    count = len(state.get("pending_restart", []))
    state["pending_restart"] = []
    _save_state()
    return {"ok": True, "cleared": count}


def _apply_undo_op(op: dict[str, Any]) -> tuple[bool, str]:
    kind = str(op.get("kind", ""))

    if kind == "registry_set":
        hive = _name_to_hive(str(op.get("hive", "")))
        if hive is None:
            return False, "Unknown registry hive"
        value = _deserialize_reg_value(op.get("value"))
        ok = _set_reg(
            hive,
            str(op.get("key_path", "")),
            str(op.get("value_name", "")),
            value,
            int(op.get("value_type", winreg.REG_SZ if _is_windows() else 1)),
            capture=False,
        )
        return ok, "registry_set"

    if kind == "registry_delete":
        hive = _name_to_hive(str(op.get("hive", "")))
        if hive is None:
            return False, "Unknown registry hive"
        ok = _delete_reg(
            hive,
            str(op.get("key_path", "")),
            str(op.get("value_name", "")),
            capture=False,
        )
        return ok, "registry_delete"

    if kind == "service_start":
        ok = _set_service_start(str(op.get("service_name", "")), str(op.get("mode", "demand")), capture=False)
        return ok, "service_start"

    if kind == "power_scheme":
        ok = _set_power_scheme(str(op.get("guid", "")), capture=False)
        return ok, "power_scheme"

    return False, f"Unknown undo operation: {kind}"


def undo_last_change(logger) -> dict[str, Any]:
    state = _load_state()
    changes = state.get("changes", [])
    target = None
    for c in reversed(changes):
        if c.get("undone"):
            continue
        if c.get("reversible") and c.get("ops"):
            target = c
            break

    if not target:
        return {"ok": False, "message": "No reversible change available."}

    ok_count = 0
    fail: list[str] = []
    for op in reversed(target.get("ops", [])):
        ok, tag = _apply_undo_op(op)
        if ok:
            ok_count += 1
        else:
            fail.append(tag)

    success = len(fail) == 0
    if success:
        target["undone"] = True
        target["undone_at"] = _now_iso()
        _remove_pending_restart_for_key(str(target.get("key", "")))

    _save_state()
    _log(
        logger,
        "tweak_undo_change",
        f"id={target.get('id')} ok_ops={ok_count} fail_ops={len(fail)}",
        success=success,
    )
    return {
        "ok": success,
        "change_id": target.get("id"),
        "label": target.get("label"),
        "ok_ops": ok_count,
        "failed_ops": len(fail),
        "fail_tags": fail,
        "message": "Undo completed" if success else "Undo completed with errors",
    }


def undo_last_batch(logger) -> dict[str, Any]:
    state = _load_state()
    batches = state.get("batches", [])
    target = next((b for b in reversed(batches) if not b.get("undone")), None)
    if not target:
        return {"ok": False, "message": "No batch to undo."}

    changes_by_id = {int(c.get("id", -1)): c for c in state.get("changes", [])}
    ordered_changes = []
    for cid in target.get("change_ids", []):
        c = changes_by_id.get(int(cid))
        if not c:
            continue
        if c.get("undone"):
            continue
        if not c.get("reversible"):
            continue
        ordered_changes.append(c)

    ok_ops = 0
    failed: list[str] = []

    for c in reversed(ordered_changes):
        for op in reversed(c.get("ops", [])):
            ok, tag = _apply_undo_op(op)
            if ok:
                ok_ops += 1
            else:
                failed.append(f"{c.get('key')}: {tag}")
        if not failed:
            c["undone"] = True
            c["undone_at"] = _now_iso()
            _remove_pending_restart_for_key(str(c.get("key", "")))

    success = len(failed) == 0
    if success:
        target["undone"] = True
        target["undone_at"] = _now_iso()

    _save_state()
    _log(logger, "tweak_undo_batch", f"id={target.get('id')} fail_ops={len(failed)}", success=success)
    return {
        "ok": success,
        "batch_id": target.get("id"),
        "ok_ops": ok_ops,
        "failed_ops": len(failed),
        "fail_tags": failed,
        "message": "Batch undo completed" if success else "Batch undo completed with errors",
    }


def get_undo_overview(limit: int = 12) -> dict[str, Any]:
    state = _load_state()
    changes = list(state.get("changes", []))[-max(1, limit):]
    batches = list(state.get("batches", []))[-max(1, limit):]
    changes.reverse()
    batches.reverse()
    return {
        "changes": changes,
        "batches": batches,
    }


def _capture_metrics(logger) -> dict[str, Any]:
    metrics: dict[str, Any] = {"timestamp": _now_iso()}

    try:
        import psutil

        metrics["cpu_percent"] = float(psutil.cpu_percent(interval=0.15))
        vm = psutil.virtual_memory()
        metrics["ram_percent"] = float(vm.percent)
        metrics["ram_used"] = int(vm.used)
        root = "C:\\" if _is_windows() else "/"
        du = psutil.disk_usage(root)
        metrics["disk_free"] = int(du.free)
    except Exception:
        pass

    try:
        from core.startup import get_startup_entries

        entries = get_startup_entries(logger)
        metrics["startup_enabled"] = sum(1 for e in entries if e.get("enabled"))
    except Exception:
        pass

    try:
        from core.optimizer import list_optimizable_services

        svcs = list_optimizable_services(logger)
        metrics["optional_services_running"] = sum(1 for s in svcs if str(s.get("status", "")).lower() == "running")
    except Exception:
        pass

    active = _get_active_power_scheme_guid()
    if active:
        metrics["power_active_guid"] = active

    return metrics


def _metrics_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    delta: dict[str, Any] = {}
    for k, bv in before.items():
        av = after.get(k)
        if isinstance(bv, (int, float)) and isinstance(av, (int, float)):
            delta[k] = av - bv
    return delta


def _write_benchmark_report(payload: dict[str, Any]) -> str:
    p = Path("logs") / f"tweak_benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        return ""
    return str(p)


def detect_conflicts(keys: list[str]) -> list[str]:
    uniq = set(keys)
    rows: list[str] = []
    for rule in _CONFLICT_RULES:
        a, b = rule["keys"]
        if a in uniq and b in uniq:
            rows.append(str(rule["message"]))

    # Current-state conflict hints for IPv6 policy.
    if _is_windows():
        v = _read_reg(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters",
            "DisabledComponents",
        )
        try:
            cur = int(v) if v is not None else None
        except Exception:
            cur = None

        if "disable_ipv6" in uniq and cur == 0x20:
            rows.append("Current policy already prefers IPv4 (0x20). Applying Disable IPv6 will override it.")
        if "prefer_ipv4" in uniq and cur == 0xFF:
            rows.append("Current policy already disables IPv6 (0xFF). Applying Prefer IPv4 will override it.")

    return rows


def list_groups() -> list[dict[str, str]]:
    return [{"key": k, "label": v} for k, v in _GROUPS.items()]


def list_all_tweaks(group: str | None = None) -> list[dict[str, Any]]:
    state = _load_state()
    favorites = set(state.get("favorites", []))
    rows: list[dict[str, Any]] = []

    for t in _TWEAKS:
        if group and t.group != group:
            continue

        cur_state: bool | None = None
        if t.kind == "toggle" and t.probe_fn:
            try:
                cur_state = t.probe_fn()
            except Exception:
                cur_state = None

        meta = _meta_for(t.key)
        comp = _compatibility_for_key(t.key)

        rows.append(
            {
                "key": t.key,
                "label": t.label,
                "group": t.group,
                "kind": t.kind,
                "caution": t.caution,
                "state": cur_state,
                "favorite": t.key in favorites,
                "requires_admin": bool(meta.get("requires_admin", False)),
                "restart_required": bool(meta.get("restart_required", False)),
                "compatibility": comp,
            }
        )

    return rows


def list_tweaks(group: str) -> list[dict[str, Any]]:
    return list_all_tweaks(group=group)


def search_tweaks(query: str, group: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    q = (query or "").strip().lower()
    all_rows = list_all_tweaks(group=group)
    if not q:
        all_rows.sort(key=lambda x: (not x.get("favorite", False), x.get("label", "")))
        return all_rows[: max(1, limit)]

    out = []
    for r in all_rows:
        text = f"{r.get('label','')} {r.get('key','')}".lower()
        if q in text:
            out.append(r)

    out.sort(key=lambda x: (not x.get("favorite", False), x.get("label", "")))
    return out[: max(1, limit)]


def set_favorite(key: str, is_favorite: bool = True) -> dict[str, Any]:
    if key not in _TWEAK_MAP:
        return {"ok": False, "message": "Unknown tweak key"}

    state = _load_state()
    fav = set(state.get("favorites", []))
    if is_favorite:
        fav.add(key)
    else:
        fav.discard(key)

    state["favorites"] = sorted(fav)
    _save_state()
    return {"ok": True, "key": key, "favorite": is_favorite}


def toggle_favorite(key: str) -> dict[str, Any]:
    state = _load_state()
    fav = set(state.get("favorites", []))
    return set_favorite(key, is_favorite=(key not in fav))


def list_favorites() -> list[dict[str, Any]]:
    rows = [r for r in list_all_tweaks() if r.get("favorite")]
    rows.sort(key=lambda x: x.get("label", ""))
    return rows


def _sanitize_profile_name(name: str) -> str:
    s = (name or "").strip().lower()
    s = re.sub(r"[^a-z0-9_\-]", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def _profile_path(name: str) -> Path:
    safe = _sanitize_profile_name(name)
    return _PROFILE_DIR / f"{safe}.json"


def list_profiles() -> list[dict[str, Any]]:
    _PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for p in sorted(_PROFILE_DIR.glob("*.json")):
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            rows.append(
                {
                    "name": str(obj.get("name", p.stem)),
                    "description": str(obj.get("description", "")),
                    "keys": [k for k in obj.get("keys", []) if k in _TWEAK_MAP],
                    "updated_at": str(obj.get("updated_at", "")),
                    "path": str(p),
                }
            )
        except Exception:
            continue
    return rows


def save_profile(name: str, keys: list[str], description: str = "") -> dict[str, Any]:
    safe = _sanitize_profile_name(name)
    if not safe:
        return {"ok": False, "message": "Invalid profile name"}

    uniq = []
    seen = set()
    for k in keys:
        if k in _TWEAK_MAP and k not in seen:
            uniq.append(k)
            seen.add(k)

    if not uniq:
        return {"ok": False, "message": "Profile must include at least one valid tweak key"}

    _PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "name": safe,
        "description": description,
        "keys": uniq,
        "updated_at": _now_iso(),
    }
    path = _profile_path(safe)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"ok": True, "name": safe, "path": str(path), "count": len(uniq)}


def load_profile(name: str) -> dict[str, Any]:
    p = _profile_path(name)
    if not p.exists():
        return {"ok": False, "message": "Profile not found"}
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "message": str(e)}

    keys = [k for k in obj.get("keys", []) if k in _TWEAK_MAP]
    return {
        "ok": True,
        "name": str(obj.get("name", p.stem)),
        "description": str(obj.get("description", "")),
        "keys": keys,
        "path": str(p),
    }


def delete_profile(name: str) -> dict[str, Any]:
    p = _profile_path(name)
    if not p.exists():
        return {"ok": False, "message": "Profile not found"}
    try:
        p.unlink()
    except Exception as e:
        return {"ok": False, "message": str(e)}
    return {"ok": True, "name": _sanitize_profile_name(name)}


def export_profile(name: str, path: str) -> dict[str, Any]:
    loaded = load_profile(name)
    if not loaded.get("ok"):
        return loaded

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "name": loaded.get("name"),
        "description": loaded.get("description"),
        "keys": loaded.get("keys", []),
        "updated_at": _now_iso(),
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"ok": True, "path": str(out)}


def import_profile(path: str, name_override: str = "") -> dict[str, Any]:
    p = Path(path)
    if not p.exists() or not p.is_file():
        return {"ok": False, "message": "File not found"}
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "message": str(e)}

    profile_name = name_override.strip() or str(obj.get("name", p.stem))
    keys = [k for k in obj.get("keys", []) if k in _TWEAK_MAP]
    return save_profile(profile_name, keys, description=str(obj.get("description", "")))


def _resolve_toggle_desired(tweak: TweakDef, enable: bool | None) -> bool:
    desired = enable
    if desired is None:
        current = None
        if tweak.probe_fn:
            try:
                current = tweak.probe_fn()
            except Exception:
                current = None
        desired = False if current is True else True
    return bool(desired)


def _execute_tweak(tweak: TweakDef, logger, desired_toggle: bool | None, dry_run: bool) -> tuple[bool, str, dict[str, Any]]:
    _begin_exec_context(tweak.key, tweak.label, dry_run=dry_run)
    ok = False
    message = ""
    try:
        if tweak.kind == "toggle":
            if tweak.set_fn is None:
                return False, "Toggle handler missing", {"undo_ops": [], "plan_ops": []}
            ok, message = tweak.set_fn(bool(desired_toggle), logger)
        else:
            if tweak.action_fn is None:
                return False, "Action handler missing", {"undo_ops": [], "plan_ops": []}
            ok, message = tweak.action_fn(logger)
    except Exception as e:
        ok = False
        message = str(e)

    ctx = _end_exec_context()
    return ok, message, ctx


def apply_tweak(
    key: str,
    logger,
    enable: bool | None = None,
    dry_run: bool = False,
    _batch_id: int | None = None,
) -> dict[str, Any]:
    tweak = _TWEAK_MAP.get(key)
    if not tweak:
        return {"ok": False, "key": key, "message": "Unknown tweak"}

    meta = _meta_for(key)
    comp = _compatibility_for_key(key)
    if not comp.get("compatible"):
        return {
            "ok": False,
            "key": key,
            "label": tweak.label,
            "kind": tweak.kind,
            "message": str(comp.get("reason", "Incompatible tweak")),
            "compatibility": comp,
            "requires_admin": bool(meta.get("requires_admin", False)),
            "restart_required": bool(meta.get("restart_required", False)),
            "dry_run": dry_run,
        }

    desired_toggle = _resolve_toggle_desired(tweak, enable) if tweak.kind == "toggle" else None
    ok, message, ctx = _execute_tweak(tweak, logger, desired_toggle, dry_run=dry_run)

    plan_ops = list(ctx.get("plan_ops", []))
    undo_ops = list(ctx.get("undo_ops", []))
    reversible = bool(undo_ops)
    change_id: int | None = None

    if ok and not dry_run:
        change_id = _record_change(
            key=tweak.key,
            label=tweak.label,
            ops=undo_ops,
            reversible=reversible,
            batch_id=_batch_id,
            requires_admin=bool(meta.get("requires_admin", False)),
            restart_required=bool(meta.get("restart_required", False)),
        )
        if bool(meta.get("restart_required", False)):
            _add_pending_restart(tweak.key, tweak.label, _batch_id)

    row = {
        "ok": ok,
        "key": key,
        "label": tweak.label,
        "kind": tweak.kind,
        "message": message,
        "plan": plan_ops,
        "reversible": reversible,
        "undo_count": len(undo_ops),
        "change_id": change_id,
        "compatibility": comp,
        "requires_admin": bool(meta.get("requires_admin", False)),
        "restart_required": bool(meta.get("restart_required", False)),
        "dry_run": dry_run,
    }
    if tweak.kind == "toggle":
        row["enabled"] = bool(desired_toggle)
    return row


def apply_many(keys: list[str], logger, enable: bool | None = None, dry_run: bool = False) -> dict[str, Any]:
    uniq_keys: list[str] = []
    seen = set()
    for key in keys:
        if key in _TWEAK_MAP and key not in seen:
            seen.add(key)
            uniq_keys.append(key)

    if not uniq_keys:
        return {
            "total": 0,
            "ok": 0,
            "failed": 0,
            "results": [],
            "conflicts": [],
            "dry_run": dry_run,
        }

    before = _capture_metrics(logger) if not dry_run else {}
    batch_id = _allocate_batch_id() if not dry_run else None
    conflicts = detect_conflicts(uniq_keys)

    results: list[dict[str, Any]] = []
    ok_count = 0
    fail_count = 0
    change_ids: list[int] = []

    for key in uniq_keys:
        res = apply_tweak(
            key,
            logger,
            enable=enable,
            dry_run=dry_run,
            _batch_id=batch_id,
        )
        results.append(res)
        if res.get("ok"):
            ok_count += 1
        else:
            fail_count += 1
        if not dry_run and isinstance(res.get("change_id"), int):
            change_ids.append(int(res["change_id"]))

    report_path = ""
    after = _capture_metrics(logger) if not dry_run else {}
    delta = _metrics_delta(before, after) if not dry_run else {}

    if not dry_run and batch_id is not None:
        _record_batch(
            batch_id=batch_id,
            keys=uniq_keys,
            labels=[str(_TWEAK_MAP[k].label) for k in uniq_keys],
            change_ids=change_ids,
            success=(fail_count == 0),
        )
        report_path = _write_benchmark_report(
            {
                "timestamp": _now_iso(),
                "batch_id": batch_id,
                "keys": uniq_keys,
                "before": before,
                "after": after,
                "delta": delta,
                "ok": ok_count,
                "failed": fail_count,
            }
        )

    return {
        "total": len(uniq_keys),
        "ok": ok_count,
        "failed": fail_count,
        "results": results,
        "conflicts": conflicts,
        "dry_run": dry_run,
        "batch_id": batch_id,
        "benchmark": {
            "before": before,
            "after": after,
            "delta": delta,
            "report_path": report_path,
        },
        "pending_restart": get_pending_restart(),
    }


def dry_run_many(keys: list[str], logger, enable: bool | None = None) -> dict[str, Any]:
    return apply_many(keys, logger=logger, enable=enable, dry_run=True)

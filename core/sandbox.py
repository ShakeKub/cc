"""Sandbox — filesystem+registry snapshot, diff, and protected app launch."""

from __future__ import annotations
import os
import subprocess
import time
from pathlib import Path
from typing import Any


# ── snapshot helpers ──────────────────────────────────────────────────────────

def _file_sig(path: Path) -> str:
    """Fast change signature: size + mtime_ns. No full hash needed for diff."""
    try:
        s = path.stat()
        return f"{s.st_size}:{s.st_mtime_ns}"
    except OSError:
        return "?"


def take_snapshot(paths: list[str], include_registry: bool = True) -> dict[str, Any]:
    """
    Snapshot the filesystem under each path in `paths` and key registry hives.
    Returns a dict suitable for diff_snapshots().
    """
    snap: dict[str, Any] = {
        "files":     {},
        "registry":  {},
        "timestamp": time.time(),
    }
    for p_str in paths:
        p = Path(p_str)
        if not p.is_dir():
            continue
        try:
            for item in p.rglob("*"):
                if item.is_file():
                    try:
                        snap["files"][str(item)] = _file_sig(item)
                    except OSError:
                        pass
        except PermissionError:
            pass

    if include_registry and os.name == "nt":
        snap["registry"] = _snapshot_registry()

    return snap


def _snapshot_registry() -> dict[str, Any]:
    """Snapshot key HKCU/HKLM paths relevant to software installs."""
    result: dict[str, Any] = {}
    try:
        import winreg as w
        paths_to_snap = [
            (w.HKEY_CURRENT_USER,  r"Software",                                       "HKCU\\Software"),
            (w.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",  "HKLM\\Run"),
            (w.HKEY_LOCAL_MACHINE,
             r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",                  "HKLM\\Uninstall"),
            (w.HKEY_LOCAL_MACHINE,
             r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",      "HKLM\\Uninstall32"),
        ]
        for hive, key_path, label in paths_to_snap:
            try:
                key = w.OpenKey(hive, key_path, 0, w.KEY_READ)
                vals: dict[str, str] = {}
                subs: list[str] = []
                i = 0
                while True:
                    try:
                        name, value, _ = w.EnumValue(key, i)
                        vals[name] = str(value)[:300]
                        i += 1
                    except OSError:
                        break
                i = 0
                while True:
                    try:
                        subs.append(w.EnumKey(key, i))
                        i += 1
                    except OSError:
                        break
                w.CloseKey(key)
                result[label] = {"values": vals, "subkeys": subs}
            except OSError:
                pass
    except ImportError:
        pass
    return result


# ── diff ──────────────────────────────────────────────────────────────────────

def diff_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """
    Compare two snapshots and return a structured diff:
      files_added, files_modified, files_deleted, files_unchanged_count
      registry: list of {type, path, old?, new?}
    """
    bf = before.get("files", {})
    af = after.get("files",  {})

    added    = sorted(p for p in af if p not in bf)
    deleted  = sorted(p for p in bf if p not in af)
    modified = sorted(p for p in af if p in bf and af[p] != bf[p])
    unchanged_count = sum(1 for p in af if p in bf and af[p] == bf[p])

    reg_changes: list[dict[str, str]] = []
    before_reg = before.get("registry", {})
    after_reg  = after.get("registry",  {})

    for key, after_data in after_reg.items():
        before_data = before_reg.get(key, {"values": {}, "subkeys": []})
        for sub in after_data.get("subkeys", []):
            if sub not in before_data.get("subkeys", []):
                reg_changes.append({"type": "key_added",   "path": f"{key}\\{sub}"})
        for sub in before_data.get("subkeys", []):
            if sub not in after_data.get("subkeys", []):
                reg_changes.append({"type": "key_deleted", "path": f"{key}\\{sub}"})
        for name, val in after_data.get("values", {}).items():
            old_val = before_data.get("values", {}).get(name)
            if old_val is None:
                reg_changes.append({"type": "value_added",    "path": f"{key}\\{name}", "new": val})
            elif old_val != val:
                reg_changes.append({"type": "value_modified", "path": f"{key}\\{name}",
                                    "old": old_val, "new": val})
        for name in before_data.get("values", {}):
            if name not in after_data.get("values", {}):
                reg_changes.append({"type": "value_deleted", "path": f"{key}\\{name}"})

    return {
        "files_added":       added,
        "files_modified":    modified,
        "files_deleted":     deleted,
        "files_unchanged":   unchanged_count,
        "registry":          reg_changes,
        "snapshot_duration": round(after.get("timestamp", 0) - before.get("timestamp", 0), 1),
        "summary": {
            "added":     len(added),
            "modified":  len(modified),
            "deleted":   len(deleted),
            "unchanged": unchanged_count,
            "registry":  len(reg_changes),
        },
    }


# ── protected launch ──────────────────────────────────────────────────────────

def launch_protected(
    exe_path: str,
    block_network: bool = True,
    watch_paths: list[str] | None = None,
    logger=None,
) -> dict[str, Any]:
    """
    Protected launch:
    1. Snapshot watch_paths before launch.
    2. Optionally block the exe's outbound internet via Windows Firewall.
    3. Start the process.
    Returns a context dict; pass it to finish_protected() when the app exits.
    """
    if watch_paths is None:
        watch_paths = [str(Path.home())]

    before = take_snapshot(watch_paths)

    blocked    = False
    rule_name  = ""
    block_err  = ""
    if block_network and os.name == "nt":
        from core.appmgr import block_app_internet
        res = block_app_internet(exe_path, logger)
        blocked   = res["ok"]
        rule_name = res.get("rule_name", "")
        block_err = res.get("error", "")

    try:
        proc = subprocess.Popen([exe_path])
        pid  = proc.pid
    except Exception as e:
        if blocked:
            _remove_firewall_rule(rule_name)
        return {"ok": False, "error": str(e)}

    if logger:
        logger.log_action("launch_protected",
                          f"PID={pid} blocked={blocked} exe={exe_path}")

    return {
        "ok":          True,
        "pid":         pid,
        "process":     proc,
        "before":      before,
        "watch_paths": watch_paths,
        "exe_path":    exe_path,
        "blocked":     blocked,
        "rule_name":   rule_name,
        "block_err":   block_err,
    }


def finish_protected(ctx: dict[str, Any], logger=None) -> dict[str, Any]:
    """
    Call after the protected process exits (or is killed):
    1. Remove firewall block if any.
    2. Take after-snapshot and return diff.
    """
    if ctx.get("blocked") and ctx.get("rule_name"):
        _remove_firewall_rule(ctx["rule_name"])

    after = take_snapshot(ctx.get("watch_paths", [str(Path.home())]))
    diff  = diff_snapshots(ctx["before"], after)

    if logger:
        s = diff["summary"]
        logger.log_action("finish_protected",
                          f"added={s['added']} mod={s['modified']} "
                          f"del={s['deleted']} reg={s['registry']}")
    return diff


def _remove_firewall_rule(rule_name: str) -> None:
    try:
        subprocess.run(
            ["netsh", "advfirewall", "firewall", "delete", "rule",
             f"name={rule_name}"],
            capture_output=True, timeout=10,
        )
    except Exception:
        pass


# ── static pre-launch scan ────────────────────────────────────────────────────

def pre_launch_scan(app_name: str, logger=None) -> dict[str, Any]:
    """
    Run the static AppTracer scan for app_name.
    Returns the traces dict so the caller can display/clean before launching.
    """
    from core.tracer import AppTracer
    tracer = AppTracer(app_name, logger=logger)
    traces = tracer.scan_all()
    summary = tracer.get_summary()
    return {"traces": traces, "summary": summary, "tracer": tracer}

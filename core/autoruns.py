"""Autoruns — comprehensive startup entry viewer beyond Run keys."""

import json
import subprocess

try:
    import winreg
except ImportError:
    winreg = None  # non-Windows


# ── Registry helpers ────────────────────────────────────────

def _reg_read_values(hive, key_path: str, source_label: str) -> list[dict]:
    if not winreg:
        return []
    entries = []
    try:
        k = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
        i = 0
        while True:
            try:
                name, val, _ = winreg.EnumValue(k, i)
                entries.append({
                    "name":      name,
                    "command":   str(val),
                    "source":    source_label,
                    "reg_hive":  "HKCU" if hive == winreg.HKEY_CURRENT_USER else "HKLM",
                    "reg_key":   key_path,
                    "enabled":   True,
                })
                i += 1
            except OSError:
                break
        winreg.CloseKey(k)
    except OSError:
        pass
    return entries


def _ps(cmd: str, timeout: int = 20) -> str:
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=timeout,
        )
        return r.stdout.strip()
    except Exception:
        return ""


# ── Data collectors ─────────────────────────────────────────

def _get_run_entries() -> list[dict]:
    if not winreg:
        return []
    sources = [
        (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",     "HKCU Run"),
        (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce", "HKCU RunOnce"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",     "HKLM Run"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce", "HKLM RunOnce"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run", "HKLM Run (x86)"),
    ]
    out = []
    for hive, key, label in sources:
        out.extend(_reg_read_values(hive, key, label))
    return out


def _get_winlogon_entries() -> list[dict]:
    if not winreg:
        return []
    key_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
    watch = ("Shell", "Userinit", "TaskMan")
    entries = []
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            k = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
            for name in watch:
                try:
                    val, _ = winreg.QueryValueEx(k, name)
                    entries.append({
                        "name":    name,
                        "command": str(val),
                        "source":  "Winlogon",
                        "reg_hive": "HKLM" if hive == winreg.HKEY_LOCAL_MACHINE else "HKCU",
                        "reg_key": key_path,
                        "enabled": True,
                    })
                except OSError:
                    pass
            winreg.CloseKey(k)
        except OSError:
            pass
    return entries


def _get_shell_extensions() -> list[dict]:
    if not winreg:
        return []
    key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Shell Extensions\Approved"
    entries = []
    try:
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_READ)
        i = 0
        while True:
            try:
                clsid, name, _ = winreg.EnumValue(k, i)
                entries.append({
                    "name":    str(name) or clsid,
                    "command": clsid,
                    "source":  "Shell Extension",
                    "enabled": True,
                })
                i += 1
            except OSError:
                break
        winreg.CloseKey(k)
    except OSError:
        pass
    return entries


def _get_scheduled_tasks() -> list[dict]:
    raw = _ps(
        "Get-ScheduledTask | "
        "Select-Object TaskName,TaskPath,State,"
        "@{n='Cmd';e={($_.Actions | Select-Object -First 1).Execute}} | "
        "ConvertTo-Json -Compress",
        timeout=25,
    )
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        return [
            {
                "name":    d.get("TaskName", ""),
                "command": d.get("Cmd") or "",
                "source":  f"Task Scheduler ({d.get('TaskPath','')})",
                "enabled": str(d.get("State", "")) != "Disabled",
            }
            for d in data
        ]
    except (json.JSONDecodeError, TypeError):
        return []


# ── Public API ───────────────────────────────────────────────

def get_autoruns(logger=None) -> dict[str, list[dict]]:
    """Return categorised autorun entries."""
    return {
        "Run Keys":         _get_run_entries(),
        "Winlogon":         _get_winlogon_entries(),
        "Shell Extensions": _get_shell_extensions(),
        "Scheduled Tasks":  _get_scheduled_tasks(),
    }


def disable_run_entry(entry: dict, logger=None) -> bool:
    """Delete a Run registry value to disable it."""
    if not winreg or entry.get("source", "") not in (
        "HKCU Run", "HKCU RunOnce", "HKLM Run", "HKLM RunOnce", "HKLM Run (x86)"
    ):
        return False
    hive = winreg.HKEY_CURRENT_USER if entry.get("reg_hive") == "HKCU" else winreg.HKEY_LOCAL_MACHINE
    try:
        k = winreg.OpenKey(hive, entry["reg_key"], 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(k, entry["name"])
        winreg.CloseKey(k)
        if logger:
            logger.log("autorun_disable", "autoruns", f"name={entry['name']} src={entry['source']}")
        return True
    except OSError:
        return False


def disable_scheduled_task(task: dict, logger=None) -> bool:
    name = task.get("name", "")
    path = (task.get("source", "\\").replace("Task Scheduler (", "").rstrip(")")) or "\\"
    out = _ps(f'Disable-ScheduledTask -TaskName "{name}" -TaskPath "{path}" -ErrorAction SilentlyContinue')
    if logger:
        logger.log("task_disable", "autoruns", f"task={name}")
    return True  # PowerShell doesn't always return non-zero on success


def enable_scheduled_task(task: dict, logger=None) -> bool:
    name = task.get("name", "")
    path = (task.get("source", "\\").replace("Task Scheduler (", "").rstrip(")")) or "\\"
    _ps(f'Enable-ScheduledTask -TaskName "{name}" -TaskPath "{path}" -ErrorAction SilentlyContinue')
    if logger:
        logger.log("task_enable", "autoruns", f"task={name}")
    return True

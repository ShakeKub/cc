"""Firewall Rule Viewer — list, toggle, and delete Windows Firewall rules."""

import os
import json
import subprocess
from core.logger import CleanerLogger


def get_firewall_rules(direction: str = "all", enabled_only: bool = False,
                        logger: CleanerLogger | None = None) -> list[dict]:
    """Return firewall rules via Get-NetFirewallRule."""
    if os.name != "nt":
        return []
    dir_filter = ""
    if direction == "in":
        dir_filter = "| Where-Object {$_.Direction -eq 'Inbound'}"
    elif direction == "out":
        dir_filter = "| Where-Object {$_.Direction -eq 'Outbound'}"
    enabled_filter = "| Where-Object {$_.Enabled -eq 'True'}" if enabled_only else ""

    script = (
        f"Get-NetFirewallRule {dir_filter} {enabled_filter} "
        "| Select-Object DisplayName, Direction, Action, Enabled, Profile, "
        "@{N='Program';E={(Get-NetFirewallApplicationFilter -AssociatedNetFirewallRule $_ "
        "-ErrorAction SilentlyContinue).Program}} "
        "| ConvertTo-Json -Compress -Depth 2"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=30,
        )
        if not r.stdout.strip():
            return []
        raw = json.loads(r.stdout)
        if isinstance(raw, dict):
            raw = [raw]
        rules = []
        for item in (raw or []):
            rules.append({
                "name":      item.get("DisplayName", ""),
                "direction": item.get("Direction", ""),
                "action":    item.get("Action", ""),
                "enabled":   str(item.get("Enabled", "")).lower() in ("true", "1"),
                "profile":   item.get("Profile", ""),
                "program":   item.get("Program") or "",
            })
        return rules
    except Exception as e:
        if logger:
            logger.error(f"get_firewall_rules error: {e}")
        return []


def enable_rule(name: str, logger: CleanerLogger) -> bool:
    """Enable a firewall rule by display name."""
    return _set_rule_enabled(name, True, logger)


def disable_rule(name: str, logger: CleanerLogger) -> bool:
    """Disable a firewall rule by display name."""
    return _set_rule_enabled(name, False, logger)


def _set_rule_enabled(name: str, enabled: bool, logger: CleanerLogger) -> bool:
    if os.name != "nt":
        return False
    state = "True" if enabled else "False"
    safe_name = name.replace("'", "''")
    script = f"Set-NetFirewallRule -DisplayName '{safe_name}' -Enabled {state}"
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=15,
        )
        ok = r.returncode == 0
        logger.log("fw_toggle", "firewall",
                   f"{'Enabled' if enabled else 'Disabled'} rule: {name}" if ok
                   else f"Failed to toggle: {name} — {r.stderr.strip()}")
        return ok
    except Exception as e:
        logger.error(f"_set_rule_enabled error: {e}")
        return False


def delete_rule(name: str, logger: CleanerLogger) -> bool:
    """Delete a firewall rule by display name."""
    if os.name != "nt":
        return False
    safe_name = name.replace("'", "''")
    script = f"Remove-NetFirewallRule -DisplayName '{safe_name}'"
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=15,
        )
        ok = r.returncode == 0
        logger.log("del_fw_rule", "firewall",
                   f"Deleted rule: {name}" if ok else f"Failed to delete: {name}")
        return ok
    except Exception as e:
        logger.error(f"delete_rule error: {e}")
        return False

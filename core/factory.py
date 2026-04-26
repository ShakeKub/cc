"""Factory setup wizard and smart startup/services optimizer."""

from __future__ import annotations

import copy
import os
from datetime import datetime
from typing import Any

from core import pkgmgr
from core.optimizer import disable_service, get_power_plans, list_optimizable_services, set_power_plan
from core.restore import create_restore_point
from core.startup import disable_startup_entry, get_startup_entries

_FACTORY_PROFILES: dict[str, dict[str, str]] = {
    "dev": {
        "id": "dev",
        "label": "Developer Workstation",
        "description": "Dev tools + balanced startup/services tuning.",
        "manifest_profile": "dev",
        "optimizer_mode": "balanced",
        "power_target": "high_performance",
    },
    "gaming": {
        "id": "gaming",
        "label": "Gaming Rig",
        "description": "Gaming apps + high-performance tuning.",
        "manifest_profile": "gaming",
        "optimizer_mode": "aggressive",
        "power_target": "high_performance",
    },
    "office": {
        "id": "office",
        "label": "Office Productivity",
        "description": "Office apps + low-risk optimization.",
        "manifest_profile": "office",
        "optimizer_mode": "safe",
        "power_target": "balanced",
    },
    "family": {
        "id": "family",
        "label": "Family PC",
        "description": "Everyday apps + conservative optimization.",
        "manifest_profile": "family",
        "optimizer_mode": "safe",
        "power_target": "balanced",
    },
}

_KEEP_PATTERNS = (
    "security", "defender", "windows security", "realtek", "intel",
    "nvidia", "amd", "audio", "touchpad", "bluetooth",
)

_DISABLE_PATTERNS = (
    "teams", "discord", "onedrive", "spotify", "steam", "epic",
    "updater", "update", "adobe", "launcher", "helper", "telemetry",
)

_AGGRESSIVE_PATTERNS = (
    "assistant", "agent", "sync", "cloud", "widgets", "chat", "news",
)

_SERVICE_RISK = {
    "WSearch": "Search indexing and Start menu search can become slower.",
    "SysMain": "App preloading behavior is reduced; may impact HDD systems.",
}

_POWER_KEYWORDS = {
    "high_performance": ("high performance", "ultimate performance", "performance"),
    "balanced": ("balanced",),
    "power_saver": ("power saver", "power saving", "energy saver"),
}


def _audit(logger, action: str, details: str, success: bool = True, meta: dict[str, Any] | None = None):
    if not logger:
        return
    try:
        logger.audit_event(action, "factory", details, success=success, metadata=meta or {})
    except Exception:
        pass


def _normalize_mode(mode: str) -> str:
    m = (mode or "balanced").strip().lower()
    if m not in ("safe", "balanced", "aggressive"):
        return "balanced"
    return m


def _startup_score(impact: str, suspicious: bool) -> int:
    base = {"low": 1, "medium": 2, "high": 3}.get(impact, 2)
    return base + (3 if suspicious else 0)


def _startup_gain_ms(impact: str, suspicious: bool) -> int:
    base = {"low": 120, "medium": 450, "high": 900}.get(impact, 300)
    return base + (300 if suspicious else 0)


def get_factory_profiles() -> list[dict[str, str]]:
    return [copy.deepcopy(_FACTORY_PROFILES[k]) for k in sorted(_FACTORY_PROFILES.keys())]


def get_factory_profile(profile_id: str) -> dict[str, str]:
    key = (profile_id or "").strip().lower()
    if key not in _FACTORY_PROFILES:
        raise ValueError(f"Unknown factory profile: {profile_id}")
    return copy.deepcopy(_FACTORY_PROFILES[key])


def preview_factory_plan(profile_id: str) -> dict[str, Any]:
    profile = get_factory_profile(profile_id)
    manifest = pkgmgr.get_builtin_manifest(profile["manifest_profile"])
    pkgs = manifest.get("packages", [])
    required = sum(1 for p in pkgs if not p.get("optional"))
    optional = len(pkgs) - required
    return {
        "profile": profile,
        "manifest_name": manifest.get("name", profile["manifest_profile"]),
        "manifest_packages": len(pkgs),
        "manifest_required": required,
        "manifest_optional": optional,
        "optimizer_mode": profile["optimizer_mode"],
        "power_target": profile["power_target"],
    }


def _decide_startup_action(entry: dict[str, Any], mode: str) -> tuple[str, str]:
    name = str(entry.get("name", "")).lower()
    command = str(entry.get("command", "")).lower()
    text = f"{name} {command}"
    impact = str(entry.get("impact", "medium")).lower()
    suspicious = bool(entry.get("suspicious"))
    enabled = bool(entry.get("enabled", True))

    if not enabled:
        return "keep", "Already disabled."

    if suspicious:
        return "disable", "Suspicious startup signature detected."

    if any(pat in text for pat in _KEEP_PATTERNS):
        return "keep", "Looks like a system, security, or driver component."

    if mode == "safe":
        if impact == "high" and any(pat in text for pat in _DISABLE_PATTERNS):
            return "disable", "High-impact background app not required at boot."
        return "keep", "Safe mode keeps medium/low-risk startup items enabled."

    if mode == "balanced":
        if impact == "high":
            return "disable", "High startup impact with low boot-time value."
        if impact == "medium" and any(pat in text for pat in _DISABLE_PATTERNS):
            return "disable", "Medium-impact background app can be delayed/manual."
        return "keep", "Balanced mode keeps lower-impact entries."

    # aggressive
    if impact in ("high", "medium"):
        return "disable", "Aggressive mode disables most non-essential medium/high-impact entries."
    if any(pat in text for pat in _AGGRESSIVE_PATTERNS):
        return "disable", "Aggressive mode disables optional assistants and sync helpers."
    return "keep", "Low-impact startup item preserved."


def _decide_service_action(service: dict[str, Any], mode: str) -> tuple[str, str]:
    name = str(service.get("name", ""))
    category = str(service.get("category", "")).lower()
    impact = str(service.get("impact", "medium")).lower()
    start_type = str(service.get("start_type", "")).lower()

    if start_type == "disabled":
        return "keep", "Already disabled."

    if mode == "safe":
        if category in ("telemetry", "unused") and impact == "low":
            return "disable", "Safe mode disables low-risk telemetry/unused services."
        return "keep", "Safe mode keeps performance-sensitive services enabled."

    if mode == "balanced":
        if category in ("telemetry", "unused", "privacy"):
            return "disable", "Balanced mode disables non-essential background services."
        if category == "performance" and impact == "high":
            return "disable", "High-impact service can be disabled for better responsiveness."
        return "keep", "Service kept in balanced profile."

    # aggressive
    if service.get("safe_to_disable", True):
        return "disable", "Aggressive mode disables all marked optional services."
    return "keep", "Service is not marked safe to disable."


def analyze_startup_services(logger, mode: str = "balanced") -> dict[str, Any]:
    mode_n = _normalize_mode(mode)

    startup_entries = get_startup_entries(logger)
    startup_recs: list[dict[str, Any]] = []
    startup_disable = 0
    startup_gain = 0

    for i, entry in enumerate(startup_entries):
        action, reason = _decide_startup_action(entry, mode_n)
        impact = str(entry.get("impact", "medium")).lower()
        suspicious = bool(entry.get("suspicious"))
        score = _startup_score(impact, suspicious)
        gain_ms = _startup_gain_ms(impact, suspicious)

        if action == "disable" and entry.get("enabled", True):
            startup_disable += 1
            startup_gain += gain_ms

        startup_recs.append({
            "index": i,
            "name": entry.get("name", ""),
            "enabled": bool(entry.get("enabled", True)),
            "impact": impact,
            "suspicious": suspicious,
            "action": action,
            "reason": reason,
            "score": score,
            "estimated_gain_ms": gain_ms,
            "entry": entry,
        })

    services = list_optimizable_services(logger)
    service_recs: list[dict[str, Any]] = []
    service_disable = 0

    for svc in services:
        action, reason = _decide_service_action(svc, mode_n)
        risk_note = _SERVICE_RISK.get(str(svc.get("name", "")), "")
        if action == "disable" and str(svc.get("start_type", "")).lower() != "disabled":
            service_disable += 1

        service_recs.append({
            "name": svc.get("name", ""),
            "display_name": svc.get("display_name", ""),
            "status": svc.get("status", "unknown"),
            "start_type": svc.get("start_type", "unknown"),
            "impact": svc.get("impact", "medium"),
            "category": svc.get("category", ""),
            "action": action,
            "reason": reason,
            "risk_note": risk_note,
        })

    startup_recs.sort(key=lambda x: (x["action"] != "disable", -x["score"], x["name"]))
    service_recs.sort(key=lambda x: (x["action"] != "disable", x["name"]))

    return {
        "mode": mode_n,
        "startup": {
            "total": len(startup_recs),
            "to_disable": startup_disable,
            "estimated_boot_gain_ms": startup_gain,
            "recommendations": startup_recs,
        },
        "services": {
            "total": len(service_recs),
            "to_disable": service_disable,
            "recommendations": service_recs,
        },
    }


def apply_startup_services(
    logger,
    mode: str = "balanced",
    startup_limit: int = 12,
    service_limit: int = 8,
) -> dict[str, Any]:
    analysis = analyze_startup_services(logger, mode=mode)

    startup_candidates = [
        r for r in analysis["startup"]["recommendations"]
        if r["action"] == "disable" and r["enabled"]
    ]
    service_candidates = [
        r for r in analysis["services"]["recommendations"]
        if r["action"] == "disable" and r["start_type"] != "disabled"
    ]

    startup_applied: list[str] = []
    startup_failed: list[str] = []
    services_applied: list[str] = []
    services_failed: list[str] = []

    for rec in startup_candidates[: max(0, startup_limit)]:
        if disable_startup_entry(rec["entry"], logger):
            startup_applied.append(rec["name"])
        else:
            startup_failed.append(rec["name"])

    for rec in service_candidates[: max(0, service_limit)]:
        name = str(rec["name"])
        if disable_service(name, logger):
            services_applied.append(name)
        else:
            services_failed.append(name)

    result = {
        "mode": analysis["mode"],
        "analysis": analysis,
        "startup": {
            "attempted": min(len(startup_candidates), max(0, startup_limit)),
            "applied": startup_applied,
            "failed": startup_failed,
        },
        "services": {
            "attempted": min(len(service_candidates), max(0, service_limit)),
            "applied": services_applied,
            "failed": services_failed,
        },
    }

    _audit(
        logger,
        "startup_service_optimize",
        (
            f"mode={result['mode']} startup_applied={len(startup_applied)} "
            f"startup_failed={len(startup_failed)} services_applied={len(services_applied)} "
            f"services_failed={len(services_failed)}"
        ),
        success=(not startup_failed and not services_failed),
        meta={
            "mode": result["mode"],
            "startup_applied": len(startup_applied),
            "startup_failed": len(startup_failed),
            "services_applied": len(services_applied),
            "services_failed": len(services_failed),
        },
    )

    return result


def apply_power_target(target: str, logger) -> dict[str, Any]:
    wanted = (target or "balanced").strip().lower()
    keywords = _POWER_KEYWORDS.get(wanted, _POWER_KEYWORDS["balanced"])
    plans = get_power_plans(logger)

    selected = None
    for plan in plans:
        name = str(plan.get("name", "")).lower()
        if any(k in name for k in keywords):
            selected = plan
            break

    if not selected and wanted == "high_performance":
        # Built-in High Performance GUID fallback
        if set_power_plan("8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c", logger):
            return {"ok": True, "target": wanted, "name": "High Performance", "guid": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"}
        return {"ok": False, "target": wanted, "error": "Could not switch to high performance"}

    if not selected:
        return {"ok": False, "target": wanted, "error": "No matching power plan found"}

    ok = set_power_plan(selected.get("guid", ""), logger)
    return {
        "ok": ok,
        "target": wanted,
        "name": selected.get("name", ""),
        "guid": selected.get("guid", ""),
    }


def run_factory_wizard(
    profile_id: str,
    logger,
    create_checkpoint: bool = True,
    install_apps: bool = True,
    optimize_system: bool = True,
    retries: int = 1,
) -> dict[str, Any]:
    profile = get_factory_profile(profile_id)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    result: dict[str, Any] = {
        "run_id": run_id,
        "profile": profile,
        "checkpoint": {"enabled": create_checkpoint, "ok": None, "name": "", "error": ""},
        "manifest": {"enabled": install_apps, "ok": None},
        "optimizer": {"enabled": optimize_system, "ok": None},
        "power": {"ok": None},
        "ok": True,
    }

    _audit(logger, "factory_wizard_start", f"profile={profile['id']}", success=True, meta={"run_id": run_id})

    if create_checkpoint:
        if os.name != "nt":
            result["checkpoint"]["ok"] = False
            result["checkpoint"]["error"] = "Restore points are supported on Windows only"
            result["ok"] = False
        else:
            rp_name = f"SystemCleaner-{profile['id']}-{run_id}"
            result["checkpoint"]["name"] = rp_name
            try:
                ok = create_restore_point(rp_name, logger)
                result["checkpoint"]["ok"] = bool(ok)
                if not ok:
                    result["checkpoint"]["error"] = "Checkpoint creation failed (admin/System Restore required)"
                    result["ok"] = False
            except Exception as e:
                result["checkpoint"]["ok"] = False
                result["checkpoint"]["error"] = str(e)
                result["ok"] = False

    if install_apps:
        try:
            manifest = pkgmgr.get_builtin_manifest(profile["manifest_profile"])
            manifest_result = pkgmgr.install_from_manifest(manifest, logger=logger, retries=max(0, retries))
            result["manifest"] = {
                "enabled": True,
                "ok": bool(manifest_result.get("ok")),
                "name": manifest_result.get("name", manifest.get("name", "")),
                "installed": int(manifest_result.get("installed", 0)),
                "failed": int(manifest_result.get("failed", 0)),
                "skipped": int(manifest_result.get("skipped", 0)),
                "duration_s": float(manifest_result.get("duration_s", 0.0)),
                "entries": manifest_result.get("entries", []),
            }
            if not result["manifest"]["ok"]:
                result["ok"] = False
        except Exception as e:
            result["manifest"] = {
                "enabled": True,
                "ok": False,
                "error": str(e),
                "installed": 0,
                "failed": 0,
                "skipped": 0,
                "entries": [],
                "duration_s": 0.0,
            }
            result["ok"] = False

    if optimize_system:
        try:
            opt_result = apply_startup_services(
                logger,
                mode=profile["optimizer_mode"],
                startup_limit=12,
                service_limit=8,
            )
            power_result = apply_power_target(profile["power_target"], logger)

            result["optimizer"] = {
                "enabled": True,
                "ok": not (opt_result["startup"]["failed"] or opt_result["services"]["failed"]),
                "mode": opt_result["mode"],
                "startup_applied": len(opt_result["startup"]["applied"]),
                "startup_failed": len(opt_result["startup"]["failed"]),
                "services_applied": len(opt_result["services"]["applied"]),
                "services_failed": len(opt_result["services"]["failed"]),
                "details": opt_result,
            }
            result["power"] = power_result

            if not result["optimizer"]["ok"] or not power_result.get("ok", False):
                result["ok"] = False
        except Exception as e:
            result["optimizer"] = {"enabled": True, "ok": False, "error": str(e)}
            result["power"] = {"ok": False, "error": str(e)}
            result["ok"] = False

    _audit(
        logger,
        "factory_wizard_done",
        f"profile={profile['id']} ok={result['ok']}",
        success=result["ok"],
        meta={
            "run_id": run_id,
            "profile": profile["id"],
            "checkpoint_ok": result["checkpoint"].get("ok"),
            "manifest_ok": result["manifest"].get("ok"),
            "optimizer_ok": result["optimizer"].get("ok"),
            "power_ok": result["power"].get("ok"),
        },
    )

    return result

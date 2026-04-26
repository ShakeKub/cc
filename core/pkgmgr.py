"""Package Manager — winget + Chocolatey integration + manifest installer."""

from __future__ import annotations

import copy
import json
import subprocess
import time
from pathlib import Path
from typing import Any


BUILTIN_MANIFESTS: dict[str, dict[str, Any]] = {
    "dev": {
        "name": "Developer Essentials",
        "description": "Common development workstation baseline.",
        "packages": [
            {"id": "Git.Git", "name": "Git", "manager": "winget", "optional": False},
            {"id": "Microsoft.VisualStudioCode", "name": "VS Code", "manager": "winget", "optional": False},
            {"id": "Python.Python.3.12", "name": "Python 3.12", "manager": "winget", "optional": False},
            {"id": "OpenJS.NodeJS.LTS", "name": "Node.js LTS", "manager": "winget", "optional": False},
            {"id": "Docker.DockerDesktop", "name": "Docker Desktop", "manager": "winget", "optional": True},
            {"id": "Postman.Postman", "name": "Postman", "manager": "winget", "optional": True},
        ],
    },
    "gaming": {
        "name": "Gaming Rig",
        "description": "Launchers, voice and streaming tools.",
        "packages": [
            {"id": "Valve.Steam", "name": "Steam", "manager": "winget", "optional": False},
            {"id": "EpicGames.EpicGamesLauncher", "name": "Epic Games Launcher", "manager": "winget", "optional": True},
            {"id": "Discord.Discord", "name": "Discord", "manager": "winget", "optional": False},
            {"id": "OBSProject.OBSStudio", "name": "OBS Studio", "manager": "winget", "optional": True},
            {"id": "7zip.7zip", "name": "7-Zip", "manager": "winget", "optional": False},
        ],
    },
    "office": {
        "name": "Office Productivity",
        "description": "General office and communication setup.",
        "packages": [
            {"id": "Google.Chrome", "name": "Google Chrome", "manager": "winget", "optional": False},
            {"id": "Mozilla.Firefox", "name": "Mozilla Firefox", "manager": "winget", "optional": True},
            {"id": "Notepad++.Notepad++", "name": "Notepad++", "manager": "winget", "optional": True},
            {"id": "VideoLAN.VLC", "name": "VLC", "manager": "winget", "optional": True},
            {"id": "7zip.7zip", "name": "7-Zip", "manager": "winget", "optional": False},
        ],
    },
    "family": {
        "name": "Family PC",
        "description": "Safe and common apps for everyday users.",
        "packages": [
            {"id": "Google.Chrome", "name": "Google Chrome", "manager": "winget", "optional": False},
            {"id": "TeamViewer.TeamViewer", "name": "TeamViewer", "manager": "winget", "optional": True},
            {"id": "VideoLAN.VLC", "name": "VLC", "manager": "winget", "optional": False},
            {"id": "Adobe.Acrobat.Reader.64-bit", "name": "Adobe Reader", "manager": "winget", "optional": True},
            {"id": "7zip.7zip", "name": "7-Zip", "manager": "winget", "optional": False},
        ],
    },
}


def _run(cmd: list[str], timeout: int = 60) -> tuple[int, str, str]:
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


def _log(logger: Any, action: str, details: str, success: bool = True):
    if not logger:
        return
    try:
        logger.log(action, "pkgmgr", details, success=success)
    except Exception:
        pass


def _normalize_manager(value: str | None) -> str:
    v = (value or "auto").strip().lower()
    if v in ("winget", "choco", "auto"):
        return v
    return "auto"


def list_builtin_manifest_profiles() -> list[str]:
    return sorted(BUILTIN_MANIFESTS.keys())


def get_builtin_manifest(profile: str) -> dict[str, Any]:
    key = profile.strip().lower()
    if key not in BUILTIN_MANIFESTS:
        raise ValueError(f"Unknown manifest profile: {profile}")
    return copy.deepcopy(BUILTIN_MANIFESTS[key])


def create_manifest_template(profile: str = "dev") -> dict[str, Any]:
    base = get_builtin_manifest(profile)
    base["schema_version"] = 1
    base["created_from"] = profile
    base["notes"] = [
        "Supported manager values: winget, choco, auto",
        "When manager is auto, winget is preferred and choco is fallback",
        "Set optional=true for packages that can fail without failing the full run",
        "You can set choco_id to use a different package id for Chocolatey",
    ]
    return base


def write_manifest_template(path: str, profile: str = "dev", overwrite: bool = False) -> str:
    out = Path(path)
    if out.exists() and not overwrite:
        raise FileExistsError(f"Manifest already exists: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(create_manifest_template(profile), indent=2), encoding="utf-8")
    return str(out)


def load_manifest_file(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Manifest must be a JSON object")
    return data


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    packages = manifest.get("packages")
    if not isinstance(packages, list) or not packages:
        errors.append("'packages' must be a non-empty list")
        return errors

    for i, item in enumerate(packages, 1):
        if not isinstance(item, dict):
            errors.append(f"packages[{i}] must be an object")
            continue
        pkg_id = str(item.get("id", "")).strip()
        if not pkg_id:
            errors.append(f"packages[{i}].id is required")
        manager = _normalize_manager(item.get("manager") or item.get("source") or item.get("backend"))
        if manager not in ("winget", "choco", "auto"):
            errors.append(f"packages[{i}].manager must be winget/choco/auto")
    return errors


def _select_backend(preferred: str | None = None) -> str | None:
    wg = winget_available()
    ch = choco_available()
    pref = _normalize_manager(preferred)

    if pref == "winget":
        return "winget" if wg else ("choco" if ch else None)
    if pref == "choco":
        return "choco" if ch else ("winget" if wg else None)
    if wg:
        return "winget"
    if ch:
        return "choco"
    return None


def install_package(package_id: str, manager: str = "auto", logger=None) -> dict[str, Any]:
    backend = _select_backend(manager)
    if not backend:
        return {"ok": False, "code": -1, "output": "", "error": "No package manager available", "backend": "none"}
    if backend == "winget":
        res = winget_install(package_id, logger)
    else:
        res = choco_install(package_id, logger)
    res["backend"] = backend
    return res


def install_from_manifest(
    manifest: dict[str, Any],
    logger=None,
    retries: int = 1,
    stop_on_failure: bool = False,
) -> dict[str, Any]:
    start = time.time()
    errors = validate_manifest(manifest)
    if errors:
        return {
            "ok": False,
            "name": manifest.get("name", "manifest"),
            "error": "; ".join(errors),
            "total": 0,
            "installed": 0,
            "failed": 0,
            "skipped": 0,
            "entries": [],
            "duration_s": 0.0,
        }

    packages = manifest.get("packages", [])
    results: list[dict[str, Any]] = []
    installed = failed = skipped = 0

    for item in packages:
        pkg_id = str(item.get("id", "")).strip()
        manager = _normalize_manager(item.get("manager") or item.get("source") or item.get("backend"))
        optional = bool(item.get("optional", False))
        display_name = str(item.get("name", pkg_id)).strip() or pkg_id

        if not pkg_id:
            skipped += 1
            results.append({
                "name": display_name,
                "id": pkg_id,
                "ok": False,
                "skipped": True,
                "reason": "missing id",
                "backend": "none",
                "attempts": 0,
            })
            continue

        alt_choco = str(item.get("choco_id", "")).strip()
        attempts = 0
        last = {"ok": False, "code": -99, "output": "", "error": "not attempted", "backend": "none"}

        for _ in range(max(0, retries) + 1):
            attempts += 1
            backend_pref = manager
            run_pkg_id = pkg_id
            if backend_pref == "choco" and alt_choco:
                run_pkg_id = alt_choco

            last = install_package(run_pkg_id, manager=backend_pref, logger=logger)
            if last.get("ok"):
                break

            # If auto manager and choco fallback id is provided, one fallback attempt with choco id.
            if manager == "auto" and alt_choco and last.get("backend") == "winget":
                last = choco_install(alt_choco, logger)
                last["backend"] = "choco"
                if last.get("ok"):
                    break

        entry = {
            "name": display_name,
            "id": pkg_id,
            "ok": bool(last.get("ok")),
            "optional": optional,
            "backend": last.get("backend", "none"),
            "code": int(last.get("code", -99)),
            "error": str(last.get("error", ""))[:500],
            "attempts": attempts,
        }

        if entry["ok"]:
            installed += 1
            _log(logger, "manifest_install_ok", f"{display_name} via {entry['backend']}", success=True)
        else:
            if optional:
                skipped += 1
                entry["skipped"] = True
                _log(logger, "manifest_install_optional_failed", f"{display_name}: {entry['error']}", success=True)
            else:
                failed += 1
                _log(logger, "manifest_install_failed", f"{display_name}: {entry['error']}", success=False)

        results.append(entry)

        if stop_on_failure and failed > 0:
            break

    duration = max(0.0, time.time() - start)
    total = len(packages)
    ok = failed == 0

    _log(logger, "manifest_install_summary",
         f"name={manifest.get('name','manifest')} installed={installed} failed={failed} skipped={skipped}",
         success=ok)

    return {
        "ok": ok,
        "name": manifest.get("name", "manifest"),
        "description": manifest.get("description", ""),
        "total": total,
        "installed": installed,
        "failed": failed,
        "skipped": skipped,
        "entries": results,
        "duration_s": duration,
    }


def install_from_manifest_file(path: str, logger=None, retries: int = 1, stop_on_failure: bool = False) -> dict[str, Any]:
    manifest = load_manifest_file(path)
    result = install_from_manifest(manifest, logger=logger, retries=retries, stop_on_failure=stop_on_failure)
    result["path"] = str(path)
    return result


# ── winget ───────────────────────────────────────────────────

def winget_available() -> bool:
    code, _, _ = _run(["winget", "--version"])
    return code == 0


def winget_list(logger=None) -> list[dict[str, str]]:
    code, out, _ = _run(["winget", "list", "--disable-interactivity"], timeout=90)
    if code != 0:
        return []
    return _parse_winget_table(out)


def winget_search(query: str, logger=None) -> list[dict[str, str]]:
    code, out, _ = _run(["winget", "search", query, "--disable-interactivity"], timeout=30)
    if code != 0:
        return []
    return _parse_winget_table(out)


def winget_upgradable(logger=None) -> list[dict[str, str]]:
    code, out, _ = _run(["winget", "upgrade", "--disable-interactivity"], timeout=90)
    if code != 0:
        return []
    rows = _parse_winget_table(out)
    return [r for r in rows if r.get("Available") and r.get("Available") != r.get("Version", "")]


def winget_install(package_id: str, logger=None) -> dict[str, Any]:
    code, out, err = _run(
        ["winget", "install", "--id", package_id, "--accept-package-agreements",
         "--accept-source-agreements", "--disable-interactivity"],
        timeout=300,
    )
    success = code == 0
    _log(logger, "pkg_install", f"winget install {package_id}", success=success)
    return {"ok": success, "code": code, "output": out, "error": err}


def winget_uninstall(package_id: str, logger=None) -> dict[str, Any]:
    code, out, err = _run(
        ["winget", "uninstall", "--id", package_id,
         "--accept-source-agreements", "--disable-interactivity"],
        timeout=300,
    )
    success = code == 0
    _log(logger, "pkg_uninstall", f"winget uninstall {package_id}", success=success)
    return {"ok": success, "code": code, "output": out, "error": err}


def winget_upgrade(package_id: str, logger=None) -> dict[str, Any]:
    code, out, err = _run(
        ["winget", "upgrade", "--id", package_id, "--accept-package-agreements",
         "--accept-source-agreements", "--disable-interactivity"],
        timeout=300,
    )
    success = code == 0
    _log(logger, "pkg_upgrade", f"winget upgrade {package_id}", success=success)
    return {"ok": success, "code": code, "output": out, "error": err}


def winget_upgrade_all(logger=None) -> dict[str, Any]:
    code, out, err = _run(
        ["winget", "upgrade", "--all", "--accept-package-agreements",
         "--accept-source-agreements", "--disable-interactivity"],
        timeout=600,
    )
    success = code == 0
    _log(logger, "pkg_upgrade_all", "winget upgrade --all", success=success)
    return {"ok": success, "code": code, "output": out, "error": err}


def _parse_winget_table(text: str) -> list[dict[str, str]]:
    """Parse the fixed-width table output from winget."""
    lines = text.splitlines()
    header_idx = -1
    separator_idx = -1

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("Name") and ("Id" in stripped or "Source" in stripped):
            header_idx = i
        elif header_idx >= 0 and set(stripped.replace(" ", "")) <= set("-"):
            separator_idx = i
            break

    if header_idx < 0 or separator_idx < 0:
        return _parse_winget_fallback(lines)

    header_line = lines[header_idx]
    sep_line = lines[separator_idx]

    col_ends = []
    in_dashes = False
    start = 0
    for j, ch in enumerate(sep_line):
        if ch == "-" and not in_dashes:
            in_dashes = True
            start = j
        elif ch == " " and in_dashes:
            in_dashes = False
            col_ends.append((start, j))
    if in_dashes:
        col_ends.append((start, len(sep_line)))

    def _slice(line: str, bounds: list[tuple[int, int]]) -> list[str]:
        return [line[s:e].strip() for s, e in bounds]

    headers = _slice(header_line, col_ends)

    results = []
    for line in lines[separator_idx + 1:]:
        if not line.strip():
            continue
        vals = _slice(line, col_ends)
        if not vals or not vals[0]:
            continue
        row = dict(zip(headers, vals))
        if row.get("Name") and row.get("Name") not in ("", "-", "Name"):
            results.append(row)
    return results


def _parse_winget_fallback(lines: list[str]) -> list[dict[str, str]]:
    results = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("-") or stripped.startswith("Name"):
            continue
        parts = stripped.split(None, 3)
        if len(parts) >= 2:
            results.append({"Name": parts[0], "Id": parts[1],
                            "Version": parts[2] if len(parts) > 2 else "",
                            "Source": parts[3] if len(parts) > 3 else ""})
    return results


# ── Chocolatey ───────────────────────────────────────────────

def choco_available() -> bool:
    code, _, _ = _run(["choco", "--version"])
    return code == 0


def choco_list(logger=None) -> list[dict[str, str]]:
    code, out, _ = _run(["choco", "list", "--local-only", "-r"], timeout=60)
    if code != 0:
        return []
    results = []
    for line in out.splitlines():
        parts = line.strip().split("|")
        if len(parts) >= 2:
            results.append({"Name": parts[0], "Version": parts[1], "Id": parts[0]})
    return results


def choco_search(query: str, logger=None) -> list[dict[str, str]]:
    code, out, _ = _run(["choco", "search", query, "-r", "--limit-output"], timeout=30)
    if code != 0:
        return []
    results = []
    for line in out.splitlines():
        parts = line.strip().split("|")
        if len(parts) >= 2:
            results.append({"Name": parts[0], "Version": parts[1], "Id": parts[0]})
    return results


def choco_install(name: str, logger=None) -> dict[str, Any]:
    code, out, err = _run(["choco", "install", name, "-y"], timeout=300)
    success = code == 0
    _log(logger, "pkg_install", f"choco install {name}", success=success)
    return {"ok": success, "code": code, "output": out, "error": err}


def choco_uninstall(name: str, logger=None) -> dict[str, Any]:
    code, out, err = _run(["choco", "uninstall", name, "-y"], timeout=300)
    success = code == 0
    _log(logger, "pkg_uninstall", f"choco uninstall {name}", success=success)
    return {"ok": success, "code": code, "output": out, "error": err}


def choco_upgrade_all(logger=None) -> dict[str, Any]:
    code, out, err = _run(["choco", "upgrade", "all", "-y"], timeout=600)
    success = code == 0
    _log(logger, "pkg_upgrade_all", "choco upgrade all", success=success)
    return {"ok": success, "code": code, "output": out, "error": err}

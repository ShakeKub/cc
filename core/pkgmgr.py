"""Package Manager — winget + Chocolatey integration."""

from __future__ import annotations
import subprocess
import csv
import io
from typing import Any


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
    if logger and success:
        logger.log_action("pkg_install", f"winget install {package_id}")
    return {"ok": success, "code": code, "output": out, "error": err}


def winget_uninstall(package_id: str, logger=None) -> dict[str, Any]:
    code, out, err = _run(
        ["winget", "uninstall", "--id", package_id,
         "--accept-source-agreements", "--disable-interactivity"],
        timeout=300,
    )
    success = code == 0
    if logger and success:
        logger.log_action("pkg_uninstall", f"winget uninstall {package_id}")
    return {"ok": success, "code": code, "output": out, "error": err}


def winget_upgrade(package_id: str, logger=None) -> dict[str, Any]:
    code, out, err = _run(
        ["winget", "upgrade", "--id", package_id, "--accept-package-agreements",
         "--accept-source-agreements", "--disable-interactivity"],
        timeout=300,
    )
    success = code == 0
    if logger and success:
        logger.log_action("pkg_upgrade", f"winget upgrade {package_id}")
    return {"ok": success, "code": code, "output": out, "error": err}


def winget_upgrade_all(logger=None) -> dict[str, Any]:
    code, out, err = _run(
        ["winget", "upgrade", "--all", "--accept-package-agreements",
         "--accept-source-agreements", "--disable-interactivity"],
        timeout=600,
    )
    success = code == 0
    if logger and success:
        logger.log_action("pkg_upgrade_all", "winget upgrade --all")
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
    if logger and success:
        logger.log_action("pkg_install", f"choco install {name}")
    return {"ok": success, "code": code, "output": out, "error": err}


def choco_uninstall(name: str, logger=None) -> dict[str, Any]:
    code, out, err = _run(["choco", "uninstall", name, "-y"], timeout=300)
    success = code == 0
    if logger and success:
        logger.log_action("pkg_uninstall", f"choco uninstall {name}")
    return {"ok": success, "code": code, "output": out, "error": err}


def choco_upgrade_all(logger=None) -> dict[str, Any]:
    code, out, err = _run(["choco", "upgrade", "all", "-y"], timeout=600)
    success = code == 0
    if logger and success:
        logger.log_action("pkg_upgrade_all", "choco upgrade all")
    return {"ok": success, "code": code, "output": out, "error": err}

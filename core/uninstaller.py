"""Advanced uninstaller - list, uninstall, smart detect, deep clean, batch operations."""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast
from core.logger import CleanerLogger

if os.name == "nt":
    import winreg as _winreg

    winreg = cast(Any, _winreg)
else:
    winreg = cast(Any, None)


# ── Built-in (AppX) apps ────────────────────────────────────────────────────

BUILTIN_APPS: list[tuple[str, str]] = [
    ("Microsoft Teams",          "MicrosoftTeams"),
    ("Cortana",                  "Microsoft.549981C3F5F10"),
    ("Xbox",                     "Microsoft.XboxApp"),
    ("Xbox Game Bar",            "Microsoft.XboxGamingOverlay"),
    ("Xbox Identity Provider",   "Microsoft.XboxIdentityProvider"),
    ("Xbox Speech To Text",      "Microsoft.XboxSpeechToTextOverlay"),
    ("Xbox Game Overlay",        "Microsoft.XboxGameOverlay"),
    ("Mail and Calendar",        "microsoft.windowscommunicationsapps"),
    ("Maps",                     "Microsoft.WindowsMaps"),
    ("Movies & TV",              "Microsoft.ZuneVideo"),
    ("Groove Music",             "Microsoft.ZuneMusic"),
    ("Mixed Reality Portal",     "Microsoft.MixedReality.Portal"),
    ("News",                     "Microsoft.BingNews"),
    ("Weather",                  "Microsoft.BingWeather"),
    ("Solitaire Collection",     "Microsoft.MicrosoftSolitaireCollection"),
    ("OneNote",                  "Microsoft.Office.OneNote"),
    ("Paint 3D",                 "Microsoft.MSPaint"),
    ("3D Viewer",                "Microsoft.Microsoft3DViewer"),
    ("Skype",                    "Microsoft.SkypeApp"),
    ("Tips / Get Started",       "Microsoft.Getstarted"),
    ("People",                   "Microsoft.People"),
    ("Phone Link",               "Microsoft.YourPhone"),
    ("Get Help",                 "Microsoft.GetHelp"),
    ("Feedback Hub",             "Microsoft.WindowsFeedbackHub"),
    ("Clipchamp",                "Clipchamp.Clipchamp"),
    ("Sticky Notes",             "Microsoft.MicrosoftStickyNotes"),
    ("Power Automate",           "Microsoft.PowerAutomateDesktop"),
    ("Microsoft To Do",          "Microsoft.Todos"),
    ("Bing Search",              "Microsoft.BingSearch"),
    ("Quick Assist",             "MicrosoftCorporationII.QuickAssist"),
    ("Microsoft Store",          "Microsoft.WindowsStore"),
    ("MSN Sports",               "Microsoft.BingSports"),
    ("MSN Finance",              "Microsoft.BingFinance"),
    ("Office Hub",               "Microsoft.MicrosoftOfficeHub"),
    ("OneDrive",                 "Microsoft.OneDriveSync"),
    ("Windows Media Player",     "Microsoft.ZuneMusic"),
    ("Camera",                   "Microsoft.WindowsCamera"),
    ("Alarms & Clock",           "Microsoft.WindowsAlarms"),
    ("Calculator",               "Microsoft.WindowsCalculator"),
]

# Apps that are safe to batch-remove as "bloatware"
BLOATWARE_IDS: set[str] = {
    "MicrosoftTeams", "Microsoft.549981C3F5F10", "Microsoft.XboxApp",
    "Microsoft.XboxGamingOverlay", "Microsoft.XboxIdentityProvider",
    "Microsoft.XboxSpeechToTextOverlay", "Microsoft.XboxGameOverlay",
    "microsoft.windowscommunicationsapps", "Microsoft.WindowsMaps",
    "Microsoft.ZuneVideo", "Microsoft.ZuneMusic", "Microsoft.MixedReality.Portal",
    "Microsoft.BingNews", "Microsoft.BingWeather", "Microsoft.MicrosoftSolitaireCollection",
    "Microsoft.Office.OneNote", "Microsoft.MSPaint", "Microsoft.Microsoft3DViewer",
    "Microsoft.SkypeApp", "Microsoft.Getstarted", "Microsoft.People",
    "Microsoft.YourPhone", "Microsoft.GetHelp", "Microsoft.WindowsFeedbackHub",
    "Clipchamp.Clipchamp", "Microsoft.PowerAutomateDesktop",
    "Microsoft.BingSearch", "MicrosoftCorporationII.QuickAssist",
    "Microsoft.BingSports", "Microsoft.BingFinance", "Microsoft.MicrosoftOfficeHub",
}


TOKEN_STOPWORDS: set[str] = {
    "app", "apps", "application", "software", "program", "suite", "client",
    "setup", "update", "launcher", "service", "services", "windows", "microsoft",
    "company", "corp", "inc", "ltd", "tool", "tools",
}


def _tokenize(value: str) -> set[str]:
    """Tokenize free text into searchable lowercase terms."""
    if not value:
        return set()

    terms: set[str] = set()
    current: list[str] = []
    for ch in value.lower():
        if ch.isalnum():
            current.append(ch)
            continue
        if current:
            tok = "".join(current)
            if len(tok) >= 3 and tok not in TOKEN_STOPWORDS:
                terms.add(tok)
            current.clear()

    if current:
        tok = "".join(current)
        if len(tok) >= 3 and tok not in TOKEN_STOPWORDS:
            terms.add(tok)

    collapsed = "".join(ch for ch in value.lower() if ch.isalnum())
    if len(collapsed) >= 4:
        terms.add(collapsed)

    return terms


def _program_tokens(program: dict[str, Any], extra_terms: list[str] | None = None) -> set[str]:
    """Build search tokens from program metadata."""
    tokens: set[str] = set()

    for field in (
        program.get("name", ""),
        program.get("publisher", ""),
        Path(program.get("install_location", "") or "").name,
        Path(program.get("install_location", "") or "").parent.name,
    ):
        if field:
            tokens.update(_tokenize(str(field)))

    if extra_terms:
        for term in extra_terms:
            tokens.update(_tokenize(term))

    return tokens


def _ps_single_quote(value: str) -> str:
    """Escape text for a single-quoted PowerShell string literal."""
    return value.replace("'", "''")


def _discover_shortcuts(path: Path) -> list[Path]:
    """Return shortcut files from a .lnk path or folder."""
    if not path.exists():
        return []

    if path.is_file():
        return [path] if path.suffix.lower() == ".lnk" else []

    shortcuts: list[Path] = []
    try:
        for lnk in path.rglob("*.lnk"):
            shortcuts.append(lnk)
            if len(shortcuts) >= 4000:
                break
    except OSError:
        return []
    return shortcuts


def _read_shortcut_metadata(lnk_path: Path) -> dict[str, str]:
    """Resolve shortcut target details using PowerShell COM automation."""
    if not lnk_path.exists() or lnk_path.suffix.lower() != ".lnk":
        return {}

    try:
        ps = (
            "$sh = New-Object -ComObject WScript.Shell; "
            f"$sc = $sh.CreateShortcut('{_ps_single_quote(str(lnk_path))}'); "
            "[PSCustomObject]@{"
            "TargetPath=$sc.TargetPath;"
            "Arguments=$sc.Arguments;"
            "WorkingDirectory=$sc.WorkingDirectory"
            "} | ConvertTo-Json -Compress"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return {}

        raw = json.loads(result.stdout.strip())
        if not isinstance(raw, dict):
            return {}

        return {
            "target_path": str(raw.get("TargetPath", "") or ""),
            "arguments": str(raw.get("Arguments", "") or ""),
            "working_directory": str(raw.get("WorkingDirectory", "") or ""),
        }
    except Exception:
        return {}


def find_program_candidates(
    programs: list[dict[str, Any]],
    query: str = "",
    shortcut_path: str = "",
    logger: CleanerLogger | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    Return ranked candidates by text query and/or shortcut path evidence.
    Adds `match_score` and `match_reasons` to each returned program dict.
    """
    query = (query or "").strip()
    shortcut_path = (shortcut_path or "").strip().strip('"')
    query_terms = _tokenize(query)

    shortcut_terms: set[str] = set()
    shortcut_targets: list[str] = []

    if shortcut_path:
        shortcut_files = _discover_shortcuts(Path(shortcut_path))
        for lnk in shortcut_files:
            shortcut_terms.update(_tokenize(lnk.stem))
            meta = _read_shortcut_metadata(lnk)
            target = meta.get("target_path", "")
            if target:
                target_low = target.lower()
                shortcut_targets.append(target_low)
                shortcut_terms.update(_tokenize(Path(target).stem))
                shortcut_terms.update(_tokenize(Path(target).parent.name))

        if logger:
            logger.info(
                f"Shortcut-based match context: {len(shortcut_files)} shortcuts, "
                f"{len(shortcut_targets)} resolved targets"
            )

    ranked: list[dict[str, Any]] = []
    for program in programs:
        name = str(program.get("name", "") or "")
        publisher = str(program.get("publisher", "") or "")
        install_loc = str(program.get("install_location", "") or "")
        uninstall_blob = (
            str(program.get("uninstall_string", "") or "")
            + " "
            + str(program.get("quiet_uninstall", "") or "")
        ).lower()

        name_l = name.lower()
        publisher_l = publisher.lower()
        install_l = install_loc.lower()

        score = 0
        reasons: list[str] = []
        program_terms = _program_tokens(program)

        if query:
            ql = query.lower()
            if ql in name_l:
                score += 14
                reasons.append("name contains query")
            if ql in publisher_l:
                score += 8
                reasons.append("publisher contains query")

            overlap = query_terms.intersection(program_terms)
            if overlap:
                score += min(10, len(overlap) * 2)
                reasons.append("query token overlap")

        if shortcut_terms:
            overlap = shortcut_terms.intersection(program_terms)
            if overlap:
                score += min(12, len(overlap) * 2)
                reasons.append("shortcut token overlap")

        if shortcut_targets:
            for target in shortcut_targets:
                if install_l and (target.startswith(install_l) or install_l in target):
                    score += 22
                    reasons.append("shortcut target points to install location")
                    break
            else:
                target_names = {Path(target).name.lower() for target in shortcut_targets if target}
                if any(tn and tn in uninstall_blob for tn in target_names):
                    score += 6
                    reasons.append("uninstall command matches shortcut target")

        if score <= 0:
            continue

        candidate = dict(program)
        candidate["match_score"] = score
        candidate["match_reasons"] = reasons
        ranked.append(candidate)

    ranked.sort(key=lambda p: (-int(p.get("match_score", 0)), p.get("name", "").lower()))
    trimmed = ranked[:max(1, limit)]

    if logger:
        logger.info(
            f"Program candidate search: query='{query}' shortcut='{shortcut_path}' "
            f"-> {len(trimmed)} candidates"
        )
    return trimmed


def find_programs_by_shortcut_folder(
    shortcut_path: str,
    logger: CleanerLogger,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Find likely installed program entries from a folder containing shortcuts."""
    programs = list_installed_programs(logger)
    return find_program_candidates(
        programs,
        shortcut_path=shortcut_path,
        logger=logger,
        limit=limit,
    )


def find_programs_by_query(
    query: str,
    logger: CleanerLogger,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Find likely installed program entries from free-text query."""
    programs = list_installed_programs(logger)
    return find_program_candidates(
        programs,
        query=query,
        logger=logger,
        limit=limit,
    )


def list_builtin_apps(logger: CleanerLogger) -> list[dict[str, Any]]:
    """Return installed Windows built-in (AppX) apps via PowerShell."""
    try:
        ps_cmd = (
            "Get-AppxPackage | "
            "Select-Object Name,PackageFullName,Version | "
            "ConvertTo-Json -Compress"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=45,
        )
        if result.returncode != 0 or not result.stdout.strip():
            logger.warning("PowerShell AppX query returned no data")
            return []

        raw = json.loads(result.stdout.strip())
        packages: list[dict] = [raw] if isinstance(raw, dict) else raw

        installed: list[dict[str, Any]] = []
        for display_name, pkg_id in BUILTIN_APPS:
            for pkg in packages:
                pkg_name: str = pkg.get("Name", "")
                if pkg_id.lower() in pkg_name.lower():
                    installed.append({
                        "display_name":       display_name,
                        "package_name":       pkg_name,
                        "package_full_name":  pkg.get("PackageFullName", ""),
                        "version":            pkg.get("Version", ""),
                        "type":               "builtin",
                    })
                    break

        logger.info(f"Found {len(installed)} installed built-in apps")
        return installed
    except json.JSONDecodeError as exc:
        logger.error(f"Failed to parse AppX package list: {exc}")
        return []
    except Exception as exc:
        logger.error(f"Error listing built-in apps: {exc}")
        return []


def uninstall_builtin_app(app: dict, logger: CleanerLogger,
                           all_users: bool = False) -> bool:
    """Remove a Windows built-in AppX package using PowerShell."""
    pkg_full = app.get("package_full_name", "")
    pkg_name = app.get("package_name", "")
    display  = app.get("display_name", pkg_name)

    if not pkg_full and not pkg_name:
        logger.error(f"No package identifier for: {display}")
        return False

    try:
        if all_users:
            ps_cmd = (
                f'Get-AppxPackage -AllUsers -Name "{pkg_name}" '
                f'| Remove-AppxPackage -AllUsers'
            )
        else:
            identifier = pkg_full or pkg_name
            ps_cmd = f'Remove-AppxPackage -Package "{identifier}"'

        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=120,
        )
        success = result.returncode == 0
        logger.log(
            "uninstall_builtin", "uninstaller",
            f"{'Removed' if success else 'Failed to remove'} built-in app: {display}",
            success=success,
        )
        if not success and result.stderr.strip():
            logger.warning(f"PowerShell stderr: {result.stderr.strip()[:300]}")
        return success
    except subprocess.TimeoutExpired:
        logger.error(f"Timeout removing built-in app: {display}")
        return False
    except Exception as exc:
        logger.error(f"Error removing built-in app {display}: {exc}")
        return False


def remove_all_bloatware(logger: CleanerLogger,
                          all_users: bool = False) -> dict[str, bool]:
    """
    Remove all apps whose package ID is in BLOATWARE_IDS.
    Returns {display_name: success} for every app attempted.
    """
    apps = list_builtin_apps(logger)
    bloatware = [
        a for a in apps
        if any(bid.lower() in a["package_name"].lower() for bid in BLOATWARE_IDS)
    ]
    results: dict[str, bool] = {}
    for app in bloatware:
        results[app["display_name"]] = uninstall_builtin_app(app, logger, all_users=all_users)
    return results


# Registry locations for installed programs
if os.name == "nt":
    UNINSTALL_KEYS = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
else:
    UNINSTALL_KEYS = []


def _read_reg_value(key, name: str, default: Any = "") -> Any:
    """Safely read a registry value."""
    try:
        value, _ = winreg.QueryValueEx(key, name)
        return value
    except (FileNotFoundError, OSError):
        return default


def list_installed_programs(logger: CleanerLogger) -> list[dict[str, Any]]:
    """List all installed programs from the registry."""
    if os.name != "nt":
        logger.warning("Installed program registry scan is available on Windows only")
        return []

    programs = []
    seen = set()

    for hive, key_path in UNINSTALL_KEYS:
        try:
            reg_key = winreg.OpenKey(hive, key_path)
        except OSError:
            continue

        try:
            i = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(reg_key, i)
                    i += 1
                    try:
                        subkey = winreg.OpenKey(reg_key, subkey_name)
                        name = _read_reg_value(subkey, "DisplayName")
                        if not name or name in seen:
                            winreg.CloseKey(subkey)
                            continue
                        seen.add(name)

                        # Check if it's a system component (skip those)
                        system_component = _read_reg_value(subkey, "SystemComponent", 0)
                        if system_component == 1:
                            winreg.CloseKey(subkey)
                            continue

                        hive_name = "HKLM" if hive == winreg.HKEY_LOCAL_MACHINE else "HKCU"
                        program = {
                            "name": name,
                            "version": _read_reg_value(subkey, "DisplayVersion"),
                            "publisher": _read_reg_value(subkey, "Publisher"),
                            "install_date": _read_reg_value(subkey, "InstallDate"),
                            "install_location": _read_reg_value(subkey, "InstallLocation"),
                            "uninstall_string": _read_reg_value(subkey, "UninstallString"),
                            "quiet_uninstall": _read_reg_value(subkey, "QuietUninstallString"),
                            "size": _read_reg_value(subkey, "EstimatedSize", 0),
                            "reg_key": subkey_name,
                            "hive": hive_name,
                            "reg_path": f"{hive_name}\\{key_path}\\{subkey_name}",
                        }
                        programs.append(program)
                        winreg.CloseKey(subkey)
                    except OSError:
                        pass
                except OSError:
                    break
        finally:
            winreg.CloseKey(reg_key)

    programs.sort(key=lambda p: p["name"].lower())
    logger.info(f"Found {len(programs)} installed programs")
    return programs


def search_programs(programs: list[dict], query: str) -> list[dict]:
    """Filter programs by search query."""
    query_lower = query.lower()
    return [p for p in programs if query_lower in p["name"].lower()
            or query_lower in p.get("publisher", "").lower()]


def uninstall_program(program: dict, logger: CleanerLogger, silent: bool = False) -> bool:
    """Uninstall a program using its uninstall string."""
    uninstall_cmd = program.get("quiet_uninstall") if silent else None
    if not uninstall_cmd:
        uninstall_cmd = program.get("uninstall_string")
    if not uninstall_cmd:
        logger.error(f"No uninstall command for: {program['name']}")
        return False

    try:
        # Handle MsiExec uninstallers
        if "msiexec" in uninstall_cmd.lower():
            if silent and "/quiet" not in uninstall_cmd.lower():
                uninstall_cmd += " /quiet /norestart"
            result = subprocess.run(uninstall_cmd, shell=True, capture_output=True,
                                    text=True, timeout=300)
        else:
            if silent:
                # Try common silent switches
                for switch in ["/S", "/s", "/silent", "/quiet", "/VERYSILENT"]:
                    test_cmd = f'{uninstall_cmd} {switch}'
                    result = subprocess.run(test_cmd, shell=True, capture_output=True,
                                            text=True, timeout=300)
                    if result.returncode == 0:
                        break
                else:
                    result = subprocess.run(uninstall_cmd, shell=True, capture_output=True,
                                            text=True, timeout=300)
            else:
                result = subprocess.run(uninstall_cmd, shell=True, capture_output=True,
                                        text=True, timeout=300)

        success = result.returncode == 0
        logger.log(
            "uninstall", "uninstaller",
            f"{'Uninstalled' if success else 'Failed to uninstall'}: {program['name']}",
            success=success,
        )
        return success
    except subprocess.TimeoutExpired:
        logger.error(f"Uninstall timed out: {program['name']}")
        return False
    except Exception as e:
        logger.error(f"Uninstall error for {program['name']}: {e}")
        return False


def find_leftovers(
    program: dict[str, Any],
    logger: CleanerLogger,
    extra_terms: list[str] | None = None,
    shortcut_path: str = "",
) -> dict[str, list[str]]:
    """Find leftover files, shortcuts, and registry artifacts after uninstall."""
    leftovers: dict[str, list[str]] = {
        "files": [],
        "registry": [],
        "dirs": [],
        "registry_values": [],
    }

    if os.name != "nt":
        logger.warning("Advanced leftover registry scan is available on Windows only")
        return leftovers

    name = str(program.get("name", "") or "")
    publisher = str(program.get("publisher", "") or "")
    install_loc = str(program.get("install_location", "") or "")

    tokens = _program_tokens(program, extra_terms)
    if not tokens and name:
        tokens.add(name.lower().replace(" ", ""))

    candidate_dirs: set[Path] = set()

    if install_loc:
        install_path = Path(install_loc)
        if install_path.exists():
            candidate_dirs.add(install_path)

    env_roots: list[Path] = []
    for env_name in ("APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"):
        raw = os.environ.get(env_name, "")
        if raw:
            env_roots.append(Path(raw))

    for root in env_roots:
        if not root.exists():
            continue

        if name:
            candidate_dirs.add(root / name)
        if publisher and name:
            candidate_dirs.add(root / publisher / name)

        try:
            for child in root.iterdir():
                if not child.is_dir():
                    continue
                cname = child.name.lower()
                matched = [tok for tok in tokens if tok in cname]
                if len(matched) >= 2 or any(len(tok) >= 6 for tok in matched):
                    candidate_dirs.add(child)
        except OSError:
            pass

    for directory in sorted(candidate_dirs, key=lambda p: len(str(p))):
        if not directory.exists():
            continue
        leftovers["dirs"].append(str(directory))
        try:
            for item in directory.rglob("*"):
                if item.is_file():
                    leftovers["files"].append(str(item))
        except OSError:
            continue

    # Shortcut leftovers from Desktop + Start Menu + optional user-provided path.
    shortcut_roots: list[Path] = [Path.home() / "Desktop"]
    public_root = os.environ.get("PUBLIC", r"C:\Users\Public")
    if public_root:
        shortcut_roots.append(Path(public_root) / "Desktop")

    appdata_root = os.environ.get("APPDATA", "")
    if appdata_root:
        shortcut_roots.append(Path(appdata_root) / r"Microsoft\Windows\Start Menu")

    programdata_root = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
    if programdata_root:
        shortcut_roots.append(Path(programdata_root) / r"Microsoft\Windows\Start Menu")

    shortcut_path = (shortcut_path or "").strip().strip('"')
    if shortcut_path:
        shortcut_roots.append(Path(shortcut_path))

    install_loc_l = install_loc.lower()
    for root in shortcut_roots:
        for lnk in _discover_shortcuts(root):
            stem_l = lnk.stem.lower()
            matched = any(tok in stem_l for tok in tokens)
            if not matched:
                meta = _read_shortcut_metadata(lnk)
                target_l = meta.get("target_path", "").lower()
                matched = bool(
                    (install_loc_l and target_l and install_loc_l in target_l)
                    or (target_l and any(tok in target_l for tok in tokens))
                )
            if matched:
                leftovers["files"].append(str(lnk))

    # Add original uninstall entry path when available.
    reg_path = str(program.get("reg_path", "") or "")
    if reg_path:
        leftovers["registry"].append(reg_path)

    # Broad registry key scan based on top-level software keys.
    reg_locations = [
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node"),
    ]
    for hive, base_key in reg_locations:
        try:
            key = winreg.OpenKey(hive, base_key)
        except OSError:
            continue

        try:
            i = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(key, i)
                    i += 1
                    sub_l = subkey_name.lower()
                    if any(tok in sub_l for tok in tokens):
                        hive_name = "HKCU" if hive == winreg.HKEY_CURRENT_USER else "HKLM"
                        leftovers["registry"].append(f"{hive_name}\\{base_key}\\{subkey_name}")
                except OSError:
                    break
        finally:
            winreg.CloseKey(key)

    # Run/RunOnce values related to the app.
    run_keys = [
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"),
    ]
    for hive, key_path in run_keys:
        try:
            run_key = winreg.OpenKey(hive, key_path)
        except OSError:
            continue

        try:
            i = 0
            while True:
                try:
                    value_name, value_data, _ = winreg.EnumValue(run_key, i)
                    i += 1
                    blob = f"{value_name} {value_data}".lower()
                    if any(tok in blob for tok in tokens):
                        hive_name = "HKCU" if hive == winreg.HKEY_CURRENT_USER else "HKLM"
                        leftovers["registry_values"].append(
                            f"{hive_name}\\{key_path}::{value_name}"
                        )
                except OSError:
                    break
        finally:
            winreg.CloseKey(run_key)

    for key in leftovers:
        leftovers[key] = sorted(set(leftovers[key]))

    logger.info(
        f"Found leftovers for {name}: "
        f"{len(leftovers['files'])} files, "
        f"{len(leftovers['dirs'])} dirs, "
        f"{len(leftovers['registry'])} registry keys, "
        f"{len(leftovers['registry_values'])} registry values"
    )
    return leftovers


def _delete_registry_tree(hive, subkey_path: str) -> bool:
    """Delete a registry key recursively."""
    try:
        key = winreg.OpenKey(hive, subkey_path, 0, winreg.KEY_READ | winreg.KEY_WRITE)
    except FileNotFoundError:
        return True
    except OSError:
        try:
            winreg.DeleteKey(hive, subkey_path)
            return True
        except OSError:
            return False

    try:
        while True:
            try:
                sub = winreg.EnumKey(key, 0)
            except OSError:
                break
            _delete_registry_tree(hive, f"{subkey_path}\\{sub}")
    finally:
        winreg.CloseKey(key)

    try:
        winreg.DeleteKey(hive, subkey_path)
        return True
    except OSError:
        return False


def remove_leftovers(leftovers: dict[str, list[str]], logger: CleanerLogger) -> int:
    """Remove leftover files and directories. Returns bytes freed."""
    total_freed = 0

    # Remove files first
    for filepath in sorted(set(leftovers.get("files", [])), key=len, reverse=True):
        try:
            path = Path(filepath)
            if path.exists() and path.is_file():
                size = path.stat().st_size
                path.unlink()
                total_freed += size
                logger.log("remove_leftover", "uninstaller", f"Removed file: {filepath}", size)
        except (PermissionError, OSError) as e:
            logger.warning(f"Cannot remove: {filepath} - {e}")

    # Remove directories
    for dirpath in sorted(set(leftovers.get("dirs", [])), key=len, reverse=True):
        try:
            path = Path(dirpath)
            if path.exists():
                size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
                shutil.rmtree(path, ignore_errors=True)
                total_freed += size
                logger.log("remove_leftover", "uninstaller", f"Removed dir: {dirpath}", size)
        except (PermissionError, OSError) as e:
            logger.warning(f"Cannot remove dir: {dirpath} - {e}")

    if os.name == "nt":
        # Remove startup/run values before deleting whole keys.
        for reg_value in sorted(set(leftovers.get("registry_values", [])), key=len, reverse=True):
            try:
                full_key, value_name = reg_value.split("::", 1)
                hive_prefix, subkey = full_key.split("\\", 1)
                hive = winreg.HKEY_CURRENT_USER if hive_prefix == "HKCU" else winreg.HKEY_LOCAL_MACHINE

                key = winreg.OpenKey(hive, subkey, 0, winreg.KEY_SET_VALUE)
                try:
                    winreg.DeleteValue(key, value_name)
                finally:
                    winreg.CloseKey(key)

                logger.log("remove_leftover", "uninstaller", f"Removed registry value: {reg_value}")
            except OSError as e:
                logger.warning(f"Cannot remove registry value: {reg_value} - {e}")
            except ValueError:
                logger.warning(f"Bad registry value format: {reg_value}")

        # Remove registry entries
        for reg_path in sorted(set(leftovers.get("registry", [])), key=len, reverse=True):
            try:
                parts = reg_path.split("\\", 1)
                if len(parts) != 2:
                    logger.warning(f"Bad registry path format: {reg_path}")
                    continue
                hive = winreg.HKEY_CURRENT_USER if parts[0] == "HKCU" else winreg.HKEY_LOCAL_MACHINE
                removed = _delete_registry_tree(hive, parts[1])
                if removed:
                    logger.log("remove_leftover", "uninstaller", f"Removed registry: {reg_path}")
                else:
                    logger.warning(f"Cannot remove registry: {reg_path}")
            except OSError as e:
                logger.warning(f"Cannot remove registry: {reg_path} - {e}")

    return total_freed


def full_uninstall_program(
    program: dict[str, Any],
    logger: CleanerLogger,
    silent: bool = True,
    shortcut_path: str = "",
) -> dict[str, Any]:
    """
    Run uninstall and then aggressively remove all detected related leftovers.
    Returns operation summary with bytes freed and found artifact counts.
    """
    uninstall_ok = uninstall_program(program, logger, silent=silent)

    leftovers = find_leftovers(
        program,
        logger,
        extra_terms=[program.get("name", ""), program.get("publisher", "")],
        shortcut_path=shortcut_path,
    )
    bytes_freed = remove_leftovers(leftovers, logger)

    result = {
        "name": program.get("name", ""),
        "uninstall_ok": uninstall_ok,
        "bytes_freed": bytes_freed,
        "leftovers_found": {
            "files": len(leftovers.get("files", [])),
            "dirs": len(leftovers.get("dirs", [])),
            "registry": len(leftovers.get("registry", [])),
            "registry_values": len(leftovers.get("registry_values", [])),
        },
    }

    logger.log(
        "full_uninstall",
        "uninstaller",
        (
            f"Full uninstall for {program.get('name', 'unknown')}: "
            f"uninstall={'ok' if uninstall_ok else 'failed'}, "
            f"artifacts={result['leftovers_found']}, freed={bytes_freed}"
        ),
        bytes_freed,
        success=uninstall_ok,
    )
    return result


def remove_traced_files(files: list[str], logger: CleanerLogger) -> int:
    """Remove files traced during an application's runtime. Returns bytes freed."""
    total_freed = 0
    for filepath in files:
        try:
            path = Path(filepath)
            if path.exists() and path.is_file():
                size = path.stat().st_size
                path.unlink()
                total_freed += size
                logger.log("remove_traced", "uninstaller", f"Removed traced file: {filepath}", size)
        except (PermissionError, OSError) as e:
            logger.warning(f"Cannot remove traced file: {filepath} - {e}")
    return total_freed


def detect_orphaned_entries(logger: CleanerLogger) -> list[dict]:
    """Detect registry entries pointing to non-existent install locations."""
    orphaned = []
    programs = list_installed_programs(logger)
    for prog in programs:
        install_loc = prog.get("install_location", "")
        uninstall_str = prog.get("uninstall_string", "")
        is_orphan = False

        if install_loc and not Path(install_loc).exists():
            is_orphan = True
        elif uninstall_str:
            # Extract executable path from uninstall string
            exe_path = uninstall_str.strip('"').split('"')[0]
            if exe_path and not Path(exe_path).exists():
                is_orphan = True

        if is_orphan:
            orphaned.append(prog)

    logger.info(f"Found {len(orphaned)} orphaned registry entries")
    return orphaned


def batch_uninstall(programs: list[dict], logger: CleanerLogger,
                    silent: bool = True) -> dict[str, bool]:
    """Uninstall multiple programs. Returns dict of name -> success."""
    results = {}
    for prog in programs:
        results[prog["name"]] = uninstall_program(prog, logger, silent)
    return results

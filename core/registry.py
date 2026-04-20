"""Registry cleaner - scan, fix, backup, restore invalid entries."""

import base64
import json
import os
import subprocess
import winreg
from datetime import datetime
from pathlib import Path
from typing import Any
from core.logger import CleanerLogger


# Registry locations to scan for invalid entries
SCAN_LOCATIONS = [
    # Shared DLLs
    (winreg.HKEY_LOCAL_MACHINE,
     r"SOFTWARE\Microsoft\Windows\CurrentVersion\SharedDLLs",
     "shared_dlls"),
    # File extensions
    (winreg.HKEY_CLASSES_ROOT, "", "file_associations"),
    # App Paths
    (winreg.HKEY_LOCAL_MACHINE,
     r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
     "app_paths"),
    # Uninstall entries
    (winreg.HKEY_LOCAL_MACHINE,
     r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
     "uninstall"),
    (winreg.HKEY_CURRENT_USER,
     r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
     "uninstall_user"),
    # MUI Cache
    (winreg.HKEY_CURRENT_USER,
     r"SOFTWARE\Classes\Local Settings\Software\Microsoft\Windows\Shell\MuiCache",
     "mui_cache"),
]

RISK_LEVELS = {
    "shared_dlls": "medium",
    "file_associations": "low",
    "app_paths": "low",
    "uninstall": "medium",
    "uninstall_user": "low",
    "mui_cache": "low",
}


SNAPSHOT_HIVES = [
    ("HKCU", winreg.HKEY_CURRENT_USER),
    ("HKLM", winreg.HKEY_LOCAL_MACHINE),
    ("HKCR", winreg.HKEY_CLASSES_ROOT),
    ("HKU", winreg.HKEY_USERS),
    ("HKCC", winreg.HKEY_CURRENT_CONFIG),
]

HIVE_BY_NAME = {name: hive for name, hive in SNAPSHOT_HIVES}

_REG_TYPE_NAMES: dict[int, str] = {}
for _type_name in (
    "REG_NONE",
    "REG_SZ",
    "REG_EXPAND_SZ",
    "REG_BINARY",
    "REG_DWORD",
    "REG_DWORD_BIG_ENDIAN",
    "REG_LINK",
    "REG_MULTI_SZ",
    "REG_RESOURCE_LIST",
    "REG_FULL_RESOURCE_DESCRIPTOR",
    "REG_RESOURCE_REQUIREMENTS_LIST",
    "REG_QWORD",
):
    if hasattr(winreg, _type_name):
        _REG_TYPE_NAMES[getattr(winreg, _type_name)] = _type_name

_REG_TYPE_BY_NAME = {name: type_id for type_id, name in _REG_TYPE_NAMES.items()}
_DEFAULT_TYPE_ID = _REG_TYPE_BY_NAME.get("REG_SZ", 1)

_BINARY_TYPE_IDS: set[int] = set()
for _name in (
    "REG_BINARY",
    "REG_RESOURCE_LIST",
    "REG_FULL_RESOURCE_DESCRIPTOR",
    "REG_RESOURCE_REQUIREMENTS_LIST",
):
    if _name in _REG_TYPE_BY_NAME:
        _BINARY_TYPE_IDS.add(_REG_TYPE_BY_NAME[_name])

_INT_TYPE_IDS: set[int] = set()
for _name in ("REG_DWORD", "REG_DWORD_BIG_ENDIAN", "REG_QWORD"):
    if _name in _REG_TYPE_BY_NAME:
        _INT_TYPE_IDS.add(_REG_TYPE_BY_NAME[_name])


def _normalize_key_path(key_path: str) -> str:
    return key_path.strip().strip("\\")


def _normalize_value_name(value_name: str) -> str:
    name = value_name.strip()
    if name in ("", "@"):
        return ""
    if name.lower() == "(default)":
        return ""
    return name


def _parse_hive_and_key(hive_name: str, key_path: str) -> tuple[str, str]:
    hive_raw = (hive_name or "").strip()
    key_raw = (key_path or "").strip()

    # Allow callers to pass full key as either first or second argument.
    for candidate in (hive_raw, key_raw):
        if "\\" in candidate:
            maybe_hive, maybe_path = candidate.split("\\", 1)
            maybe_hive = maybe_hive.upper().strip()
            if maybe_hive in HIVE_BY_NAME:
                return maybe_hive, _normalize_key_path(maybe_path)

    hive_norm = hive_raw.upper()
    if hive_norm in HIVE_BY_NAME:
        return hive_norm, _normalize_key_path(key_raw)

    return hive_norm, _normalize_key_path(key_raw)


def _reg_type_name(type_id: int) -> str:
    return _REG_TYPE_NAMES.get(type_id, f"REG_UNKNOWN_{type_id}")


def _resolve_reg_type(reg_type: str | int | None, default: int = _DEFAULT_TYPE_ID) -> int:
    if isinstance(reg_type, int):
        return reg_type
    if isinstance(reg_type, str):
        value = reg_type.strip().upper()
        if value.isdigit():
            return int(value)
        return _REG_TYPE_BY_NAME.get(value, default)
    return default


def _serialize_registry_data(value: Any) -> tuple[Any, str]:
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii"), "base64"
    if isinstance(value, tuple):
        return list(value), "plain"
    return value, "plain"


def _deserialize_registry_data(value: Any, encoding: str) -> Any:
    if encoding == "base64" and isinstance(value, str):
        return base64.b64decode(value.encode("ascii"))
    return value


def _parse_registry_value_input(raw_value: str, type_id: int) -> Any:
    if type_id in _INT_TYPE_IDS:
        return int(raw_value.strip(), 0)

    if type_id in _BINARY_TYPE_IDS:
        compact = raw_value.replace(" ", "").replace(",", "")
        if compact == "":
            return b""
        if len(compact) % 2 != 0:
            raise ValueError("Binary value must have an even number of hex digits")
        return bytes.fromhex(compact)

    multi_sz_type = _REG_TYPE_BY_NAME.get("REG_MULTI_SZ")
    if multi_sz_type is not None and type_id == multi_sz_type:
        if raw_value.strip() == "":
            return []
        return [part.strip() for part in raw_value.split("|") if part.strip()]

    return raw_value


def _snapshot_stats_from_entries(entries: list[dict[str, Any]],
                                 error_count: int = 0) -> dict[str, int]:
    return {
        "keys": len(entries),
        "values": sum(len(entry.get("values", [])) for entry in entries),
        "errors": error_count,
    }


def _load_snapshot(snapshot_file: str) -> dict[str, Any]:
    return json.loads(Path(snapshot_file).read_text(encoding="utf-8"))


def _save_snapshot(snapshot_file: str, snapshot: dict[str, Any]) -> None:
    snapshot["updated_at"] = datetime.now().isoformat()
    Path(snapshot_file).write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _find_snapshot_entry(snapshot: dict[str, Any], hive_name: str,
                         key_path: str) -> dict[str, Any] | None:
    hive_norm, key_norm = _parse_hive_and_key(hive_name, key_path)
    for entry in snapshot.get("entries", []):
        if str(entry.get("hive", "")).upper() != hive_norm:
            continue
        entry_key = _normalize_key_path(str(entry.get("key_path", "")))
        if entry_key.lower() == key_norm.lower():
            return entry
    return None


def create_registry_snapshot_json(output_file: str = "",
                                  logger: CleanerLogger | None = None) -> str:
    """Create a JSON snapshot of registry keys and values across major hives."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_file = Path("backups") / f"registry_snapshot_{timestamp}.json"
    output_path = Path(output_file) if output_file else default_file
    output_path.parent.mkdir(parents=True, exist_ok=True)

    entries: list[dict[str, Any]] = []
    error_samples: list[dict[str, str]] = []
    error_count = 0

    def _record_error(hive_name: str, key_path: str, exc: Exception):
        nonlocal error_count
        error_count += 1
        if len(error_samples) < 200:
            error_samples.append({
                "hive": hive_name,
                "key_path": key_path,
                "error": str(exc),
            })

    for hive_name, hive in SNAPSHOT_HIVES:
        stack: list[str] = [""]

        while stack:
            key_path = stack.pop()
            try:
                key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
            except OSError as e:
                _record_error(hive_name, key_path, e)
                continue

            try:
                subkey_count, value_count, _ = winreg.QueryInfoKey(key)

                values: list[dict[str, Any]] = []
                for idx in range(value_count):
                    try:
                        value_name, value_data, value_type = winreg.EnumValue(key, idx)
                        serialized_data, encoding = _serialize_registry_data(value_data)
                        values.append({
                            "name": value_name,
                            "type": _reg_type_name(value_type),
                            "type_id": value_type,
                            "data": serialized_data,
                            "encoding": encoding,
                        })
                    except OSError as e:
                        _record_error(hive_name, key_path, e)

                entries.append({
                    "hive": hive_name,
                    "key_path": key_path,
                    "values": values,
                })

                for idx in range(subkey_count):
                    try:
                        subkey_name = winreg.EnumKey(key, idx)
                        next_path = f"{key_path}\\{subkey_name}" if key_path else subkey_name
                        stack.append(next_path)
                    except OSError as e:
                        _record_error(hive_name, key_path, e)
            finally:
                winreg.CloseKey(key)

    snapshot = {
        "format": "system_cleaner_registry_snapshot_v1",
        "created_at": datetime.now().isoformat(),
        "machine": os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME", ""),
        "entries": entries,
        "stats": _snapshot_stats_from_entries(entries, error_count),
        "error_samples": error_samples,
    }

    output_path.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if logger:
        logger.log(
            "snapshot_registry_json",
            "registry",
            f"Registry snapshot saved: {output_path}",
        )

    return str(output_path)


def get_snapshot_info(snapshot_file: str) -> dict[str, Any]:
    """Return metadata and counts for a registry snapshot JSON file."""
    snapshot = _load_snapshot(snapshot_file)
    entries = snapshot.get("entries", [])
    stats = snapshot.get("stats") or _snapshot_stats_from_entries(entries)
    return {
        "path": snapshot_file,
        "format": snapshot.get("format", "unknown"),
        "created_at": snapshot.get("created_at", ""),
        "updated_at": snapshot.get("updated_at", ""),
        "machine": snapshot.get("machine", ""),
        "keys": stats.get("keys", len(entries)),
        "values": stats.get("values", sum(len(e.get("values", [])) for e in entries)),
        "errors": stats.get("errors", 0),
    }


def list_snapshot_keys(snapshot_file: str, query: str = "",
                       limit: int = 25) -> list[dict[str, Any]]:
    """List keys from a snapshot, optionally filtered by query text."""
    snapshot = _load_snapshot(snapshot_file)
    entries = snapshot.get("entries", [])
    q = query.lower().strip()
    results: list[dict[str, Any]] = []

    for entry in entries:
        hive = str(entry.get("hive", ""))
        key_path = str(entry.get("key_path", ""))
        values = entry.get("values", [])
        full_key = f"{hive}\\{key_path}" if key_path else hive

        if q:
            match_in_values = any(q in str(v.get("name", "")).lower() for v in values)
            if q not in full_key.lower() and not match_in_values:
                continue

        results.append({
            "hive": hive,
            "key_path": key_path,
            "value_count": len(values),
            "sample_values": [str(v.get("name", "")) for v in values[:3]],
        })

        if limit > 0 and len(results) >= limit:
            break

    return results


def edit_snapshot_value(snapshot_file: str, hive_name: str, key_path: str,
                        value_name: str, value_raw: str,
                        value_type: str | int | None = None,
                        logger: CleanerLogger | None = None) -> bool:
    """Edit or create a single value inside a snapshot JSON file."""
    snapshot = _load_snapshot(snapshot_file)
    hive_norm, key_norm = _parse_hive_and_key(hive_name, key_path)
    if hive_norm not in HIVE_BY_NAME:
        raise ValueError(f"Unsupported hive: {hive_name}")

    entry = _find_snapshot_entry(snapshot, hive_norm, key_norm)
    if entry is None:
        entry = {
            "hive": hive_norm,
            "key_path": key_norm,
            "values": [],
        }
        snapshot.setdefault("entries", []).append(entry)

    normalized_name = _normalize_value_name(value_name)
    values = entry.setdefault("values", [])

    existing = None
    for item in values:
        if _normalize_value_name(str(item.get("name", ""))).lower() == normalized_name.lower():
            existing = item
            break

    if value_type is None and existing is not None:
        type_id = _resolve_reg_type(existing.get("type_id", existing.get("type")), _DEFAULT_TYPE_ID)
    else:
        type_id = _resolve_reg_type(value_type, _DEFAULT_TYPE_ID)

    parsed_value = _parse_registry_value_input(value_raw, type_id)
    serialized_value, encoding = _serialize_registry_data(parsed_value)
    value_payload = {
        "name": normalized_name,
        "type": _reg_type_name(type_id),
        "type_id": type_id,
        "data": serialized_value,
        "encoding": encoding,
    }

    if existing is None:
        values.append(value_payload)
    else:
        existing.update(value_payload)

    prev_errors = int(snapshot.get("stats", {}).get("errors", 0))
    snapshot["stats"] = _snapshot_stats_from_entries(snapshot.get("entries", []), prev_errors)
    _save_snapshot(snapshot_file, snapshot)

    if logger:
        logger.log(
            "edit_snapshot_value",
            "registry",
            f"Updated {hive_norm}\\{key_norm}::{normalized_name or '(Default)'} in snapshot",
        )

    return True


def delete_snapshot_key(snapshot_file: str, hive_name: str, key_path: str,
                        logger: CleanerLogger | None = None) -> bool:
    """Delete an entire key record from snapshot JSON."""
    snapshot = _load_snapshot(snapshot_file)
    hive_norm, key_norm = _parse_hive_and_key(hive_name, key_path)
    if hive_norm not in HIVE_BY_NAME:
        raise ValueError(f"Unsupported hive: {hive_name}")

    entries = snapshot.get("entries", [])
    before = len(entries)
    snapshot["entries"] = [
        e for e in entries
        if not (
            str(e.get("hive", "")).upper() == hive_norm and
            _normalize_key_path(str(e.get("key_path", ""))).lower() == key_norm.lower()
        )
    ]

    if len(snapshot["entries"]) == before:
        return False

    prev_errors = int(snapshot.get("stats", {}).get("errors", 0))
    snapshot["stats"] = _snapshot_stats_from_entries(snapshot.get("entries", []), prev_errors)
    _save_snapshot(snapshot_file, snapshot)

    if logger:
        logger.log("delete_snapshot_key", "registry", f"Removed {hive_norm}\\{key_norm} from snapshot")

    return True


def delete_snapshot_value(snapshot_file: str, hive_name: str, key_path: str,
                          value_name: str,
                          logger: CleanerLogger | None = None) -> bool:
    """Delete one value from a snapshot key."""
    snapshot = _load_snapshot(snapshot_file)
    hive_norm, key_norm = _parse_hive_and_key(hive_name, key_path)
    if hive_norm not in HIVE_BY_NAME:
        raise ValueError(f"Unsupported hive: {hive_name}")

    entry = _find_snapshot_entry(snapshot, hive_norm, key_norm)
    if entry is None:
        return False

    target_name = _normalize_value_name(value_name).lower()
    values = entry.get("values", [])
    before = len(values)
    entry["values"] = [
        v for v in values
        if _normalize_value_name(str(v.get("name", ""))).lower() != target_name
    ]

    if len(entry["values"]) == before:
        return False

    prev_errors = int(snapshot.get("stats", {}).get("errors", 0))
    snapshot["stats"] = _snapshot_stats_from_entries(snapshot.get("entries", []), prev_errors)
    _save_snapshot(snapshot_file, snapshot)

    if logger:
        logger.log(
            "delete_snapshot_value",
            "registry",
            f"Removed value {value_name or '(Default)'} from {hive_norm}\\{key_norm} in snapshot",
        )

    return True


def import_registry_snapshot(snapshot_file: str,
                             logger: CleanerLogger | None = None) -> dict[str, int]:
    """Import keys/values from a snapshot JSON file back into the registry."""
    snapshot = _load_snapshot(snapshot_file)
    entries = snapshot.get("entries", [])
    results = {
        "keys_total": 0,
        "keys_opened": 0,
        "values_total": 0,
        "values_imported": 0,
        "failed": 0,
    }

    for entry in entries:
        hive_name = str(entry.get("hive", "")).upper()
        key_path = _normalize_key_path(str(entry.get("key_path", "")))
        values = entry.get("values", [])
        results["keys_total"] += 1

        hive = HIVE_BY_NAME.get(hive_name)
        if hive is None:
            results["failed"] += 1
            if logger:
                logger.error(f"Skipping unknown hive '{hive_name}' in snapshot")
            continue

        try:
            if key_path:
                key = winreg.CreateKeyEx(hive, key_path, 0, winreg.KEY_WRITE)
            else:
                key = winreg.OpenKey(hive, "", 0, winreg.KEY_WRITE)
            results["keys_opened"] += 1
        except OSError as e:
            results["failed"] += 1
            if logger:
                logger.error(f"Cannot open key {hive_name}\\{key_path}: {e}")
            continue

        try:
            for value in values:
                results["values_total"] += 1
                try:
                    value_name = _normalize_value_name(str(value.get("name", "")))
                    type_id = _resolve_reg_type(value.get("type_id", value.get("type")), _DEFAULT_TYPE_ID)
                    value_data = _deserialize_registry_data(value.get("data"), str(value.get("encoding", "plain")))
                    winreg.SetValueEx(key, value_name, 0, type_id, value_data)
                    results["values_imported"] += 1
                except Exception as e:
                    results["failed"] += 1
                    if logger:
                        logger.error(
                            f"Failed to import value {value.get('name', '')} "
                            f"at {hive_name}\\{key_path}: {e}"
                        )
        finally:
            winreg.CloseKey(key)

    if logger:
        logger.log(
            "import_registry_snapshot",
            "registry",
            f"Imported {results['values_imported']}/{results['values_total']} values from snapshot",
        )

    return results


def scan_invalid_entries(logger: CleanerLogger,
                         progress_callback=None) -> list[dict[str, Any]]:
    """Scan registry for invalid entries (broken paths, missing files)."""
    invalid = []
    total_scanned = 0

    for hive, key_path, category in SCAN_LOCATIONS:
        try:
            if category == "shared_dlls":
                invalid.extend(_scan_shared_dlls(hive, key_path, logger))
            elif category == "app_paths":
                invalid.extend(_scan_app_paths(hive, key_path, logger))
            elif category in ("uninstall", "uninstall_user"):
                invalid.extend(_scan_uninstall_entries(hive, key_path, logger))
            elif category == "mui_cache":
                invalid.extend(_scan_mui_cache(hive, key_path, logger))
            elif category == "file_associations":
                invalid.extend(_scan_file_associations(hive, logger))

            total_scanned += 1
            if progress_callback:
                progress_callback(total_scanned, len(SCAN_LOCATIONS))
        except Exception as e:
            logger.error(f"Error scanning {category}: {e}")

    logger.info(f"Registry scan complete: {len(invalid)} invalid entries found")
    return invalid


def _scan_shared_dlls(hive, key_path: str, logger: CleanerLogger) -> list[dict]:
    """Find SharedDLLs entries pointing to non-existent files."""
    invalid = []
    try:
        key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
        i = 0
        while True:
            try:
                name, value, _ = winreg.EnumValue(key, i)
                if not Path(name).exists():
                    invalid.append({
                        "category": "Shared DLLs",
                        "key_path": f"HKLM\\{key_path}",
                        "value_name": name,
                        "value_data": str(value),
                        "issue": f"File not found: {name}",
                        "risk": "medium",
                        "hive": hive,
                        "full_key": key_path,
                    })
                i += 1
            except OSError:
                break
        winreg.CloseKey(key)
    except OSError:
        pass
    return invalid


def _scan_app_paths(hive, key_path: str, logger: CleanerLogger) -> list[dict]:
    """Find App Paths entries pointing to non-existent executables."""
    invalid = []
    try:
        key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
        i = 0
        while True:
            try:
                subkey_name = winreg.EnumKey(key, i)
                subkey = winreg.OpenKey(key, subkey_name)
                try:
                    exe_path, _ = winreg.QueryValueEx(subkey, "")
                    if exe_path and not Path(exe_path.strip('"')).exists():
                        invalid.append({
                            "category": "App Paths",
                            "key_path": f"HKLM\\{key_path}\\{subkey_name}",
                            "value_name": "(Default)",
                            "value_data": exe_path,
                            "issue": f"Executable not found: {exe_path}",
                            "risk": "low",
                            "hive": hive,
                            "full_key": f"{key_path}\\{subkey_name}",
                        })
                except (FileNotFoundError, OSError):
                    pass
                winreg.CloseKey(subkey)
                i += 1
            except OSError:
                break
        winreg.CloseKey(key)
    except OSError:
        pass
    return invalid


def _scan_uninstall_entries(hive, key_path: str, logger: CleanerLogger) -> list[dict]:
    """Find uninstall entries with invalid paths."""
    invalid = []
    hive_name = "HKLM" if hive == winreg.HKEY_LOCAL_MACHINE else "HKCU"
    try:
        key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
        i = 0
        while True:
            try:
                subkey_name = winreg.EnumKey(key, i)
                subkey = winreg.OpenKey(key, subkey_name)
                try:
                    uninstall_str, _ = winreg.QueryValueEx(subkey, "UninstallString")
                    exe = uninstall_str.strip('"').split('"')[0].split(" ")[0]
                    if exe and not Path(exe).exists() and not exe.lower().startswith("msiexec"):
                        name = ""
                        try:
                            name, _ = winreg.QueryValueEx(subkey, "DisplayName")
                        except (FileNotFoundError, OSError):
                            name = subkey_name
                        invalid.append({
                            "category": "Uninstall Entries",
                            "key_path": f"{hive_name}\\{key_path}\\{subkey_name}",
                            "value_name": name or subkey_name,
                            "value_data": uninstall_str,
                            "issue": f"Uninstaller not found: {exe}",
                            "risk": "medium",
                            "hive": hive,
                            "full_key": f"{key_path}\\{subkey_name}",
                        })
                except (FileNotFoundError, OSError):
                    pass
                winreg.CloseKey(subkey)
                i += 1
            except OSError:
                break
        winreg.CloseKey(key)
    except OSError:
        pass
    return invalid


def _scan_mui_cache(hive, key_path: str, logger: CleanerLogger) -> list[dict]:
    """Find MUI cache entries for non-existent files."""
    invalid = []
    try:
        key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
        i = 0
        while True:
            try:
                name, value, _ = winreg.EnumValue(key, i)
                # MUI cache names often contain file paths
                if name and "." in name and not name.startswith("@"):
                    filepath = name.split(".")[0] + "." + name.split(".")[1]
                    if not Path(filepath).exists():
                        invalid.append({
                            "category": "MUI Cache",
                            "key_path": f"HKCU\\{key_path}",
                            "value_name": name,
                            "value_data": str(value),
                            "issue": "Cached entry for missing application",
                            "risk": "low",
                            "hive": hive,
                            "full_key": key_path,
                        })
                i += 1
            except OSError:
                break
        winreg.CloseKey(key)
    except OSError:
        pass
    return invalid


def _scan_file_associations(hive, logger: CleanerLogger) -> list[dict]:
    """Find file associations pointing to non-existent handlers."""
    invalid = []
    try:
        key = winreg.OpenKey(hive, "", 0, winreg.KEY_READ)
        i = 0
        checked = 0
        while checked < 500:  # Limit scan depth
            try:
                subkey_name = winreg.EnumKey(key, i)
                i += 1
                if not subkey_name.startswith("."):
                    continue
                checked += 1
                # Check the associated program
                try:
                    subkey = winreg.OpenKey(key, subkey_name)
                    default_val, _ = winreg.QueryValueEx(subkey, "")
                    if default_val:
                        try:
                            prog_key = winreg.OpenKey(hive, f"{default_val}\\shell\\open\\command")
                            cmd, _ = winreg.QueryValueEx(prog_key, "")
                            exe = cmd.strip('"').split('"')[0].split(" ")[0]
                            if exe and not Path(exe).exists() and "%" not in exe:
                                invalid.append({
                                    "category": "File Associations",
                                    "key_path": f"HKCR\\{subkey_name}",
                                    "value_name": subkey_name,
                                    "value_data": cmd,
                                    "issue": f"Handler not found: {exe}",
                                    "risk": "low",
                                    "hive": hive,
                                    "full_key": subkey_name,
                                })
                            winreg.CloseKey(prog_key)
                        except OSError:
                            pass
                    winreg.CloseKey(subkey)
                except OSError:
                    pass
            except OSError:
                break
        winreg.CloseKey(key)
    except OSError:
        pass
    return invalid


def backup_registry(backup_dir: str = "backups", logger: CleanerLogger | None = None) -> str:
    """Create a full registry backup using reg.exe export."""
    backup_path = Path(backup_dir)
    backup_path.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_path / f"registry_backup_{timestamp}.reg"

    try:
        result = subprocess.run(
            ["reg", "export", "HKLM", str(backup_file), "/y"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            if logger:
                logger.log("backup_registry", "registry",
                          f"Registry backed up to: {backup_file}")
            return str(backup_file)
    except Exception as e:
        if logger:
            logger.error(f"Registry backup failed: {e}")

    return ""


def restore_registry(backup_file: str, logger: CleanerLogger) -> bool:
    """Restore registry from a backup file."""
    if not Path(backup_file).exists():
        logger.error(f"Backup file not found: {backup_file}")
        return False
    try:
        result = subprocess.run(
            ["reg", "import", backup_file],
            capture_output=True, text=True, timeout=120,
        )
        success = result.returncode == 0
        if success:
            logger.log("restore_registry", "registry", f"Registry restored from: {backup_file}")
        else:
            logger.error(f"Registry restore failed: {result.stderr}")
        return success
    except Exception as e:
        logger.error(f"Registry restore error: {e}")
        return False


def fix_invalid_entry(entry: dict, logger: CleanerLogger) -> bool:
    """Remove a single invalid registry entry."""
    try:
        if entry.get("category") == "Shared DLLs":
            key = winreg.OpenKey(entry["hive"], entry["full_key"], 0, winreg.KEY_WRITE)
            winreg.DeleteValue(key, entry["value_name"])
            winreg.CloseKey(key)
        elif entry.get("category") == "MUI Cache":
            key = winreg.OpenKey(entry["hive"], entry["full_key"], 0, winreg.KEY_WRITE)
            winreg.DeleteValue(key, entry["value_name"])
            winreg.CloseKey(key)
        else:
            # For subkey-based entries, delete the entire subkey
            winreg.DeleteKey(entry["hive"], entry["full_key"])

        logger.log("fix_registry", "registry",
                  f"Removed invalid entry: {entry['value_name']}", risk_level=entry["risk"])
        return True
    except OSError as e:
        logger.error(f"Cannot fix registry entry: {entry['value_name']} - {e}")
        return False


def fix_selected_entries(entries: list[dict], logger: CleanerLogger,
                          auto_backup: bool = True) -> dict[str, int]:
    """Fix a caller-supplied subset of registry entries."""
    return fix_all_invalid(entries, logger, auto_backup=auto_backup)


def fix_all_invalid(entries: list[dict], logger: CleanerLogger,
                    auto_backup: bool = True) -> dict[str, int]:
    """Fix all invalid registry entries. Returns counts."""
    if auto_backup:
        backup_registry(logger=logger)

    results = {"fixed": 0, "failed": 0, "skipped": 0}
    for entry in entries:
        if entry.get("risk") == "high":
            results["skipped"] += 1
            continue
        if fix_invalid_entry(entry, logger):
            results["fixed"] += 1
        else:
            results["failed"] += 1

    return results

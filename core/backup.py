"""Encrypted backup manager — backup + encrypt folders, restore + verify."""

import json
import os
import shutil
import time
from pathlib import Path
from typing import Callable

from . import fileencrypt as _enc
from . import integrity   as _intg


_MANIFEST = "backup_manifest.json"


def _collect_files(sources: list[str]) -> list[tuple[Path, str]]:
    """Return [(abs_path, relative_name), ...] for all source files."""
    files = []
    for src in sources:
        p = Path(src)
        if p.is_file():
            files.append((p, p.name))
        elif p.is_dir():
            for child in p.rglob("*"):
                if child.is_file():
                    rel = str(child.relative_to(p.parent))
                    files.append((child, rel))
    return files


def create(
    sources: list[str],
    dest_dir: str,
    password: str,
    algo: str = "AES-256-GCM",
    progress_cb: Callable | None = None,
    logger=None,
) -> dict:
    """Encrypt *sources* into *dest_dir*. Creates a timestamped subfolder.

    Returns summary dict with ok, backup_dir, encrypted, failed, manifest_path.
    """
    ts         = time.strftime("%Y%m%d_%H%M%S")
    backup_dir = Path(dest_dir) / f"backup_{ts}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    files   = _collect_files(sources)
    ok_list: list[dict] = []
    errors:  list[str]  = []

    for i, (src_path, rel) in enumerate(files):
        if progress_cb:
            progress_cb(i + 1, len(files), str(src_path))

        # Recreate directory structure inside backup_dir
        dst_file = backup_dir / (rel.replace("/", "_").replace("\\", "_") + ".scenc")
        try:
            r = _enc.encrypt_file(src_path, password, logger=None, algo=algo,
                                   dst=str(dst_file))
            if r["ok"]:
                import hashlib
                h = hashlib.sha256(src_path.read_bytes()).hexdigest()
                ok_list.append({
                    "original":  str(src_path),
                    "rel":       rel,
                    "encrypted": str(dst_file),
                    "size":      src_path.stat().st_size,
                    "sha256":    h,
                })
            else:
                errors.append(f"{src_path}: {r.get('error', '?')}")
        except Exception as exc:
            errors.append(f"{src_path}: {exc}")

    manifest = {
        "version":    1,
        "created_at": time.time(),
        "created_ts": ts,
        "sources":    sources,
        "algo":       algo,
        "files":      ok_list,
        "errors":     errors,
    }
    manifest_path = backup_dir / _MANIFEST
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if logger:
        logger.log("backup_create", "backup",
                   f"dir={backup_dir} files={len(ok_list)} errors={len(errors)}")

    return {
        "ok":           True,
        "backup_dir":   str(backup_dir),
        "manifest":     str(manifest_path),
        "encrypted":    len(ok_list),
        "failed":       len(errors),
        "errors":       errors,
        "algo":         algo,
    }


def list_backups(dest_dir: str) -> list[dict]:
    """Return metadata for all backups found in *dest_dir*."""
    root    = Path(dest_dir)
    backups = []
    for d in sorted(root.glob("backup_*"), reverse=True):
        m = d / _MANIFEST
        if m.is_file():
            try:
                data = json.loads(m.read_text(encoding="utf-8"))
                backups.append({
                    "dir":       str(d),
                    "ts":        data.get("created_ts", "?"),
                    "created":   data.get("created_at"),
                    "files":     len(data.get("files", [])),
                    "errors":    len(data.get("errors", [])),
                    "algo":      data.get("algo", "?"),
                    "sources":   data.get("sources", []),
                    "size_mb":   round(
                        sum(f.get("size", 0) for f in data.get("files", [])) / 1e6, 2
                    ),
                })
            except Exception:
                pass
    return backups


def restore(
    backup_dir: str,
    dest_dir: str,
    password: str,
    verify: bool = True,
    progress_cb: Callable | None = None,
    logger=None,
) -> dict:
    """Decrypt a backup from *backup_dir* to *dest_dir*.

    If *verify* is True, SHA-256 of restored files is compared to the manifest.
    """
    bd           = Path(backup_dir)
    manifest_path = bd / _MANIFEST
    if not manifest_path.is_file():
        return {"ok": False, "error": "backup_manifest.json not found."}

    data    = json.loads(manifest_path.read_text(encoding="utf-8"))
    files   = data.get("files", [])
    dest    = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    restored: list[str] = []
    errors:   list[str] = []
    bad_hash: list[str] = []

    for i, entry in enumerate(files):
        if progress_cb:
            progress_cb(i + 1, len(files), entry.get("rel", "?"))

        enc_path = Path(entry["encrypted"])
        if not enc_path.is_file():
            errors.append(f"Missing: {enc_path}")
            continue

        out_path = dest / Path(entry["rel"]).name
        r = _enc.decrypt_file(enc_path, password, logger=None, dst=str(out_path))

        if not r["ok"]:
            errors.append(f"{entry['rel']}: {r.get('error', '?')}")
            continue

        restored.append(str(out_path))

        if verify and "sha256" in entry:
            import hashlib
            actual = hashlib.sha256(out_path.read_bytes()).hexdigest()
            if actual != entry["sha256"]:
                bad_hash.append(str(out_path))

    if logger:
        logger.log("backup_restore", "backup",
                   f"dir={backup_dir} restored={len(restored)} errors={len(errors)}")

    return {
        "ok":           len(errors) == 0,
        "restored":     len(restored),
        "failed":       len(errors),
        "hash_mismatch": bad_hash,
        "errors":       errors,
        "dest":         str(dest),
    }


def delete_backup(backup_dir: str) -> dict:
    """Permanently remove a backup directory."""
    try:
        shutil.rmtree(backup_dir)
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

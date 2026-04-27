"""File integrity monitor — create baseline hash snapshot, compare and diff."""

import hashlib
import json
import time
from pathlib import Path
from typing import Callable


def _hash_file(path: Path, algo: str = "sha256", chunk: int = 65536) -> str | None:
    try:
        h = hashlib.new(algo)
        with path.open("rb") as f:
            while True:
                buf = f.read(chunk)
                if not buf:
                    break
                h.update(buf)
        return h.hexdigest()
    except Exception:
        return None


def create_baseline(
    directory: str,
    baseline_file: str,
    algo: str = "sha256",
    exclude_patterns: list[str] | None = None,
    progress_cb: Callable | None = None,
) -> dict:
    """Scan *directory* and write a hash baseline to *baseline_file* (JSON)."""
    root = Path(directory).resolve()
    out  = Path(baseline_file).resolve()
    exclude = list(exclude_patterns or [])

    baseline: dict = {}
    errors:   list = []
    count = 0

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.resolve() == out:
            continue  # never hash the baseline file itself
        rel = str(path.relative_to(root))
        if any(pat in rel for pat in exclude):
            continue
        count += 1
        if progress_cb and count % 50 == 0:
            progress_cb(count, rel)
        digest = _hash_file(path, algo)
        if digest is None:
            errors.append(rel)
            continue
        try:
            stat = path.stat()
            baseline[rel] = {"hash": digest, "size": stat.st_size, "mtime": stat.st_mtime}
        except Exception:
            errors.append(rel)

    data = {
        "created_at": time.time(),
        "directory":  str(root),
        "algo":       algo,
        "files":      baseline,
        "errors":     errors,
    }
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")

    return {
        "ok": True,
        "baseline_file": str(out),
        "scanned": count,
        "hashed":  len(baseline),
        "errors":  len(errors),
        "algo":    algo,
    }


def check_baseline(
    baseline_file: str,
    directory: str | None = None,
    progress_cb: Callable | None = None,
) -> dict:
    """Compare current directory state to a saved baseline."""
    data   = json.loads(Path(baseline_file).read_text(encoding="utf-8"))
    root   = Path(directory or data["directory"]).resolve()
    algo   = data["algo"]
    saved: dict = data["files"]

    added:    list = []
    modified: list = []
    deleted:  list = []
    errors:   list = []
    count = 0

    # Check every saved file
    for rel, info in saved.items():
        count += 1
        if progress_cb and count % 50 == 0:
            progress_cb(count, rel)
        path = root / rel
        if not path.exists():
            deleted.append(rel)
            continue
        digest = _hash_file(path, algo)
        if digest is None:
            errors.append(rel)
            continue
        if digest != info["hash"]:
            entry: dict = {"path": rel, "old_hash": info["hash"], "new_hash": digest,
                           "old_size": info["size"]}
            try:
                entry["new_size"] = path.stat().st_size
            except Exception:
                pass
            modified.append(entry)

    # Detect new files not in baseline (exclude the baseline file itself)
    baseline_abs = Path(baseline_file).resolve()
    current_rels = set()
    for p in root.rglob("*"):
        if p.is_file() and p.resolve() != baseline_abs:
            current_rels.add(str(p.relative_to(root)))
    added = sorted(current_rels - set(saved.keys()))

    return {
        "ok":               True,
        "baseline_created": data.get("created_at"),
        "directory":        str(root),
        "algo":             algo,
        "added":            added,
        "modified":         modified,
        "deleted":          deleted,
        "errors":           errors,
        "clean":            not (added or modified or deleted),
    }


def baseline_meta(baseline_file: str) -> dict | None:
    """Load only the header metadata (fast, no file walking)."""
    try:
        data = json.loads(Path(baseline_file).read_text(encoding="utf-8"))
        import datetime
        ts = data.get("created_at")
        return {
            "created_at":  datetime.datetime.fromtimestamp(ts).isoformat() if ts else "?",
            "directory":   data.get("directory", "?"),
            "algo":        data.get("algo", "?"),
            "file_count":  len(data.get("files", {})),
            "error_count": len(data.get("errors", [])),
        }
    except Exception:
        return None

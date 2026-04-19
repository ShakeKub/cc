"""Duplicate file finder — groups files by SHA-1 hash."""

import hashlib
import os
from collections import defaultdict


def _sha1(path: str, block: int = 65536) -> str | None:
    h = hashlib.sha1()
    try:
        with open(path, "rb") as f:
            while chunk := f.read(block):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def find_duplicates(root: str, min_size: int = 4096, logger=None) -> list[list[dict]]:
    """
    Return groups of duplicate files (≥2 per group), sorted largest-first.
    Each entry: {path, size, modified}.
    Two-pass: first group by size (cheap), then hash only size-collisions.
    """
    size_map: dict[int, list[str]] = defaultdict(list)
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            fp = os.path.join(dirpath, name)
            try:
                sz = os.path.getsize(fp)
                if sz >= min_size:
                    size_map[sz].append(fp)
            except OSError:
                continue

    hash_map: dict[str, list[str]] = defaultdict(list)
    for sz, paths in size_map.items():
        if len(paths) < 2:
            continue
        for p in paths:
            h = _sha1(p)
            if h:
                hash_map[h].append(p)

    groups: list[list[dict]] = []
    for paths in hash_map.values():
        if len(paths) < 2:
            continue
        entries = []
        for p in paths:
            try:
                st = os.stat(p)
                entries.append({"path": p, "size": st.st_size, "modified": st.st_mtime})
            except OSError:
                entries.append({"path": p, "size": 0, "modified": 0.0})
        groups.append(entries)

    groups.sort(key=lambda g: g[0]["size"], reverse=True)
    return groups


def delete_files(paths: list[str], logger=None) -> int:
    """Delete the given files. Returns bytes freed."""
    freed = 0
    for p in paths:
        try:
            sz = os.path.getsize(p)
            os.remove(p)
            freed += sz
            if logger:
                logger.log("dup_delete", "duplicates", f"file={p}")
        except OSError:
            pass
    return freed

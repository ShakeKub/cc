"""Disk space analyzer — folder sizes, large files, extension breakdown."""

import os
from pathlib import Path
from typing import Callable


def analyze(root: str, top_n: int = 20,
            progress_cb: Callable | None = None) -> dict:
    """Walk *root* and return size breakdown by folder and extension."""
    root_path = Path(root).resolve()
    ext_sizes: dict[str, int] = {}
    all_files: list[tuple[int, Path]] = []
    dir_sizes: dict[Path, int] = {}   # direct children size only
    total = 0
    scanned = 0

    for dirpath, dirnames, filenames in os.walk(root_path, followlinks=False,
                                                 onerror=lambda e: None):
        dp = Path(dirpath)
        dir_size = 0
        for fname in filenames:
            fp = dp / fname
            try:
                size = fp.stat().st_size
            except (OSError, PermissionError):
                continue
            total += size
            dir_size += size
            all_files.append((size, fp))
            ext = fp.suffix.lower() or "(no ext)"
            ext_sizes[ext] = ext_sizes.get(ext, 0) + size
            scanned += 1
            if progress_cb and scanned % 200 == 0:
                progress_cb(scanned, str(fp))
        dir_sizes[dp] = dir_size

    # Cumulative folder sizes (bottom-up)
    cumulative: dict[Path, int] = {}
    for dirpath, dirnames, _ in os.walk(root_path, topdown=False, followlinks=False,
                                         onerror=lambda e: None):
        dp = Path(dirpath)
        size = dir_sizes.get(dp, 0)
        for child in dirnames:
            size += cumulative.get(dp / child, 0)
        cumulative[dp] = size

    top_files   = sorted(all_files, key=lambda x: x[0], reverse=True)[:top_n]
    top_folders = sorted(cumulative.items(), key=lambda x: x[1], reverse=True)[:top_n]
    top_exts    = sorted(ext_sizes.items(), key=lambda x: x[1], reverse=True)[:30]

    return {
        "root":         str(root_path),
        "total_bytes":  total,
        "file_count":   len(all_files),
        "top_files":    [(sz, str(p)) for sz, p in top_files],
        "top_folders":  [(str(p), sz) for p, sz in top_folders],
        "ext_breakdown": top_exts,
    }


def fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def bar(pct: float, width: int = 20) -> str:
    filled = int(width * pct / 100)
    return "█" * filled + "░" * (width - filled)

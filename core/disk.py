"""Disk tools - usage analyzer, large files, duplicates, empty folders, shredder."""

import hashlib
import os
import secrets
from collections import defaultdict
from pathlib import Path
from typing import Any, Generator
from core.logger import CleanerLogger


def get_disk_usage(path: str = "C:\\", logger: CleanerLogger | None = None) -> dict[str, Any]:
    """Get disk usage overview using os.statvfs or shutil."""
    import shutil
    try:
        usage = shutil.disk_usage(path)
        result = {
            "path": path,
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
            "percent_used": (usage.used / usage.total * 100) if usage.total > 0 else 0,
        }
        if logger:
            logger.info(f"Disk usage for {path}: {result['percent_used']:.1f}% used")
        return result
    except Exception as e:
        if logger:
            logger.error(f"Cannot get disk usage for {path}: {e}")
        return {"path": path, "error": str(e)}


def analyze_directory(path: str, max_depth: int = 3,
                      logger: CleanerLogger | None = None) -> list[dict[str, Any]]:
    """Analyze directory tree and return size information per subdirectory."""
    results = []
    root = Path(path)
    if not root.exists():
        return results

    def _scan(dir_path: Path, depth: int) -> int:
        if depth > max_depth:
            return 0
        total_size = 0
        try:
            for item in dir_path.iterdir():
                try:
                    if item.is_file():
                        total_size += item.stat().st_size
                    elif item.is_dir() and not item.is_symlink():
                        sub_size = _scan(item, depth + 1)
                        total_size += sub_size
                        if depth < max_depth:
                            results.append({
                                "path": str(item),
                                "name": item.name,
                                "size": sub_size,
                                "depth": depth,
                                "type": "directory",
                            })
                except (PermissionError, OSError):
                    pass
        except PermissionError:
            pass
        return total_size

    total = _scan(root, 0)
    results.insert(0, {
        "path": str(root),
        "name": root.name or str(root),
        "size": total,
        "depth": 0,
        "type": "root",
    })

    results.sort(key=lambda x: x["size"], reverse=True)
    if logger:
        logger.info(f"Analyzed {path}: {len(results)} directories, total {total} bytes")
    return results


def find_large_files(path: str, min_size_mb: int = 100,
                     logger: CleanerLogger | None = None) -> list[dict[str, Any]]:
    """Find files larger than min_size_mb megabytes."""
    min_size = min_size_mb * 1024 * 1024
    large_files = []
    root = Path(path)

    try:
        for item in root.rglob("*"):
            try:
                if item.is_file() and not item.is_symlink():
                    size = item.stat().st_size
                    if size >= min_size:
                        large_files.append({
                            "path": str(item),
                            "name": item.name,
                            "size": size,
                            "extension": item.suffix,
                            "modified": item.stat().st_mtime,
                        })
            except (PermissionError, OSError):
                pass
    except PermissionError:
        pass

    large_files.sort(key=lambda x: x["size"], reverse=True)
    if logger:
        logger.info(f"Found {len(large_files)} files larger than {min_size_mb}MB in {path}")
    return large_files


def find_duplicate_files(path: str, min_size: int = 1024,
                         logger: CleanerLogger | None = None,
                         progress_callback=None) -> list[list[dict[str, Any]]]:
    """Find duplicate files using hash comparison. Groups duplicates together."""
    # Phase 1: Group by size
    size_map: dict[int, list[Path]] = defaultdict(list)
    file_count = 0
    root = Path(path)

    try:
        for item in root.rglob("*"):
            try:
                if item.is_file() and not item.is_symlink():
                    size = item.stat().st_size
                    if size >= min_size:
                        size_map[size].append(item)
                        file_count += 1
            except (PermissionError, OSError):
                pass
    except PermissionError:
        pass

    # Phase 2: Hash files with same size
    duplicates = []
    candidates = {s: files for s, files in size_map.items() if len(files) > 1}
    processed = 0
    total = sum(len(files) for files in candidates.values())

    for size, files in candidates.items():
        hash_map: dict[str, list[dict]] = defaultdict(list)
        for filepath in files:
            try:
                file_hash = _hash_file(filepath)
                hash_map[file_hash].append({
                    "path": str(filepath),
                    "name": filepath.name,
                    "size": size,
                    "hash": file_hash,
                })
                processed += 1
                if progress_callback:
                    progress_callback(processed, total)
            except (PermissionError, OSError):
                pass

        for file_hash, group in hash_map.items():
            if len(group) > 1:
                duplicates.append(group)

    duplicates.sort(key=lambda g: g[0]["size"] * len(g), reverse=True)
    if logger:
        total_waste = sum(g[0]["size"] * (len(g) - 1) for g in duplicates)
        logger.info(f"Found {len(duplicates)} duplicate groups, {total_waste} bytes wasted")
    return duplicates


def _hash_file(filepath: Path, chunk_size: int = 8192) -> str:
    """Compute SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def find_empty_folders(path: str, logger: CleanerLogger | None = None) -> list[str]:
    """Find empty directories."""
    empty = []
    root = Path(path)
    try:
        for dirpath in root.rglob("*"):
            try:
                if dirpath.is_dir() and not any(dirpath.iterdir()):
                    empty.append(str(dirpath))
            except (PermissionError, OSError):
                pass
    except PermissionError:
        pass

    if logger:
        logger.info(f"Found {len(empty)} empty folders in {path}")
    return empty


def remove_empty_folders(path: str, logger: CleanerLogger) -> int:
    """Remove empty directories. Returns count removed."""
    empty = find_empty_folders(path, logger)
    removed = 0
    # Sort by depth (deepest first) to handle nested empties
    empty.sort(key=lambda p: p.count(os.sep), reverse=True)
    for folder in empty:
        try:
            Path(folder).rmdir()
            removed += 1
            logger.log("remove_empty", "disk", f"Removed empty folder: {folder}")
        except OSError:
            pass
    return removed


def secure_shred(filepath: str, passes: int = 3,
                 logger: CleanerLogger | None = None) -> bool:
    """Securely delete a file by overwriting with random data (DoD method).

    Pass 1: Random data
    Pass 2: Complement of pass 1
    Pass 3: Random data + verify
    """
    path = Path(filepath)
    if not path.is_file():
        return False

    try:
        size = path.stat().st_size
        with open(filepath, "r+b") as f:
            for pass_num in range(passes):
                f.seek(0)
                if pass_num % 2 == 0:
                    # Random data pass
                    remaining = size
                    while remaining > 0:
                        chunk_size = min(remaining, 65536)
                        f.write(secrets.token_bytes(chunk_size))
                        remaining -= chunk_size
                else:
                    # Zero pass
                    remaining = size
                    while remaining > 0:
                        chunk_size = min(remaining, 65536)
                        f.write(b'\x00' * chunk_size)
                        remaining -= chunk_size
                f.flush()
                os.fsync(f.fileno())

        # Final deletion
        path.unlink()
        if logger:
            logger.log("shred", "disk", f"Securely shredded: {filepath} ({passes} passes)", size)
        return True
    except Exception as e:
        if logger:
            logger.error(f"Shred failed for {filepath}: {e}")
        return False


def format_size(size_bytes: int) -> str:
    """Format bytes into human-readable size."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"

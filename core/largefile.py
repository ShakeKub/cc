"""Large file finder — locate files above a size threshold."""

import os


def find_large_files(root: str, min_bytes: int = 100 * 1024 * 1024,
                     scan_filter=None, logger=None) -> list[dict]:
    """Return list of files >= min_bytes, sorted largest first."""
    results = []
    for dirpath, dirnames, filenames in os.walk(root):
        if scan_filter:
            dirnames[:] = [d for d in dirnames
                           if not scan_filter.should_skip_dir(os.path.join(dirpath, d))]
        for name in filenames:
            fp = os.path.join(dirpath, name)
            try:
                st = os.stat(fp)
                if scan_filter and scan_filter.should_skip_file(fp, st.st_size):
                    continue
                if st.st_size >= min_bytes:
                    results.append({"path": fp, "size": st.st_size, "modified": st.st_mtime})
            except OSError:
                continue
    results.sort(key=lambda x: x["size"], reverse=True)
    return results


def delete_file(path: str, logger=None) -> bool:
    try:
        os.remove(path)
        if logger:
            logger.log("large_delete", "largefile", f"file={path}")
        return True
    except OSError:
        return False

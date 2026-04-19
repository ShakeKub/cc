"""Secure file wipe — multi-pass overwrite before deletion."""

import os


def _overwrite_passes(path: str, passes: int) -> None:
    size = os.path.getsize(path)
    if size == 0:
        return
    with open(path, "r+b") as f:
        for i in range(passes):
            f.seek(0)
            if i == 0:
                f.write(b"\x00" * size)
            elif i == 1:
                f.write(b"\xff" * size)
            else:
                f.write(os.urandom(size))
            f.flush()
            os.fsync(f.fileno())


def secure_wipe(path: str, passes: int = 3, logger=None) -> bool:
    """Overwrite file content `passes` times then delete. Returns True on success."""
    try:
        _overwrite_passes(path, passes)
        os.remove(path)
        if logger:
            logger.log("secure_wipe", "securewipe", f"passes={passes} file={path}")
        return True
    except OSError as e:
        if logger:
            logger.log("secure_wipe_fail", "securewipe", f"file={path} err={e}", success=False)
        return False


def secure_wipe_dir(root: str, passes: int = 3, logger=None) -> tuple[int, int]:
    """
    Recursively wipe and delete all files under root, then remove empty dirs.
    Returns (files_wiped, bytes_freed).
    """
    wiped = 0
    freed = 0
    for dirpath, _, filenames in os.walk(root, topdown=False):
        for name in filenames:
            fp = os.path.join(dirpath, name)
            try:
                sz = os.path.getsize(fp)
                if secure_wipe(fp, passes, logger):
                    wiped += 1
                    freed += sz
            except OSError:
                pass
        try:
            os.rmdir(dirpath)
        except OSError:
            pass
    return wiped, freed

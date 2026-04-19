"""Empty folder finder and cleaner."""

import os


def find_empty_folders(root: str, logger=None) -> list[str]:
    """
    Return list of empty directory paths (bottom-up order).
    A directory is considered empty if os.listdir() returns nothing,
    which accounts for folders that only contain other empty folders.
    """
    empties = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        if os.path.normpath(dirpath) == os.path.normpath(root):
            continue
        try:
            if not os.listdir(dirpath):
                empties.append(dirpath)
        except OSError:
            continue
    return empties


def delete_folders(folders: list[str], logger=None) -> int:
    """Remove empty directories. Returns count actually deleted."""
    deleted = 0
    for path in folders:
        try:
            os.rmdir(path)
            deleted += 1
            if logger:
                logger.log("empty_folder_delete", "emptyfolders", f"path={path}")
        except OSError:
            pass
    return deleted

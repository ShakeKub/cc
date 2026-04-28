"""Git repository scanner — find all repos on disk with status."""
import os, subprocess
from pathlib import Path
from typing import Callable

_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".cache",
              "venv", ".venv", "dist", "build", "target"}

def _run(cmd, cwd=None, timeout=8):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, cwd=cwd)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception:
        return -1, "", ""

def find_repos(root: str, max_depth: int = 6,
               progress_cb: Callable | None = None) -> list[dict]:
    repos = []
    root_path = Path(root)

    def _walk(path: Path, depth: int):
        if depth > max_depth:
            return
        try:
            entries = list(path.iterdir())
        except PermissionError:
            return
        git_dir = path / ".git"
        if git_dir.is_dir() or git_dir.is_file():
            info = _repo_info(path)
            repos.append(info)
            if progress_cb:
                progress_cb(len(repos), str(path))
            return  # don't recurse into a repo
        for entry in entries:
            if entry.is_dir() and entry.name not in _SKIP_DIRS:
                _walk(entry, depth + 1)

    _walk(root_path, 0)
    return repos

def _repo_info(path: Path) -> dict:
    p = str(path)
    _, branch, _  = _run(["git", "branch", "--show-current"], cwd=p)
    _, status, _  = _run(["git", "status", "--short"], cwd=p)
    _, remotes, _ = _run(["git", "remote", "-v"], cwd=p)
    _, last_log, _ = _run(["git", "log", "-1", "--pretty=%h %s %ar", "--no-walk"], cwd=p)
    _, stash_list, _ = _run(["git", "stash", "list"], cwd=p)

    dirty   = bool(status.strip())
    remote  = remotes.splitlines()[0].split()[1] if remotes.strip() else ""
    stashes = len(stash_list.splitlines()) if stash_list.strip() else 0

    return {
        "path":     p,
        "name":     path.name,
        "branch":   branch or "?",
        "dirty":    dirty,
        "status_lines": len(status.splitlines()),
        "remote":   remote,
        "last_commit": last_log or "",
        "stashes":  stashes,
    }

def repo_full_status(path: str) -> str:
    _, out, _ = _run(["git", "status"], cwd=path, timeout=10)
    return out

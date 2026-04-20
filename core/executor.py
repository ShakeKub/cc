"""MTA Lua Executor — write and deploy client-side Lua resources locally.

User-mode design: scripts are deployed to the LOCAL MTA client's
mods\deathmatch\resources\ folder (no server filesystem access needed,
no .luac compilation needed).  The user starts the resource from the
MTA F8 console with:  start sc_executor
"""

import os
import re
from pathlib import Path
from typing import Any
from core.logger import CleanerLogger

# ── constants ─────────────────────────────────────────────────────────────────

_SCRIPTS_DIR          = Path(__file__).parent.parent / "executor_scripts"
_EXECUTOR_RESOURCE    = "sc_executor"

# Candidate MTA install roots (checked in order)
_MTA_INSTALL_ROOTS = [
    Path(r"C:\Program Files (x86)\MTA San Andreas 1.6"),
    Path(r"C:\Program Files\MTA San Andreas 1.6"),
    Path(r"C:\Program Files (x86)\MTA San Andreas"),
    Path(r"C:\Program Files\MTA San Andreas"),
    Path(r"C:\MTA San Andreas 1.6"),
    Path(r"C:\MTA San Andreas"),
]

# meta.xml templates
_META_CLIENT_ONLY = """\
<meta>
    <info name="SC Executor" description="System Cleaner client script"
          author="SC" version="1.0" type="script"/>
    <script src="client.lua" type="client" cache="false"/>
</meta>
"""

_META_SERVER_ONLY = """\
<meta>
    <info name="SC Executor" description="System Cleaner server script"
          author="SC" version="1.0" type="script"/>
    <script src="server.lua" type="server" cache="false"/>
</meta>
"""

_META_BOTH = """\
<meta>
    <info name="SC Executor" description="System Cleaner script"
          author="SC" version="1.0" type="script"/>
    <script src="client.lua" type="client" cache="false"/>
    <script src="server.lua" type="server" cache="false"/>
</meta>
"""

_CLIENT_HEADER = "-- [SC Executor] client-side\n"
_SERVER_HEADER = "-- [SC Executor] server-side\n"


# ── path discovery ────────────────────────────────────────────────────────────

def find_mta_install() -> str:
    """Return the MTA installation root directory (not the server subfolder)."""
    # 1. Try registry (MTA stores its install path there)
    if os.name == "nt":
        try:
            import winreg as w
            for hive in (w.HKEY_LOCAL_MACHINE, w.HKEY_CURRENT_USER):
                for base in (
                    r"SOFTWARE\WOW6432Node\Multi Theft Auto: San Andreas All",
                    r"SOFTWARE\Multi Theft Auto: San Andreas All",
                ):
                    for version in ("1.6", "1.5", ""):
                        key_path = f"{base}\\{version}".rstrip("\\")
                        for value_name in ("Last Install Location", "Install Location", ""):
                            try:
                                with w.OpenKey(hive, key_path) as key:
                                    if value_name:
                                        val, _ = w.QueryValueEx(key, value_name)
                                        p = Path(str(val))
                                    else:
                                        # Try default value
                                        val, _ = w.QueryValueEx(key, "")
                                        p = Path(str(val))
                                    if p.is_dir() and (p / "mods").is_dir():
                                        return str(p)
                            except OSError:
                                pass
        except ImportError:
            pass

    # 2. Try running MTA processes
    try:
        import psutil
        for proc in psutil.process_iter(["exe"]):
            try:
                exe = proc.info.get("exe") or ""
                if "mta" in exe.lower() and exe.lower().endswith(".exe"):
                    for candidate in (Path(exe).parent, Path(exe).parent.parent):
                        if (candidate / "mods").is_dir():
                            return str(candidate)
            except Exception:
                pass
    except ImportError:
        pass

    # 3. Static path list
    for p in _MTA_INSTALL_ROOTS:
        if p.is_dir() and (p / "mods").is_dir():
            return str(p)

    return ""


def find_resources_dir(logger: CleanerLogger | None = None) -> str:
    """
    Return the LOCAL MTA client resources directory:
      {install}\mods\deathmatch\resources\

    This is the folder the user controls — no server access required.
    Scripts placed here can be started from the MTA F8 console.
    """
    install = find_mta_install()
    if install:
        rd = Path(install) / "mods" / "deathmatch" / "resources"
        if rd.exists():
            return str(rd)
        # Create it if the parent exists
        parent = rd.parent
        if parent.exists():
            try:
                rd.mkdir(parents=True, exist_ok=True)
                return str(rd)
            except OSError:
                pass

    # Fallback: any existing path from the old server search
    old_server_paths = [
        p / "server" / "mods" / "deathmatch" / "resources"
        for p in _MTA_INSTALL_ROOTS
    ]
    for p in old_server_paths:
        if p.exists():
            return str(p)

    return ""


def list_resources(resources_dir: str) -> list[dict]:
    rd = Path(resources_dir)
    if not rd.exists():
        return []
    resources = []
    for item in sorted(rd.iterdir()):
        if item.is_dir():
            meta = item / "meta.xml"
            scripts = list(item.glob("*.lua"))
            resources.append({
                "name":          item.name,
                "path":          str(item),
                "has_meta":      meta.exists(),
                "script_count":  len(scripts),
                "is_executor":   item.name == _EXECUTOR_RESOURCE,
            })
    return resources


# ── deployment ────────────────────────────────────────────────────────────────

def deploy_script(
    code: str,
    script_type: str,         # "client" | "server" | "both"
    resources_dir: str,
    logger: CleanerLogger,
) -> dict[str, Any]:
    """
    Write user Lua code into the sc_executor resource folder.

    For script_type "client" (the default / user mode):
      - Only client.lua is written.
      - meta.xml references only client.lua — no server.lua needed.
      - No server access required.

    For script_type "server" or "both":
      - server.lua is written; meta.xml references it.
      - Only useful if you have access to the SERVER's resources folder.
    """
    rd = Path(resources_dir) / _EXECUTOR_RESOURCE
    rd.mkdir(parents=True, exist_ok=True)

    client_written = server_written = False

    if script_type == "client":
        meta = _META_CLIENT_ONLY
        (rd / "client.lua").write_text(_CLIENT_HEADER + code, encoding="utf-8")
        client_written = True
        # Remove stale server.lua if present
        stale = rd / "server.lua"
        if stale.exists():
            stale.unlink(missing_ok=True)

    elif script_type == "server":
        meta = _META_SERVER_ONLY
        (rd / "server.lua").write_text(_SERVER_HEADER + code, encoding="utf-8")
        server_written = True
        stale = rd / "client.lua"
        if stale.exists():
            stale.unlink(missing_ok=True)

    else:  # "both"
        meta = _META_BOTH
        (rd / "client.lua").write_text(_CLIENT_HEADER + code, encoding="utf-8")
        (rd / "server.lua").write_text(_SERVER_HEADER + code, encoding="utf-8")
        client_written = server_written = True

    (rd / "meta.xml").write_text(meta, encoding="utf-8")

    logger.log("executor_deploy", "executor",
               f"Deployed {script_type} to {rd}")
    return {
        "path":           str(rd),
        "resource_name":  _EXECUTOR_RESOURCE,
        "script_type":    script_type,
        "client_written": client_written,
        "server_written": server_written,
    }


# ── saved scripts ─────────────────────────────────────────────────────────────

def ensure_scripts_dir():
    _SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)


def list_saved_scripts() -> list[dict]:
    ensure_scripts_dir()
    scripts = []
    for f in sorted(_SCRIPTS_DIR.glob("*.lua")):
        try:
            size = f.stat().st_size
            code = f.read_text(encoding="utf-8", errors="replace")
            preview = code.strip().splitlines()[0][:60] if code.strip() else ""
            scripts.append({
                "name":    f.stem,
                "path":    str(f),
                "size":    size,
                "preview": preview,
                "code":    code,
            })
        except OSError:
            pass
    return scripts


def save_script(name: str, code: str) -> bool:
    ensure_scripts_dir()
    safe = re.sub(r"[^\w\-]", "", name)
    if not safe:
        return False
    try:
        (_SCRIPTS_DIR / f"{safe}.lua").write_text(code, encoding="utf-8")
        return True
    except OSError:
        return False


def delete_script(name: str) -> bool:
    ensure_scripts_dir()
    try:
        f = _SCRIPTS_DIR / f"{name}.lua"
        if f.exists():
            f.unlink()
        return True
    except OSError:
        return False


def load_script(name: str) -> str:
    ensure_scripts_dir()
    try:
        return (_SCRIPTS_DIR / f"{name}.lua").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# ── trigger finder ────────────────────────────────────────────────────────────

# Patterns: (category_label, regex)
_TRIGGER_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("addEvent",                re.compile(r'addEvent\s*\(\s*["\']([^"\']+)["\']',               re.IGNORECASE)),
    ("addEventHandler",         re.compile(r'addEventHandler\s*\(\s*["\']([^"\']+)["\']',        re.IGNORECASE)),
    ("triggerServerEvent",      re.compile(r'triggerServerEvent\s*\(\s*["\']([^"\']+)["\']',     re.IGNORECASE)),
    ("triggerClientEvent",      re.compile(r'triggerClientEvent\s*\(\s*["\']([^"\']+)["\']',     re.IGNORECASE)),
    ("triggerLatentServerEvent",re.compile(r'triggerLatentServerEvent\s*\(\s*["\']([^"\']+)["\']', re.IGNORECASE)),
    ("triggerLatentClientEvent",re.compile(r'triggerLatentClientEvent\s*\(\s*["\']([^"\']+)["\']', re.IGNORECASE)),
    ("removeEventHandler",      re.compile(r'removeEventHandler\s*\(\s*["\']([^"\']+)["\']',     re.IGNORECASE)),
]

_CATEGORY_ORDER = [
    "addEvent",
    "addEventHandler",
    "triggerServerEvent",
    "triggerClientEvent",
    "triggerLatentServerEvent",
    "triggerLatentClientEvent",
    "removeEventHandler",
]


def find_triggers(search_path: str) -> dict:
    """
    Recursively scan *.lua files under search_path for MTA event API calls.

    Returns:
      {
        "by_category": {category: [{name, file, line}]},
        "by_event":    {event_name: [{category, file, line}]},
        "files_scanned": int,
        "total": int,
      }
    """
    root = Path(search_path)
    if not root.exists():
        return {"by_category": {}, "by_event": {}, "files_scanned": 0, "total": 0}

    by_category: dict[str, list[dict]] = {c: [] for c, _ in _TRIGGER_PATTERNS}
    by_event:    dict[str, list[dict]] = {}
    files_scanned = 0

    lua_files = list(root.rglob("*.lua"))
    for fpath in lua_files:
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        files_scanned += 1
        lines = text.splitlines()
        for lineno, line in enumerate(lines, 1):
            for cat, pat in _TRIGGER_PATTERNS:
                for m in pat.finditer(line):
                    event_name = m.group(1)
                    entry = {
                        "name":     event_name,
                        "category": cat,
                        "file":     str(fpath.relative_to(root)),
                        "line":     lineno,
                        "context":  line.strip()[:120],
                    }
                    by_category[cat].append(entry)
                    by_event.setdefault(event_name, []).append(entry)

    total = sum(len(v) for v in by_category.values())
    return {
        "by_category":    by_category,
        "by_event":       by_event,
        "files_scanned":  files_scanned,
        "total":          total,
    }


def build_trigger_snippet(event_name: str, entries: list[dict]) -> str:
    """Generate a ready-to-deploy client Lua snippet to call a found trigger."""
    cats = {e["category"] for e in entries}
    if "triggerServerEvent" in cats:
        return (
            f'-- trigger: {event_name}\n'
            f'addCommandHandler("run_{_safe_cmd(event_name)}", function()\n'
            f'    triggerServerEvent("{event_name}", localPlayer)\n'
            f'end)\n'
        )
    elif "addEventHandler" in cats or "addEvent" in cats:
        return (
            f'-- listen for: {event_name}\n'
            f'addEventHandler("{event_name}", root, function(...)\n'
            f'    outputChatBox("[SC] {event_name} fired: " .. tostring(...))\n'
            f'end)\n'
        )
    else:
        return f'-- {event_name}\ntriggerServerEvent("{event_name}", localPlayer)\n'


def _safe_cmd(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)[:32]

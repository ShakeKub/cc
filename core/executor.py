"""MTA Lua Executor — create, manage and deploy Lua resources to MTA SA server."""

import json
import os
import subprocess
from pathlib import Path
from typing import Any
from core.logger import CleanerLogger

# ── paths ─────────────────────────────────────────────────────────────────────

_SCRIPTS_DIR = Path(__file__).parent.parent / "executor_scripts"

# Known MTA server resource directories (checked in order)
_RESOURCE_SEARCH = [
    Path(r"C:\Program Files (x86)\MTA San Andreas 1.6\server\mods\deathmatch\resources"),
    Path(r"C:\Program Files\MTA San Andreas 1.6\server\mods\deathmatch\resources"),
    Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
        / r"MTA San Andreas All\1.6\server\mods\deathmatch\resources",
]

_EXECUTOR_RESOURCE_NAME = "sc_executor"

_META_XML = """\
<meta>
    <info name="SC Executor" description="System Cleaner in-game executor"
          author="SystemCleaner" version="1.0" type="script"/>
    <script src="client.lua"  type="client"  cache="false"/>
    <script src="server.lua"  type="server"  cache="false"/>
</meta>
"""

_SERVER_LUA_WRAPPER = """\
-- SC Executor server bootstrap
addEventHandler("onResourceStart", resourceRoot, function()
    outputChatBox("[SC Executor] Server script loaded.", root, 0, 255, 100)
end)

{user_code}
"""

_CLIENT_LUA_WRAPPER = """\
-- SC Executor client bootstrap
addEventHandler("onClientResourceStart", resourceRoot, function()
    outputChatBox("[SC Executor] Client script loaded.", 0, 255, 100)
end)

{user_code}
"""


# ── resource directory discovery ──────────────────────────────────────────────

def find_resources_dir(logger: CleanerLogger | None = None) -> str:
    """Return the first MTA server resources directory that exists."""
    # Check hardcoded paths
    for p in _RESOURCE_SEARCH:
        if p.exists():
            return str(p)

    # Try to find via running MTA processes
    try:
        import psutil
        for proc in psutil.process_iter(["exe"]):
            try:
                exe = proc.info.get("exe") or ""
                if "mta" in exe.lower() and exe.endswith(".exe"):
                    install = Path(exe).parent
                    # Walk siblings looking for server/mods/deathmatch/resources
                    for base in (install, install.parent):
                        candidate = base / "server" / "mods" / "deathmatch" / "resources"
                        if candidate.exists():
                            return str(candidate)
            except Exception:
                pass
    except ImportError:
        pass

    return ""


def list_resources(resources_dir: str) -> list[dict]:
    """List all resources in the given directory."""
    rd = Path(resources_dir)
    if not rd.exists():
        return []
    resources = []
    for item in sorted(rd.iterdir()):
        if item.is_dir():
            meta = item / "meta.xml"
            scripts = list(item.glob("*.lua"))
            resources.append({
                "name":        item.name,
                "path":        str(item),
                "has_meta":    meta.exists(),
                "script_count": len(scripts),
                "is_executor": item.name == _EXECUTOR_RESOURCE_NAME,
            })
    return resources


# ── resource deployment ───────────────────────────────────────────────────────

def deploy_script(code: str, script_type: str, resources_dir: str,
                   logger: CleanerLogger) -> dict[str, Any]:
    """
    Write user Lua code into the sc_executor resource.
    script_type: "client" | "server" | "both"
    Returns {"path": ..., "client_written": bool, "server_written": bool}.
    """
    rd = Path(resources_dir) / _EXECUTOR_RESOURCE_NAME
    rd.mkdir(parents=True, exist_ok=True)

    # Always write meta.xml
    (rd / "meta.xml").write_text(_META_XML, encoding="utf-8")

    client_written = server_written = False

    if script_type in ("client", "both"):
        client_lua = _CLIENT_LUA_WRAPPER.format(user_code=code)
        (rd / "client.lua").write_text(client_lua, encoding="utf-8")
        client_written = True

    if script_type in ("server", "both"):
        server_lua = _SERVER_LUA_WRAPPER.format(user_code=code)
        (rd / "server.lua").write_text(server_lua, encoding="utf-8")
        server_written = True

    # If only one side, write empty stubs for the other
    if not client_written:
        (rd / "client.lua").write_text(
            "-- client stub\n", encoding="utf-8"
        )
    if not server_written:
        (rd / "server.lua").write_text(
            "-- server stub\n", encoding="utf-8"
        )

    logger.log("executor_deploy", "executor",
               f"Deployed {script_type} script to {rd}")
    return {
        "path":           str(rd),
        "client_written": client_written,
        "server_written": server_written,
        "resource_name":  _EXECUTOR_RESOURCE_NAME,
    }


def restart_resource_via_rcon(host: str, port: int, password: str,
                               resource: str, logger: CleanerLogger) -> bool:
    """
    Send 'restart <resource>' via MTA RCON (UDP) using ncat or PowerShell.
    Falls back to a simple TCP socket approach for MTA's HTTP admin interface.
    """
    # Try MTA HTTP admin interface (default port 22005)
    try:
        import urllib.request, urllib.parse
        url = f"http://{host}:{port}/ajax/resourcelist"
        # MTA HTTP interface uses basic auth
        mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        mgr.add_password(None, url, "admin", password)
        handler = urllib.request.HTTPBasicAuthHandler(mgr)
        opener = urllib.request.build_opener(handler)
        data = urllib.parse.urlencode({"action": "restart", "resource": resource})
        req = urllib.request.Request(
            f"http://{host}:{port}/resourcematch",
            data=data.encode(), method="POST",
        )
        opener.open(req, timeout=5)
        logger.log("executor_rcon", "executor",
                   f"Restarted resource {resource} via HTTP admin")
        return True
    except Exception:
        pass

    logger.log("executor_rcon", "executor",
               f"RCON restart failed for {resource} — use 'restart {resource}' in F8")
    return False


# ── saved scripts ─────────────────────────────────────────────────────────────

def ensure_scripts_dir():
    _SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)


def list_saved_scripts() -> list[dict]:
    """Return saved Lua scripts from the executor_scripts directory."""
    ensure_scripts_dir()
    scripts = []
    for f in sorted(_SCRIPTS_DIR.glob("*.lua")):
        try:
            size = f.stat().st_size
            code = f.read_text(encoding="utf-8", errors="replace")
            preview = code.split("\n")[0][:60]
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
    """Save Lua code to a named file."""
    ensure_scripts_dir()
    safe_name = "".join(c for c in name if c.isalnum() or c in ("_", "-"))
    if not safe_name:
        return False
    try:
        (_SCRIPTS_DIR / f"{safe_name}.lua").write_text(code, encoding="utf-8")
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

"""Process memory / environment inspector.

Levels of access:
  - psutil (all platforms)  : env vars, cmdline, open files, connections, maps
  - Linux /proc/PID/mem     : full heap + stack string extraction
  - Windows ReadProcessMemory: full memory string extraction
  - macOS                   : env + cmdline only (task_for_pid needs entitlements)
"""

import platform
import re
from pathlib import Path
from typing import Callable

import psutil

# Regex patterns for secrets in env vars / command-line args
_SECRET_RE = re.compile(
    r"(password|passwd|pwd|secret|token|api[_\-]?key|auth|credential|"
    r"private[_\-]?key|access[_\-]?key|aws[_\-]?|gcp[_\-]?|azure|"
    r"connection[_\-]?string|bearer|client[_\-]?secret)",
    re.IGNORECASE,
)


# ── process list ───────────────────────────────────────────────────────────────

def list_processes() -> list[dict]:
    """Return basic info for every running process, sorted by name."""
    procs = []
    for p in psutil.process_iter(["pid", "name", "username", "status"]):
        try:
            info = p.info
            try:
                cmd = " ".join(p.cmdline())[:80]
            except Exception:
                cmd = ""
            procs.append({
                "pid":      info["pid"],
                "name":     info["name"] or "",
                "username": info.get("username") or "",
                "status":   info.get("status") or "",
                "cmdline":  cmd,
            })
        except Exception:
            pass
    return sorted(procs, key=lambda x: x["name"].lower())


# ── deep process inspect ───────────────────────────────────────────────────────

def inspect_process(pid: int) -> dict:
    """Collect all available metadata for a PID using psutil."""
    result: dict = {
        "pid": pid, "name": "", "exe": "", "cmdline": [], "cwd": "",
        "username": "", "status": "", "env": {}, "open_files": [],
        "connections": [], "memory_maps": [], "children": [],
        "secrets_found": [],
    }
    try:
        p = psutil.Process(pid)
        result["name"]   = p.name()
        result["status"] = p.status()
        try:  result["exe"]     = p.exe()
        except Exception: pass
        try:  result["cmdline"] = p.cmdline()
        except Exception: pass
        try:  result["cwd"]     = p.cwd()
        except Exception: pass
        try:  result["username"] = p.username()
        except Exception: pass

        # Environment variables — may contain API keys, passwords
        try:
            env = p.environ()
            result["env"] = env
            for k, v in env.items():
                if _SECRET_RE.search(k) or _SECRET_RE.search(v):
                    result["secrets_found"].append({
                        "source": "env", "key": k, "value": v[:200],
                    })
        except psutil.AccessDenied:
            result["env"] = {"_note": "Access denied"}
        except Exception as exc:
            result["env"] = {"_note": str(exc)}

        # Cmdline secrets
        for arg in result.get("cmdline", []):
            if _SECRET_RE.search(arg):
                result["secrets_found"].append({
                    "source": "cmdline", "key": "arg", "value": arg[:200],
                })

        # Open file handles
        try:
            result["open_files"] = [f.path for f in p.open_files()]
        except Exception:
            pass

        # Network connections
        try:
            conns = []
            for c in p.net_connections():
                la = f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else ""
                ra = f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else ""
                conns.append({"local": la, "remote": ra, "status": c.status})
            result["connections"] = conns
        except Exception:
            pass

        # Mapped memory regions (file-backed)
        try:
            maps = []
            skip = {"[heap]", "[stack]", "[vdso]", "[vsyscall]", ""}
            for m in p.memory_maps():
                if m.path not in skip:
                    maps.append(m.path)
            result["memory_maps"] = sorted(set(maps))[:60]
        except Exception:
            pass

        # Child processes
        try:
            result["children"] = [
                {"pid": c.pid, "name": c.name()} for c in p.children()
            ]
        except Exception:
            pass

    except psutil.NoSuchProcess:
        result["_error"] = f"PID {pid} not found"
    except psutil.AccessDenied:
        result["_error"] = "Access denied"

    return result


# ── memory string scan (platform-specific) ────────────────────────────────────

def scan_memory_strings(
    pid: int,
    keyword: str = "",
    min_len: int = 6,
    max_strings: int = 1000,
    progress_cb: Callable | None = None,
) -> dict:
    """Read printable strings from process memory.

    Works on Linux (/proc/<pid>/mem) and Windows (ReadProcessMemory).
    macOS: returns only env/cmdline strings (requires entitlements for full scan).
    progress_cb(regions_done, strings_found_so_far)
    """
    sys = platform.system()
    if sys == "Linux":
        method, error, strings = _scan_linux(pid, keyword, min_len, max_strings, progress_cb)
    elif sys == "Windows":
        method, error, strings = _scan_windows(pid, keyword, min_len, max_strings, progress_cb)
    else:
        method = f"{sys}:psutil-only"
        error  = (f"Deep memory scan requires root/SIP-disabled on {sys}. "
                  "Showing env vars + cmdline strings instead.")
        strings = _strings_from_psutil(pid, keyword, min_len)

    return {
        "pid": pid, "platform": sys,
        "method": method, "strings": strings,
        "count": len(strings), "error": error,
    }


def _extract_strings(data: bytes, min_len: int, keyword: str) -> list[str]:
    """Pull printable ASCII strings ≥ min_len from raw bytes."""
    results: list[str] = []
    cur: list[str] = []
    kw = keyword.lower()
    for b in data:
        c = chr(b)
        if c.isprintable() and b < 128:
            cur.append(c)
        else:
            if len(cur) >= min_len:
                s = "".join(cur)
                if not kw or kw in s.lower():
                    results.append(s)
            cur = []
    if len(cur) >= min_len:
        s = "".join(cur)
        if not kw or kw in s.lower():
            results.append(s)
    return results


def _strings_from_psutil(pid: int, keyword: str, min_len: int) -> list[str]:
    results = []
    kw = keyword.lower()
    try:
        p = psutil.Process(pid)
        for s in p.cmdline():
            if len(s) >= min_len and (not kw or kw in s.lower()):
                results.append(f"[cmdline] {s}")
        env = p.environ()
        for k, v in env.items():
            combined = f"{k}={v}"
            if len(combined) >= min_len and (not kw or kw in combined.lower()):
                results.append(f"[env] {combined}")
    except Exception:
        pass
    return results


def _scan_linux(pid, keyword, min_len, max_strings, progress_cb):
    try:
        maps_path = Path(f"/proc/{pid}/maps")
        mem_path  = Path(f"/proc/{pid}/mem")
        if not maps_path.exists():
            return "linux:/proc/mem", f"PID {pid} not found", []

        strings: list[str] = []
        regions = 0
        MAX_REGION = 8 * 1024 * 1024  # skip regions > 8 MB

        with mem_path.open("rb") as mem:
            for line in maps_path.read_text().splitlines():
                if len(strings) >= max_strings:
                    break
                parts = line.split()
                if not parts:
                    continue
                perms = parts[1] if len(parts) > 1 else ""
                if "r" not in perms:
                    continue
                start_s, end_s = parts[0].split("-")
                start, end = int(start_s, 16), int(end_s, 16)
                if end - start > MAX_REGION:
                    continue
                try:
                    mem.seek(start)
                    data = mem.read(end - start)
                    strings.extend(_extract_strings(data, min_len, keyword))
                    regions += 1
                    if progress_cb:
                        progress_cb(regions, len(strings))
                except Exception:
                    continue

        return "linux:/proc/mem", None, strings[:max_strings]
    except PermissionError:
        return "linux:/proc/mem", "Permission denied — run as root", []
    except Exception as exc:
        return "linux:/proc/mem", str(exc), []


def _scan_windows(pid, keyword, min_len, max_strings, progress_cb):
    try:
        import ctypes
        import ctypes.wintypes as wt

        PROCESS_VM_READ         = 0x0010
        PROCESS_QUERY_INFORMATION = 0x0400
        MEM_COMMIT  = 0x1000
        READABLE    = {0x02, 0x04, 0x20, 0x40}  # PAGE_READONLY, RW, EXECUTE_READ, EXECUTE_RW

        k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
        if not handle:
            return "windows:ReadProcessMemory", "OpenProcess failed (access denied?)", []

        class MBI(ctypes.Structure):
            _fields_ = [
                ("BaseAddress",       ctypes.c_void_p),
                ("AllocationBase",    ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD),
                ("RegionSize",        ctypes.c_size_t),
                ("State",             wt.DWORD),
                ("Protect",           wt.DWORD),
                ("Type",              wt.DWORD),
            ]

        strings: list[str] = []
        addr    = 0
        regions = 0
        mbi     = MBI()

        while k32.VirtualQueryEx(handle, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            if (mbi.State == MEM_COMMIT
                    and (mbi.Protect & 0xFF) in READABLE
                    and mbi.RegionSize < 64 * 1024 * 1024):
                buf      = ctypes.create_string_buffer(mbi.RegionSize)
                read_out = ctypes.c_size_t(0)
                if k32.ReadProcessMemory(handle, ctypes.c_void_p(addr),
                                         buf, mbi.RegionSize, ctypes.byref(read_out)):
                    strings.extend(_extract_strings(buf.raw[:read_out.value], min_len, keyword))
                    regions += 1
                    if progress_cb:
                        progress_cb(regions, len(strings))
            addr = (addr or 0) + (mbi.RegionSize or 4096)
            if addr > 0x7FFFFFFF0000 or len(strings) >= max_strings:
                break

        k32.CloseHandle(handle)
        return "windows:ReadProcessMemory", None, strings[:max_strings]
    except Exception as exc:
        return "windows:ReadProcessMemory", str(exc), []

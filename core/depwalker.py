"""DLL/shared-library dependency walker — cross-platform."""
import os, platform, re, struct, subprocess
from pathlib import Path

_WIN_DIRS = [
    os.environ.get("SystemRoot", r"C:\Windows") + r"\System32",
    os.environ.get("SystemRoot", r"C:\Windows") + r"\SysWOW64",
    os.environ.get("SystemRoot", r"C:\Windows"),
]

def _run(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except Exception as e:
        return -1, "", str(e)

# ── PE import parsing ─────────────────────────────────────────

def _pe_imports(path: str) -> list[str]:
    """Parse PE import table to get list of required DLLs."""
    try:
        data = open(path, "rb").read()
    except Exception:
        return []
    if data[:2] != b"MZ":
        return []
    try:
        pe_off = struct.unpack_from("<I", data, 0x3C)[0]
        if data[pe_off:pe_off+4] != b"PE\x00\x00":
            return []
        machine = struct.unpack_from("<H", data, pe_off+4)[0]
        is64 = machine == 0x8664
        opt_off = pe_off + 24
        magic = struct.unpack_from("<H", data, opt_off)[0]
        if magic not in (0x10B, 0x20B):
            return []
        # Import directory RVA
        import_rva_off = opt_off + (112 if is64 else 96)
        import_rva = struct.unpack_from("<I", data, import_rva_off)[0]
        if not import_rva:
            return []
        # Find section containing import RVA
        num_sections = struct.unpack_from("<H", data, pe_off+6)[0]
        sections_off = opt_off + struct.unpack_from("<H", data, pe_off+20)[0]
        for i in range(num_sections):
            so = sections_off + i*40
            vaddr = struct.unpack_from("<I", data, so+12)[0]
            vsize = struct.unpack_from("<I", data, so+16)[0]
            raw   = struct.unpack_from("<I", data, so+20)[0]
            if vaddr <= import_rva < vaddr + vsize:
                off = raw + (import_rva - vaddr)
                dlls = []
                while True:
                    entry = data[off:off+20]
                    if len(entry) < 20 or entry == b"\x00"*20:
                        break
                    name_rva = struct.unpack_from("<I", entry, 12)[0]
                    if not name_rva:
                        break
                    name_off = raw + (name_rva - vaddr)
                    end = data.index(b"\x00", name_off)
                    dlls.append(data[name_off:end].decode("ascii", errors="replace"))
                    off += 20
                return dlls
    except Exception:
        pass
    return []

def _find_dll(name: str, extra_dirs: list[str]) -> str | None:
    for d in extra_dirs + _WIN_DIRS:
        fp = os.path.join(d, name)
        if os.path.isfile(fp):
            return fp
    return None

# ── ELF (Linux) ───────────────────────────────────────────────

def _elf_deps(path: str) -> list[str]:
    rc, out, _ = _run(["ldd", path])
    deps = []
    for line in out.splitlines():
        m = re.match(r"\s*(\S+)\s*=>\s*(\S+)?", line)
        if m:
            deps.append({"lib": m.group(1), "path": m.group(2) or "",
                         "found": bool(m.group(2)) and m.group(2) != "not found"})
    return deps  # type: ignore

# ── Mach-O (macOS) ────────────────────────────────────────────

def _macho_deps(path: str) -> list[str]:
    rc, out, _ = _run(["otool", "-L", path])
    return [l.strip().split()[0] for l in out.splitlines()[1:] if l.strip()]

# ── Public API ────────────────────────────────────────────────

def analyze(path: str) -> dict:
    sys = platform.system()
    result = {"path": path, "platform": sys, "deps": [], "missing": [], "error": ""}
    if sys == "Windows":
        dlls = _pe_imports(path)
        if not dlls:
            result["error"] = "Not a PE file or no imports found"
            return result
        extra = [str(Path(path).parent)]
        for dll in dlls:
            found = _find_dll(dll, extra)
            result["deps"].append({"lib": dll, "path": found or "", "found": bool(found)})
            if not found:
                result["missing"].append(dll)
    elif sys == "Darwin":
        deps = _macho_deps(path)
        for d in deps:
            found = os.path.isfile(d)
            result["deps"].append({"lib": os.path.basename(d), "path": d, "found": found})
            if not found:
                result["missing"].append(d)
    else:
        deps = _elf_deps(path)
        result["deps"] = deps  # type: ignore
        result["missing"] = [d["lib"] for d in deps if not d.get("found")]
    return result

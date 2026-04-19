"""MSI Installer Cache Cleaner — identify and remove orphaned installer files."""

import os
import subprocess
from pathlib import Path
from core.logger import CleanerLogger

MSI_DIR = Path(r"C:\Windows\Installer")


def _get_registered_packages() -> set[str]:
    """Return set of filenames referenced by installed MSI products."""
    if os.name != "nt":
        return set()
    script = (
        "Get-ChildItem 'HKLM:\\SOFTWARE\\Classes\\Installer\\Products' -ErrorAction SilentlyContinue | "
        "ForEach-Object { "
        "  Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue | "
        "  Select-Object -ExpandProperty SourceList -ErrorAction SilentlyContinue "
        "} | Out-String"
    )
    referenced: set[str] = set()
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=30,
        )
        for line in r.stdout.splitlines():
            line = line.strip()
            if line.lower().endswith(".msi") or line.lower().endswith(".msp"):
                referenced.add(line.lower())
    except Exception:
        pass

    # Also read from registry directly
    try:
        import winreg as wr
        base = r"SOFTWARE\Classes\Installer\Products"
        root = wr.OpenKey(wr.HKEY_LOCAL_MACHINE, base, 0, wr.KEY_READ)
        i = 0
        while True:
            try:
                prod = wr.EnumKey(root, i)
                i += 1
                try:
                    sl_key = wr.OpenKey(root, f"{prod}\\SourceList")
                    try:
                        pkg, _ = wr.QueryValueEx(sl_key, "PackageName")
                        referenced.add(str(pkg).lower())
                    except OSError:
                        pass
                    wr.CloseKey(sl_key)
                except OSError:
                    pass
            except OSError:
                break
        wr.CloseKey(root)
    except Exception:
        pass

    return referenced


def find_orphaned_msi(logger: CleanerLogger) -> list[dict]:
    """Find .msi/.msp files in Windows\\Installer not referenced by any product."""
    if not MSI_DIR.exists():
        return []
    referenced = _get_registered_packages()
    orphans = []
    try:
        for f in MSI_DIR.iterdir():
            if f.suffix.lower() not in (".msi", ".msp"):
                continue
            try:
                size = f.stat().st_size
                if f.name.lower() not in referenced:
                    orphans.append({
                        "path": str(f),
                        "name": f.name,
                        "size": size,
                        "ext":  f.suffix.upper(),
                    })
            except OSError:
                pass
    except Exception as e:
        logger.error(f"find_orphaned_msi scan error: {e}")
    orphans.sort(key=lambda x: x["size"], reverse=True)
    logger.log("find_orphaned_msi", "msicache",
               f"Found {len(orphans)} orphaned installer files")
    return orphans


def delete_msi_files(files: list[dict], logger: CleanerLogger) -> tuple[int, int]:
    """Delete orphaned MSI/MSP files. Returns (deleted_count, freed_bytes)."""
    deleted = freed = 0
    for f in files:
        try:
            p = Path(f["path"])
            size = f.get("size", 0)
            if p.exists():
                p.unlink()
                deleted += 1
                freed += size
                logger.log("del_msi", "msicache", f"Deleted: {f['name']} ({size//1024}KB)")
        except OSError as e:
            logger.error(f"del_msi error {f['name']}: {e}")
    return deleted, freed

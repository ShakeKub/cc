"""Font Manager — list and remove installed fonts."""

import os
import subprocess
from pathlib import Path
from core.logger import CleanerLogger

FONTS_DIR = Path(r"C:\Windows\Fonts")
_FONTS_REG = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"


def _winreg():
    import winreg as _wr
    return _wr


def get_installed_fonts(logger: CleanerLogger) -> list[dict]:
    """Return all installed fonts from registry + Fonts directory."""
    if os.name != "nt":
        return []
    wr = _winreg()
    fonts = []
    try:
        key = wr.OpenKey(wr.HKEY_LOCAL_MACHINE, _FONTS_REG, 0, wr.KEY_READ)
        i = 0
        while True:
            try:
                name, filename, _ = wr.EnumValue(key, i)
                i += 1
                path = FONTS_DIR / filename if not os.path.isabs(filename) else Path(filename)
                size = 0
                try:
                    size = path.stat().st_size
                except OSError:
                    pass
                fonts.append({
                    "name":     name,
                    "filename": filename,
                    "path":     str(path),
                    "size":     size,
                    "exists":   path.exists(),
                })
            except OSError:
                break
        wr.CloseKey(key)
    except OSError as e:
        logger.error(f"get_installed_fonts error: {e}")
    return sorted(fonts, key=lambda f: f["name"].upper())


def delete_font(font: dict, logger: CleanerLogger) -> bool:
    """Uninstall a font: remove registry entry and font file."""
    if os.name != "nt":
        return False
    wr = _winreg()
    removed_reg = removed_file = False
    try:
        key = wr.OpenKey(wr.HKEY_LOCAL_MACHINE, _FONTS_REG, 0, wr.KEY_SET_VALUE)
        wr.DeleteValue(key, font["name"])
        wr.CloseKey(key)
        removed_reg = True
    except OSError as e:
        logger.error(f"delete_font reg error: {e}")

    try:
        p = Path(font["path"])
        if p.exists():
            p.unlink()
            removed_file = True
    except OSError as e:
        logger.error(f"delete_font file error: {e}")

    success = removed_reg or removed_file
    logger.log("delete_font", "fontmgr",
               f"{'Removed' if success else 'Failed'} font: {font['name']}")
    return success

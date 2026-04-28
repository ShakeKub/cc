"""Scan filter — configurable ignore rules for large-file / duplicate / disk scans."""

import json
from pathlib import Path
from typing import Any

DEFAULT_FILTER_FILE = "scan_filters.json"

# ── Predefined profiles ───────────────────────────────────────

PRESET_FOLDERS: dict[str, list[str]] = {
    "steam":         ["steamapps", "SteamApps", "Steam/userdata", "steam/steamapps"],
    "epic":          ["Epic Games", "EpicGames"],
    "gog":           ["GOG Games", "GOGLibrary", "GOG.com"],
    "ea":            ["EA Games", "EA Desktop", "Electronic Arts", "Origin Games"],
    "ubisoft":       ["Ubisoft Game Launcher", "Ubisoft Connect", "Ubisoft"],
    "xbox":          ["XboxGames", "WindowsApps"],
    "node_modules":  ["node_modules"],
    "git":           [".git"],
    "venv":          ["venv", ".venv", "env", ".env", "virtualenv"],
    "build":         ["build", "dist", "target", ".next", "__pycache__", ".cache",
                      "out", "output", ".gradle", ".m2", "Pods"],
    "system_win":    ["Windows", "System32", "SysWOW64", "WinSxS", "WinSXS",
                      "Program Files", "Program Files (x86)"],
    "system_mac":    ["/System/Library", "/Library/Apple", "Contents/MacOS",
                      "/private/var", "/private/tmp"],
    "system_linux":  ["/proc", "/sys", "/dev", "/run", "/snap"],
}

PRESET_EXTENSIONS: dict[str, list[str]] = {
    "video":    [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".m4v", ".ts",
                 ".m2ts", ".flv", ".webm", ".vob", ".mpg", ".mpeg", ".3gp", ".hevc"],
    "audio":    [".flac", ".wav", ".aiff", ".aif", ".ape", ".wv", ".alac"],
    "raw_img":  [".raw", ".cr2", ".cr3", ".nef", ".arw", ".dng",
                 ".orf", ".rw2", ".pef", ".srw"],
    "iso":      [".iso", ".img", ".dmg", ".vhd", ".vhdx", ".vmdk",
                 ".ova", ".ovf", ".qcow2"],
    "archive":  [".zip", ".7z", ".rar", ".tar", ".gz", ".bz2",
                 ".xz", ".zst", ".lz4", ".cab"],
    "log":      [".log", ".jsonl", ".out", ".trace"],
}

PRESET_LABELS: dict[str, str] = {
    "steam":        "Steam hry",
    "epic":         "Epic Games hry",
    "gog":          "GOG hry",
    "ea":           "EA / Origin hry",
    "ubisoft":      "Ubisoft Connect",
    "xbox":         "Xbox Game Pass",
    "node_modules": "node_modules",
    "git":          ".git adresáře",
    "venv":         "Python virtualenv",
    "build":        "Build artefakty (dist, target, .next…)",
    "system_win":   "Windows systémové složky",
    "system_mac":   "macOS systémové složky",
    "system_linux": "Linux systémové složky (/proc, /sys…)",
    "video":        "Video soubory (mp4, mkv, avi…)",
    "audio":        "Nekomprimované audio (flac, wav…)",
    "raw_img":      "RAW fotky (cr2, nef, arw…)",
    "iso":          "ISO / disk image (iso, dmg, vmdk…)",
    "archive":      "Archivy (zip, 7z, rar…)",
    "log":          "Log soubory (.log, .jsonl…)",
}

FOLDER_PRESETS  = list(PRESET_FOLDERS.keys())
EXT_PRESETS     = list(PRESET_EXTENSIONS.keys())

_DEFAULT: dict[str, Any] = {
    "version": 1,
    "enabled_folder_presets": [],
    "enabled_ext_presets":    [],
    "custom_folders":         [],
    "custom_extensions":      [],
    "custom_paths":           [],
    "min_size_mb":            0,
    "max_size_mb":            0,
}


class ScanFilter:
    def __init__(self, config_path: str = DEFAULT_FILTER_FILE):
        self._path = Path(config_path)
        self._cfg: dict[str, Any] = {k: v for k, v in _DEFAULT.items()}
        self._folder_frags: set[str] = set()
        self._exts: set[str] = set()
        self._custom_paths: list[str] = []
        self._min_bytes = 0
        self._max_bytes = 0

    # ── Persistence ──────────────────────────────────────────

    def load(self) -> "ScanFilter":
        if self._path.is_file():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self._cfg.update(data)
            except Exception:
                pass
        self._rebuild()
        return self

    def save(self) -> None:
        self._path.write_text(json.dumps(self._cfg, indent=2, ensure_ascii=False),
                              encoding="utf-8")

    def _rebuild(self) -> None:
        frags: set[str] = set()
        for preset in self._cfg.get("enabled_folder_presets", []):
            for frag in PRESET_FOLDERS.get(preset, []):
                frags.add(frag.lower())
        for frag in self._cfg.get("custom_folders", []):
            frags.add(frag.lower())
        self._folder_frags = frags

        exts: set[str] = set()
        for preset in self._cfg.get("enabled_ext_presets", []):
            for ext in PRESET_EXTENSIONS.get(preset, []):
                exts.add(ext.lower())
        for ext in self._cfg.get("custom_extensions", []):
            e = ext.lower() if ext.startswith(".") else f".{ext.lower()}"
            exts.add(e)
        self._exts = exts

        self._custom_paths = [p.lower() for p in self._cfg.get("custom_paths", [])]
        self._min_bytes = int(self._cfg.get("min_size_mb", 0)) * 1024 * 1024
        self._max_bytes = int(self._cfg.get("max_size_mb", 0)) * 1024 * 1024

    # ── Runtime checks ───────────────────────────────────────

    def should_skip_dir(self, dirpath: str) -> bool:
        dl = dirpath.replace("\\", "/").lower()
        for cp in self._custom_paths:
            if dl.startswith(cp):
                return True
        parts = Path(dl).parts
        for frag in self._folder_frags:
            fl = frag.replace("\\", "/")
            if "/" in fl:
                if fl in dl:
                    return True
            else:
                if any(fl == part or fl in part for part in parts):
                    return True
        return False

    def should_skip_file(self, filepath: str, size: int = -1) -> bool:
        ext = Path(filepath).suffix.lower()
        if ext in self._exts:
            return True
        if size >= 0:
            if self._min_bytes and size < self._min_bytes:
                return True
            if self._max_bytes and size > self._max_bytes:
                return True
        return False

    def is_active(self) -> bool:
        return bool(
            self._cfg.get("enabled_folder_presets") or
            self._cfg.get("enabled_ext_presets") or
            self._cfg.get("custom_folders") or
            self._cfg.get("custom_extensions") or
            self._cfg.get("custom_paths") or
            self._cfg.get("min_size_mb") or
            self._cfg.get("max_size_mb")
        )

    # ── Mutation helpers ──────────────────────────────────────

    def toggle_folder_preset(self, key: str) -> bool:
        lst = self._cfg.setdefault("enabled_folder_presets", [])
        if key in lst:
            lst.remove(key); self._rebuild(); return False
        lst.append(key); self._rebuild(); return True

    def toggle_ext_preset(self, key: str) -> bool:
        lst = self._cfg.setdefault("enabled_ext_presets", [])
        if key in lst:
            lst.remove(key); self._rebuild(); return False
        lst.append(key); self._rebuild(); return True

    def add_custom_folder(self, name: str) -> None:
        lst = self._cfg.setdefault("custom_folders", [])
        if name and name not in lst:
            lst.append(name)
        self._rebuild()

    def remove_custom_folder(self, name: str) -> None:
        lst = self._cfg.setdefault("custom_folders", [])
        if name in lst:
            lst.remove(name)
        self._rebuild()

    def add_custom_ext(self, ext: str) -> None:
        if not ext.startswith("."):
            ext = "." + ext
        ext = ext.lower()
        lst = self._cfg.setdefault("custom_extensions", [])
        if ext not in lst:
            lst.append(ext)
        self._rebuild()

    def remove_custom_ext(self, ext: str) -> None:
        if not ext.startswith("."):
            ext = "." + ext
        ext = ext.lower()
        lst = self._cfg.setdefault("custom_extensions", [])
        lst[:] = [e for e in lst if e.lower() != ext]
        self._rebuild()

    def add_custom_path(self, path: str) -> None:
        lst = self._cfg.setdefault("custom_paths", [])
        if path and path not in lst:
            lst.append(path)
        self._rebuild()

    def remove_custom_path(self, path: str) -> None:
        lst = self._cfg.setdefault("custom_paths", [])
        if path in lst:
            lst.remove(path)
        self._rebuild()

    def set_size_limits(self, min_mb: int = 0, max_mb: int = 0) -> None:
        self._cfg["min_size_mb"] = max(0, min_mb)
        self._cfg["max_size_mb"] = max(0, max_mb)
        self._rebuild()

    def reset(self) -> None:
        self._cfg = {k: v for k, v in _DEFAULT.items()}
        self._rebuild()

    # ── Read-only properties ──────────────────────────────────

    @property
    def cfg(self) -> dict:
        return self._cfg

    @property
    def active_folder_presets(self) -> list[str]:
        return self._cfg.get("enabled_folder_presets", [])

    @property
    def active_ext_presets(self) -> list[str]:
        return self._cfg.get("enabled_ext_presets", [])

    @property
    def custom_folders(self) -> list[str]:
        return self._cfg.get("custom_folders", [])

    @property
    def custom_extensions(self) -> list[str]:
        return self._cfg.get("custom_extensions", [])

    @property
    def custom_paths(self) -> list[str]:
        return self._cfg.get("custom_paths", [])

    @property
    def min_size_mb(self) -> int:
        return int(self._cfg.get("min_size_mb", 0))

    @property
    def max_size_mb(self) -> int:
        return int(self._cfg.get("max_size_mb", 0))

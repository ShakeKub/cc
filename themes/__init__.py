"""Theme system for System Cleaner & Optimization Tool."""

THEMES = {
    "cyberpunk": {
        "primary": "#00ff41",
        "secondary": "#0abdc6",
        "accent": "#ff00ff",
        "warning": "#ffaa00",
        "error": "#ff0040",
        "success": "#00ff41",
        "background": "#0d0d0d",
        "surface": "#1a1a2e",
        "panel": "#16213e",
        "text": "#e0e0e0",
        "text_muted": "#666666",
        "border": "#0abdc6",
    },
    "matrix": {
        "primary": "#00ff00",
        "secondary": "#00cc00",
        "accent": "#00ff66",
        "warning": "#ccff00",
        "error": "#ff0000",
        "success": "#00ff00",
        "background": "#000000",
        "surface": "#0a0a0a",
        "panel": "#0d1a0d",
        "text": "#00ff00",
        "text_muted": "#005500",
        "border": "#00ff00",
    },
    "midnight": {
        "primary": "#7aa2f7",
        "secondary": "#bb9af7",
        "accent": "#ff9e64",
        "warning": "#e0af68",
        "error": "#f7768e",
        "success": "#9ece6a",
        "background": "#1a1b26",
        "surface": "#24283b",
        "panel": "#292e42",
        "text": "#c0caf5",
        "text_muted": "#565f89",
        "border": "#3b4261",
    },
    "blood": {
        "primary": "#ff0040",
        "secondary": "#ff4444",
        "accent": "#ff6600",
        "warning": "#ff8800",
        "error": "#ff0000",
        "success": "#00ff88",
        "background": "#0a0000",
        "surface": "#1a0000",
        "panel": "#200000",
        "text": "#ffcccc",
        "text_muted": "#664444",
        "border": "#ff0040",
    },
    "arctic": {
        "primary": "#88c0d0",
        "secondary": "#81a1c1",
        "accent": "#5e81ac",
        "warning": "#ebcb8b",
        "error": "#bf616a",
        "success": "#a3be8c",
        "background": "#2e3440",
        "surface": "#3b4252",
        "panel": "#434c5e",
        "text": "#eceff4",
        "text_muted": "#4c566a",
        "border": "#88c0d0",
    },
}


def get_theme(name: str) -> dict[str, str]:
    """Get a theme by name, defaulting to cyberpunk."""
    return THEMES.get(name, THEMES["cyberpunk"])


def list_themes() -> list[str]:
    """Return available theme names."""
    return list(THEMES.keys())

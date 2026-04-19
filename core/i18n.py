"""Internationalization — simple, zero-dependency translation layer.

Usage
-----
    from core.i18n import t, set_language, get_language, available_languages

    set_language("cs")          # switch to Czech
    print(t("menu.exit"))       # → "Konec"
    print(t("scan.found", count=42, size="1.2 MB"))  # format placeholders
"""

import json
from pathlib import Path
from typing import Any

_LOCALES_DIR = Path(__file__).parent.parent / "locales"
_CURRENT_LANG: str = "en"
_CACHE: dict[str, dict[str, str]] = {}


def _load(lang: str) -> dict[str, str]:
    if lang not in _CACHE:
        path = _LOCALES_DIR / f"{lang}.json"
        if path.exists():
            with open(path, encoding="utf-8") as fh:
                _CACHE[lang] = json.load(fh)
        else:
            _CACHE[lang] = {}
    return _CACHE[lang]


def set_language(lang: str) -> bool:
    """Switch the active language. Returns True if the locale file exists."""
    global _CURRENT_LANG
    _load(lang)             # pre-load so we know if it exists
    if lang in _CACHE:
        _CURRENT_LANG = lang
        return True
    return False


def get_language() -> str:
    return _CURRENT_LANG


def t(key: str, **kwargs: Any) -> str:
    """
    Translate *key* in the active language, falling back to English.
    Any keyword arguments are interpolated with str.format().
    If the key is missing in both languages, the key itself is returned.
    """
    text: str | None = _load(_CURRENT_LANG).get(key)
    if text is None and _CURRENT_LANG != "en":
        text = _load("en").get(key)
    if text is None:
        return key
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError):
            pass
    return text


def available_languages() -> list[dict[str, str]]:
    """Return metadata for every locale file found in the locales/ directory."""
    langs: list[dict[str, str]] = []
    if not _LOCALES_DIR.exists():
        return langs
    for path in sorted(_LOCALES_DIR.glob("*.json")):
        data = _load(path.stem)
        langs.append({
            "code":        path.stem,
            "name":        data.get("_lang_name", path.stem),
            "native_name": data.get("_lang_native", path.stem),
        })
    return langs

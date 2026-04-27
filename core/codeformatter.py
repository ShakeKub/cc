"""JSON / YAML / XML formatter and validator."""

import json
import xml.dom.minidom as _minidom


def fmt_json(text: str, indent: int = 2) -> tuple[str, list[str]]:
    """Pretty-print JSON. Returns (formatted, errors)."""
    try:
        obj = json.loads(text)
        return json.dumps(obj, indent=indent, ensure_ascii=False), []
    except json.JSONDecodeError as e:
        return text, [f"JSON error: {e}"]


def fmt_xml(text: str) -> tuple[str, list[str]]:
    """Pretty-print XML. Returns (formatted, errors)."""
    try:
        dom = _minidom.parseString(text.encode("utf-8"))
        pretty = dom.toprettyxml(indent="  ")
        # Remove the extra blank lines minidom adds
        lines = [l for l in pretty.splitlines() if l.strip()]
        return "\n".join(lines), []
    except Exception as e:
        return text, [f"XML error: {e}"]


def fmt_yaml(text: str) -> tuple[str, list[str]]:
    """Pretty-print YAML. Returns (formatted, errors)."""
    try:
        import yaml  # type: ignore
        obj = yaml.safe_load(text)
        return yaml.dump(obj, allow_unicode=True, sort_keys=False,
                         default_flow_style=False), []
    except ImportError:
        return text, ["PyYAML not installed — run: pip install pyyaml"]
    except Exception as e:
        return text, [f"YAML error: {e}"]


def detect_format(text: str) -> str:
    """Heuristic: return 'json', 'xml', or 'yaml'."""
    s = text.lstrip()
    if s.startswith(("{", "[")):
        return "json"
    if s.startswith("<"):
        return "xml"
    return "yaml"


def fmt_auto(text: str) -> tuple[str, str, list[str]]:
    """Auto-detect format and pretty-print. Returns (formatted, detected_format, errors)."""
    fmt = detect_format(text)
    if fmt == "json":
        out, errs = fmt_json(text)
    elif fmt == "xml":
        out, errs = fmt_xml(text)
    else:
        out, errs = fmt_yaml(text)
    return out, fmt, errs

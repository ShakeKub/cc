"""Plugin system for ByteSweep & Optimization Tool.

Plugins are Python modules placed in the plugins/ directory.
Each plugin must define:
    - PLUGIN_NAME: str
    - PLUGIN_VERSION: str
    - PLUGIN_DESCRIPTION: str
    - register(app) -> None: Called when plugin is loaded
"""

import importlib
import os
import sys
from pathlib import Path
from typing import Any


class PluginManager:
    """Discovers, loads, and manages plugins."""

    def __init__(self, plugins_dir: str = "plugins"):
        self.plugins_dir = Path(plugins_dir)
        self.loaded_plugins: dict[str, Any] = {}

    def discover(self) -> list[dict[str, str]]:
        """Find all available plugins."""
        plugins = []
        if not self.plugins_dir.exists():
            return plugins
        for item in self.plugins_dir.iterdir():
            if item.suffix == ".py" and item.name != "__init__.py":
                plugins.append({
                    "name": item.stem,
                    "path": str(item),
                })
        return plugins

    def load(self, plugin_name: str) -> bool:
        """Load a plugin by name."""
        plugin_path = self.plugins_dir / f"{plugin_name}.py"
        if not plugin_path.exists():
            return False
        try:
            spec = importlib.util.spec_from_file_location(plugin_name, plugin_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.loaded_plugins[plugin_name] = module
            return True
        except Exception:
            return False

    def register_all(self, app: Any) -> int:
        """Load and register all discovered plugins. Returns count loaded."""
        count = 0
        for plugin_info in self.discover():
            name = plugin_info["name"]
            if self.load(name):
                module = self.loaded_plugins[name]
                if hasattr(module, "register"):
                    module.register(app)
                    count += 1
        return count

    def get_plugin_info(self, name: str) -> dict[str, str] | None:
        """Get metadata about a loaded plugin."""
        module = self.loaded_plugins.get(name)
        if not module:
            return None
        return {
            "name": getattr(module, "PLUGIN_NAME", name),
            "version": getattr(module, "PLUGIN_VERSION", "0.0.0"),
            "description": getattr(module, "PLUGIN_DESCRIPTION", "No description"),
        }

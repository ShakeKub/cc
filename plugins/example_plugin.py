"""Example plugin demonstrating the plugin system.

To create a custom plugin:
1. Create a .py file in the plugins/ directory
2. Define PLUGIN_NAME, PLUGIN_VERSION, PLUGIN_DESCRIPTION
3. Implement a register(app) function
4. The register function receives the app instance for integration
"""

PLUGIN_NAME = "Example Plugin"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "Demonstrates the plugin system with a custom cleaning action"


def register(app):
    """Register this plugin with the application.

    Args:
        app: The SystemCleanerApp instance
    """
    # Plugins can add custom commands, cleaning actions, or UI elements
    # Example: Register a custom cleaning action
    print(f"[Plugin] {PLUGIN_NAME} v{PLUGIN_VERSION} loaded")


def custom_clean(logger):
    """Example custom cleaning action.

    Plugins can define their own cleaning functions that integrate
    with the main cleaning pipeline.
    """
    # This could clean application-specific caches, logs, etc.
    logger.info(f"[{PLUGIN_NAME}] Custom clean action executed")
    return {"freed": 0, "items_cleaned": 0}

# promptbuilder/__init__.py
import os
from loguru import logger

# Fixes Observation a: Update version for RC-1
__version__ = "0.2.0-rc1"

# Centralized plugin loading
def _initialize_plugins():
    """Loads plugins unless explicitly skipped."""
    # Allow skipping plugin loading for tests or specific environments
    if os.environ.get("PROMPTBUILDER_SKIP_PLUGINS", "0") == "1":
        logger.info("Skipping plugin loading due to PROMPTBUILDER_SKIP_PLUGINS=1.")
        return

    try:
        from .core.plugins import load_plugins
        load_plugins() # Discover and register plugins from entry points
    except ImportError as e:
         # This might happen if core modules are not yet available during partial imports
         logger.warning(f"Could not load plugins during initial import: {e}")
    except Exception as e:
        logger.exception("An unexpected error occurred during plugin loading.")

_initialize_plugins()
# promptbuilder/core/plugins.py
from abc import ABC, abstractmethod
from typing import Dict, List, Type
import importlib.metadata
from loguru import logger

from .models import ContextResult # Or maybe just return string/FileNode list?

class ContextProvider(ABC):
    """Abstract base class for context providers."""
    name: str = "Unnamed Provider" # Unique identifier name

    @abstractmethod
    def get_context(self, options: Dict | None = None) -> ContextResult:
        """
        Generates context based on the provider's logic.
        'options' dict can contain provider-specific settings.
        Should return a ContextResult similar to ContextAssembler.
        """
        pass

    @classmethod
    def get_options_schema(cls) -> Dict | None:
        """Optional: Returns a schema (e.g., Pydantic model) for configuration options."""
        return None

# --- Plugin Registry ---
_plugin_registry: Dict[str, Type[ContextProvider]] = {}

def register_plugin(cls: Type[ContextProvider]):
    """Decorator or function to register a plugin class."""
    if not issubclass(cls, ContextProvider):
        raise TypeError("Plugin must inherit from ContextProvider")
    if not cls.name or cls.name == "Unnamed Provider":
         raise ValueError(f"Plugin {cls.__name__} must define a unique 'name' attribute.")

    if cls.name in _plugin_registry:
        logger.warning(f"Plugin name conflict: '{cls.name}' already registered. Overwriting.")
    _plugin_registry[cls.name] = cls
    logger.info(f"Registered context provider plugin: '{cls.name}'")

def load_plugins(entry_point_group="promptbuilder.context_providers"):
    """Discovers and loads plugins using importlib.metadata entry points."""
    global _plugin_registry
    logger.info(f"Discovering plugins using entry point group: '{entry_point_group}'")

    try:
        entry_points = importlib.metadata.entry_points(group=entry_point_group)
    except Exception as e:
         logger.error(f"Error accessing entry points for group '{entry_point_group}': {e}")
         entry_points = [] # Continue without entry points if error occurs


    loaded_count = 0
    for ep in entry_points:
        try:
            plugin_class = ep.load()
            if issubclass(plugin_class, ContextProvider):
                 # Use the class's name attribute as the key
                 plugin_name = getattr(plugin_class, 'name', None)
                 if plugin_name and plugin_name != "Unnamed Provider":
                     if plugin_name in _plugin_registry:
                         logger.warning(f"Plugin name conflict via entry point: '{plugin_name}' already registered. Skipping {ep.name}.")
                     else:
                         _plugin_registry[plugin_name] = plugin_class
                         logger.info(f"Loaded plugin '{plugin_name}' from entry point '{ep.name}'")
                         loaded_count += 1
                 else:
                      logger.error(f"Plugin class {plugin_class.__name__} from entry point {ep.name} lacks a valid 'name' attribute.")

            else:
                logger.warning(f"Entry point {ep.name} did not load a ContextProvider subclass.")
        except Exception as e:
            logger.exception(f"Failed to load plugin from entry point {ep.name}: {e}")

    logger.info(f"Loaded {loaded_count} plugins via entry points. Total registered: {len(_plugin_registry)}")
    # TODO: Implement loading from user plugin directory ($XDG_DATA_HOME/promptbuilder/plugins)
    # This would involve iterating .py files, importing them, and checking for classes
    # inheriting from ContextProvider, then registering them. Be careful about security.

def get_available_providers() -> List[Type[ContextProvider]]:
    """Returns a list of all registered context provider classes."""
    return list(_plugin_registry.values())

def get_provider_by_name(name: str) -> Type[ContextProvider] | None:
    """Gets a specific provider class by its registered name."""
    return _plugin_registry.get(name)

# --- Load built-in plugins explicitly ---
# Example: If git_diff is a built-in plugin
# from ..plugins.git_diff import GitDiffProvider # Assuming it exists
# register_plugin(GitDiffProvider)

# --- Discover external plugins on startup ---
# Call load_plugins() early in the application lifecycle, e.g., in main.py or application.py
# load_plugins() # Call this elsewhere

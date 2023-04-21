# promptbuilder/config/paths.py
import sys
import os
from pathlib import Path
# import platform # No longer needed for Windows-only

def _get_app_name() -> str:
    # Centralize the app name
    return "PromptBuilder"

def is_frozen() -> bool:
    """Check if running in a PyInstaller bundle."""
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')

def get_bundle_dir() -> Path:
    """Get the base directory of the PyInstaller bundle or script dir."""
    if is_frozen():
        # The directory containing the executable in the bundle
        return Path(sys._MEIPASS) # type: ignore[attr-defined]
    # Running from source: return project root (assuming standard structure)
    return Path(__file__).parent.parent.parent

def get_user_data_dir() -> Path:
    """Get the Windows user application data directory."""
    app_name = _get_app_name()
    # Use %APPDATA% environment variable on Windows
    appdata_path = os.environ.get("APPDATA")
    if not appdata_path:
        # Fallback if APPDATA is not set (highly unlikely)
        path = Path.home() / "AppData/Roaming" / app_name
    else:
        path = Path(appdata_path) / app_name

    path.mkdir(parents=True, exist_ok=True)
    return path

def get_user_config_file() -> Path:
    """Get the path to the user's config.json file."""
    return get_user_data_dir() / "config.json"

def get_user_log_dir() -> Path:
    """Get the path to the user's log directory."""
    path = get_user_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_user_plugins_dir() -> Path:
    """Get the path to the user's plugins directory."""
    path = get_user_data_dir() / "plugins"
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_bundled_config_path() -> Path | None:
    """Get the path to a config file potentially bundled with the app."""
    if is_frozen():
        # Look for config.json alongside the executable or in _MEIPASS
        bundle_path = get_bundle_dir()
        config_path = bundle_path / "config.json" # Check _MEIPASS first
        if config_path.exists():
            return config_path
        # Check next to exe as well (less common for single-file bundles)
        exe_dir = Path(sys.executable).parent
        config_path_exe = exe_dir / "config.json"
        if config_path_exe.exists():
             return config_path_exe
    # If not frozen or not found in bundle, return None
    return None
# promptbuilder/config/loader.py
import json
import os
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

from pydantic import ValidationError
from loguru import logger

from .schema import AppConfig, SnippetCategory # Import SnippetCategory
from .paths import get_user_config_file, get_bundled_config_path

_cached_config: Optional[AppConfig] = None

def _merge_snippets(loaded_snippets_data: Dict[str, Any], default_snippets: Dict[str, SnippetCategory]) -> Tuple[Dict[str, Any], bool]:
    """
    Merges default snippets into loaded data, ensuring default snippet text is up-to-date.

    - Prioritizes loaded structure but adds missing default categories/items.
    - Updates the text of existing default snippets if it differs from the current code default.
    - Does NOT overwrite items named "Custom".

    Returns:
        A tuple containing:
        - The merged snippets dictionary.
        - A boolean indicating if any changes were made.
    """
    was_updated = False
    # Ensure loaded_snippets_data is a dict (it might be None or invalid)
    if not isinstance(loaded_snippets_data, dict):
        logger.warning("Loaded snippets data is not a dictionary, using defaults.")
        # Return default dict structure and mark as updated
        return {k: v.model_dump() for k, v in default_snippets.items()}, True

    # Start with a copy of the loaded data
    merged_snippets = loaded_snippets_data.copy()

    # Iterate through default categories and items
    for cat_key, default_cat_model in default_snippets.items():
        default_cat_data = default_cat_model.model_dump() # Get dict from default model
        default_items = default_cat_data.get("items", {})

        # If category doesn't exist in loaded data, add it entirely
        if cat_key not in merged_snippets or not isinstance(merged_snippets.get(cat_key), dict):
            logger.info(f"Adding missing snippet category '{cat_key}' from defaults.")
            merged_snippets[cat_key] = default_cat_data
            was_updated = True
            continue # Go to next category

        # Category exists, check its items
        loaded_cat_data = merged_snippets[cat_key]
        loaded_items = loaded_cat_data.get("items", {})
        if not isinstance(loaded_items, dict): # Ensure items is a dict
             logger.warning(f"Items in loaded category '{cat_key}' is not a dictionary. Replacing with defaults.")
             loaded_items = {} # Reset to empty dict
             loaded_cat_data["items"] = loaded_items # Fix structure
             was_updated = True # Mark as updated because structure was fixed

        # Iterate through default items within the category
        for item_key, default_item_text in default_items.items():
            # Skip the "Custom" placeholder, don't overwrite it
            if item_key == "Custom":
                # Ensure "Custom" exists if defined in defaults
                if item_key not in loaded_items:
                     logger.info(f"Adding missing 'Custom' item to category '{cat_key}'.")
                     loaded_items[item_key] = "" # Add empty custom string
                     was_updated = True
                continue

            # Check if default item exists in loaded items
            if item_key not in loaded_items:
                # Add missing default item
                logger.info(f"Adding missing default snippet '{cat_key}/{item_key}'.")
                loaded_items[item_key] = default_item_text
                was_updated = True
            else:
                # Item exists, check if text content differs from default
                loaded_item_text = loaded_items[item_key]
                if loaded_item_text != default_item_text:
                    logger.info(f"Updating outdated snippet text for '{cat_key}/{item_key}'.")
                    loaded_items[item_key] = default_item_text
                    was_updated = True

    if was_updated:
        logger.info("Prompt snippets updated based on current defaults.")

    return merged_snippets, was_updated


def load_config() -> AppConfig:
    """
    Loads the application configuration, handling potential corruption
    and merging snippet defaults if necessary.
    """
    global _cached_config
    if _cached_config:
        return _cached_config

    config_path = get_user_config_file()
    loaded_data: Dict[str, Any] = {} # Ensure loaded_data is always a dict
    config_source = "defaults" # Track where the base config came from

    if config_path.exists():
        logger.info(f"Loading user configuration from: {config_path}")
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
                # Ensure loaded_data is a dict after loading
                if not isinstance(loaded_data, dict):
                     logger.error(f"User config file {config_path} does not contain a valid JSON object. Corrupted.")
                     raise json.JSONDecodeError("Config root is not an object", "", 0)
                config_source = "user file"

        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Failed to load or parse user config file {config_path}: {e}")
            # Backup corrupted file
            try:
                 backup_path = config_path.with_suffix(".json.corrupted")
                 # Use replace for atomicity if possible, otherwise copy/delete
                 if backup_path.exists():
                     backup_path.unlink(missing_ok=True) # Remove old backup first
                 config_path.rename(backup_path) # Atomic rename
                 logger.info(f"Backed up corrupted config to: {backup_path}")
            except OSError as backup_err:
                 logger.error(f"Failed to backup corrupted config: {backup_err}")
            loaded_data = {} # Reset to empty dict to fallback to defaults
            config_source = "defaults (user file corrupt)"
    else:
        logger.info("User config file not found, trying bundled config.")
        bundled_path = get_bundled_config_path()
        if bundled_path and bundled_path.exists():
             logger.info(f"Loading bundled configuration from: {bundled_path}")
             try:
                 with open(bundled_path, 'r', encoding='utf-8') as f:
                     loaded_data = json.load(f)
                     if not isinstance(loaded_data, dict):
                          logger.error(f"Bundled config file {bundled_path} does not contain a valid JSON object.")
                          loaded_data = {} # Fallback
                          config_source = "defaults (bundled file corrupt)"
                     else:
                          config_source = "bundled file"
             except (json.JSONDecodeError, OSError) as e:
                 logger.error(f"Failed to load or parse bundled config file {bundled_path}: {e}")
                 loaded_data = {} # Fallback
                 config_source = "defaults (bundled file error)"
        else:
            logger.info("No user or bundled config found. Using default settings.")
            loaded_data = {} # Ensure it's an empty dict for defaults
            config_source = "defaults (no file found)"


    # --- Merge Snippets ---
    # Get default config instance to access default snippets
    default_config = AppConfig()
    loaded_snippets_data = loaded_data.get("prompt_snippets", {}) # Get potentially loaded snippets
    # Merge defaults into loaded snippets, checking for outdated text
    merged_snippets, snippets_were_updated = _merge_snippets(loaded_snippets_data, default_config.prompt_snippets)
    # Update loaded_data with the potentially merged snippets
    loaded_data["prompt_snippets"] = merged_snippets
    # --- End Merge Snippets ---

    try:
        # Validate the potentially modified loaded_data against the schema
        config = AppConfig(**loaded_data)
        _cached_config = config
        logger.info(f"Configuration loaded successfully from: {config_source}")

        # --- Save back migrated/updated config to user file ---
        # Save if snippets were updated OR if the config was loaded from defaults/bundle
        # This ensures the user file always reflects the running config state.
        should_save_back = snippets_were_updated or config_source != "user file"
        if should_save_back and config_path.parent.exists(): # Only save if parent dir exists
             logger.info("Saving updated/default configuration back to user file.")
             save_config(config) # Save the validated and potentially merged config
        elif not config_path.parent.exists():
             logger.warning(f"Cannot save config back, parent directory does not exist: {config_path.parent}")


        return config
    except ValidationError as e:
        logger.error(f"Configuration validation failed: {e}")
        logger.warning("Falling back to default configuration.")
        # Use default config on validation error
        default_config_on_error = AppConfig()
        _cached_config = default_config_on_error
        # Optionally try saving the default config if validation failed
        # logger.info("Saving default configuration after validation error.")
        # save_config(default_config_on_error)
        return default_config_on_error

    # TODO: Implement environment variable overrides (PROMPTBUILDER_*)

def save_config(config: AppConfig) -> None:
    """Saves the application configuration using atomic write via NamedTemporaryFile."""
    config_path = get_user_config_file()
    logger.info(f"Saving configuration to: {config_path}")
    temp_file_path: Optional[Path] = None
    try:
        # Ensure parent directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Create temp file in the *same directory* as the target for atomic os.replace
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            dir=config_path.parent,
            prefix=f".{config_path.name}_tmp", # Use a prefix related to the target file
            suffix=".json",
            delete=False # Keep the file after closing for os.replace
        ) as temp_f:
            temp_file_path = Path(temp_f.name)
            logger.debug(f"Writing config to temporary file: {temp_file_path}")
            # Use Pydantic's json export for proper serialization
            temp_f.write(config.model_dump_json(indent=4))
            # Ensure data is flushed to disk before replacing
            temp_f.flush()
            os.fsync(temp_f.fileno()) # Force write to disk

        # Atomically replace the original file with the temporary file
        os.replace(temp_file_path, config_path)
        logger.info("Configuration saved successfully.")
        temp_file_path = None # Prevent cleanup in finally block if replace succeeded

    except (OSError, IOError, TypeError, AttributeError) as e:
        logger.error(f"Failed to save configuration to {config_path}: {e}")
        # Attempt to clean up the temporary file if replace failed or error occurred before replace
        if temp_file_path and temp_file_path.exists():
            logger.warning(f"Attempting to clean up temporary config file: {temp_file_path}")
            try:
                temp_file_path.unlink()
            except OSError as unlink_err:
                 logger.error(f"Failed to remove temporary config file {temp_file_path}: {unlink_err}")
    except Exception as e:
        logger.exception(f"An unexpected error occurred during config save: {e}")
        if temp_file_path and temp_file_path.exists():
             logger.warning(f"Attempting to clean up temporary config file after unexpected error: {temp_file_path}")
             try:
                 temp_file_path.unlink()
             except OSError as unlink_err:
                 logger.error(f"Failed to remove temporary config file {temp_file_path}: {unlink_err}")
    finally:
        # Final check: Ensure temp file is removed if it still exists
        if temp_file_path and temp_file_path.exists():
             logger.warning(f"Cleaning up leftover temporary config file in finally block: {temp_file_path}")
             try:
                 temp_file_path.unlink()
             except OSError as unlink_err:
                 logger.error(f"Failed to remove temporary config file {temp_file_path} in finally: {unlink_err}")


def get_config() -> AppConfig:
    """Returns the cached configuration object, loading if necessary."""
    if _cached_config is None:
        return load_config()
    return _cached_config
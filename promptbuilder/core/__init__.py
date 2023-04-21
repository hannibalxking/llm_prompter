# promptbuilder/core/__init__.py

import sys
import warnings
from typing import TYPE_CHECKING, Any # Use TYPE_CHECKING for conditional import
from loguru import logger

# Re-export core models and components for easier access
from .models import (
    FileNode,
    PromptSnippet,
    ContextFile,
    ContextResult,
    ProjectState,
    DiffSuggestion, # Keep for now (deprecated)
    DiffHunk,       # New
    DiffBase        # New Protocol/ABC
)
from .fs_scanner import FileScannerTask, _FileScannerCore
from .context_assembler import ContextAssemblerTask, _ContextAssemblerCore
from .prompt_engine import PromptEngine
from .diff_extractor import extract_suggestions, DiffParseError
from .diff_utils import calculate_hunk_line_changes, calculate_diff_text_line_changes

# --- Refinement: Conditionally import patcher and define exports ---
_apply_suggestion_func: Any = None
_patch_apply_error_type: Any = None
_exports_include_legacy = False

try:
    from .patcher import apply_suggestion as _apply_suggestion_func_real, PatchApplyError as _patch_apply_error_type_real
    _apply_suggestion_func = _apply_suggestion_func_real
    _patch_apply_error_type = _patch_apply_error_type_real
    _exports_include_legacy = True # Mark that legacy components are available
    if 'pytest' not in sys.modules:
        warnings.warn(
            "promptbuilder.core.patcher.apply_suggestion is deprecated and will be removed in v0.3.0+. Use batch_editor.apply_hunks instead.",
            DeprecationWarning,
            stacklevel=2
        )
except ImportError:
    logger.warning("Legacy patcher module not found or removed. apply_suggestion and PatchApplyError will be None.")
    _apply_suggestion_func = None
    _patch_apply_error_type = None
    _exports_include_legacy = False

# Assign to module level names for external use (will be None if import failed)
apply_suggestion = _apply_suggestion_func
PatchApplyError = _patch_apply_error_type

from .plugins import ContextProvider, register_plugin, load_plugins, get_available_providers, get_provider_by_name

# --- New Exports ---
from .matcher import locate_hunk
from .batch_editor import apply_hunks, prune_backups, ApplyReport # ApplyReport now defined here

# --- Define __all__ dynamically ---
__all__ = [
    # Models
    "FileNode", "PromptSnippet", "ContextFile", "ContextResult", "ProjectState",
    "DiffHunk", "DiffBase", "ApplyReport",
    # Core Components
    "FileScannerTask", "_FileScannerCore", "ContextAssemblerTask", "_ContextAssemblerCore",
    "PromptEngine", "extract_suggestions", "DiffParseError",
    "locate_hunk", "apply_hunks", "prune_backups",
    # Plugins
    "ContextProvider", "register_plugin", "load_plugins", "get_available_providers", "get_provider_by_name",
    # Utils
    "calculate_hunk_line_changes", "calculate_diff_text_line_changes",
]

# Conditionally add legacy exports to __all__
if _exports_include_legacy:
    __all__.extend(["DiffSuggestion", "apply_suggestion", "PatchApplyError"])
    logger.trace("Including legacy DiffSuggestion, apply_suggestion, PatchApplyError in core exports.")
else:
     logger.trace("Excluding legacy DiffSuggestion, apply_suggestion, PatchApplyError from core exports.")
# promptbuilder/core/fs_scanner.py
import os
import fnmatch
import threading
from pathlib import Path
from typing import List, Optional, Callable, Tuple
import time
from loguru import logger

from .models import FileNode

# --- Core Logic (Pure Python) ---

class _FileScannerCore:
    """Pure Python implementation of file system scanning."""

    # Common virtual environment directory names
    _VENV_PATTERNS = {"venv", ".venv", "env", ".env", "ENV", "VENV", "virtualenv", ".virtualenv"}
    # Common system/config files/folders to potentially hide
    _SYSTEM_PATTERNS = {".git", ".svn", ".hg", ".idea", ".vscode", ".project", ".settings", ".DS_Store", "Thumbs.db"}

    def __init__(self,
                 root_path: Path, # Store root path for relative calculations
                 ignore_patterns: List[str],
                 ignore_env: bool = True, # New flag
                 ignore_init: bool = False, # New flag
                 hide_system: bool = False, # New flag
                 progress_callback: Optional[Callable[[str], None]] = None,
                 error_callback: Optional[Callable[[str], None]] = None):
        self.root_path = root_path.resolve() # Ensure root is absolute and resolved
        self.ignore_patterns = ignore_patterns
        self.ignore_env = ignore_env
        self.ignore_init = ignore_init
        self.hide_system = hide_system # Store flag
        self.progress_callback = progress_callback
        self.error_callback = error_callback
        self._is_cancelled = threading.Event() # Use threading.Event for cancellation flag
        logger.debug(f"Scanner core initialized for {self.root_path} with ignores: {self.ignore_patterns}, ignore_env={self.ignore_env}, ignore_init={self.ignore_init}, hide_system={self.hide_system}")

    def _emit_progress(self, message: str):
        if self.progress_callback:
            try: self.progress_callback(message)
            except Exception as e: logger.error(f"Error in progress callback: {e}")

    def _emit_error(self, message: str):
        if self.error_callback:
            try: self.error_callback(message)
            except Exception as e: logger.error(f"Error in error callback: {e}")

    def _is_init_significant(self, file_path: Path) -> bool:
        """Checks if an __init__.py file contains significant code."""
        logger.trace(f"Checking significance of: {file_path}")
        try:
            # Optimization: If file is empty, it's not significant
            if file_path.stat().st_size == 0:
                logger.trace(f"'{file_path.name}' is empty, considered insignificant.")
                return False

            with file_path.open('r', encoding='utf-8', errors='ignore') as f:
                in_docstring = False
                for line in f:
                    stripped_line = line.strip()
                    if not stripped_line: # Skip empty lines
                        continue

                    # Basic docstring detection (might not cover all edge cases)
                    if stripped_line.startswith('"""') or stripped_line.startswith("'''"):
                        # Toggle docstring state if quotes appear at start/end of line
                        if stripped_line.count('"""') % 2 != 0 or stripped_line.count("'''") % 2 != 0:
                             in_docstring = not in_docstring
                        # If it's a single-line docstring, continue
                        if stripped_line.endswith('"""') or stripped_line.endswith("'''"):
                             continue

                    if in_docstring: # Skip lines inside multiline docstring
                        continue

                    if stripped_line.startswith('#'): # Skip comments
                        continue

                    # If we find any non-empty line that's not a comment or inside a docstring, it's significant
                    logger.trace(f"Found significant line in '{file_path.name}': {stripped_line}")
                    return True

            # If loop finishes without finding significant code
            logger.trace(f"No significant code found in '{file_path.name}'.")
            return False
        except FileNotFoundError:
            logger.warning(f"File not found while checking significance: {file_path}")
            return False # Treat as insignificant if error occurs
        except OSError as e:
            logger.warning(f"OS error reading file {file_path} for significance check: {e}")
            return False # Treat as insignificant on error
        except Exception as e:
            logger.exception(f"Unexpected error checking significance of {file_path}: {e}")
            return False # Treat as insignificant on unexpected error


    def is_ignored(self, entry_path: Path, is_dir: bool) -> bool:
        """
        Check if a path should be ignored based on symlinks, ignore patterns,
        or specific ignore flags (env, init).
        """
        # 1. Check symlink first (important for security)
        try:
             if entry_path.is_symlink(): # lstat is implicitly used by is_symlink
                 logger.trace(f"Ignoring symlink: {entry_path}")
                 return True
        except OSError as e:
             logger.warning(f"Could not check if path is symlink {entry_path}: {e}. Assuming ignored for safety.")
             self._emit_error(f"Permission error checking symlink: {entry_path.name}")
             return True

        name = entry_path.name

        # 2. Check specific ignore flags
        if is_dir and self.ignore_env and name in self._VENV_PATTERNS:
             logger.trace(f"Ignoring directory '{name}' due to ignore_env flag.")
             return True

        if not is_dir and self.ignore_init and name == "__init__.py":
             if not self._is_init_significant(entry_path):
                 logger.trace(f"Ignoring insignificant file '{name}' due to ignore_init flag.")
                 return True
             else:
                  logger.trace(f"Keeping significant file '{name}' despite ignore_init flag.")


        # 3. Check system file hiding
        if self.hide_system and name in self._SYSTEM_PATTERNS:
             logger.trace(f"Ignoring '{name}' due to hide_system flag.")
             return True

        # 3. Check general ignore patterns (relative path and name)
        try:
            relative_path = entry_path.relative_to(self.root_path)
            relative_path_str = relative_path.as_posix() # Use POSIX slashes for consistency
        except ValueError:
            # This can happen for paths outside the root, though shouldn't occur in normal scan
            logger.warning(f"Could not get relative path for {entry_path} against root {self.root_path}. Checking name only.")
            relative_path_str = None

        for pattern in self.ignore_patterns:
            if fnmatch.fnmatch(name, pattern):
                logger.trace(f"Ignoring '{name}' due to basename pattern '{pattern}'")
                return True
            if relative_path_str and fnmatch.fnmatch(relative_path_str, pattern):
                 logger.trace(f"Ignoring '{relative_path_str}' due to relative path pattern '{pattern}'")
                 return True

        return False

    def scan_directory_sync(self) -> List[FileNode]: # Removed root_path arg, use self.root_path
        """
        Scans the configured root directory structure synchronously and returns the tree.
        Raises exceptions on major errors (e.g., root not found).
        """
        logger.info(f"[Sync Scan] Starting for: {self.root_path}")
        self._is_cancelled.clear()
        if not self.root_path.is_dir(): raise ValueError(f"Provided path is not a valid directory: {self.root_path}")
        root_node = self._scan_recursive(self.root_path)
        results = [root_node] if root_node else []
        if self._is_cancelled.is_set(): logger.info(f"[Sync Scan] Cancelled during execution for: {self.root_path}")
        else: logger.info(f"[Sync Scan] Finished successfully for: {self.root_path}")
        return results

    def _scan_recursive(self, dir_path: Path) -> Optional[FileNode]:
        """Recursive helper for scanning."""
        if self._is_cancelled.is_set(): return None
        resolved_dir_path = dir_path.resolve()
        is_root = (resolved_dir_path == self.root_path)

        # Check ignore status *before* stating the directory (avoids stating ignored dirs)
        # Note: is_ignored now handles symlinks, env, init checks internally.
        if not is_root and self.is_ignored(resolved_dir_path, is_dir=True):
             return None # Directory itself is ignored

        try:
            dir_stat = resolved_dir_path.stat()
            dir_node = FileNode(path=resolved_dir_path, name=resolved_dir_path.name, is_dir=True, mod_time=dir_stat.st_mtime)
            if not is_root: self._emit_progress(f"Scanning: {resolved_dir_path.name}")

            child_nodes: List[FileNode] = []
            try: entries = list(os.scandir(resolved_dir_path))
            except OSError as scandir_err:
                 logger.warning(f"Could not scan directory contents {resolved_dir_path}: {scandir_err}")
                 self._emit_error(f"Access Error scanning: {resolved_dir_path.name}")
                 # Return dir node even if contents unreadable, but mark somehow?
                 # For now, return the node without children if scan fails.
                 return dir_node

            for entry in entries:
                if self._is_cancelled.is_set(): return None
                try:
                    # Resolve early for checks, handle potential errors during resolving
                    entry_path_abs = Path(entry.path).resolve()
                    entry_is_dir_flag = entry.is_dir() # Check type *after* resolving symlinks implicitly
                except OSError as resolve_err:
                     logger.warning(f"Could not resolve or stat entry {entry.path}: {resolve_err}. Skipping.")
                     self._emit_error(f"Access Error resolving: {entry.name}")
                     continue

                # Check if the entry itself should be ignored (handles symlinks, env, init, patterns)
                if self.is_ignored(entry_path_abs, entry_is_dir_flag):
                    continue

                # Process directories and files
                if entry_is_dir_flag:
                    sub_dir_node = self._scan_recursive(entry_path_abs) # Pass resolved path
                    if sub_dir_node: sub_dir_node.parent = dir_node; child_nodes.append(sub_dir_node)
                elif entry.is_file(): # Check is_file *after* ignore checks
                    try:
                        # Use the already resolved path and stat info if possible
                        # Re-statting might be needed if os.scandir doesn't provide all info reliably
                        file_stat = entry_path_abs.stat() # Use resolved path
                        file_node = FileNode(path=entry_path_abs, name=entry.name, is_dir=False, size=file_stat.st_size, mod_time=file_stat.st_mtime, parent=dir_node)
                        child_nodes.append(file_node)
                    except OSError as stat_err:
                        logger.warning(f"Could not stat file {entry_path_abs}: {stat_err}")
                        self._emit_error(f"Access Error stating: {entry.name}")
                # else: ignore other types like block devices, sockets etc.

            dir_node.children = sorted(child_nodes, key=lambda n: (not n.is_dir, n.name.lower()))
            return dir_node

        except OSError as e:
            logger.warning(f"Could not stat directory {resolved_dir_path}: {e}")
            self._emit_error(f"Access Error stating dir: {resolved_dir_path.name}")
            return None

    def cancel(self):
        """Signals the scanner to stop processing."""
        logger.info("Cancellation requested for scanner core.")
        self._is_cancelled.set()

# --- Qt Adapter Task ---

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

class FileScannerSignals(QObject):
    finished = Signal(list); error = Signal(str); progress = Signal(str)

class FileScannerTask(QRunnable):
    """QRunnable adapter for running _FileScannerCore in a background thread."""
    def __init__(self,
                 root_path: Path,
                 ignore_patterns: List[str],
                 ignore_env: bool, # Pass flag
                 ignore_init: bool, # Pass flag
                 hide_system: bool # Pass flag
                 ):
        super().__init__()
        self.root_path = root_path
        self.ignore_patterns = ignore_patterns
        self.ignore_env = ignore_env # Store flag
        self.ignore_init = ignore_init # Store flag
        self.hide_system = hide_system # Store flag
        self.signals = FileScannerSignals()
        self.scanner_core: Optional[_FileScannerCore] = None
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        try:
            self.scanner_core = _FileScannerCore(
                root_path=self.root_path,
                ignore_patterns=self.ignore_patterns,
                ignore_env=self.ignore_env, # Pass to core
                ignore_init=self.ignore_init, # Pass to core
                hide_system=self.hide_system, # Pass to core
                progress_callback=self.signals.progress.emit,
                error_callback=self.signals.error.emit
            )
            results = self.scanner_core.scan_directory_sync()
            # Check cancellation status *after* scan finishes or is interrupted
            if self.scanner_core and self.scanner_core._is_cancelled.is_set():
                 self.signals.error.emit("Scan cancelled")
            else:
                 self.signals.finished.emit(results)
        except ValueError as ve:
            logger.error(f"Scan Error for {self.root_path}: {ve}")
            self.signals.error.emit(str(ve))
        except Exception as e:
            logger.exception(f"Unexpected error during file scan task for {self.root_path}: {e}")
            self.signals.error.emit(f"Unexpected Scan Error: {e}")
        finally:
            self.scanner_core = None # Ensure core reference is cleared

    def cancel(self):
        logger.info(f"Cancellation signal received for scan task: {self.root_path}")
        if self.scanner_core:
            self.scanner_core.cancel()
# promptbuilder/core/context_assembler.py
import re
import html # Keep for attribute escaping
from pathlib import Path
from typing import List, Set, Tuple, Callable, Optional
import mmap
import threading
from loguru import logger

from .models import ContextResult, ContextFile
from .token_counter import UnifiedTokenCounter # Use unified counter

# --- Helper Function for Minimal Escaping ---
def minimal_escape(text: str) -> str:
    """Escapes only '&' and '<' for safe inclusion as XML content."""
    # Replace '&' first to avoid double-escaping if '<' contains '&'
    text = text.replace("&", "&")
    text = text.replace("<", "<")
    # '>' is generally safe but can be escaped if needed:
    # text = text.replace(">", ">")
    return text

# --- Core Logic (Pure Python) ---

class _ContextAssemblerCore:
    """Pure Python implementation of context assembly."""
    # Constants for file reading strategies
    MAX_FILE_SIZE_MMAP = 10 * 1024 * 1024 # Use memory mapping for files larger than 10MB
    MAX_FILE_SIZE_WARN = 50 * 1024 * 1024 # Log warning for files larger than 50MB

    def __init__(self,
                 project_root_path: Path, # Added project root path
                 secret_patterns: List[str],
                 # --- NEW: Pass token counter settings ---
                 token_counter_backend: str,
                 token_counter_model_openai: str,
                 token_counter_model_gemini: str,
                 # --- End NEW ---
                 progress_callback: Optional[Callable[[str], None]] = None,
                 error_callback: Optional[Callable[[str], None]] = None):
        """Initializes the context assembler."""
        self.project_root_path = project_root_path.resolve() # Store resolved root path
        # Compile regex patterns for efficiency
        self.secret_patterns_compiled = [re.compile(pattern, re.IGNORECASE) for pattern in secret_patterns]
        # Callbacks for UI updates and cancellation
        self.progress_callback = progress_callback
        self.error_callback = error_callback
        # Threading event for cancellation
        self._is_cancelled = threading.Event()
        # Instantiate the token counter based on passed settings
        model_name = token_counter_model_openai if token_counter_backend == "openai" else token_counter_model_gemini
        self.token_counter = UnifiedTokenCounter(backend=token_counter_backend, model_name=model_name)
        logger.debug(f"Context assembler core initialized for root: {self.project_root_path}")

    def _emit_progress(self, message: str):
        """Safely emits a progress message via the callback."""
        if self.progress_callback:
            try:
                self.progress_callback(message)
            except Exception as e:
                # Log errors in the callback itself, but don't crash the assembler
                logger.error(f"Error in progress callback: {e}")

    def _emit_error(self, message: str):
        """Safely emits an error message via the callback."""
        if self.error_callback:
            try:
                self.error_callback(message)
            except Exception as e:
                logger.error(f"Error in error callback: {e}")

    def _read_file_content(self, file_path: Path) -> Tuple[str, str, int]:
        """
        Reads file content, handles encoding, size checks, and secrets scrubbing.

        Returns:
            Tuple containing:
            - content (str): The file content (or error message).
            - status (str): Status code (e.g., "read_ok", "read_error", "read_cancelled").
            - initial_token_count (int): Token count of the content before budgeting.
        """
        status = "read_ok"
        content = ""
        initial_tokens = 0
        try:
            # Check file size for warnings and memory mapping strategy
            fsize = file_path.stat().st_size
            if fsize > self.MAX_FILE_SIZE_WARN:
                logger.warning(f"Reading large file ({fsize / 1024**2:.1f} MB): {file_path.name}")
                self._emit_progress(f"Reading large file: {file_path.name}...")

            # Determine reading strategy (mmap or read_text/read_bytes)
            use_mmap = fsize > self.MAX_FILE_SIZE_MMAP and fsize > 0
            encodings_to_try = ['utf-8', 'latin-1', 'cp1252'] # Common encodings

            # Read content using appropriate method
            if use_mmap:
                with open(file_path, "rb") as f:
                    if fsize == 0:
                        content = "" # Handle empty files
                    else:
                        try:
                            # Use memory mapping for large files
                            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                                decoded = False
                                for enc in encodings_to_try:
                                    if self._is_cancelled.is_set():
                                        return "<cancelled>", "read_cancelled", 0
                                    try:
                                        content = mm[:].decode(enc)
                                        decoded = True
                                        break # Stop on first successful decode
                                    except UnicodeDecodeError:
                                        continue # Try next encoding
                                if not decoded:
                                    # Fallback: decode with replacement characters
                                    content = mm[:].decode('utf-8', errors='replace')
                                    status = "read_decode_error"
                                    logger.warning(f"Could not decode {file_path.name} with {encodings_to_try}, used replacement characters.")
                        except ValueError as mmap_err:
                             # Handle specific mmap error for empty files after check
                             if "mmap length is greater than file size" in str(mmap_err):
                                 content = ""
                             else:
                                 raise # Re-raise other mmap errors
            else:
                 # Read smaller files directly into memory
                 decoded = False
                 for enc in encodings_to_try:
                     if self._is_cancelled.is_set():
                         return "<cancelled>", "read_cancelled", 0
                     try:
                         content = file_path.read_text(encoding=enc)
                         decoded = True
                         break
                     except UnicodeDecodeError:
                         continue
                     except OSError as read_err:
                         logger.error(f"OS error reading file {file_path}: {read_err}")
                         return f"<Error reading file: {read_err}>", "read_error", 0
                 if not decoded:
                     try:
                         # Fallback: read as bytes and decode with replacement
                         binary_content = file_path.read_bytes()
                         content = binary_content.decode('utf-8', errors='replace')
                         status = "read_decode_error"
                         logger.warning(f"Could not decode {file_path.name} with {encodings_to_try} (read_text), used replacement characters.")
                     except OSError as read_err:
                         logger.error(f"OS error reading file as binary {file_path}: {read_err}")
                         return f"<Error reading file: {read_err}>", "read_error", 0

            # --- Secrets Scrubbing ---
            lines = content.splitlines()
            scrubbed_lines = []
            was_scrubbed = False
            for line_num, line in enumerate(lines):
                if self._is_cancelled.is_set():
                    return "<cancelled>", "read_cancelled", 0
                scrubbed_line = line
                for pattern in self.secret_patterns_compiled:
                    # Replace matches with a redaction placeholder
                    def repl(match):
                        nonlocal was_scrubbed
                        was_scrubbed = True
                        return '<redacted reason="secret">'
                    scrubbed_line = pattern.sub(repl, scrubbed_line)
                scrubbed_lines.append(scrubbed_line)

            if was_scrubbed:
                content = "\n".join(scrubbed_lines)
                logger.info(f"Scrubbed potential secrets in: {file_path.name}")
                if status == "read_ok":
                    status = "read_scrubbed" # Update status if scrubbing occurred

            # --- Token Counting & Progress ---
            # Count tokens *after* potential scrubbing
            self._emit_progress(f"Counting tokens for: {file_path.name}...")
            if self._is_cancelled.is_set():
                 return "<cancelled>", "read_cancelled", 0
            initial_tokens = self.token_counter.count(content) # Use unified counter instance
            self._emit_progress(f"Processed: {file_path.name} ({initial_tokens} tokens)")

            return content, status, initial_tokens

        except FileNotFoundError:
            logger.error(f"File not found during context assembly: {file_path}")
            self._emit_error(f"File not found: {file_path.name}")
            return "<Error: File not found>", "read_error_not_found", 0
        except OSError as e:
            logger.error(f"OS error reading file {file_path}: {e}")
            self._emit_error(f"OS Error reading {file_path.name}: {e}")
            return f"<Error reading file: {e}>", "read_error", 0
        except Exception as e:
            # Catch unexpected errors during file processing
            logger.exception(f"Unexpected error reading file {file_path}: {e}")
            self._emit_error(f"Unexpected error reading {file_path.name}")
            return f"<Unexpected error reading file: {e}>", "read_error_unexpected", 0

    def _apply_budget(self, files_data: List[ContextFile], max_tokens: int) -> Tuple[List[ContextFile], List[ContextFile], int, str]:
        """
        Applies token budget. **MODIFIED: Budget check is disabled.**
        Includes all files and calculates total tokens.
        """
        included_files: List[ContextFile] = []
        skipped_files: List[ContextFile] = [] # Should remain empty now
        current_tokens = 0
        budget_details = "All selected files included (budget limit disabled)." # Updated message

        # Sort files for consistent ordering (optional, but good practice)
        files_data.sort(key=lambda f: f.path)

        for file_info in files_data:
            if self._is_cancelled.is_set():
                 # If cancelled during this loop, mark remaining as skipped due to cancellation
                 idx = files_data.index(file_info)
                 # Mark the rest as skipped due to cancellation
                 for f_skip in files_data[idx:]:
                      if f_skip.status in {"read_ok", "read_scrubbed"}:
                           f_skip.status = "skipped_cancelled"
                      skipped_files.append(f_skip)
                 budget_details = "Assembly cancelled during processing."
                 break # Stop processing

            # --- Budgeting Logic Disabled ---
            # Always include the file, regardless of token count
            included_files.append(file_info)
            current_tokens += file_info.tokens
            # --- End Disabled Logic ---

        # Return all files as included, empty skipped list (unless cancelled), total tokens, and the new message
        return included_files, skipped_files, current_tokens, budget_details.strip()

    def assemble_context_sync(self, selected_paths: Set[Path], max_tokens: int) -> ContextResult:
        """
        Synchronously reads files, scrubs secrets, calculates tokens,
        and assembles the final <context> XML block. Budgeting is disabled.
        """
        logger.info(f"[Sync Assemble] Starting for {len(selected_paths)} paths. Max tokens setting ignored for inclusion.")
        self._is_cancelled.clear() # Reset cancellation flag for this run
        all_files_data: List[ContextFile] = []
        processed_count = 0
        sorted_paths = sorted(list(selected_paths)) # Process in a consistent order
        total_paths = len(sorted_paths)

        # --- Read and process each selected file ---
        for file_path in sorted_paths:
            if self._is_cancelled.is_set():
                logger.info("[Sync Assemble] Cancelled during file reading.")
                break # Exit loop if cancelled

            if not file_path.is_file():
                logger.warning(f"Skipping non-file path during assembly: {file_path}")
                continue # Skip directories or other non-files

            processed_count += 1
            self._emit_progress(f"Processing file {processed_count}/{total_paths}: {file_path.name}")

            content, status, initial_tokens = self._read_file_content(file_path)

            # Create ContextFile object even if there were errors, store status
            all_files_data.append(ContextFile(
                path=file_path,
                content=content,
                tokens=initial_tokens,
                status=status
            ))

            # If reading was cancelled, stop processing more files
            if status == "read_cancelled":
                break

        # If cancelled during reading, return a cancelled result
        if self._is_cancelled.is_set():
            # Mark remaining unprocessed files as skipped due to cancellation
            # Note: all_files_data contains only processed files up to cancellation point
            # We don't have easy access to the *remaining* paths here without passing them around.
            # For simplicity, return what was processed and indicate cancellation.
            return ContextResult(
                context_xml="<context><cancelled/></context>",
                included_files=[], # Or potentially files processed before cancel? Decide consistency.
                skipped_files=all_files_data, # Files processed before cancel marked appropriately
                total_tokens=0,
                budget_details="Assembly cancelled during file reading."
            )

        # --- "Apply" Budget (Now just includes all processed files) ---
        self._emit_progress("Finalizing file list...")
        included_files, skipped_files, total_tokens, budget_details = self._apply_budget(
            all_files_data, max_tokens # max_tokens is now ignored by _apply_budget
        )

        # Check for cancellation again after budgeting step
        if self._is_cancelled.is_set():
             logger.info("[Sync Assemble] Cancelled during finalization.")
             # Return potentially partially included files if needed
             return ContextResult(
                 context_xml="<context><cancelled/></context>",
                 included_files=included_files, # Files included before cancel
                 skipped_files=skipped_files, # Files skipped due to cancel
                 total_tokens=total_tokens,
                 budget_details="Assembly cancelled during finalization."
             )

        # --- Build Final XML ---
        self._emit_progress("Building final XML...")
        context_lines = ["<context>"]
        # Iterate through the files determined by the (now disabled) budgeting step
        for file_info in included_files:
             # Escape filename for XML attribute safety
             safe_name = html.escape(file_info.path.name, quote=True)

             # Calculate module path relative to project root
             try:
                 relative_path = file_info.path.relative_to(self.project_root_path)
                 # Get the parent directory part of the relative path
                 module_dir = relative_path.parent
                 # Format with backslashes and ensure trailing backslash
                 if str(module_dir) == '.': # File is in the root
                     module_path_str = "\\"
                 else:
                     module_path_str = str(module_dir).replace('/', '\\') + '\\'
             except ValueError:
                 # Should not happen if selected_paths are within root, but handle defensively
                 logger.warning(f"Could not determine relative path for {file_info.path}. Using full path.")
                 module_path_str = str(file_info.path.parent).replace('/', '\\') + '\\' # Fallback

             safe_module = html.escape(module_path_str, quote=True)

             # Use minimal escaping for the content to preserve code formatting
             escaped_content = minimal_escape(file_info.content)

             # Add file element to XML using 'name' and 'module' attributes
             context_lines.append(f"    <file name='{safe_name}' module='{safe_module}'>")
             context_lines.append(escaped_content)
             context_lines.append(f"    </file>")

        context_lines.append("</context>")
        context_xml = "\n".join(context_lines)

        # --- Create and return the final result ---
        result = ContextResult(
            context_xml=context_xml,
            included_files=included_files,
            skipped_files=skipped_files, # Should be empty unless cancelled
            total_tokens=total_tokens,
            budget_details=budget_details # Will indicate all files included
        )
        logger.info(f"[Sync Assemble] Finished. Total Tokens: {total_tokens}. Included: {len(included_files)}, Skipped: {len(skipped_files)}.")
        logger.info(f"[Sync Assemble] Budget Details: {result.budget_details}")
        return result

    def cancel(self):
        """Signals the assembler to cancel the current operation."""
        logger.info("Cancellation requested for context assembler core.")
        self._is_cancelled.set()

# --- Qt Adapter Task ---
from PySide6.QtCore import QObject, QRunnable, Signal, Slot
class ContextAssemblerSignals(QObject):
    finished = Signal(object) # Emits ContextResult
    error = Signal(str)       # Emits error message string
    progress = Signal(str)    # Emits progress message string

class ContextAssemblerTask(QRunnable):
    """Runs the _ContextAssemblerCore in a background thread via QThreadPool."""
    def __init__(self,
                 project_root_path: Path, # Added project root
                 selected_paths: Set[Path],
                 max_tokens: int,
                 secret_patterns: List[str],
                 # --- NEW: Accept token counter settings ---
                 token_counter_backend: str,
                 token_counter_model_openai: str,
                 token_counter_model_gemini: str):
        super().__init__()
        self.project_root_path = project_root_path # Store project root
        self.selected_paths = selected_paths
        self.max_tokens = max_tokens # Still passed, though not used for skipping
        self.secret_patterns = secret_patterns
        self.token_counter_backend = token_counter_backend
        self.token_counter_model_openai = token_counter_model_openai
        self.token_counter_model_gemini = token_counter_model_gemini
        self.signals = ContextAssemblerSignals()
        self.assembler_core: Optional[_ContextAssemblerCore] = None
        self.setAutoDelete(True) # Auto-delete task when finished

    @Slot()
    def run(self) -> None:
        """The entry point for the background thread."""
        try:
            # Create the core assembler instance, passing callbacks and root path
            self.assembler_core = _ContextAssemblerCore(
                project_root_path=self.project_root_path, # Pass root path
                secret_patterns=self.secret_patterns,
                # --- NEW: Pass token counter settings to core ---
                token_counter_backend=self.token_counter_backend,
                token_counter_model_openai=self.token_counter_model_openai,
                token_counter_model_gemini=self.token_counter_model_gemini,
                progress_callback=self.signals.progress.emit,
                error_callback=self.signals.error.emit
            )
            # Run the synchronous assembly process
            result = self.assembler_core.assemble_context_sync(
                self.selected_paths, self.max_tokens
            )
            # Check for cancellation *after* the sync call returns
            if self.assembler_core and self.assembler_core._is_cancelled.is_set():
                # Emit error signal if cancelled
                self.signals.error.emit("Context assembly cancelled")
            else:
                # Emit finished signal with the result if successful
                self.signals.finished.emit(result)
        except Exception as e:
            # Catch any unexpected errors during the task execution
            logger.exception(f"Unexpected error during context assembly task: {e}")
            self.signals.error.emit(f"Unexpected Assembly Error: {e}")
        finally:
            # Ensure the reference to the core is cleared
            self.assembler_core = None

    def cancel(self):
        """Requests cancellation of the running core assembler."""
        logger.info("Cancellation signal received for context assembly task.")
        if self.assembler_core:
            self.assembler_core.cancel()
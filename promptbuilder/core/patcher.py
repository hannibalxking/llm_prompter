# promptbuilder/core/patcher.py

import os
import shutil
from pathlib import Path
import difflib
from typing import List, Optional, Tuple # Added Tuple

from loguru import logger

from .models import DiffSuggestion

class PatchApplyError(Exception):
    """Custom exception for errors during patch application."""
    pass

# Removed PatchVerificationError as it's no longer raised directly to stop application
# class PatchVerificationError(PatchApplyError):
#    """Exception raised when applied changes don't match the provided diff."""
#    pass

def _normalize_diff_lines(diff_lines: List[str]) -> List[str]:
    """
    Filters out header lines (---, +++, @@) and strips whitespace
    from a list of diff lines for comparison. **Only includes change lines (+/-).**
    """
    normalized = []
    for line in diff_lines:
        # Only process lines indicating changes, ignore context lines (' ') and headers
        if line.startswith('+') and not line.startswith('+++'):
            # Explicitly remove CR and then strip trailing whitespace for robust comparison
            normalized.append(line.replace('\r', '').rstrip())
        elif line.startswith('-') and not line.startswith('---'):
            # Explicitly remove CR and then strip trailing whitespace for robust comparison
            normalized.append(line.replace('\r', '').rstrip())
    return normalized

def apply_suggestion(suggestion: DiffSuggestion, project_root: Path) -> Tuple[str, Optional[str]]:
    """
    Applies the suggested change to the target file and verifies against diff_text.

    Prioritizes using `proposed_content` for whole-file replacement.
    Creates a backup in a dedicated 'backups' directory within the project root.
    Verifies that the changes applied match the provided diff text, but **does not
    prevent application** if verification fails. Instead, returns a status indicating
    the discrepancy.

    Args:
        suggestion: The DiffSuggestion object containing the change.
        project_root: The absolute path to the project root (for validation).

    Returns:
        A tuple containing:
        - status (str): 'applied_ok', 'applied_with_discrepancies'.
        - message (Optional[str]): Details about verification failure or skip reason.

    Raises:
        PatchApplyError: If the file path is invalid, backup fails, writing fails,
                         or other critical OS errors occur.
        FileNotFoundError: If the original file doesn't exist (and shouldn't for diffs).
    """
    target_path = suggestion.path
    rel_path = suggestion.rel_path # Use the relative path for backup structure
    status = "applied_ok" # Default status
    message: Optional[str] = None

    # --- Safety Checks ---
    try:
        # Ensure the target path is within the project root for safety
        target_path.relative_to(project_root)
    except ValueError:
        msg = f"Target path '{target_path}' is outside the project root '{project_root}'. Aborting."
        logger.error(msg)
        raise PatchApplyError(msg)

    is_new_file = not target_path.exists()
    logger.debug(f"Target path: {target_path}, Exists: {not is_new_file}")

    if not target_path.is_file():
        # If using proposed_content, the file might be new.
        # If using diff_text only (not implemented), the file MUST exist.
        if suggestion.proposed_content is None and suggestion.diff_text:
             msg = f"Original file '{target_path}' not found for applying diff."
             logger.error(msg)
             raise FileNotFoundError(msg)
        elif suggestion.proposed_content is not None:
             logger.info(f"Target file '{suggestion.rel_path}' does not exist. Will create it.")
             # Ensure parent directory exists for the *target* file
             try:
                 target_path.parent.mkdir(parents=True, exist_ok=True)
             except OSError as e:
                  msg = f"Failed to create parent directory for new file '{target_path.parent}': {e}"
                  logger.error(msg)
                  raise PatchApplyError(msg) from e
        else:
             # Should not happen if validation is correct
             msg = f"Target file '{target_path}' not found and no content provided."
             logger.error(msg)
             raise FileNotFoundError(msg)


    # --- Strategy 1: Whole-file replacement (Preferred) ---
    if suggestion.proposed_content is not None:
        action_desc = "Creating new file" if is_new_file else "Applying suggestion to"
        logger.info(f"{action_desc} '{suggestion.rel_path}' using proposed_content.")
        backup_path: Optional[Path] = None # Initialize backup_path
        temp_path: Optional[Path] = None # Initialize temp_path

        try:
            # 1. Create Backup (only if original file exists)
            if not is_new_file:
                # Construct backup path: root/backups/relative/path/file.py
                backup_dir = project_root / "backups"
                backup_path = backup_dir / rel_path.replace('\\', '/') # Ensure posix separators for joining

                # Ensure the backup directory structure exists
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                logger.debug(f"Ensured backup directory exists: {backup_path.parent}")

                # Copy the original file to the backup location, overwriting if exists
                shutil.copy2(target_path, backup_path) # copy2 preserves metadata and overwrites
                logger.info(f"Created/Overwritten backup: {backup_path}")
            else:
                logger.debug(f"Skipping backup for new file: {suggestion.rel_path}")

            # 2. Write new content (atomic via temp file)
            # Create temp file in the same directory as the target for atomic replace
            temp_path = target_path.with_suffix(target_path.suffix + '.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(suggestion.proposed_content)
            # Atomically replace the original file with the temporary file
            os.replace(temp_path, target_path)
            logger.info(f"Successfully wrote proposed content to: {target_path}")
            temp_path = None # Prevent cleanup in finally if replace succeeded

            # 3. Verification Step (Only if file existed before, i.e., backup was made)
            if not is_new_file and backup_path and backup_path.exists():
                if not suggestion.diff_text:
                     logger.warning(f"Skipping verification for existing file '{suggestion.rel_path}' because no diff_text was provided.")
                     message = "Verification skipped: no diff_text provided."
                else:
                    logger.info(f"Verifying changes applied to {suggestion.rel_path} against provided diff...")
                    try:
                        backup_content_lines = backup_path.read_text(encoding='utf-8').splitlines()
                        new_content_lines = target_path.read_text(encoding='utf-8').splitlines()

                        # Generate the actual diff between backup and new file
                        actual_diff_generator = difflib.unified_diff(
                            backup_content_lines,
                            new_content_lines,
                            fromfile=f'a/{rel_path}',
                            tofile=f'b/{rel_path}',
                            lineterm='' # Important: Prevent difflib adding its own newlines
                        )
                        actual_diff_lines = list(actual_diff_generator)

                        # --- DEBUG LOGGING ---
                        logger.debug(f"Raw actual_diff_lines ({len(actual_diff_lines)} lines):\n" + "\n".join(f'ACTUAL: {line!r}' for line in actual_diff_lines))
                        expected_diff_lines_raw = suggestion.diff_text.splitlines()
                        logger.debug(f"Raw expected_diff_lines ({len(expected_diff_lines_raw)} lines):\n" + "\n".join(f'EXPECT: {line!r}' for line in expected_diff_lines_raw))
                        # --- END DEBUG LOGGING ---

                        # Normalize both actual and expected diffs for comparison
                        norm_actual_diff = _normalize_diff_lines(actual_diff_lines)
                        norm_expected_diff = _normalize_diff_lines(suggestion.diff_text.splitlines())

                        if norm_actual_diff != norm_expected_diff:
                            logger.error("Verification FAILED: Applied content differs from expected diff.")
                            # Log the differences for debugging
                            diff_of_diffs = list(difflib.unified_diff(norm_expected_diff, norm_actual_diff, fromfile="expected_diff", tofile="actual_diff", lineterm=''))
                            logger.debug("Difference between expected and actual diff (change lines only):\n" + "\n".join(diff_of_diffs))

                            # --- MODIFICATION: Do NOT restore, set status and message ---
                            status = "applied_with_discrepancies"
                            message = f"Verification failed for '{suggestion.rel_path}'. Applied content differs from the provided diff text. Please review the changes."
                            logger.warning(message)
                            # --- END MODIFICATION ---
                        else:
                            logger.info(f"Verification successful for {suggestion.rel_path}.")
                            message = "Verification successful." # Optional success message
                    except Exception as verify_err:
                        # Catch errors during verification itself (e.g., reading files)
                        # Log the error, but don't prevent the application from being considered done
                        logger.exception(f"Error during verification for {suggestion.rel_path}: {verify_err}")
                        # Set status to indicate discrepancy due to verification error
                        status = "applied_with_discrepancies"
                        message = f"Error during verification for '{suggestion.rel_path}': {verify_err}. File was modified, but verification failed."
                        # Do NOT raise an error here that would stop the flow

            elif is_new_file:
                logger.debug(f"Skipping verification for new file: {suggestion.rel_path}")
                message = "Verification skipped for new file."

        except (IOError, OSError, shutil.Error) as e:
            # Catch critical errors during backup or writing
            msg = f"Error applying proposed content to '{suggestion.rel_path}': {e}"
            logger.exception(msg) # Log exception details
            raise PatchApplyError(msg) from e # Re-raise as PatchApplyError
        finally:
            # Ensure temporary file is removed if it still exists after failure
            if temp_path and temp_path.exists():
                logger.warning(f"Cleaning up temporary file: {temp_path}")
                try:
                    temp_path.unlink()
                except OSError as unlink_err:
                    logger.error(f"Failed to remove temporary file {temp_path}: {unlink_err}")

        return status, message # Return status and message

    # --- Strategy 2: Apply Diff (Fallback - Requires external lib or complex logic) ---
    elif suggestion.diff_text:
        logger.warning(f"Applying suggestion to '{suggestion.rel_path}' using diff_text is not yet implemented.")
        raise PatchApplyError("Applying diff text directly is not implemented. Please ensure LLM provides <proposed_content>.")

    else:
        # Should not happen if extraction is correct
        msg = f"No content (diff or proposed) found for suggestion: {suggestion.rel_path}"
        logger.error(msg)
        raise PatchApplyError(msg)
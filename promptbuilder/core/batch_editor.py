# promptbuilder/core/batch_editor.py

import os
import shutil
import time
import hashlib
from pathlib import Path
from typing import List, Optional, Dict, Literal, Tuple
from dataclasses import dataclass, field

from loguru import logger

from .models import DiffHunk
from .matcher import locate_hunk

@dataclass
class ApplyReport:
    """Report detailing the outcome of applying hunks to a file."""
    file_path: Path
    status: Literal[
        "ok", "skipped_unmatched", "skipped_external_change",
        "skipped_overlap", "failed_backup", "failed_write",
        "failed_read", "no_action"
    ]
    unmatched_hunks: List[DiffHunk] = field(default_factory=list)
    message: str = ""
    lines_applied: Optional[int] = None # Track number of lines actually changed (+ added, - deleted)

    def is_successful(self) -> bool:
        """Helper to check if the operation was considered successful (file written)."""
        return self.status == "ok"


def _calculate_sha1(file_path: Path) -> Optional[str]:
    """Calculates the SHA1 hash of a file."""
    try:
        hasher = hashlib.sha1()
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(4096)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()
    except OSError as e:
        logger.error(f"Failed to calculate SHA1 for {file_path}: {e}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error calculating SHA1 for {file_path}: {e}")
        return None

def apply_hunks(
    file_path: Path,
    hunks: List[DiffHunk],
    project_root: Path,
    config_max_distance: float
) -> ApplyReport:
    """
    Applies a list of DiffHunk objects to a single target file.

    Handles locating hunks, checking for overlaps and external modifications,
    creating backups, and performing atomic writes.

    Args:
        file_path: The absolute path to the target file.
        hunks: A list of DiffHunk objects intended for this file.
        project_root: The absolute path to the project root directory.
        config_max_distance: The fuzzy matching threshold from config.

    Returns:
        An ApplyReport object detailing the outcome.
    """
    # --- FIX: Wrap relative_to in try-except for logging ---
    try:
        log_rel_path_str = str(file_path.relative_to(project_root))
    except ValueError:
        log_rel_path_str = str(file_path) # Fallback to absolute path if outside root
    logger.info(f"Attempting to apply {len(hunks)} hunk(s) to: {log_rel_path_str}")
    # --- END FIX ---

    original_content: List[str] = []
    initial_sha1: Optional[str] = None
    located_hunks: List[DiffHunk] = []
    unmatched_hunks_report: List[DiffHunk] = []
    temp_checksums: Dict[Path, str] = {}
    total_lines_applied = 0

    # --- 1. Load File and Initial Checks ---
    is_new_file = not file_path.exists()
    if is_new_file:
        logger.info(f"Target file {file_path.name} does not exist, treating as new file creation.")
        for hunk in hunks:
            if any(line.startswith('-') and not line.startswith('---') for line in hunk.hunk_lines):
                msg = f"File {file_path.name} does not exist, but hunk contains '-' deletion lines. Cannot apply."
                logger.error(msg)
                return ApplyReport(file_path=file_path, status="failed_read", message=msg)
        original_content = []
        initial_sha1 = None
    else:
        try:
            with file_path.open('r', encoding='utf-8', errors='replace') as f:
                original_content = f.read().splitlines()
            calculated_sha1 = _calculate_sha1(file_path)
            if calculated_sha1 is None:
                msg = f"Failed to calculate initial checksum for {file_path.name}. Aborting apply."
                logger.error(msg)
                return ApplyReport(file_path=file_path, status="failed_read", message=msg)
            temp_checksums[file_path] = calculated_sha1
            initial_sha1 = calculated_sha1
            logger.debug(f"Initial SHA1 for {file_path.name}: {initial_sha1}")
        except OSError as e:
            msg = f"Failed to read original file {file_path.name}: {e}"
            logger.error(msg)
            return ApplyReport(file_path=file_path, status="failed_read", message=msg)
        except Exception as e:
            msg = f"Unexpected error reading original file {file_path.name}: {e}"
            logger.exception(msg)
            return ApplyReport(file_path=file_path, status="failed_read", message=msg)

    # --- 2. Locate Hunks ---
    for hunk in hunks:
        hunk.first_target_line = None
        hunk.status = 'pending'
        start_line = locate_hunk(original_content, hunk, max_distance=config_max_distance)
        if start_line is not None:
            hunk.first_target_line = start_line
            hunk.status = 'matched'
            located_hunks.append(hunk)
        else:
            hunk.status = 'unmatched'
            unmatched_hunks_report.append(hunk)

    # --- 3. Pre-check: Any Unmatched? ---
    if unmatched_hunks_report:
        msg = f"Skipping apply for {file_path.name}: {len(unmatched_hunks_report)} hunk(s) could not be located confidently."
        logger.warning(msg)
        return ApplyReport(file_path=file_path, status="skipped_unmatched", unmatched_hunks=unmatched_hunks_report, message=msg)

    if not located_hunks:
         msg = f"No matched hunks to apply for {file_path.name}."
         logger.info(msg)
         return ApplyReport(file_path=file_path, status="no_action", message=msg)

    # --- 4. Sort Located Hunks ---
    located_hunks.sort(key=lambda h: h.first_target_line if h.first_target_line is not None else float('inf'))

    # --- 5. Overlap Check (Refined) ---
    effective_ranges: List[Tuple[int, int]] = []
    current_offset = 0
    for hunk in located_hunks:
        if hunk.first_target_line is None: continue

        effective_start = hunk.first_target_line + current_offset
        original_block_len = len(hunk.context_before) + \
                             sum(1 for line in hunk.hunk_lines if line.startswith('-') or line.startswith(' ')) + \
                             len(hunk.context_after)
        effective_end = effective_start + original_block_len
        effective_ranges.append((effective_start, effective_end))

        num_added = sum(1 for line in hunk.hunk_lines if line.startswith('+'))
        num_deleted = sum(1 for line in hunk.hunk_lines if line.startswith('-'))
        current_offset += (num_added - num_deleted)

    for i in range(len(effective_ranges) - 1):
        end1 = effective_ranges[i][1]
        start2 = effective_ranges[i+1][0]
        if start2 < end1:
            hunk1 = located_hunks[i]
            hunk2 = located_hunks[i+1]
            msg = (f"Skipping apply for {file_path.name}: Hunks overlap detected after calculating shifts. "
                   f"Hunk near original line {hunk1.first_target_line+1} (effective end {end1}) overlaps with "
                   f"hunk near original line {hunk2.first_target_line+1} (effective start {start2}).")
            logger.error(msg)
            return ApplyReport(file_path=file_path, status="skipped_overlap", message=msg)

    # --- 6. Apply In-Memory ---
    modified_content = list(original_content)
    line_offset = 0

    for hunk in located_hunks:
        if hunk.first_target_line is None:
             logger.error(f"Internal error: Hunk marked as located has no target line: {hunk.rel_path}")
             continue

        current_hunk_start_line = hunk.first_target_line + line_offset
        insert_lines = []
        num_added = 0
        num_deleted = 0
        num_context = 0
        for line in hunk.hunk_lines:
            if line.startswith('+'):
                insert_lines.append(line[1:])
                num_added += 1
            elif line.startswith('-'):
                num_deleted += 1
            elif line.startswith(' '):
                num_context += 1

        original_lines_start_index = current_hunk_start_line + len(hunk.context_before)
        num_original_lines_in_hunk_body = num_deleted + num_context
        original_lines_end_index = original_lines_start_index + num_original_lines_in_hunk_body

        try:
            if not (0 <= original_lines_start_index <= len(modified_content) and 0 <= original_lines_end_index <= len(modified_content)):
                 raise IndexError(f"Calculated original line range [{original_lines_start_index}:{original_lines_end_index}] invalid for len {len(modified_content)}")
            del modified_content[original_lines_start_index:original_lines_end_index]
            if not (0 <= original_lines_start_index <= len(modified_content)):
                 raise IndexError(f"Calculated insertion point {original_lines_start_index} invalid after deletion (len {len(modified_content)})")
            modified_content[original_lines_start_index:original_lines_start_index] = insert_lines
        except IndexError as e:
             msg = f"Error applying hunk in-memory for {file_path.name} at adjusted line {current_hunk_start_line+1}: {e}"
             logger.exception(msg)
             return ApplyReport(file_path=file_path, status="failed_write", message=f"Internal error during patching: {e}")

        line_offset += (num_added - num_deleted)
        total_lines_applied += (num_added + num_deleted)

    # --- 7. Backup ---
    backup_path: Optional[Path] = None
    if not is_new_file:
        try:
            rel_path = file_path.relative_to(project_root)
            backup_dir = project_root / "backups"
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            backup_target_dir = backup_dir / rel_path.parent
            backup_path = backup_target_dir / f"{file_path.stem}_{timestamp}{file_path.suffix}"
            backup_target_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, backup_path)
            try:
                log_rel_path = backup_path.relative_to(project_root)
                logger.info(f"Created backup: backups/{log_rel_path}")
            except ValueError:
                logger.info(f"Created backup: {backup_path}")
        except OSError as e:
            msg = f"Failed to create backup for {file_path.name}: {e}"
            logger.error(msg)
            return ApplyReport(file_path=file_path, status="failed_backup", message=msg)
        except Exception as e:
            msg = f"Unexpected error creating backup for {file_path.name}: {e}"
            logger.exception(msg)
            return ApplyReport(file_path=file_path, status="failed_backup", message=msg)

    # --- 8. Pre-write Checksum Re-check ---
    if not is_new_file:
        stored_initial_sha1 = temp_checksums.get(file_path)
        if stored_initial_sha1:
            current_sha1 = _calculate_sha1(file_path)
            if current_sha1 is None:
                msg = f"Failed to calculate current checksum for {file_path.name} before writing. Aborting apply."
                logger.error(msg)
                return ApplyReport(file_path=file_path, status="failed_read", message=msg)
            if current_sha1 != stored_initial_sha1:
                backup_msg_part = f" Backup was created at {backup_path}." if backup_path and backup_path.exists() else ""
                msg = f"Skipping apply for {file_path.name}: File was modified externally since preview.{backup_msg_part}"
                logger.warning(msg)
                logger.debug(f"  Initial SHA1: {stored_initial_sha1}")
                logger.debug(f"  Current SHA1: {current_sha1}")
                return ApplyReport(file_path=file_path, status="skipped_external_change", message=msg)
            logger.debug(f"Pre-write checksum matches initial SHA1 for {file_path.name}.")
        else:
             logger.error(f"Internal error: Initial checksum not found in temp storage for {file_path.name}. Cannot verify external changes.")
             return ApplyReport(file_path=file_path, status="failed_read", message="Internal error: Missing initial checksum for verification.")

    # --- 9. Atomic Write ---
    temp_file_path: Optional[Path] = None
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        temp_file_name = f".{file_path.name}.pb_tmp"
        temp_file_path = file_path.with_name(temp_file_name)
        newline_char = '\n'
        if not is_new_file and original_content and any('\r\n' in line for line in original_content):
             newline_char = '\r\n'
             logger.trace(f"Detected CRLF line endings for {file_path.name}")
        with open(temp_file_path, 'w', encoding='utf-8', newline=newline_char) as temp_f:
            output_content = newline_char.join(modified_content)
            # Ensure final newline unless file was completely empty
            if output_content or modified_content == ['']:
                 output_content += newline_char
            temp_f.write(output_content)
            temp_f.flush()
            os.fsync(temp_f.fileno())
        os.replace(temp_file_path, file_path)
        # --- FIX: Wrap relative_to in try-except for logging ---
        try:
            log_write_path_str = str(file_path.relative_to(project_root))
        except ValueError:
            log_write_path_str = str(file_path)
        logger.info(f"Successfully applied changes and wrote to: {log_write_path_str}")
        # --- END FIX ---
        temp_file_path = None
        return ApplyReport(
            file_path=file_path,
            status="ok",
            message="Changes applied successfully.",
            lines_applied=total_lines_applied
        )
    except OSError as e:
        msg = f"Failed to write changes to {file_path.name}: {e}"
        logger.exception(msg)
        # --- FIX: Guard backup deletion and use missing_ok=True ---
        if backup_path and backup_path.exists():
            logger.warning(f"Attempting to remove backup {backup_path} due to write failure.")
            try: backup_path.unlink(missing_ok=True)
            except OSError as unlink_err: logger.error(f"Failed to remove backup {backup_path}: {unlink_err}")
        # --- END FIX ---
        return ApplyReport(file_path=file_path, status="failed_write", message=msg)
    except Exception as e:
        msg = f"Unexpected error writing changes to {file_path.name}: {e}"
        logger.exception(msg)
        # --- FIX: Guard backup deletion and use missing_ok=True ---
        if backup_path and backup_path.exists():
            logger.warning(f"Attempting to remove backup {backup_path} due to unexpected write error.")
            try: backup_path.unlink(missing_ok=True)
            except OSError as unlink_err: logger.error(f"Failed to remove backup {backup_path}: {unlink_err}")
        # --- END FIX ---
        return ApplyReport(file_path=file_path, status="failed_write", message=msg)
    finally:
        if temp_file_path and temp_file_path.exists():
            logger.warning(f"Cleaning up leftover temporary file: {temp_file_path}")
            try:
                temp_file_path.unlink(missing_ok=True) # Use missing_ok
            except OSError as unlink_err:
                logger.error(f"Failed to remove temporary file {temp_file_path} in finally: {unlink_err}")


def prune_backups(backups_root: Path, days: int):
    """Removes backup files older than the specified number of days."""
    if not backups_root.is_dir() or days <= 0:
        if days <= 0: logger.debug("Backup pruning skipped: retention days <= 0.")
        else: logger.debug(f"Backup pruning skipped: Directory not found: {backups_root}")
        return

    cutoff_time = time.time() - (days * 86400)
    pruned_count = 0
    error_count = 0
    logger.info(f"Pruning backups older than {days} days in: {backups_root} (Cutoff: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(cutoff_time))})")

    try:
        # Iterate safely, handling potential race conditions if files are deleted during iteration
        paths_to_check = list(backups_root.rglob("*"))
        for item in paths_to_check:
            try:
                if not item.exists(): continue # Skip if deleted during iteration

                if item.is_file():
                    mod_time = item.stat().st_mtime
                    if mod_time < cutoff_time:
                        try:
                            log_path = item.relative_to(backups_root.parent)
                        except ValueError:
                            log_path = item
                        logger.trace(f"Pruning old backup: {log_path} (Modified: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mod_time))})")
                        item.unlink(missing_ok=True)
                        pruned_count += 1
                elif item.is_dir():
                     # Check if directory is empty after potential file deletions
                     # Use try-except in case of permission errors during iteration
                     try:
                         is_empty = not any(item.iterdir())
                         if is_empty:
                             logger.trace(f"Removing empty backup directory: {item}")
                             item.rmdir() # rmdir fails if not empty
                     except OSError as dir_err:
                          logger.warning(f"Could not check/remove backup directory {item}: {dir_err}")
                          error_count += 1


            except OSError as e:
                logger.warning(f"Could not process backup item {item}: {e}")
                error_count += 1
            except Exception as e:
                 logger.exception(f"Unexpected error processing backup item {item}: {e}")
                 error_count += 1
    except Exception as e:
        logger.exception(f"Error during backup pruning process in {backups_root}: {e}")
        error_count += 1

    if pruned_count > 0 or error_count > 0:
        logger.info(f"Backup pruning finished. Pruned: {pruned_count} files. Errors: {error_count}.")
    else:
        logger.debug("Backup pruning finished. No old backups found or errors encountered.")
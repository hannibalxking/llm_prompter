# promptbuilder/core/matcher.py

import difflib
import re
from typing import List, Optional, Tuple

from loguru import logger

from .models import DiffHunk

_whitespace_pattern = re.compile(r'\s+')

def _normalize_line(line: str) -> str:
    """
    Normalizes a line for fuzzy comparison.
    Strips leading/trailing whitespace and collapses internal whitespace sequences to single spaces.
    """
    return _whitespace_pattern.sub(' ', line.strip())

def _extract_original_lines(hunk: DiffHunk) -> List[str]:
    """Extracts the original content lines from a hunk."""
    original_lines = []
    original_lines.extend(hunk.context_before)
    for line in hunk.hunk_lines:
        # Include original line for '-' and context ' ' lines
        if line.startswith('-') and not line.startswith('---'):
            original_lines.append(line[1:])
        elif line.startswith(' ') or not line.startswith('+'):
             # Handle lines that might not start with space but aren't '+' (e.g., '\ No newline at end of file')
             original_lines.append(line[1:] if line.startswith(' ') else line)
    original_lines.extend(hunk.context_after)
    return original_lines

def locate_hunk(
        file_lines: List[str],
        hunk: DiffHunk,
        max_distance: float = 0.05
) -> Optional[int]:
    """
    Finds the best starting line index for a DiffHunk within file content.
    Uses SequenceMatcher for fuzzy matching and includes a fast-path search.
    """
    if not file_lines and not hunk.context_before and not hunk.context_after and \
       all(line.startswith('+') for line in hunk.hunk_lines):
        logger.debug(f"Treating hunk for {hunk.path.name} as new file addition (empty file, no context/deletions).")
        return 0 # Match at the beginning of an empty file if it's pure addition

    if not file_lines and (hunk.context_before or hunk.context_after or any(line.startswith('-') or line.startswith(' ') for line in hunk.hunk_lines)):
        logger.warning(f"Cannot locate hunk in empty file when context or original lines exist: {hunk.path.name}")
        return None

    original_hunk_lines = _extract_original_lines(hunk)
    if not original_hunk_lines:
        # If it's a pure addition hunk (no context, no deletions), it should match at line 0 if file is empty,
        # otherwise it's hard to place without context. For now, return None if file isn't empty.
        if not file_lines and all(line.startswith('+') for line in hunk.hunk_lines):
             logger.debug(f"Pure addition hunk matching at start of empty file: {hunk.path.name}")
             return 0
        logger.warning(f"Hunk for {hunk.path.name} has no original lines (context/deletion) to match against in non-empty file.")
        return None

    hunk_len = len(original_hunk_lines)
    file_len = len(file_lines)

    if hunk_len > file_len:
        logger.warning(f"Hunk length ({hunk_len}) > file length ({file_len}) for {hunk.path.name}.")
        return None

    # --- Refinement: Cache normalized needle ---
    normalized_hunk_needle = [_normalize_line(line) for line in original_hunk_lines]
    # --- End Refinement ---

    matcher = difflib.SequenceMatcher(None, [], autojunk=False)
    matcher.set_seq2(normalized_hunk_needle)

    best_ratio = 0.0
    best_match_index: Optional[int] = None
    ambiguous = False

    # Fast-path search: Find potential start indices based on the first non-empty, non-context line
    first_search_line_content = None
    first_search_line_hunk_index = -1
    context_before_len = len(hunk.context_before)
    for idx, line in enumerate(original_hunk_lines[context_before_len:]):
        stripped_line = line.strip()
        if stripped_line:
            first_search_line_content = stripped_line
            first_search_line_hunk_index = context_before_len + idx
            break

    potential_starts = range(file_len - hunk_len + 1)
    if first_search_line_content and first_search_line_hunk_index != -1:
        try:
            # Find all occurrences of the first significant line's content (case-sensitive for now)
            found_indices = [i for i, file_line in enumerate(file_lines) if first_search_line_content in file_line]
            adjusted_starts = [idx - first_search_line_hunk_index for idx in found_indices]
            valid_starts = {
                start for start in adjusted_starts
                if 0 <= start <= file_len - hunk_len
            }
            if valid_starts:
                potential_starts = sorted(list(valid_starts))
                logger.trace(f"Fast-path search found {len(potential_starts)} potential start(s) for hunk in {hunk.path.name}")
            else:
                 logger.trace(f"Fast-path search found no potential starts for hunk in {hunk.path.name}, proceeding with full scan.")
                 potential_starts = range(file_len - hunk_len + 1)
        except Exception as e:
            logger.warning(f"Error during fast-path search for {hunk.path.name}: {e}. Falling back to full scan.")
            potential_starts = range(file_len - hunk_len + 1)

    # Sliding Window Comparison using potential_starts
    for i in potential_starts:
        window_lines = file_lines[i : i + hunk_len]
        normalized_window = [_normalize_line(line) for line in window_lines]

        matcher.set_seq1(normalized_window)
        ratio = matcher.ratio()

        required_ratio = 1.0 - max_distance
        epsilon = 1e-9
        if ratio >= required_ratio - epsilon:
            is_better = ratio > best_ratio + epsilon
            is_equal = abs(ratio - best_ratio) < epsilon

            if is_better:
                best_ratio = ratio
                best_match_index = i
                ambiguous = False
            elif is_equal and best_match_index != i:
                ambiguous = True
                logger.warning(f"Ambiguous match detected for hunk in {hunk.path.name} at lines {best_match_index+1} and {i+1} (Ratio: {ratio:.4f}).")

    if ambiguous:
        logger.error(f"Hunk matching failed for {hunk.path.name}: Ambiguous matches found with best ratio {best_ratio:.4f}.")
        return None

    if best_match_index is not None:
        logger.debug(f"Best match found for hunk in {hunk.path.name} at line {best_match_index+1} (Ratio: {best_ratio:.4f})")
        return best_match_index
    else:
        logger.warning(f"No suitable match found for hunk in {hunk.path.name} (Required ratio >= {1.0 - max_distance:.4f}, Best found: {best_ratio:.4f})")
        return None
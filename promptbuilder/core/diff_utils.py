# promptbuilder/core/diff_utils.py

from typing import List, Tuple

def calculate_hunk_line_changes(hunk_lines: List[str]) -> Tuple[int, int]:
    """
    Parses hunk lines (+/-/space) to count added/deleted lines.

    Args:
        hunk_lines: List of strings representing the hunk body lines.

    Returns:
        Tuple[int, int]: Number of added lines, number of deleted lines.
    """
    added = 0
    deleted = 0
    if not hunk_lines:
        return 0, 0
    for line in hunk_lines:
        # Count lines starting with '+' or '-' but not '+++' or '---'
        # Ensure line is not empty before checking index 0
        if line and line.startswith('+') and not line.startswith('+++'):
            added += 1
        elif line and line.startswith('-') and not line.startswith('---'):
            deleted += 1
    return added, deleted

def calculate_diff_text_line_changes(diff_text: str) -> Tuple[int, int]:
    """
    Parses standard unified diff text to count added/deleted lines.

    Args:
        diff_text: The full unified diff text.

    Returns:
        Tuple[int, int]: Number of added lines, number of deleted lines.
    """
    added = 0
    deleted = 0
    if not diff_text:
        return 0, 0
    for line in diff_text.splitlines():
        # Ensure line is not empty before checking index 0
        if line and line.startswith('+') and not line.startswith('+++'):
            added += 1
        elif line and line.startswith('-') and not line.startswith('---'):
            deleted += 1
    return added, deleted
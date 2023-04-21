# promptbuilder/ui/utils/diff_formatter.py

import html
import re
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from functools import lru_cache

from loguru import logger

from ...core.models import DiffSuggestion, DiffHunk, DiffBase

_artifact_line_pattern = re.compile(r"^(python|bash|csharp|javascript|typescript|html|css|scss|sql|pgsql|json|xml|yaml|dockerfile|makefile|nginx|arduino|vbnet|Copy)\s*$", re.IGNORECASE)

@lru_cache(maxsize=10)
def _read_file_content_cached(file_path: Path, mod_time: float) -> Tuple[Optional[List[str]], Optional[str]]:
    """Reads file content, caching based on path and modification time."""
    try:
        content = file_path.read_text(encoding='utf-8', errors='replace').splitlines()
        return content, None
    except FileNotFoundError:
        logger.error(f"File not found for preview: {file_path}")
        return None, f"Error: File not found at {html.escape(str(file_path))}."
    except OSError as e:
        logger.error(f"Error reading file for preview {file_path}: {e}")
        return None, f"Error reading file: {html.escape(str(e))}."
    except Exception as e:
        logger.exception(f"Unexpected error reading file for preview {file_path}: {e}")
        return None, f"Unexpected error reading file: {html.escape(str(e))}."

def generate_hunk_preview_html(hunk: DiffHunk, project_root: Path) -> str:
    """
    Generates an HTML representation of the full file content, highlighting
    the specified DiffHunk's location and changes. Uses cached file reads.
    """
    html_lines = ['<pre>']
    target_file = hunk.path

    if hunk.status == 'unmatched' or hunk.first_target_line is None:
        logger.warning(f"Generating preview for explicitly unmatched hunk: {hunk.rel_path}")
        html_lines.append('<span class="error-message">⚠️ Hunk could not be located in the file.</span>')
        html_lines.append('<span class="error-message">   The file content might have changed significantly.</span>')
        html_lines.append('<span class="error-message">   Applying this change is disabled.</span>')
        html_lines.append("</pre>")
        return "\n".join(html_lines)

    is_new_file = not target_file.exists()
    if is_new_file:
        if not any(line.startswith('-') for line in hunk.hunk_lines):
            logger.info(f"Previewing new file creation for: {hunk.rel_path}")
            html_lines.append('<span class="diff-header">--- New File ---</span>')
            added_lines = [line[1:] for line in hunk.hunk_lines if line.startswith('+')]
            for line_content in added_lines:
                safe_line = html.escape(line_content) if line_content else " "
                html_lines.append(f'<span class="hunk-added">{safe_line}</span>')
            html_lines.append("</pre>")
            return "\n".join(html_lines)
        else:
            logger.error(f"Cannot preview: File {target_file} does not exist, but hunk contains deletions.")
            html_lines.append(f'<span class="error-message">Error: File not found at {html.escape(str(target_file))}, but hunk contains deletions.</span>')
            html_lines.append("</pre>")
            return "\n".join(html_lines)

    try:
        mod_time = target_file.stat().st_mtime
        file_content_lines, read_error = _read_file_content_cached(target_file, mod_time)
        if read_error:
            html_lines.append(f'<span class="error-message">{read_error}</span>')
            html_lines.append("</pre>")
            return "\n".join(html_lines)
        # --- FIX: Add assertion ---
        assert file_content_lines is not None, "File content lines should not be None if read_error is None"
        # --- END FIX ---
    except OSError as e:
         logger.error(f"Error stating file {target_file} for preview: {e}")
         html_lines.append(f'<span class="error-message">Error accessing file stats: {html.escape(str(e))}.</span>')
         html_lines.append("</pre>")
         return "\n".join(html_lines)
    except Exception as e:
         logger.exception(f"Unexpected error preparing file read for {target_file}: {e}")
         html_lines.append(f'<span class="error-message">Unexpected error preparing preview: {html.escape(str(e))}.</span>')
         html_lines.append("</pre>")
         return "\n".join(html_lines)

    # Highlighting Logic
    hunk_start_line_idx = hunk.first_target_line # Already checked for None
    context_before_len = len(hunk.context_before)
    context_after_len = len(hunk.context_after)
    file_line_iter = enumerate(file_content_lines)
    hunk_line_iter = iter(hunk.hunk_lines)
    current_file_idx = 0

    while True:
        try:
            current_file_idx, current_file_line = next(file_line_iter)
            safe_file_line = html.escape(current_file_line) if current_file_line else " "

            num_original_lines_in_hunk_body = sum(1 for hl in hunk.hunk_lines if hl.startswith(' ') or hl.startswith('-'))
            change_block_end_idx = hunk_start_line_idx + context_before_len + num_original_lines_in_hunk_body

            is_in_context_before = hunk_start_line_idx <= current_file_idx < hunk_start_line_idx + context_before_len
            is_in_change_block = hunk_start_line_idx + context_before_len <= current_file_idx < change_block_end_idx
            is_in_context_after = change_block_end_idx <= current_file_idx < change_block_end_idx + context_after_len

            if is_in_context_before:
                html_lines.append(f'<span class="hunk-context-before">{safe_file_line}</span>')
            elif is_in_context_after:
                html_lines.append(f'<span class="hunk-context-after">{safe_file_line}</span>')
            elif is_in_change_block:
                processed_this_file_line = False
                while not processed_this_file_line:
                    try:
                        hunk_line = next(hunk_line_iter)
                        if hunk_line.startswith('-'):
                            safe_hunk_line = html.escape(hunk_line[1:]) if hunk_line[1:] else " "
                            html_lines.append(f'<span class="hunk-deleted">{safe_hunk_line}</span>')
                        elif hunk_line.startswith('+'):
                            safe_hunk_line = html.escape(hunk_line[1:]) if hunk_line[1:] else " "
                            html_lines.append(f'<span class="hunk-added">{safe_hunk_line}</span>')
                        elif hunk_line.startswith(' '):
                            html_lines.append(f'<span class="hunk-context-hunk">{safe_file_line}</span>')
                            processed_this_file_line = True
                        else:
                             safe_hunk_line = html.escape(hunk_line) if hunk_line else " "
                             html_lines.append(f'<span class="diff-header">{safe_hunk_line}</span>')
                    except StopIteration:
                        logger.warning(f"Ran out of hunk lines while processing change block for {hunk.rel_path} at file line {current_file_idx+1}")
                        html_lines.append(f'<span class="file-context error-message">[Error: Hunk shorter than expected file section] {safe_file_line}</span>')
                        processed_this_file_line = True
            else:
                html_lines.append(f'<span class="file-context">{safe_file_line}</span>')

        except StopIteration:
            break

    try:
        while True:
            hunk_line = next(hunk_line_iter)
            if hunk_line.startswith('+'):
                safe_hunk_line = html.escape(hunk_line[1:]) if hunk_line[1:] else " "
                html_lines.append(f'<span class="hunk-added">{safe_hunk_line}</span>')
            elif hunk_line.strip():
                 logger.warning(f"Unexpected trailing line in hunk for {hunk.rel_path}: {hunk_line}")
    except StopIteration:
        pass

    html_lines.append("</pre>")
    return "\n".join(html_lines)


def generate_legacy_diff_html(suggestion: DiffSuggestion) -> str:
    """Generates an HTML representation of the diff text from a legacy suggestion."""
    # (This function remains unchanged)
    diff_text = suggestion.diff_text
    html_lines = ['<pre>']
    if not diff_text:
        if suggestion.proposed_content:
            return "<pre>New file suggestion (no diff).</pre>"
        else:
            return "<pre>No diff information provided.</pre>"
    has_markers = re.search(r"^(--- a/|\+\+\+ b/|@@ |[+\- ] )", diff_text, re.MULTILINE) is not None
    has_newlines = "\n" in diff_text.strip()
    if has_markers and not has_newlines:
        logger.error("Legacy diff text is malformed: Missing newlines.")
        html_lines.append('<span class="error-message">Error: Cannot display diff.</span>')
        html_lines.append('<span class="error-message">Legacy diff text missing newlines.</span>')
        html_lines.append("</pre>")
        return "\n".join(html_lines)
    diff_lines = diff_text.splitlines()
    for line in diff_lines:
        if _artifact_line_pattern.match(line):
            continue
        safe_line = html.escape(line) if line else " "
        if line.startswith('+') and not line.startswith('+++'):
            html_lines.append(f'<span class="diff-add">{safe_line}</span>')
        elif line.startswith('-') and not line.startswith('---'):
            html_lines.append(f'<span class="diff-del">{safe_line}</span>')
        elif line.startswith('@@') or line.startswith('---') or line.startswith('+++'):
            html_lines.append(f'<span class="diff-header">{safe_line}</span>')
        else:
            html_lines.append(f'<span class="diff-context">{safe_line}</span>')
    html_lines.append("</pre>")
    return "\n".join(html_lines)


def generate_diff_html(suggestion: Optional[DiffBase], project_root: Optional[Path] = None) -> str:
    """
    Generates an HTML representation for a DiffBase object (Hunk or Suggestion).
    """
    if not suggestion:
        return "<pre>No suggestion selected.</pre>"

    if isinstance(suggestion, DiffHunk):
        if not project_root:
             logger.error("Project root is required to generate preview for DiffHunk.")
             return '<pre><span class="error-message">Error: Project root not available for preview.</span></pre>'
        html_content = generate_hunk_preview_html(suggestion, project_root)
        return html_content
    elif isinstance(suggestion, DiffSuggestion):
        return generate_legacy_diff_html(suggestion)
    else:
        logger.error(f"Unsupported suggestion type for preview: {type(suggestion)}")
        return '<pre><span class="error-message">Error: Unsupported suggestion type.</span></pre>'
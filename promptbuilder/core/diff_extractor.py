# promptbuilder/core/diff_extractor.py

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple, Union
import re
import json
import warnings

from loguru import logger

from .models import DiffSuggestion, DiffHunk, DiffBase # Import DiffBase
from .diff_utils import calculate_hunk_line_changes, calculate_diff_text_line_changes

class DiffParseError(Exception):
    """Custom exception for errors during diff parsing."""
    pass

# --- XML Parsing Helper (Handles Legacy DiffSuggestion only) ---
def _parse_xml_diffs(text: str, project_root: Path) -> List[DiffSuggestion]:
    """Parses legacy XML formatted diff/content blocks using ElementTree."""
    logger.warning("Parsing legacy XML format (DiffSuggestion).")
    suggestions_map: Dict[Path, DiffSuggestion] = {}
    logger.debug("Attempting legacy XML parsing...")
    try:
        parser = ET.XMLParser(target=ET.TreeBuilder())
        parser.feed(f"<root>{text}</root>")
        root = parser.close()
    except ET.ParseError as e:
        context_lines = 10
        error_line = e.position[0]
        lines = text.splitlines()
        start = max(0, error_line - context_lines)
        end = min(len(lines), error_line + context_lines)
        context_snippet = "\n".join(f"{i+1:4d}: {line}" for i, line in enumerate(lines[start:end]))
        logger.error(f"XML parsing failed: {e}\nContext around line {error_line}:\n{context_snippet}")
        raise DiffParseError(f"Invalid XML structure detected: {e}") from e
    proposed_content_map: Dict[str, str] = {}
    for content_el in root.iter("proposed_content"):
        rel_path_str = content_el.attrib.get("file")
        content_text = (content_el.text or "").strip()
        if rel_path_str:
            rel_path_norm = rel_path_str.replace('\\', '/')
            proposed_content_map[rel_path_norm] = content_text
        else:
            logger.warning("Found <proposed_content> tag without 'file' attribute. Skipping.")
    for diff_el in root.iter("diff"):
        rel_path_str = diff_el.attrib.get("file")
        diff_text = (diff_el.text or "").strip()
        if not rel_path_str:
            logger.warning("Found <diff> tag without 'file' attribute. Skipping.")
            continue
        rel_path_norm = rel_path_str.replace('\\', '/')
        try:
            abs_path = project_root.joinpath(rel_path_norm).resolve()
            abs_path.relative_to(project_root)
        except Exception as e:
            logger.warning(f"Could not resolve path '{rel_path_str}' (XML): {e}. Skipping.")
            continue
        lines_added, lines_deleted = calculate_diff_text_line_changes(diff_text)
        proposed_content = proposed_content_map.pop(rel_path_norm, None)
        suggestions_map[abs_path] = DiffSuggestion(
            path=abs_path, rel_path=rel_path_str, diff_text=diff_text,
            proposed_content=proposed_content, lines_added=lines_added,
            lines_deleted=lines_deleted, status='pending'
        )
    for rel_path_norm, proposed_content in proposed_content_map.items():
        try:
            abs_path = project_root.joinpath(rel_path_norm).resolve()
            if not str(abs_path).startswith(str(project_root)):
                 raise ValueError("Resolved path is outside project root")
        except Exception as e:
            logger.warning(f"Could not resolve path '{rel_path_norm}' (XML New File): {e}. Skipping.")
            continue
        if abs_path in suggestions_map: continue
        suggestions_map[abs_path] = DiffSuggestion(
            path=abs_path, rel_path=rel_path_norm, diff_text="",
            proposed_content=proposed_content, lines_added=0, lines_deleted=0,
            status='pending'
        )
        logger.info(f"Created suggestion for NEW file (Legacy XML): {rel_path_norm}")
    return list(suggestions_map.values())

# --- JSON Parsing Helper (Handles NEW DiffHunk format) ---
def _parse_json_hunks(text: str, project_root: Path) -> List[DiffHunk]:
    """Parses JSON formatted hunks (single object or array)."""
    hunks: List[DiffHunk] = []
    logger.debug("Attempting JSON Hunk parsing...")
    json_block_match = re.search(r"```json\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if json_block_match:
        json_str = json_block_match.group(1).strip()
        logger.debug("Found JSON block wrapped in markdown.")
    else:
        # Try to find the first '{' or '[' and the last '}' or ']'
        json_start_obj = text.find('{')
        json_start_arr = text.find('[')
        json_end_obj = text.rfind('}')
        json_end_arr = text.rfind(']')

        start_index, end_index = -1, -1
        is_likely_array = json_start_arr != -1 and json_end_arr != -1 and json_end_arr > json_start_arr
        is_likely_object = json_start_obj != -1 and json_end_obj != -1 and json_end_obj > json_start_obj

        # Prefer array if both seem possible and array starts earlier or is valid
        if is_likely_array and is_likely_object:
            if json_start_arr <= json_start_obj:
                start_index, end_index = json_start_arr, json_end_arr
            else:
                 # Check if object is actually inside an array structure
                 temp_str = text[json_start_arr : json_end_arr + 1] if is_likely_array else ""
                 if json_start_obj > json_start_arr and json_end_obj < json_end_arr and temp_str:
                      start_index, end_index = json_start_arr, json_end_arr
                 else:
                      start_index, end_index = json_start_obj, json_end_obj
        elif is_likely_array:
            start_index, end_index = json_start_arr, json_end_arr
        elif is_likely_object:
             start_index, end_index = json_start_obj, json_end_obj

        if start_index != -1:
             json_str = text[start_index : end_index + 1]
             logger.debug("Attempting to parse text segment as JSON object or array.")
        else:
             # If no structure found, maybe it's just a single object without wrapping?
             # This is less robust, but handles the single-object paste case better.
             if is_likely_object:
                 json_str = text.strip() # Assume the whole thing might be the object
                 logger.debug("No clear array/object bounds, trying to parse entire input as single JSON object.")
             else:
                 raise DiffParseError("Could not find JSON object '{}' or array '[]' structure in the text.")

    try:
        data = json.loads(json_str)
        items_to_process = []
        # --- FIX: Handle single object parsing ---
        if isinstance(data, dict):
            logger.debug("Parsing as single JSON Hunk object.")
            items_to_process.append(data)
        # --- END FIX ---
        elif isinstance(data, list):
            logger.debug("Parsing as JSON Hunk array.")
            items_to_process = data
        else:
            raise DiffParseError("JSON root is not an object or an array.")

        for item in items_to_process:
            if not isinstance(item, dict):
                logger.warning(f"Skipping non-dictionary item in JSON: {item}")
                continue

            rel_path_str = item.get("file")
            hunk_lines = item.get("hunk") or item.get("hunk_lines")
            context_before = item.get("context_before")
            context_after = item.get("context_after")

            if not rel_path_str or not isinstance(rel_path_str, str):
                logger.warning(f"Skipping JSON item due to missing/invalid 'file': {item}")
                continue
            if not isinstance(hunk_lines, list) or not all(isinstance(line, str) for line in hunk_lines):
                 logger.warning(f"Skipping JSON item for '{rel_path_str}' due to invalid 'hunk'/'hunk_lines' (must be list of strings): {item}")
                 continue

            context_before_lines = []
            if isinstance(context_before, list) and all(isinstance(line, str) for line in context_before):
                 context_before_lines = context_before
            elif isinstance(context_before, int):
                 logger.trace(f"Integer 'context_before' ({context_before}) ignored for '{rel_path_str}'.")
            elif context_before is not None:
                 logger.warning(f"Invalid 'context_before' type for '{rel_path_str}', treating as empty.")

            context_after_lines = []
            if isinstance(context_after, list) and all(isinstance(line, str) for line in context_after):
                 context_after_lines = context_after
            elif isinstance(context_after, int):
                 logger.trace(f"Integer 'context_after' ({context_after}) ignored for '{rel_path_str}'.")
            elif context_after is not None:
                 logger.warning(f"Invalid 'context_after' type for '{rel_path_str}', treating as empty.")

            try:
                rel_path_norm = rel_path_str.replace('\\', '/')
                abs_path = project_root.joinpath(rel_path_norm).resolve()
            except Exception as e:
                logger.warning(f"Could not resolve path '{rel_path_str}' (JSON Hunk): {e}. Skipping.")
                continue

            lines_added, lines_deleted = calculate_hunk_line_changes(hunk_lines)

            hunks.append(DiffHunk(
                path=abs_path, rel_path=rel_path_str, hunk_lines=hunk_lines,
                context_before=context_before_lines, context_after=context_after_lines,
                status='pending', first_target_line=None,
                lines_added=lines_added, lines_deleted=lines_deleted
            ))
            logger.debug(f"Extracted JSON Hunk for: {rel_path_str} (+{lines_added}/-{lines_deleted})")

    except json.JSONDecodeError as e:
        raise DiffParseError(f"Invalid JSON detected: {e}") from e
    except Exception as e:
        logger.exception(f"Unexpected error during JSON Hunk parsing: {e}")
        raise DiffParseError(f"Unexpected error during JSON Hunk parsing: {e}") from e

    return hunks

# --- Markdown Parsing Helper (Handles Legacy DiffSuggestion only) ---
def _parse_markdown_diffs(text: str, project_root: Path) -> List[DiffSuggestion]:
    """Parses legacy Markdown formatted diff/content blocks."""
    logger.warning("Parsing legacy Markdown format (DiffSuggestion).")
    suggestions_map: Dict[Path, DiffSuggestion] = {}
    logger.debug("Attempting legacy Markdown parsing...")
    diff_block_pattern = re.compile(r'^```diff\s+file=(["\'])(.*?)\1\s*?\n([\s\S]*?)\n```', re.MULTILINE)
    content_block_pattern = re.compile(r'^```(?:python|[\w-]+)\s+file=(["\'])(.*?)\1\s+type="proposed"\s*?\n([\s\S]*?)\n```', re.MULTILINE | re.IGNORECASE)
    for match in diff_block_pattern.finditer(text):
        rel_path_str = match.group(2)
        diff_text = match.group(3).strip()
        if not rel_path_str: continue
        try:
            rel_path_norm = rel_path_str.replace('\\', '/')
            abs_path = project_root.joinpath(rel_path_norm).resolve()
            abs_path.relative_to(project_root)
        except Exception as e:
            logger.warning(f"Could not resolve path '{rel_path_str}' (MD Diff): {e}. Skipping.")
            continue
        lines_added, lines_deleted = calculate_diff_text_line_changes(diff_text)
        suggestions_map[abs_path] = DiffSuggestion(
            path=abs_path, rel_path=rel_path_str, diff_text=diff_text,
            lines_added=lines_added, lines_deleted=lines_deleted,
            proposed_content=None, status='pending'
        )
    for match in content_block_pattern.finditer(text):
        rel_path_str = match.group(2)
        proposed_content = match.group(3).strip()
        if not rel_path_str: continue
        try:
            rel_path_norm = rel_path_str.replace('\\', '/')
            abs_path = project_root.joinpath(rel_path_norm).resolve()
        except Exception as e:
            logger.warning(f"Could not resolve path '{rel_path_str}' (MD Proposed Content): {e}. Skipping.")
            continue
        if abs_path in suggestions_map:
            suggestions_map[abs_path].proposed_content = proposed_content
        else:
            logger.info(f"Found MD proposed content for '{rel_path_str}' without diff block. Treating as NEW file (Legacy MD).")
            suggestions_map[abs_path] = DiffSuggestion(
                path=abs_path, rel_path=rel_path_str, diff_text="",
                proposed_content=proposed_content, lines_added=0, lines_deleted=0,
                status='pending'
            )
    return list(suggestions_map.values())

# --- Main Extractor Function ---
def extract_suggestions(text: str, project_root: Path) -> List[DiffBase]:
    """
    Detects the format (JSON Hunk, Legacy XML, Legacy Markdown) and extracts diffs.

    Args:
        text: The raw text input (likely from LLM).
        project_root: The absolute path to the project's root directory.

    Returns:
        A list of DiffHunk or DiffSuggestion objects (as DiffBase).

    Raises:
        DiffParseError: If parsing fails for the detected format.
    """
    if not text or not text.strip():
        return []
    stripped_text = text.strip()
    detected_format = "unknown"
    parser = None
    is_legacy = False
    suggestions: List[DiffBase] = []

    # --- JSON Hunk Detection (Priority) ---
    looks_like_json = (stripped_text.startswith('{') and stripped_text.endswith('}')) or \
                      (stripped_text.startswith('[') and stripped_text.endswith(']')) or \
                      ("```json" in text)

    if looks_like_json:
        try:
            suggestions = _parse_json_hunks(text, project_root)
            if suggestions:
                logger.info(f"Successfully parsed JSON Hunk format.")
                return suggestions # Return immediately if JSON Hunk parsing succeeds
            else:
                logger.debug("Parsed as JSON but found no valid hunks, falling back.")
        except DiffParseError as json_err:
            logger.debug(f"JSON Hunk parsing failed ({json_err}), falling back.")
        except Exception as json_ex:
            logger.debug(f"Unexpected error during JSON Hunk parsing ({json_ex}), falling back.")

    # --- Fallback to Legacy Format Detection ---
    if '<diff file=' in stripped_text or '<proposed_content file=' in stripped_text:
        logger.info("Detected potential legacy XML format.")
        parser = _parse_xml_diffs
        detected_format = "Legacy XML"
        is_legacy = True
    elif '```diff file=' in stripped_text and 'type="proposed"' in stripped_text:
        logger.info("Detected potential legacy Markdown format.")
        parser = _parse_markdown_diffs
        detected_format = "Legacy Markdown"
        is_legacy = True
    # TODO: Add detection for new Markdown Hunk format here if implemented

    if parser is None:
        # If no format was detected after trying JSON, return empty
        if not suggestions: # Ensure we didn't get an empty list from a failed JSON parse
             logger.warning("Could not detect known diff format (JSON Hunk, Legacy XML, Legacy Markdown). No suggestions extracted.")
        return []

    if is_legacy:
        warnings.warn(
            f"{detected_format} format is considered legacy and will be removed in v0.3.0+. Use JSON Hunk format.",
            DeprecationWarning,
            stacklevel=2
        )

    try:
        # We know parser is not None here
        suggestions = parser(text, project_root) # type: ignore
        if not suggestions:
             logger.warning(f"Parser for detected format ({detected_format}) found no valid suggestions.")
        return suggestions
    except DiffParseError as e:
        # Re-raise specific parse errors from legacy parsers
        raise e
    except Exception as e:
        # Wrap unexpected parsing errors from legacy parsers
        logger.exception(f"Unexpected error during {detected_format} parsing.")
        raise DiffParseError(f"Unexpected error during {detected_format} parsing: {e}") from e
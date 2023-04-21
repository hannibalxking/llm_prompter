# promptbuilder/core/models.py

from __future__ import annotations # Allows using Literal without quotes

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Set, Literal, Protocol, runtime_checkable

from promptbuilder.config.schema import TabConfig


@dataclass
class FileNode:
    """Represents a file or directory in the scanned tree."""
    path: Path
    name: str
    is_dir: bool
    size: int = 0
    mod_time: float = 0.0
    tokens: int = 0
    children: List[FileNode] = field(default_factory=list)
    parent: Optional[FileNode] = None

    def __hash__(self):
        return hash(self.path)

    def __eq__(self, other):
        if not isinstance(other, FileNode):
            return NotImplemented
        return self.path == other.path

@dataclass
class PromptSnippet:
    """Represents a selected instruction snippet."""
    category: str
    name: str
    text: str

@dataclass
class ContextFile:
    """Represents a file included in the context."""
    path: Path
    content: str
    tokens: int
    status: str = "included"

@dataclass
class ContextResult:
    """Result of the context assembly process."""
    context_xml: str
    included_files: List[ContextFile]
    skipped_files: List[ContextFile]
    total_tokens: int
    budget_details: str

@dataclass
class ProjectState:
    """Represents the state of a single project tab."""
    id: str
    config: TabConfig
    root_node: Optional[FileNode] = None
    selected_files: Set[Path] = field(default_factory=set)
    selected_snippets: Dict[str, Dict[str, Optional[str]]] = field(default_factory=dict)
    selected_questions: Set[str] = field(default_factory=set)


@runtime_checkable
class DiffBase(Protocol):
    """Base protocol for different diff representations."""
    path: Path
    rel_path: str
    # --- FIX: Ensure status Literal includes all possible states ---
    status: Literal['pending', 'matched', 'unmatched', 'accepted', 'rejected']
    # --- END FIX ---
    lines_added: int
    lines_deleted: int


# Note: Marked as deprecated. Will be removed in v0.3.0+.
@dataclass
class DiffSuggestion(DiffBase):
    """
    Represents a single code change suggestion extracted from LLM output.
    (DEPRECATED: Use DiffHunk instead for new diff-only format)
    """
    path: Path
    rel_path: str
    diff_text: str
    proposed_content: Optional[str] = None
    # --- FIX: Ensure status Literal includes all possible states ---
    status: Literal['pending','accepted','rejected', 'matched', 'unmatched'] = 'pending'
    # --- END FIX ---
    lines_added: int = 0
    lines_deleted: int = 0

    def __hash__(self):
        return hash(self.path)

    def __eq__(self, other):
        if not isinstance(other, DiffSuggestion):
            return NotImplemented
        return self.path == other.path

@dataclass
class DiffHunk(DiffBase):
    """Represents a diff hunk with context lines for diff-only application."""
    path: Path
    rel_path: str
    hunk_lines: List[str]
    context_before: List[str]
    context_after: List[str]
    status: Literal[
        "pending", "matched", "unmatched",
        "accepted", "rejected"
    ] = "pending"
    first_target_line: Optional[int] = None # 0-based index where the hunk starts
    lines_added: int = 0 # Calculated from hunk_lines
    lines_deleted: int = 0 # Calculated from hunk_lines

    def __hash__(self):
        return hash(self.path)

    def __eq__(self, other):
        if not isinstance(other, DiffHunk):
            return NotImplemented
        return self.path == other.path

# ApplyReport is now defined in batch_editor.py and re-exported in core/__init__.py
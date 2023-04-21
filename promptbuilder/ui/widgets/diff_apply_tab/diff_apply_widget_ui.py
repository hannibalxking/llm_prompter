# promptbuilder/ui/widgets/diff_apply_tab/diff_apply_widget_ui.py

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase, QPalette, QColor # <-- FIX: Added QColor import
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
                               QListWidget, QTextBrowser, QPlainTextEdit,
                               QPushButton, QLabel, QComboBox)

if TYPE_CHECKING:
    from .diff_apply_widget import DiffApplyWidget

# --- Constants for CSS Styling ---
STYLE_SHEET = """
    pre {
        white-space: pre-wrap;
        background-color: transparent;
        word-wrap: break-word;
        font-family: "Consolas", "Courier New", monospace;
        padding: 5px;
        margin: 0;
        line-height: 1.2;
    }
    /* Legacy Diff Styles */
    .diff-add { color: #118811; background-color: #ddffdd; display: block; }
    .diff-del { color: #cc0000; background-color: #ffdddd; text-decoration: line-through; display: block; }
    .diff-header { color: #aaaaaa; font-weight: bold; display: block; }
    .diff-context { display: block; }
    /* New Hunk Preview Styles */
    .file-context { color: inherit; background-color: transparent; display: block; }
    .hunk-context-before, .hunk-context-after {
        color: #555555;
        background-color: #f0f0f0;
        display: block;
    }
    .hunk-context-hunk {
        color: #444444;
        background-color: #f8f8f8;
        display: block;
    }
    .hunk-added { color: #006400; background-color: #e6ffed; display: block; }
    .hunk-deleted { color: #8B0000; background-color: #ffeef0; text-decoration: line-through; display: block; }
    /* Error/Warning Styles */
    .error-message { color: #D8000C; font-weight: bold; background-color: #FFD2D2; display: block; padding: 2px 5px; border: 1px solid #FFBABA; margin-bottom: 2px; }
"""

# --- FIX: Define LIST_ITEM_COLORS ---
LIST_ITEM_COLORS = {
    "new_file": QColor(230, 255, 230, 100), # Light green tint for new files
    "unmatched": QColor(255, 240, 200, 120), # Light yellow/orange tint for unmatched
    "default": QColor(0, 0, 0, 0) # Transparent default
}
# --- END FIX ---

class DiffApplyWidgetUI:
    """Handles the creation and layout of UI elements for DiffApplyWidget."""

    def setup_ui(self, main_widget: 'DiffApplyWidget'):
        """Creates the UI layout and assigns widgets to the main_widget."""
        top_layout = QVBoxLayout(main_widget)
        top_layout.setContentsMargins(5, 5, 5, 5)
        top_layout.setSpacing(5)
        main_widget.setLayout(top_layout)

        # --- Meta Info Bar ---
        meta_bar_layout = QHBoxLayout()
        meta_bar_layout.addWidget(QLabel("<b>Summary:</b>"))
        main_widget.files_changed_label = QLabel("Files: 0")
        main_widget.lines_added_label = QLabel("Added: 0")
        main_widget.lines_deleted_label = QLabel("Deleted: 0")
        meta_bar_layout.addWidget(main_widget.files_changed_label)
        meta_bar_layout.addWidget(main_widget.lines_added_label)
        meta_bar_layout.addWidget(main_widget.lines_deleted_label)
        meta_bar_layout.addStretch(1)
        top_layout.addLayout(meta_bar_layout)

        # --- Main Splitter ---
        main_splitter = QSplitter(Qt.Orientation.Horizontal, main_widget)
        top_layout.addWidget(main_splitter, 1)

        # --- Left Panel: File List ---
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(5, 5, 5, 5)

        list_header_layout = QHBoxLayout()
        list_header_layout.addWidget(QLabel("Modifications to Review:"))
        list_header_layout.addStretch(1)
        main_widget.sort_combo = QComboBox()
        main_widget.sort_combo.addItems(["Sort by Path", "Sort by Changes (Asc)", "Sort by Changes (Desc)"])
        main_widget.sort_combo.setCurrentIndex(2)
        list_header_layout.addWidget(main_widget.sort_combo)
        left_layout.addLayout(list_header_layout)

        main_widget.file_list_widget = QListWidget()
        main_widget.file_list_widget.setObjectName("fileListWidget")
        list_style_sheet = "QListWidget#fileListWidget::item { padding: 5px; }"
        main_widget.file_list_widget.setStyleSheet(list_style_sheet)
        left_layout.addWidget(main_widget.file_list_widget)

        # --- Right Panel: LLM Output, Diff Viewer, Actions ---
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(5, 5, 5, 5)

        # Top: LLM Output Area
        right_layout.addWidget(QLabel("Paste LLM Response:"))
        main_widget.llm_output_edit = QPlainTextEdit()
        main_widget.llm_output_edit.setPlaceholderText(
            "Paste the full response from the LLM.\n"
            "Expected format: JSON object or array containing 'file', 'hunk', 'context_before', 'context_after'.\n"
            "Legacy XML/Markdown diff+proposed_content formats are still supported but deprecated."
        )
        main_widget.llm_output_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        right_layout.addWidget(main_widget.llm_output_edit, 1)

        # Middle: Diff Viewer
        right_layout.addWidget(QLabel("Preview (Full File with Changes Highlighted):"))
        main_widget.diff_viewer_browser = QTextBrowser()
        fixed_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        main_widget.diff_viewer_browser.setFont(fixed_font)
        main_widget.diff_viewer_browser.setLineWrapMode(QTextBrowser.LineWrapMode.NoWrap)
        main_widget.diff_viewer_browser.document().setDefaultStyleSheet(STYLE_SHEET)
        pal = main_widget.diff_viewer_browser.palette()
        pal.setColor(QPalette.ColorRole.Base, main_widget.palette().color(QPalette.ColorRole.Window))
        main_widget.diff_viewer_browser.setPalette(pal)
        right_layout.addWidget(main_widget.diff_viewer_browser, 2)

        # --- Action Buttons (Below file list - Left Panel) ---
        action_layout = QHBoxLayout()
        main_widget.clear_button = QPushButton("Clear")
        main_widget.apply_all_button = QPushButton("Apply All")
        main_widget.reject_all_button = QPushButton("Reject All")
        main_widget.clear_button.setEnabled(False)
        main_widget.apply_all_button.setEnabled(False)
        main_widget.reject_all_button.setEnabled(False)
        action_layout.addWidget(main_widget.clear_button)
        action_layout.addWidget(main_widget.apply_all_button)
        action_layout.addWidget(main_widget.reject_all_button)
        action_layout.addStretch(1)
        left_layout.addLayout(action_layout)

        # --- Action Buttons (Below Diff Preview - Right Panel) ---
        diff_action_layout = QHBoxLayout()
        main_widget.reject_button = QPushButton("Reject")
        main_widget.accept_button = QPushButton("Apply")
        main_widget.copy_diff_button = QPushButton("Copy Preview")
        main_widget.reject_button.setEnabled(False)
        main_widget.accept_button.setEnabled(False)
        main_widget.copy_diff_button.setEnabled(False)
        diff_action_layout.addWidget(main_widget.accept_button)
        diff_action_layout.addWidget(main_widget.reject_button)
        diff_action_layout.addWidget(main_widget.copy_diff_button)
        diff_action_layout.addStretch(1)
        right_layout.addLayout(diff_action_layout)

        main_splitter.addWidget(left_container)
        main_splitter.addWidget(right_container)

        main_splitter.setSizes([int(main_widget.width() * 0.35), int(main_widget.width() * 0.65)])
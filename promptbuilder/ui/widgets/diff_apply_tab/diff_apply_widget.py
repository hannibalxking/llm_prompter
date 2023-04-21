# promptbuilder/ui/widgets/diff_apply_tab/diff_apply_widget.py

import html
from pathlib import Path
from typing import Dict, Optional, List, Union
from collections import defaultdict

from PySide6.QtCore import Qt, Slot, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QWidget, QListWidgetItem, QMessageBox,
                               QApplication)
from loguru import logger

from .diff_action_handler import DiffActionHandler
from .diff_apply_widget_ui import DiffApplyWidgetUI
from .diff_list_manager import DiffListManager
from ....core import (
    extract_suggestions, DiffParseError, DiffSuggestion, DiffHunk, DiffBase, locate_hunk
)
from ....ui.utils.diff_formatter import generate_diff_html
from ....ui.windows.main_window import MainWindow


class DiffApplyWidget(QWidget):
    """
    Widget for pasting LLM output containing diffs, reviewing, and applying them.
    Delegates UI setup, action handling, and list management to helper classes.
    """

    def __init__(self, parent: QWidget | None = None):
        """Initializes the DiffApplyWidget."""
        super().__init__(parent)
        self._project_root: Optional[Path] = None
        self._suggestions: Dict[Path, List[DiffBase]] = defaultdict(list)
        self._current_suggestion: Optional[DiffBase] = None

        self.parse_debounce_timer = QTimer(self)
        self.parse_debounce_timer.setInterval(750)
        self.parse_debounce_timer.setSingleShot(True)
        self.parse_debounce_timer.timeout.connect(self._parse_llm_output)

        self._sort_order = Qt.SortOrder.AscendingOrder
        self._sort_column = "path"

        self.ui = DiffApplyWidgetUI()
        self.ui.setup_ui(self)
        self.action_handler = DiffActionHandler(self)
        self.list_manager = DiffListManager(self)

        self._connect_signals()
        self._setup_shortcuts()
        logger.info("DiffApplyWidget initialized.")

    def _connect_signals(self):
        """Connects signals to slots."""
        self.llm_output_edit.textChanged.connect(self._on_llm_text_changed)
        self.file_list_widget.currentItemChanged.connect(self._on_file_selected)
        self.accept_button.clicked.connect(self.action_handler.accept_current)
        self.reject_button.clicked.connect(self.action_handler.reject_current)
        self.copy_diff_button.clicked.connect(self._copy_diff_preview)
        self.apply_all_button.clicked.connect(self.action_handler.apply_all)
        self.reject_all_button.clicked.connect(self.action_handler.reject_all)
        self.clear_button.clicked.connect(self._clear_all_diff_data)
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)

    def _setup_shortcuts(self):
        """Sets up keyboard shortcuts for common actions."""
        apply_shortcut = QShortcut(QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_Return), self)
        apply_shortcut.activated.connect(self._handle_apply_shortcut)
        apply_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)

        reject_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        reject_shortcut.activated.connect(self._handle_reject_shortcut)
        reject_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)

        self.accept_button.setToolTip("Apply the selected change (Ctrl+Enter)")
        self.reject_button.setToolTip("Reject the selected change (Esc)")

    @Slot()
    def _handle_apply_shortcut(self):
        """Handles the Ctrl+Enter shortcut."""
        if self.accept_button.isEnabled() and self.accept_button.isVisible():
             # --- FIX: Remove focus check ---
             logger.debug("Apply shortcut triggered.")
             self.action_handler.accept_current()
             # --- END FIX ---
        else:
            logger.trace("Apply shortcut ignored (button disabled/hidden).")

    @Slot()
    def _handle_reject_shortcut(self):
        """Handles the Escape shortcut."""
        if self.reject_button.isEnabled() and self.reject_button.isVisible():
             # --- FIX: Remove focus check ---
             logger.debug("Reject shortcut triggered.")
             self.action_handler.reject_current()
             # --- END FIX ---
        else:
            logger.trace("Reject shortcut ignored (button disabled/hidden).")


    def set_project_root(self, path: Optional[Path]):
        """Sets the project root directory for resolving relative paths."""
        logger.info(f"DiffApplyWidget project root set to: {path}")
        new_root = path.resolve() if path else None
        if new_root != self._project_root:
            self._project_root = new_root
            self._clear_all_diff_data()
            logger.info("Project root changed, cleared Diff Apply tab state.")
        else:
            logger.debug("Project root unchanged.")

    @Slot()
    def _on_llm_text_changed(self):
        """Handles text changes in the LLM output edit."""
        has_text = bool(self.llm_output_edit.toPlainText().strip())
        self.clear_button.setEnabled(has_text)
        self.parse_debounce_timer.start()

    @Slot(int)
    def _on_sort_changed(self, index):
        """Handles changes in the sort dropdown."""
        self.list_manager.update_list()

    @Slot()
    def _parse_llm_output(self):
        """Parses the text in the LLM output editor after debounce."""
        if not self._project_root:
            logger.warning("Cannot parse LLM output: Project root not set.")
            return
        text = self.llm_output_edit.toPlainText()
        self._suggestions = defaultdict(list)
        self._current_suggestion = None
        self.list_manager.update_list()
        if not text.strip():
            logger.info("LLM output cleared.")
            return
        logger.info("Parsing LLM output for diff suggestions...")
        try:
            extracted: List[DiffBase] = extract_suggestions(text, self._project_root)
            for s in extracted:
                self._suggestions[s.path].append(s)
            total_items = sum(len(v) for v in self._suggestions.values())
            logger.info(f"Found {total_items} potential suggestions across {len(self._suggestions)} files.")
        except DiffParseError as e:
            logger.error(f"Failed to parse LLM output: {e}")
            QMessageBox.warning(self, "Parsing Error", f"Could not parse suggestions:\n{e}")
        except Exception as e:
            logger.exception(f"Unexpected error during LLM output parsing: {e}")
            QMessageBox.critical(self, "Error", f"An unexpected error occurred during parsing:\n{e}")
        self.list_manager.update_list()


    @Slot(QListWidgetItem, QListWidgetItem)
    def _on_file_selected(self, current: QListWidgetItem, previous: QListWidgetItem):
        """Handles selection changes in the file list, locates hunk, and updates the diff view."""
        if current is None:
            self._clear_diff_view()
            self._current_suggestion = None
            return

        suggestion = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(suggestion, DiffBase):
            logger.error("Invalid data found in list item.")
            self._clear_diff_view()
            self._current_suggestion = None
            return

        self._current_suggestion = suggestion
        logger.info(f"File selected for diff view: {suggestion.rel_path}")

        # Pre-match Hunk on Selection
        if isinstance(suggestion, DiffHunk) and suggestion.status == 'pending':
            if not self._project_root:
                 logger.error("Cannot locate hunk: Project root not set.")
                 suggestion.status = 'unmatched'
            else:
                try:
                    max_dist = 0.05 # Default
                    main_window_ref: Optional[MainWindow] = None
                    parent = self
                    while parent is not None:
                        if isinstance(parent, MainWindow):
                            main_window_ref = parent
                            break
                        parent = parent.parent()
                    if main_window_ref and hasattr(main_window_ref, 'config'):
                         config_obj = getattr(main_window_ref, 'config', None)
                         if config_obj:
                             max_dist = getattr(config_obj, 'diff_matcher_max_distance', 0.05)
                         else:
                             logger.warning("MainWindow found but config attribute missing.")
                    else:
                         logger.warning("Could not find MainWindow or config for max_distance, using default.")

                    logger.debug(f"Locating hunk for {suggestion.rel_path} with max_distance={max_dist}...")
                    file_content: List[str] = []
                    if suggestion.path.exists():
                        file_content = suggestion.path.read_text(encoding='utf-8', errors='replace').splitlines()
                    elif not any(line.startswith('-') for line in suggestion.hunk_lines):
                         logger.debug(f"File {suggestion.path} doesn't exist, treating as new file for matching.")
                         suggestion.status = 'matched'
                         suggestion.first_target_line = 0
                    else:
                         raise FileNotFoundError(f"File {suggestion.path} not found, but hunk contains deletions.")

                    if suggestion.status != 'matched': # Avoid re-running if already marked matched (new file)
                        line_index = locate_hunk(file_content, suggestion, max_distance=max_dist)
                        if line_index is not None:
                            suggestion.first_target_line = line_index
                            suggestion.status = 'matched'
                            logger.debug(f"Hunk located successfully at line {line_index + 1}.")
                        else:
                            suggestion.first_target_line = None
                            suggestion.status = 'unmatched'
                            logger.warning(f"Hunk could not be located for {suggestion.rel_path}.")

                    # Update list visually after status change
                    self.list_manager.update_list()
                    # Ensure the current item remains selected after list update
                    # Find item by comparing data, not text, as text might change
                    for i in range(self.file_list_widget.count()):
                        item = self.file_list_widget.item(i)
                        if item and item.data(Qt.ItemDataRole.UserRole) == suggestion:
                            self.file_list_widget.setCurrentItem(item)
                            break

                except FileNotFoundError:
                     logger.error(f"File not found during hunk location: {suggestion.path}")
                     suggestion.status = 'unmatched'
                     self.list_manager.update_list()
                except Exception as e:
                     logger.exception(f"Error locating hunk for {suggestion.rel_path}: {e}")
                     suggestion.status = 'unmatched'
                     self.list_manager.update_list()

        # Generate preview HTML based on the (potentially updated) suggestion status
        try:
            diff_html = generate_diff_html(suggestion, self._project_root)
            self.diff_viewer_browser.setHtml(diff_html)

            is_error_display = 'class="error-message"' in diff_html
            can_accept = False
            if not is_error_display:
                if isinstance(suggestion, DiffHunk):
                    can_accept = suggestion.status == 'matched'
                elif isinstance(suggestion, DiffSuggestion):
                    can_accept = suggestion.status == 'pending' and suggestion.proposed_content is not None

            self.accept_button.setEnabled(can_accept)
            self.reject_button.setEnabled(suggestion.status in ['pending', 'matched', 'unmatched'])
            self.copy_diff_button.setEnabled(not is_error_display)

        except Exception as e:
            logger.exception(f"Error generating diff view for {suggestion.rel_path}: {e}")
            self.diff_viewer_browser.setHtml(f'<pre class="error-message">Error generating diff view:\n{html.escape(str(e))}</pre>')
            self.accept_button.setEnabled(False)
            self.reject_button.setEnabled(False)
            self.copy_diff_button.setEnabled(False)


    def _clear_diff_view(self):
        """Clears the diff viewer and disables action buttons."""
        self.diff_viewer_browser.clear()
        self.accept_button.setEnabled(False)
        self.reject_button.setEnabled(False)
        self.copy_diff_button.setEnabled(False)
        self._current_suggestion = None

    @Slot()
    def _clear_all_diff_data(self):
        """Clears LLM output, suggestions, list, and viewer."""
        logger.info("Clearing all Diff Apply data.")
        self.llm_output_edit.clear()
        self._suggestions.clear()
        self._current_suggestion = None
        self.list_manager.update_list()
        self.clear_button.setEnabled(False)

    @Slot()
    def _copy_diff_preview(self):
        """Copies the content of the diff preview to the clipboard."""
        text = self.diff_viewer_browser.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            logger.info(f"Copied {len(text)} characters from diff preview to clipboard.")
        else:
            logger.warning("Attempted to copy empty diff preview.")
# promptbuilder/ui/widgets/diff_apply_tab/diff_list_manager.py

from typing import TYPE_CHECKING, List, Optional

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor
# --- FIX: Import QAbstractItemView ---
from PySide6.QtWidgets import QListWidgetItem, QAbstractItemView
# --- END FIX ---
from loguru import logger

from .diff_apply_widget_ui import LIST_ITEM_COLORS  # Use defined colors
from ....core.models import DiffBase, DiffHunk, DiffSuggestion

if TYPE_CHECKING:
    from .diff_apply_widget import DiffApplyWidget


class DiffListManager:
    """Manages the population and updating of the suggestions QListWidget."""

    def __init__(self, widget: 'DiffApplyWidget'):
        """Initializes the list manager."""
        self.widget = widget
        self.list_widget = widget.file_list_widget

    def _get_status_color(self, suggestion: DiffBase) -> QColor:
        """Determines the background color based on suggestion status."""
        is_new_file = not suggestion.path.exists()
        if suggestion.status == 'unmatched':
            return LIST_ITEM_COLORS["unmatched"]
        if is_new_file and suggestion.status in {'pending', 'matched'}:
            # Only color as new if it's not also unmatched
            return LIST_ITEM_COLORS["new_file"]
        return LIST_ITEM_COLORS["default"]

    def update_list(self):
        """Updates the QListWidget with pending suggestions based on current state."""
        current_selection_data: Optional[DiffBase] = self.widget._current_suggestion
        self.list_widget.blockSignals(True)
        self.list_widget.clear()

        all_suggestions_flat: List[DiffBase] = []
        for suggestion_list in self.widget._suggestions.values():
            all_suggestions_flat.extend(suggestion_list)

        display_suggestions = [s for s in all_suggestions_flat if s.status in {'pending', 'matched', 'unmatched'}]

        sort_index = self.widget.sort_combo.currentIndex()
        if sort_index == 0: # Path
            display_suggestions.sort(key=lambda s: s.rel_path)
        elif sort_index == 1: # Changes Asc
            display_suggestions.sort(key=lambda s: (s.lines_added + s.lines_deleted, s.rel_path))
        elif sort_index == 2: # Changes Desc
            display_suggestions.sort(key=lambda s: (s.lines_added + s.lines_deleted, s.rel_path), reverse=True)

        selected_item = None
        # Calculate unique files and total changes from *displayable* items
        display_paths = {s.path for s in display_suggestions}
        total_files = len(display_paths)
        # Note: Summing lines like this might double-count if multiple hunks affect the same lines.
        # A more accurate count would require analyzing line overlaps, which is complex.
        # For now, this sum represents the total lines touched by all displayed hunks/suggestions.
        total_added = sum(s.lines_added for s in display_suggestions)
        total_deleted = sum(s.lines_deleted for s in display_suggestions)

        for suggestion in display_suggestions:
            added = suggestion.lines_added
            deleted = suggestion.lines_deleted
            is_new_file = not suggestion.path.exists()
            status_indicator = ""
            if suggestion.status == 'unmatched':
                status_indicator = "[Cannot Locate]"
            elif suggestion.status == 'matched':
                 status_indicator = "[Located]"
            elif is_new_file:
                 status_indicator = "[New File]"

            change_summary = f"(+{added} / -{deleted})"
            hunk_index_str = ""
            siblings_for_path = [s for s in display_suggestions if s.path == suggestion.path]
            if len(siblings_for_path) > 1 and isinstance(suggestion, DiffHunk):
                 try:
                     hunk_idx = siblings_for_path.index(suggestion)
                     hunk_index_str = f" [Item {hunk_idx+1}/{len(siblings_for_path)}]"
                 except ValueError: pass

            display_text = f"{suggestion.rel_path}{hunk_index_str}\n{change_summary} {status_indicator}".strip()

            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, suggestion)
            item.setToolTip(f"Path: {suggestion.path}\nStatus: {suggestion.status}")

            status_color = self._get_status_color(suggestion)
            item.setBackground(status_color)

            font_metrics = self.list_widget.fontMetrics()
            item_height = (font_metrics.height() * 2) + 10
            item.setSizeHint(QSize(self.list_widget.width(), item_height))

            self.list_widget.addItem(item)
            if suggestion is current_selection_data:
                selected_item = item

        self.list_widget.blockSignals(False)

        if selected_item:
            self.list_widget.setCurrentItem(selected_item)
            # --- FIX: Use QAbstractItemView for ScrollHint ---
            self.list_widget.scrollToItem(selected_item, QAbstractItemView.ScrollHint.EnsureVisible)
            # --- END FIX ---
        elif self.list_widget.count() > 0:
             # If previous selection is gone, select the first item
             self.list_widget.setCurrentRow(0)
        else:
            # If list is now empty, clear the preview
            self.widget._clear_diff_view()

        logger.debug(f"Updated file list with {len(display_suggestions)} items to review.")

        # Update Meta Bar
        self.widget.files_changed_label.setText(f"Files: {total_files}")
        self.widget.lines_added_label.setText(f"Added: {total_added}")
        self.widget.lines_deleted_label.setText(f"Deleted: {total_deleted}")
        has_pending_or_matched = any(s.status in {'pending', 'matched', 'unmatched'} for s in display_suggestions)

        has_applicable = any(
            (isinstance(s, DiffHunk) and s.status == 'matched') or
            (isinstance(s, DiffSuggestion) and s.status == 'pending' and s.proposed_content is not None)
            for s in display_suggestions
        )
        self.widget.apply_all_button.setEnabled(has_applicable)
        self.widget.reject_all_button.setEnabled(has_pending_or_matched)
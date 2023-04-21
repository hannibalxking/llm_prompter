# promptbuilder/ui/widgets/prompt_tab/file_tree.py

import platform
import subprocess
import time  # For formatting modification time
from pathlib import Path
from typing import List, Optional, Set, Dict, Tuple

from PySide6.QtCore import Qt, Signal, Slot, QPoint
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QHeaderView,
    QAbstractItemView, QMenu, QTreeWidgetItemIterator, QMessageBox
)
from loguru import logger

from promptbuilder.core.models import FileNode, ContextResult  # Added ContextResult, ContextFile


class FileTreeWidget(QTreeWidget):
    """
    Displays the file/folder structure with checkboxes for selection.

    Handles recursive checking/unchecking of items and provides methods
    to retrieve selected file paths. Also supports filtering (text and selection)
    and expanding/collapsing selections. Displays token counts after context assembly.
    """

    # Signal emitted when the checked state of any item changes
    item_selection_changed = Signal()
    codemap_requested = Signal(FileNode) # Signal for codemap context menu

    # Column indices constants for clarity
    COL_NAME = 0
    COL_TOKENS = 1
    COL_MODIFIED = 2
    COL_PATH = 3 # Hidden

    def __init__(self, parent=None):
        """Initializes the FileTreeWidget."""
        super().__init__(parent)
        self.setColumnCount(4) # Name, Tokens, Modified, FullPath (Hidden)
        # Updated header label from "Size" to "Tokens"
        self.setHeaderLabels(["Name", "Tokens", "Modified", "Path"])
        self.setColumnHidden(self.COL_PATH, True) # Hide full path column
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection) # Disable standard selection
        self.setAnimated(False) # Disable animation for potentially large trees

        # Internal mapping for quick lookup
        self._item_map: Dict[QTreeWidgetItem, FileNode] = {} # Map Qt item to FileNode
        self._node_map: Dict[Path, QTreeWidgetItem] = {} # Map Path to Qt item

        # Configure header appearance and behavior
        header = self.header()
        header.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeMode.Stretch) # Name column stretches
        # Change Tokens and Modified to resize to contents, giving Name more space
        header.setSectionResizeMode(self.COL_TOKENS, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_MODIFIED, QHeaderView.ResizeMode.ResizeToContents)
        # No need to set initial width for Name if it stretches
        header.setStretchLastSection(False) # Ensure 'Modified' doesn't stretch automatically
        # self.setColumnWidth(self.COL_NAME, 300)
        self.setMinimumWidth(400) # Minimum overall width

        # Connect signals
        self.itemChanged.connect(self._on_item_changed)
        self.itemExpanded.connect(lambda: self.resizeColumnToContents(self.COL_NAME)) # Resize name col on expand
        self.itemCollapsed.connect(lambda: self.resizeColumnToContents(self.COL_NAME)) # Resize name col on collapse
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    # --- Helper methods (_format_size, _create_tree_item) --- (No changes needed)
    def _format_size(self, size_bytes: int) -> str:
        """Formats file size in bytes to a human-readable string (KB, MB)."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"

    def _create_tree_item(self, node: FileNode, parent_item: Optional[QTreeWidgetItem] = None) -> QTreeWidgetItem:
        """Creates a QTreeWidgetItem from a FileNode."""
        if parent_item:
            item = QTreeWidgetItem(parent_item)
        else:
            item = QTreeWidgetItem(self) # Top-level item

        # Set display text and tooltip
        item.setText(self.COL_NAME, node.name)
        item.setToolTip(self.COL_NAME, str(node.path)) # Tooltip shows full path
        item.setText(self.COL_PATH, str(node.path)) # Store full path in hidden column

        # Set modified time for files, leave tokens blank initially
        if node.is_dir:
            item.setText(self.COL_TOKENS, "") # No tokens for directories (yet?)
            item.setText(self.COL_MODIFIED, "") # No modified time for directories
        else:
            item.setText(self.COL_TOKENS, "") # Tokens column initially blank
            try:
                # Format modification time
                mod_time_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(node.mod_time))
            except ValueError:
                # Handle potential errors with invalid timestamps
                mod_time_str = "Invalid Date"
            item.setText(self.COL_MODIFIED, mod_time_str)

        # Set flags to make the item checkable and selectable
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        # Default check state is unchecked
        item.setCheckState(self.COL_NAME, Qt.CheckState.Unchecked)

        # Store mappings for easy lookup
        self._item_map[item] = node
        self._node_map[node.path] = item
        return item

    # --- Tree Population and Management --- (No changes needed)
    def populate_tree(self, root_node: FileNode):
        """Populates the tree view from a root FileNode."""
        self.clear_tree() # Clear existing items first
        logger.debug(f"Populating tree with root: {root_node.name}")
        self.blockSignals(True) # Block signals during bulk population
        try:
            # Use an iterative approach (stack) to avoid deep recursion
            stack = [(root_node, None)] # Store (node, parent_qt_item)
            while stack:
                node, parent_qt_item = stack.pop()
                current_qt_item = self._create_tree_item(node, parent_qt_item)

                # Sort children: directories first, then files, alphabetically
                sorted_children = sorted(node.children, key=lambda n: (not n.is_dir, n.name.lower()))

                # Add children to the stack in reverse order for correct processing
                for child_node in reversed(sorted_children):
                    stack.append((child_node, current_qt_item))

            # Expand the first level (root node) by default
            for i in range(self.topLevelItemCount()):
                 self.topLevelItem(i).setExpanded(True)

            # Resize columns to fit content after population
            self.resizeColumnToContents(self.COL_NAME)
            self.resizeColumnToContents(self.COL_TOKENS)
            self.resizeColumnToContents(self.COL_MODIFIED)
        finally:
            self.blockSignals(False) # Re-enable signals
        logger.debug("Tree population complete.")

    def clear_tree(self):
        """Clears all items from the tree and resets internal maps."""
        logger.debug("Clearing file tree.")
        self.blockSignals(True)
        self.clear()
        self._item_map.clear()
        self._node_map.clear()
        self.blockSignals(False)

    def show_loading_indicator(self, show: bool):
        """Shows or hides a 'Scanning...' placeholder item."""
        self.blockSignals(True)
        try:
            # Safely get the current top-level item if it exists
            if self.topLevelItemCount() == 0:
                current_item = None
            else:
                current_item = self.topLevelItem(0)

            # Remove existing "Scanning..." placeholder if present
            if current_item and "Scanning" in current_item.text(self.COL_NAME):
                self.takeTopLevelItem(0)

            if show:
                # Insert a fresh placeholder item
                self.clear_tree() # Ensure tree is empty before showing loading
                loading_item = QTreeWidgetItem(self)
                loading_item.setText(self.COL_NAME, "Scanning directory…")
                # Disable the loading item
                loading_item.setFlags(loading_item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                # Set text color to placeholder color for visual cue
                loading_item.setForeground(
                    self.COL_NAME, self.palette().color(QPalette.ColorRole.PlaceholderText)
                )
        finally:
            self.blockSignals(False)

    # --- Checkbox Handling & Propagation --- (No changes needed)
    @Slot(QTreeWidgetItem, int)
    def _on_item_changed(self, item: QTreeWidgetItem, column: int):
        """Handles checkbox state changes and propagates them."""
        if column != self.COL_NAME:
            return

        if not item or item not in self._item_map:
            logger.warning("Item changed signal received for unknown item.")
            return

        node = self._item_map.get(item)
        if not node:
             logger.error(f"Item found but no corresponding FileNode for path: {item.text(self.COL_PATH)}")
             return

        new_state = item.checkState(self.COL_NAME)
        logger.trace(f"Item '{node.name}' check state changed to: {new_state}")

        self.blockSignals(True)
        try:
            if node.is_dir:
                self._set_children_check_state(item, new_state)
            self._update_parent_check_state(item)
        finally:
            self.blockSignals(False)

        logger.trace("Emitting item_selection_changed signal.")
        self.item_selection_changed.emit()

    def _set_children_check_state(self, item: QTreeWidgetItem, state: Qt.CheckState):
        """Recursively sets the check state for all children of an item."""
        for i in range(item.childCount()):
            child = item.child(i)
            if child.checkState(self.COL_NAME) != state:
                child.setCheckState(self.COL_NAME, state)
                child_node = self._item_map.get(child)
                if child_node and child_node.is_dir:
                    self._set_children_check_state(child, state)

    def _update_parent_check_state(self, item: QTreeWidgetItem):
        """Updates the check state of parent items based on children states."""
        parent = item.parent()
        while parent:
            if parent not in self._item_map: break

            child_states = set()
            has_checkable_children = False
            for i in range(parent.childCount()):
                child = parent.child(i)
                if child.flags() & Qt.ItemFlag.ItemIsEnabled:
                    has_checkable_children = True
                    child_states.add(child.checkState(self.COL_NAME))

            new_parent_state = parent.checkState(self.COL_NAME)

            if not has_checkable_children:
                pass
            elif len(child_states) == 1:
                single_state = list(child_states)[0]
                if single_state == Qt.CheckState.Checked:
                    new_parent_state = Qt.CheckState.Checked
                elif single_state == Qt.CheckState.Unchecked:
                    new_parent_state = Qt.CheckState.Unchecked
                else:
                    new_parent_state = Qt.CheckState.PartiallyChecked
            else:
                new_parent_state = Qt.CheckState.PartiallyChecked

            if parent.checkState(self.COL_NAME) != new_parent_state:
                parent.setCheckState(self.COL_NAME, new_parent_state)

            parent = parent.parent()

    # --- Selection Retrieval --- (No changes needed)
    def get_selected_nodes(self) -> List[FileNode]:
        """
        Returns a list of FileNode objects for all items that are
        Checked or PartiallyChecked.
        """
        selected_nodes: List[FileNode] = []
        iterator = QTreeWidgetItemIterator(self, QTreeWidgetItemIterator.IteratorFlag.All)
        while iterator.value():
            item = iterator.value()
            if item.checkState(self.COL_NAME) in (Qt.CheckState.Checked, Qt.CheckState.PartiallyChecked):
                node = self._item_map.get(item)
                if node:
                    selected_nodes.append(node)
            iterator += 1
        logger.debug(f"Found {len(selected_nodes)} selected (checked or partial) nodes.")
        return selected_nodes

    def get_selected_file_paths(self) -> Set[Path]:
        """
        Returns a set of absolute Paths for all *files* that are fully Checked.
        Recursively checks children of checked directories.
        """
        selected_files: Set[Path] = set()
        iterator = QTreeWidgetItemIterator(self, QTreeWidgetItemIterator.IteratorFlag.All)
        while iterator.value():
            item = iterator.value()
            if item.checkState(self.COL_NAME) == Qt.CheckState.Checked:
                node = self._item_map.get(item)
                if node and not node.is_dir:
                    selected_files.add(node.path)
            iterator += 1
        logger.debug(f"Collected {len(selected_files)} selected file paths.")
        return selected_files

    def uncheck_all_items(self):
        """Unchecks all items in the tree."""
        logger.debug("Unchecking all items in the tree.")
        changed = False
        self.blockSignals(True)
        try:
            iterator = QTreeWidgetItemIterator(self, QTreeWidgetItemIterator.IteratorFlag.All)
            while iterator.value():
                item = iterator.value()
                if item.checkState(self.COL_NAME) != Qt.CheckState.Unchecked:
                    item.setCheckState(self.COL_NAME, Qt.CheckState.Unchecked)
                    changed = True
                iterator += 1
        finally:
            self.blockSignals(False)

        if changed:
            logger.debug("Items were unchecked, emitting selection change.")
            self.item_selection_changed.emit()

    # --- Filtering, Expanding, Collapsing ---
    def apply_filters(self, text_filter: str, hide_unselected: bool):
        """Applies text and selection filters simultaneously."""
        filter_text = text_filter.strip().lower()
        logger.debug(f"Applying combined filters: text='{filter_text}', hide_unselected={hide_unselected}")
        self.blockSignals(True)
        try:
            iterator = QTreeWidgetItemIterator(self, QTreeWidgetItemIterator.IteratorFlag.All)
            items_to_process = []
            while iterator.value():
                 items_to_process.append(iterator.value())
                 iterator += 1

            visibility_map: Dict[QTreeWidgetItem, bool] = {}

            # Iterate backwards (leaves first) to determine visibility based on children
            for item in reversed(items_to_process):
                 node = self._item_map.get(item)
                 # --- Root Item Check ---
                 is_root_item = (item.parent() is None)
                 # --- End Root Item Check ---

                 item_text = item.text(self.COL_NAME).lower() if item else ""
                 check_state = item.checkState(self.COL_NAME)

                 # 1. Check text filter match
                 text_match = (not filter_text) or (filter_text in item_text)

                 # 2. Check selection filter match (item itself must be selected if filter is on)
                 # Root items are always considered a match for selection filter
                 selection_match = is_root_item or (not hide_unselected) or (check_state != Qt.CheckState.Unchecked)

                 # 3. Check if any children are visible (needed to keep parent visible)
                 child_visible = False
                 if node and node.is_dir: # Only check children for directories
                     for i in range(item.childCount()):
                         child_item = item.child(i)
                         if visibility_map.get(child_item, False): # Check if child is marked visible
                             child_visible = True
                             break

                 # Determine final visibility
                 # Item is visible if:
                 # - It is the root item OR
                 # - It has a visible child OR
                 # - It matches the text filter AND it matches the selection filter
                 is_visible = is_root_item or child_visible or (text_match and selection_match)
                 visibility_map[item] = is_visible
                 item.setHidden(not is_visible)

                 # Expand parents of visible items if text filter is active
                 # (Expansion based on selection is handled separately)
                 if filter_text and is_visible and not child_visible: # Expand only if item itself matches
                      parent = item.parent()
                      while parent:
                          if parent.isHidden(): # Ensure parent is also visible before expanding
                               parent.setHidden(False)
                               visibility_map[parent] = True # Mark parent as visible too
                          parent.setExpanded(True)
                          parent = parent.parent()

        finally:
            self.blockSignals(False)

    def expand_selected_parents(self):
        """Expands the parent items of all currently checked items."""
        logger.debug("Expanding parents of selected items.")
        self.blockSignals(True)
        try:
            items_to_expand = set() # Use set to avoid redundant expansions
            iterator = QTreeWidgetItemIterator(self, QTreeWidgetItemIterator.IteratorFlag.All)
            while iterator.value():
                item = iterator.value()
                # Expand parents if item is checked (fully or partially matters less here)
                if not item.isHidden() and item.checkState(self.COL_NAME) != Qt.CheckState.Unchecked:
                    parent = item.parent()
                    while parent:
                        # Only add parent if it's not already expanded and not hidden
                        if not parent.isExpanded() and not parent.isHidden():
                            items_to_expand.add(parent)
                        parent = parent.parent()
                iterator += 1

            # Expand the collected items
            for item in items_to_expand:
                item.setExpanded(True)
        finally:
            self.blockSignals(False)

    def collapse_unselected_items(self):
        """Collapses directory items that have no selected descendants."""
        logger.debug("Collapsing items with no selected descendants.")
        self.blockSignals(True)
        try:
            iterator = QTreeWidgetItemIterator(self, QTreeWidgetItemIterator.IteratorFlag.All)
            items_to_process = []
            while iterator.value():
                items_to_process.append(iterator.value())
                iterator += 1

            # Iterate from top-level down
            for item in items_to_process:
                # --- Check if it's a top-level item ---
                is_top_level = (item.parent() is None)
                if is_top_level:
                    continue # Never collapse the root item(s)

                node = self._item_map.get(item)
                # Only consider visible directories that are currently expanded
                if node and node.is_dir and not item.isHidden() and item.isExpanded():
                    if not self._has_selected_descendant(item):
                        item.setExpanded(False)
        finally:
            self.blockSignals(False)

    def _has_selected_descendant(self, item: QTreeWidgetItem) -> bool:
        """Recursively checks if an item or any of its descendants are checked."""
        # Check the item itself first (if it's a file and checked)
        if item.checkState(self.COL_NAME) == Qt.CheckState.Checked:
             node = self._item_map.get(item)
             if node and not node.is_dir:
                 return True # A selected file is found

        # If it's partially checked, it must have a selected descendant
        if item.checkState(self.COL_NAME) == Qt.CheckState.PartiallyChecked:
            return True

        # Recursively check children
        for i in range(item.childCount()):
            child = item.child(i)
            # Important: Only consider visible children for this check
            if not child.isHidden():
                if self._has_selected_descendant(child):
                    return True
        return False


    @Slot(QPoint)
    def _show_context_menu(self, pos: QPoint):
        """Shows a context menu for the item at the given position."""
        item = self.itemAt(pos)
        if not item: return
        node = self._item_map.get(item)
        if not node: return

        menu = QMenu(self)
        if node.is_dir:
            action_expand = menu.addAction("Expand All")
            action_collapse = menu.addAction("Collapse All")
            action_expand.triggered.connect(lambda: self.expandRecursively(item))
            action_collapse.triggered.connect(lambda: self.collapseRecursively(item))
            menu.addSeparator()

        action_check = menu.addAction("Check")
        action_uncheck = menu.addAction("Uncheck")
        action_check.triggered.connect(lambda: self._set_item_checked_state(item, Qt.CheckState.Checked))
        action_uncheck.triggered.connect(lambda: self._set_item_checked_state(item, Qt.CheckState.Unchecked))
        menu.addSeparator()

        action_open_externally = menu.addAction("Open Location")
        action_open_externally.triggered.connect(lambda: self._open_item_location(node))

        # Add Codemap action only for files
        if not node.is_dir:
            menu.addSeparator()
            action_codemap = menu.addAction("Select Related (Codemap)")
            action_codemap.triggered.connect(lambda: self.codemap_requested.emit(node))

        menu.exec(self.mapToGlobal(pos))

    def expandRecursively(self, item: QTreeWidgetItem):
        """Recursively expands an item and all its children."""
        if not item: return
        item.setExpanded(True)
        for i in range(item.childCount()):
            self.expandRecursively(item.child(i))

    def collapseRecursively(self, item: QTreeWidgetItem):
        """Recursively collapses an item and all its children."""
        if not item: return
        for i in range(item.childCount()):
            self.collapseRecursively(item.child(i))
        item.setExpanded(False)

    def _set_item_checked_state(self, item: QTreeWidgetItem, state: Qt.CheckState):
        """Sets the check state of an item, triggering propagation."""
        if item and item.checkState(self.COL_NAME) != state:
             item.setCheckState(self.COL_NAME, state)

    def _open_item_location(self, node: FileNode):
        """Opens the file or directory location in the system's file explorer."""
        path_to_open = node.path
        logger.info(f"Attempting to open location: {path_to_open}")
        try:
            if platform.system() == "Windows":
                if path_to_open.is_file():
                    subprocess.run(['explorer', '/select,', str(path_to_open)], check=True, shell=False)
                elif path_to_open.is_dir():
                    subprocess.run(['explorer', str(path_to_open)], check=True, shell=False)
                else:
                    logger.warning(f"Cannot open location for non-file/dir: {path_to_open}")
                    return
                logger.info(f"Opened location for: {path_to_open}")
            else:
                logger.warning(f"Unsupported OS for opening location: {platform.system()}")
                QMessageBox.information(self, "Unsupported", "Opening location is currently only supported on Windows.")
        except FileNotFoundError:
            logger.error(f"File explorer command not found. Could not open location {path_to_open}")
            QMessageBox.warning(self, "Open Error", "Could not run the file explorer to open location.")
        except Exception as e:
            logger.exception(f"Failed to open location {path_to_open}: {e}")
            QMessageBox.warning(self, "Open Error", f"Could not open location:\n{e}")

    @Slot(ContextResult)
    def update_token_counts(self, context_result: ContextResult):
        """Updates the 'Tokens' column in the tree based on context assembly results."""
        logger.debug(f"Updating token counts in tree from ContextResult (Included: {len(context_result.included_files)}, Skipped: {len(context_result.skipped_files)})")
        self.blockSignals(True)
        try:
            token_map: Dict[Path, Tuple[int, str]] = {}
            for f in context_result.included_files:
                token_map[f.path] = (f.tokens, f.status)
            for f in context_result.skipped_files:
                token_map[f.path] = (f.tokens, f.status)

            iterator = QTreeWidgetItemIterator(self, QTreeWidgetItemIterator.IteratorFlag.All)
            while iterator.value():
                item = iterator.value()
                node = self._item_map.get(item)
                if node and not node.is_dir:
                    token_info = token_map.get(node.path)
                    if token_info:
                        tokens, status = token_info
                        token_text = f"{tokens:,}" if tokens > 0 else "0"
                        if status not in {"read_ok", "read_scrubbed", "included"}:
                            status_simple = status.replace("read_", "").replace("skipped_", "").split('_')[0]
                            token_text += f" ({status_simple})"
                            item.setToolTip(self.COL_TOKENS, f"Status: {status}, Tokens: {tokens}")
                        else:
                            item.setToolTip(self.COL_TOKENS, f"Tokens: {tokens}")
                        item.setText(self.COL_TOKENS, token_text)
                        item.setTextAlignment(self.COL_TOKENS, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    else:
                        item.setText(self.COL_TOKENS, "-")
                        item.setToolTip(self.COL_TOKENS, "Not processed for context")
                        item.setTextAlignment(self.COL_TOKENS, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                elif node and node.is_dir:
                    item.setText(self.COL_TOKENS, "")
                    item.setToolTip(self.COL_TOKENS, "")
                iterator += 1
            self.resizeColumnToContents(self.COL_TOKENS)
        except Exception as e:
            logger.exception(f"Error updating token counts in tree: {e}")
        finally:
            self.blockSignals(False)

    def clear_token_counts(self):
        """Clears the 'Tokens' column for all items."""
        logger.debug("Clearing token counts in tree.")
        self.blockSignals(True)
        try:
            iterator = QTreeWidgetItemIterator(self, QTreeWidgetItemIterator.IteratorFlag.All)
            while iterator.value():
                item = iterator.value()
                item.setText(self.COL_TOKENS, "")
                item.setToolTip(self.COL_TOKENS, "")
                iterator += 1
        finally:
            self.blockSignals(False)
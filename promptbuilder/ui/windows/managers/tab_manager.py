# promptbuilder/ui/windows/managers/tab_manager.py

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Slot, QTimer
from PySide6.QtWidgets import QInputDialog
from loguru import logger

from ....config.schema import TabConfig
from ...widgets.prompt_tab.project_tab import ProjectTabWidget

if TYPE_CHECKING:
    from ..main_window import MainWindow
    from .status_manager import StatusManager


class TabManager(QObject):
    """Manages project tabs (creation, removal, switching, renaming)."""

    def __init__(self, window: 'MainWindow', ui, status_manager: 'StatusManager'):
        super().__init__(window)
        self.window = window
        self.ui = ui
        self.status_manager = status_manager

    def load_initial_tabs(self):
        """Loads initial tabs based on configuration."""
        self.ui.project_tabs.clear()
        if not self.window.config.tabs:
            self.add_new_tab(title="Default Project", activate=True)
        else:
            for i, tab_config in enumerate(self.window.config.tabs):
                self.add_new_tab(config=tab_config, activate=(i == 0))

        # Ensure at least one tab exists
        if self.ui.project_tabs.count() == 0:
            self.add_new_tab(title="Project 1", activate=True)

        logger.info(f"Loaded {self.ui.project_tabs.count()} project tabs.")

    @Slot()
    def add_new_tab(self, config: TabConfig | None = None, title: str | None = None, activate=True):
        """Adds a new project tab."""
        if config is None:
            config = TabConfig()
        tab_title = title or config.title or f"Project {self.ui.project_tabs.count() + 1}"
        logger.info(f"Adding new project tab: '{tab_title}' (Dir: {config.directory})")

        new_tab_widget = ProjectTabWidget(config, parent=self.ui.project_tabs)
        idx = self.ui.project_tabs.addTab(new_tab_widget, tab_title)
        self.window._connect_tab_signals(new_tab_widget) # Connect signals via MainWindow

        if activate:
            self.ui.project_tabs.setCurrentIndex(idx)
            # Ensure the "Prompt" top-level tab is active when adding a new project tab
            self.ui.top_level_tabs.setCurrentWidget(self.ui.prompt_tab_widget)

        # Trigger scan if directory exists and tab is activated
        if config.directory and activate:
            # Use QTimer to ensure the tab is fully visible before scanning
            QTimer.singleShot(50, new_tab_widget.scan_directory)

    @Slot(int)
    def remove_tab_by_index(self, index: int):
        """Removes the project tab at the specified index."""
        if index < 0 or index >= self.ui.project_tabs.count():
            return
        widget = self.ui.project_tabs.widget(index)
        tab_text = self.ui.project_tabs.tabText(index)
        logger.info(f"Removing project tab: '{tab_text}' at index {index}")

        if isinstance(widget, ProjectTabWidget):
            self.window._disconnect_tab_signals(widget) # Disconnect via MainWindow
            widget.cancel_scan() # Cancel any ongoing scan
            widget.deleteLater() # Schedule for deletion

        self.ui.project_tabs.removeTab(index)

        # Add a default tab if the last one was removed
        if self.ui.project_tabs.count() == 0:
            self.add_new_tab(activate=True)

    @Slot()
    def remove_current_tab(self):
        """Removes the currently active project tab."""
        self.remove_tab_by_index(self.ui.project_tabs.currentIndex())

    @Slot()
    def rename_current_tab(self):
        """Opens a dialog to rename the current project tab."""
        idx = self.ui.project_tabs.currentIndex()
        if idx < 0: return
        current_name = self.ui.project_tabs.tabText(idx)
        new_name, ok = QInputDialog.getText(self.window, "Rename Project Tab", "Enter new tab name:", text=current_name)
        if ok and new_name and new_name != current_name:
            self.ui.project_tabs.setTabText(idx, new_name)
            widget = self.ui.project_tabs.widget(idx)
            if isinstance(widget, ProjectTabWidget):
                widget.config.title = new_name # Update config stored in the widget
            logger.info(f"Renamed project tab {idx} to '{new_name}'")

    @Slot(int)
    def on_project_tab_changed(self, index: int):
        """Handles actions when the current *project* tab changes."""
        if index < 0 or index >= self.ui.project_tabs.count():
            logger.warning(f"Project tab changed to invalid index: {index}")
            # Disable relevant actions if index is invalid
            self.ui.open_folder_action.setEnabled(False)
            self.ui.rename_tab_action.setEnabled(False)
            self.ui.close_tab_action.setEnabled(False)
            return

        tab_text = self.ui.project_tabs.tabText(index)
        logger.debug(f"Switched to project tab: '{tab_text}' (Index: {index})")

        # Enable actions relevant to the selected tab
        self.ui.open_folder_action.setEnabled(True)
        self.ui.rename_tab_action.setEnabled(True)
        self.ui.close_tab_action.setEnabled(True)

        # Update the root directory for the Diff Apply tab
        self.update_diff_apply_tab_root()

        # Request a context rebuild for the newly selected tab
        self.window._request_rebuild_context_debounced()

        # Trigger scan if the tab is activated and has a directory but no tree items (and isn't already scanning)
        current_widget = self.ui.project_tabs.widget(index)
        if isinstance(current_widget, ProjectTabWidget):
            if current_widget.config.directory and current_widget.file_tree.topLevelItemCount() == 0:
                # Check if the placeholder "Scanning..." item exists
                top_item = current_widget.file_tree.topLevelItem(0) if current_widget.file_tree.topLevelItemCount() > 0 else None
                if not (top_item and "Scanning" in top_item.text(0)):
                    logger.info(f"Triggering scan for newly activated project tab '{tab_text}' which has no tree items.")
                    QTimer.singleShot(50, current_widget.scan_directory) # Use timer for safety

    @Slot(int)
    def on_main_tab_changed(self, index: int):
        """Handles actions when the top-level tab changes."""
        current_widget = self.ui.top_level_tabs.widget(index)
        if current_widget == self.ui.diff_apply_tab_widget:
            logger.debug("Switched to Diff Apply tab.")
            self.update_diff_apply_tab_root() # Ensure root is set correctly
        elif current_widget == self.ui.prompt_tab_widget:
            logger.debug("Switched to Prompt tab.")
            # Request rebuild only if the prompt tab becomes active
            self.window._request_rebuild_context_debounced()

    def update_diff_apply_tab_root(self):
        """Sets the project root for the Diff Apply tab based on the current project tab."""
        current_project_widget = self.ui.project_tabs.currentWidget()
        root_path = None
        if isinstance(current_project_widget, ProjectTabWidget) and current_project_widget.config.directory:
            try:
                root_path = Path(current_project_widget.config.directory).resolve()
            except Exception as e:
                logger.error(f"Failed to resolve project root path '{current_project_widget.config.directory}': {e}")
                root_path = None # Ensure it's None on error

        # Pass the resolved Path object (or None) to the diff apply widget
        self.ui.diff_apply_tab_widget.set_project_root(root_path)
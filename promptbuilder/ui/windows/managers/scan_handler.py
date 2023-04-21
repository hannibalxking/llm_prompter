# promptbuilder/ui/windows/managers/scan_handler.py

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QMessageBox

from ...widgets.prompt_tab.project_tab import ProjectTabWidget

if TYPE_CHECKING:
    from ..main_window import MainWindow
    from .status_manager import StatusManager


class ScanHandler(QObject):
    """Handles callbacks related to file system scanning."""

    def __init__(self, window: 'MainWindow', ui, status_manager: 'StatusManager'):
        super().__init__(window)
        self.window = window
        self.ui = ui
        self.status_manager = status_manager

    @Slot()
    def on_scan_started(self):
        """Handles scan start."""
        self.status_manager.show_status_message("Scanning files...", 0, show_progress=True)
        sender_widget = self.sender()
        if isinstance(sender_widget, ProjectTabWidget):
            sender_widget.file_tree.clear_token_counts()

    @Slot(list) # Receives list[FileNode]
    def on_scan_finished(self, root_nodes: list):
        """Handles scan finish."""
        self.status_manager.show_status_message("File scan complete.", 4000, show_progress=False)
        # Trigger context rebuild if the scan finished for the *currently active* tab
        if self.sender() == self.ui.project_tabs.currentWidget():
            self.window._request_rebuild_context_debounced()

    @Slot(str)
    def on_scan_error(self, error_msg: str):
        """Handles scan errors."""
        sender_widget = self.sender()
        if isinstance(sender_widget, ProjectTabWidget):
            sender_widget.file_tree.clear_token_counts()

        is_cancel = "cancel" in error_msg.lower()
        if not is_cancel:
            self.status_manager.show_status_message(f"Scan Error: {error_msg}", 0, show_progress=False)
            QMessageBox.warning(self.window, "Scan Error", f"Could not scan directory:\n{error_msg}")
        else:
            self.status_manager.show_status_message("Scan cancelled.", 4000, show_progress=False)
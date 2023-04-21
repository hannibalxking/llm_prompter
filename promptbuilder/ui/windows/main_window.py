# promptbuilder/ui/windows/main_window.py

from typing import TYPE_CHECKING

from PySide6.QtCore import Slot, Signal, QTimer
from PySide6.QtWidgets import (QMainWindow, QWidget)
from loguru import logger

# --- New Widget Import ---
# --- Existing Imports ---
from promptbuilder.ui.widgets.prompt_tab.project_tab import ProjectTabWidget
from .main_window_manager import MainWindowManager
# --- Refactored Component Imports ---
from .main_window_ui import MainWindowUI
from ...config.loader import get_config
from ...core.prompt_engine import PromptEngine

if TYPE_CHECKING:
    pass


class MainWindow(QMainWindow):
    """
    Main application window containing the tabbed project interface,
    prompt snippet selection panel, and the generated prompt preview.
    Includes a tab for reviewing and applying code diffs.
    Delegates UI setup and logic handling to helper classes.
    """

    # Signal to indicate context needs rebuilding (debounced)
    request_context_rebuild = Signal()

    def __init__(self, parent: QWidget | None = None):
        """Initializes the MainWindow."""
        super().__init__(parent)
        self.setWindowTitle("PromptBuilder")

        self.config = get_config() # Config needed by manager
        self.prompt_engine = PromptEngine() # Engine needed by manager

        # --- UI Setup (Delegated) ---
        self.ui = MainWindowUI(self)

        # Debounce timer for context rebuild requests
        self.rebuild_debounce_timer = QTimer(self)
        self.rebuild_debounce_timer.setInterval(350)
        self.rebuild_debounce_timer.setSingleShot(True)
        self.rebuild_debounce_timer.timeout.connect(self._trigger_context_assembly)

        # --- Manager Setup (Handles Logic, State, Actions) ---
        self.manager = MainWindowManager(self)

        # --- Connect Signals ---
        self._connect_signals()

        # --- Load Initial State (Delegated) ---
        self.manager.load_state()
        # Delay initial rebuild slightly to ensure UI is fully initialized
        # self._request_rebuild_context_debounced() # Initial prompt update - Moved
        QTimer.singleShot(100, self._request_rebuild_context_debounced) # Schedule initial rebuild

        logger.info("MainWindow initialized.")
        self.manager.check_tiktoken_availability()

    # --- Signal Connections ---
    def _connect_signals(self):
        """Connects signals from UI elements to slots."""
        # Connect signals for the *project* tabs (within the "Prompt" tab)
        self.ui.project_tabs.tabCloseRequested.connect(self.manager.remove_tab_by_index)
        self.ui.project_tabs.currentChanged.connect(self.manager.on_project_tab_changed)

        # Connect signals for the *top-level* tabs
        self.ui.top_level_tabs.currentChanged.connect(self.manager.on_main_tab_changed)

        # Prompt panel signal
        self.ui.prompt_panel.snippets_changed.connect(self._request_rebuild_context_debounced)

        # Bottom bar buttons (in Prompt tab)
        self.ui.copy_button.clicked.connect(self.manager.copy_content)
        self.ui.clear_button.clicked.connect(self.manager.clear_all)

        # Central request signal to debounce timer
        self.request_context_rebuild.connect(self.rebuild_debounce_timer.start)

    def _connect_tab_signals(self, tab_widget: ProjectTabWidget):
        """Connects signals for a specific project tab instance."""
        tab_widget.selection_changed.connect(self.request_context_rebuild.emit)
        tab_widget.scan_started.connect(self.manager.on_scan_started)
        tab_widget.scan_finished.connect(self.manager.on_scan_finished)
        tab_widget.scan_progress.connect(self.manager.show_status_message)
        tab_widget.scan_error.connect(self.manager.on_scan_error)

    def _disconnect_tab_signals(self, tab_widget: ProjectTabWidget):
        """Disconnects signals for a specific project tab instance."""
        try:
            tab_widget.selection_changed.disconnect(self.request_context_rebuild.emit)
            tab_widget.scan_started.disconnect(self.manager.on_scan_started) # Corrected slot name
            tab_widget.scan_finished.disconnect(self.manager.on_scan_finished) # Corrected slot name
            tab_widget.scan_progress.disconnect(self.manager.show_status_message) # Corrected slot name
            tab_widget.scan_error.disconnect(self.manager.on_scan_error) # Corrected slot name
        except RuntimeError as e:
            logger.warning(f"Error disconnecting signals (may be expected): {e}")

    @Slot()
    def _request_rebuild_context_debounced(self):
        """Requests a context rebuild after a short delay."""
        # Only trigger rebuild if the "Prompt" tab is active
        if self.ui.top_level_tabs.currentWidget() == self.ui.prompt_tab_widget:
            logger.trace("Requesting debounced context rebuild.")
            self.request_context_rebuild.emit()
        else:
            logger.trace("Ignoring context rebuild request (Prompt tab not active).")

    def closeEvent(self, event):
        """Handles the main window close event."""
        logger.info("Close event triggered. Saving state...")
        # Delegate saving and task cancellation to the manager
        if not self.manager.handle_close_event():
            event.ignore()
        else:
            event.accept()

    # --- Prompt Generation ---
    @Slot()
    def _trigger_context_assembly(self):
        """Gathers selections from the *current* project tab and triggers context assembly task."""
        logger.debug("Debounced trigger for context assembly.")
        # Delegate context assembly to the manager
        self.manager.trigger_context_assembly()
# promptbuilder/ui/windows/main_window_manager.py

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QMessageBox
from loguru import logger

from .managers.action_handler import ActionHandler
from .managers.context_assembler_handler import ContextAssemblerHandler
from .managers.scan_handler import ScanHandler
# Import the new manager components
from .managers.state_manager import StateManager
from .managers.status_manager import StatusManager
from .managers.tab_manager import TabManager
# Import necessary types and widgets
from ..widgets.prompt_tab.project_tab import ProjectTabWidget
from ..dialogs.settings_dialog import SettingsDialog # Import SettingsDialog
from ...services.theming import Theme

if TYPE_CHECKING:
    from ..main_window import MainWindow


class MainWindowManager(QObject):
    """
    Coordinates the different manager components for the MainWindow.
    Initializes managers and connects signals between them and the UI/MainWindow.
    Handles the main window close event.
    """

    def __init__(self, main_window: 'MainWindow'):
        super().__init__(main_window)
        self.window = main_window
        self.config = main_window.config
        self.prompt_engine = main_window.prompt_engine
        self.ui = main_window.ui

        # --- Initialize Manager Components ---
        self.status_manager = StatusManager(self.window, self.ui)
        self.state_manager = StateManager(self.window, self.config, self.ui, self.status_manager)
        self.tab_manager = TabManager(self.window, self.ui, self.status_manager)
        self.scan_handler = ScanHandler(self.window, self.ui, self.status_manager)
        self.context_assembler_handler = ContextAssemblerHandler(self.window, self.config, self.prompt_engine, self.ui, self.status_manager)
        self.action_handler = ActionHandler(self.window, self.ui, self.state_manager, self.tab_manager, self.context_assembler_handler)

        # Connect menu actions via the ActionHandler
        self._connect_menu_actions()

    def _connect_menu_actions(self):
        """Connect signals from menu actions to manager slots."""
        self.ui.new_tab_action.triggered.connect(self.add_new_tab)
        self.ui.open_folder_action.triggered.connect(self.open_folder_in_current_tab)
        self.ui.rename_tab_action.triggered.connect(self.rename_current_tab)
        self.ui.close_tab_action.triggered.connect(self.remove_current_tab)
        self.ui.save_config_action.triggered.connect(self.save_state_now)
        self.ui.quit_action.triggered.connect(self.window.close)
        self.ui.copy_action.triggered.connect(self.copy_content)
        self.ui.clear_action.triggered.connect(self.clear_all)
        # Theme actions are connected directly in UI setup (via ActionHandler)
        self.ui.toggle_statusbar_action.triggered.connect(self.toggle_statusbar)
        self.ui.about_action.triggered.connect(self.show_about_dialog)
        self.ui.settings_action.triggered.connect(self.show_settings_dialog) # Connect settings action

    # --- Public Methods Delegated to Managers ---

    def load_state(self):
        """Delegates state loading to the StateManager."""
        self.state_manager.load_state()
        self.tab_manager.load_initial_tabs()
        self.tab_manager.update_diff_apply_tab_root() # Ensure diff tab root is set after load

    def update_config_before_save(self):
        """Delegates updating the config object to the StateManager."""
        self.state_manager.update_config_before_save()

    @Slot()
    def save_state_now(self):
        """Delegates immediate state saving to the StateManager."""
        self.state_manager.save_state_now()

    def handle_close_event(self) -> bool:
        """Handles logic before closing the window (saving, task cancellation). Returns True if close should proceed."""
        # Check context assembler task
        if self.context_assembler_handler.is_task_running():
            reply = QMessageBox.question(self.window, "Task Running",
                                         "Context assembly task is running. Quit anyway?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                         QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.No: return False
            else:
                logger.info("Requesting cancellation of context task on close via handler.")
                self.context_assembler_handler.cancel_task()

        # Cancel any running scan tasks in tabs
        for i in range(self.ui.project_tabs.count()):
            widget = self.ui.project_tabs.widget(i)
            if isinstance(widget, ProjectTabWidget): widget.cancel_scan()

        # Save state before closing
        self.update_config_before_save()
        logger.info("Proceeding with close.")
        return True

    # --- Project Tab Management ---
    @Slot()
    def add_new_tab(self, config=None, title=None, activate=True):
        """Delegates adding a new tab to the TabManager."""
        self.tab_manager.add_new_tab(config, title, activate)

    @Slot(int)
    def remove_tab_by_index(self, index: int):
        """Delegates removing a tab by index to the TabManager."""
        self.tab_manager.remove_tab_by_index(index)

    @Slot()
    def remove_current_tab(self):
        """Delegates removing the current tab to the TabManager."""
        self.tab_manager.remove_current_tab()

    @Slot()
    def rename_current_tab(self):
        """Delegates renaming the current tab to the TabManager."""
        self.tab_manager.rename_current_tab()

    @Slot(int)
    def on_project_tab_changed(self, index: int):
        """Delegates handling project tab changes to the TabManager."""
        self.tab_manager.on_project_tab_changed(index)

    @Slot(int)
    def on_main_tab_changed(self, index: int):
        """Delegates handling main tab changes to the TabManager."""
        self.tab_manager.on_main_tab_changed(index)

    @Slot()
    def open_folder_in_current_tab(self):
        """Delegates opening a folder to the ActionHandler."""
        self.action_handler.open_folder_in_current_tab()

    # --- Tiktoken Check ---
    def check_tiktoken_availability(self):
        """Delegates Tiktoken check to the StatusManager."""
        self.status_manager.check_tiktoken_availability()

    # --- Prompt Generation Logic ---
    @Slot()
    def trigger_context_assembly(self):
        """Delegates context assembly triggering to the ContextAssemblerHandler."""
        self.context_assembler_handler.trigger_context_assembly()

    # --- Actions ---
    @Slot()
    def copy_content(self):
        """Delegates copying content to the ActionHandler."""
        self.action_handler.copy_content()

    @Slot()
    def clear_all(self):
        """Delegates clearing selections to the ActionHandler."""
        self.action_handler.clear_all()

    @Slot(Theme)
    def change_theme(self, theme: 'Theme'):
        """Delegates theme changing to the ActionHandler."""
        self.action_handler.change_theme(theme)

    @Slot()
    def toggle_statusbar(self):
        """Delegates toggling the status bar to the ActionHandler."""
        self.action_handler.toggle_statusbar()

    @Slot()
    def show_about_dialog(self):
        """Delegates showing the About dialog to the ActionHandler."""
        self.action_handler.show_about_dialog()

    @Slot()
    def show_settings_dialog(self):
        """Creates and shows the Settings dialog."""
        dialog = SettingsDialog(self.config, self.window)
        if dialog.exec():
            logger.info("Settings dialog accepted. Applying changes...")
            # Re-instantiate components that depend on settings
            self.context_assembler_handler.reinitialize_token_counter()
            self.status_manager.reinitialize_token_counter()
            # Optionally trigger a prompt rebuild if settings affect it
            self.window._request_rebuild_context_debounced()
            # Save the updated config immediately
            self.save_state_now()

    # --- Status Bar Updates ---
    @Slot(str)
    @Slot(str, int)
    def show_status_message(self, message: str, timeout: int = 0, show_progress: bool | None = None):
        """Delegates showing status messages to the StatusManager."""
        self.status_manager.show_status_message(message, timeout, show_progress)

    # --- Scan Status Callbacks ---
    @Slot()
    def on_scan_started(self):
        """Delegates handling scan start to the ScanHandler."""
        self.scan_handler.on_scan_started()

    @Slot(list) # Receives list[FileNode]
    def on_scan_finished(self, root_nodes: list):
        """Delegates handling scan finish to the ScanHandler."""
        self.scan_handler.on_scan_finished(root_nodes)

    @Slot(str)
    def on_scan_error(self, error_msg: str):
        """Delegates handling scan errors to the ScanHandler."""
        self.scan_handler.on_scan_error(error_msg)
# promptbuilder/ui/windows/managers/action_handler.py

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QMessageBox, QFileDialog, QApplication
from loguru import logger

from ....services.theming import Theme, apply_theme
from ...widgets.prompt_tab.project_tab import ProjectTabWidget

if TYPE_CHECKING:
    from ..main_window import MainWindow
    from .state_manager import StateManager
    from .tab_manager import TabManager
    from .context_assembler_handler import ContextAssemblerHandler


class ActionHandler(QObject):
    """Handles user actions triggered by menus or buttons."""

    def __init__(self, window: 'MainWindow', ui, state_manager: 'StateManager', tab_manager: 'TabManager', context_handler: 'ContextAssemblerHandler'):
        super().__init__(window)
        self.window = window
        self.ui = ui
        self.state_manager = state_manager
        self.tab_manager = tab_manager
        self.context_handler = context_handler # Needed for clear_all

    @Slot()
    def copy_content(self):
        """Copies prompt preview to clipboard."""
        text = self.ui.prompt_preview_edit.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            logger.info(f"Copied {len(text)} characters to clipboard.")
            self.window.manager.show_status_message("Prompt copied to clipboard!", 3000)
        else:
            logger.warning("Attempted to copy empty prompt.")
            self.window.manager.show_status_message("Nothing to copy.", 3000)

    @Slot()
    def clear_all(self):
        """Clears selections in the prompt panel and current project tab."""
        logger.info("Clearing all selections.")
        self.ui.prompt_panel.clear_selections()
        current_widget = self.ui.project_tabs.currentWidget()
        if isinstance(current_widget, ProjectTabWidget):
            current_widget.clear_selection()
        # Clearing selections should trigger a context rebuild automatically via signals
        self.window.manager.show_status_message("Selections cleared.", 3000)

    @Slot(Theme)
    def change_theme(self, theme: Theme):
        """Applies theme and updates config."""
        logger.info(f"User changed theme to: {theme.name}")
        try:
            apply_theme(theme)
            self.window.config.theme = theme.value
            self.window.manager.show_status_message(f"Theme changed to {theme.name}", 3000)
        except Exception as e:
            logger.exception(f"Failed to apply theme {theme.name}: {e}")
            QMessageBox.warning(self.window, "Theme Error", f"Could not apply theme: {e}")

    @Slot()
    def toggle_statusbar(self):
        """Toggles status bar visibility."""
        is_visible = self.ui.status_bar.isVisible()
        self.ui.status_bar.setVisible(not is_visible)
        self.ui.toggle_statusbar_action.setChecked(not is_visible)

    @Slot()
    def show_about_dialog(self):
        """Displays the About dialog."""
        from .... import __version__
        about_text = (f"<b>PromptBuilder v{__version__}</b><br><br>"
                      "A workbench for crafting LLM prompts.<br><br>"
                      "(c) 2023-2024 Your Name/Company")
        QMessageBox.about(self.window, "About PromptBuilder", about_text)

    @Slot()
    def open_folder_in_current_tab(self):
        """Opens a folder selection dialog for the current project tab."""
        current_widget = self.ui.project_tabs.currentWidget()
        if not isinstance(current_widget, ProjectTabWidget):
            QMessageBox.warning(self.window, "No Active Project", "Please select a project tab first.")
            return

        current_dir = current_widget.get_config().directory or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self.window, "Select Project Folder", current_dir)

        if folder:
            folder_path = Path(folder)
            logger.info(f"Setting folder for project tab '{self.ui.project_tabs.tabText(self.ui.project_tabs.currentIndex())}': {folder_path}")
            current_widget.set_directory(folder_path) # This triggers scan internally
            self.ui.project_tabs.setTabText(self.ui.project_tabs.currentIndex(), folder_path.name) # Update tab title
            self.tab_manager.update_diff_apply_tab_root() # Update diff root via TabManager
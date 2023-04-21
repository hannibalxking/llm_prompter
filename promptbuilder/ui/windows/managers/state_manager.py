# promptbuilder/ui/windows/managers/state_manager.py

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Slot
from loguru import logger

from ...widgets.prompt_tab.project_tab import ProjectTabWidget
from ....config.loader import save_config
from ....services.theming import Theme, apply_theme

if TYPE_CHECKING:
    from ..main_window import MainWindow
    from ....config.loader import AppConfig
    from .status_manager import StatusManager


class StateManager(QObject):
    """Manages loading and saving application state."""

    def __init__(self, window: 'MainWindow', config: 'AppConfig', ui, status_manager: 'StatusManager'):
        super().__init__(window)
        self.window = window
        self.config = config
        self.ui = ui
        self.status_manager = status_manager

    def load_state(self):
        """Loads window geometry, state, and project tabs from configuration."""
        logger.info("Loading window state and project tabs...")
        self.window.restoreGeometry(self.config.window_geometry or b'')
        self.window.restoreState(self.config.window_state or b'')
        #if not self.config.window_geometry:
        self.window.resize(1300, 920) # Default size if no geometry saved

        # Tab loading is handled by TabManager, called after StateManager init
        # Theme application
        try:
            apply_theme(Theme(self.config.theme))
        except Exception as e:
            logger.exception("Error applying theme during state load.")

    def update_config_before_save(self):
        """Updates the global config object with the current UI state."""
        logger.debug("Updating config object before saving...")
        try:
            # Use toHex() to get a string representation, then encode to bytes
            self.config.window_geometry = self.window.saveGeometry().toHex().data()
            self.config.window_state = self.window.saveState().toHex().data()
        except Exception as e:
            logger.error(f"Could not save window geometry/state: {e}")

        self.config.tabs.clear()
        for i in range(self.ui.project_tabs.count()):
            widget = self.ui.project_tabs.widget(i)
            if isinstance(widget, ProjectTabWidget):
                tab_conf = widget.get_config() # Get config from the tab widget itself
                tab_conf.title = self.ui.project_tabs.tabText(i) # Update title from tab bar
                self.config.tabs.append(tab_conf)
            else:
                logger.warning(f"Widget at project tab index {i} is not a ProjectTabWidget.")
        logger.debug("Config object updated with window state and tab configurations.")

    @Slot()
    def save_state_now(self):
        """Saves the current application state to the config file immediately."""
        self.update_config_before_save()
        save_config(self.config)
        self.status_manager.show_status_message("Configuration saved.", 3000)
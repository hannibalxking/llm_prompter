# promptbuilder/ui/application.py
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from loguru import logger

from .windows.main_window import MainWindow
from ..config.loader import load_config, save_config, get_config
from ..services.theming import apply_theme, Theme
# from ..core.plugins import load_plugins # No longer loaded here

def run(argv=None):
    """Initializes and runs the QApplication."""
    if argv is None:
        argv = sys.argv

    # Enable High DPI support
    # AA_EnableHighDpiScaling is default in Qt6, AA_UseHighDpiPixmaps might be useful
    # QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)

    app = QApplication(argv)
    app.setOrganizationName("YourCompany") # Optional: For QSettings etc.
    app.setApplicationName("PromptBuilder")

    # Load configuration early
    try:
        config = load_config()
    except Exception as e:
        logger.exception("Fatal error loading configuration on startup.")
        # Show error message to user?
        QApplication.beep() # Simple feedback
        # Consider a minimal QMessageBox if possible here
        return 1 # Exit if config fails critically

    # Plugins are now loaded via promptbuilder/__init__.py

    # Apply theme based on config
    try:
        apply_theme(Theme(config.theme))
    except Exception as e:
        logger.exception("Error applying theme on startup.")


    # Create and show the main window
    try:
        main_window = MainWindow()
        main_window.show()
    except Exception as e:
        logger.exception("Fatal error creating or showing the main window.")
        # Show error message?
        QApplication.beep()
        return 1

    # --- Main application loop ---
    exit_code = app.exec()

    # --- Save configuration on exit ---
    # Get potentially updated config (e.g., window state) from main window
    # This assumes MainWindow updates the global config object or provides a method
    try:
        # Let MainWindow handle saving its state to the config object
        main_window.update_config_before_save()
        updated_config = get_config() # Get the potentially modified config
        save_config(updated_config)
    except Exception as e:
        logger.exception("Error saving configuration on exit.")

    logger.info(f"Application finished with exit code {exit_code}.")
    sys.exit(exit_code)
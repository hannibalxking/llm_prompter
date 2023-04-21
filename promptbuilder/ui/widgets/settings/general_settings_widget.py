# promptbuilder/ui/widgets/settings/general_settings_widget.py

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QComboBox,
                               QLabel, QGroupBox)
from loguru import logger

from ....config.loader import AppConfig


class GeneralSettingsWidget(QWidget):
    """
    Widget for displaying and modifying general application settings.
    """

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10) # Add some padding
        self.setLayout(main_layout)

        # --- Token Counter Group ---
        token_group = QGroupBox("Token Counter")
        token_layout = QFormLayout(token_group)

        self.backend_combo = QComboBox()
        self.backend_combo.addItems(["openai", "gemini"])
        token_layout.addRow(QLabel("Backend:"), self.backend_combo)

        # TODO: Add fields for model names if needed later
        # self.openai_model_edit = QLineEdit()
        # self.gemini_model_edit = QLineEdit()
        # token_layout.addRow(QLabel("OpenAI Model/Encoding:"), self.openai_model_edit)
        # token_layout.addRow(QLabel("Gemini Model:"), self.gemini_model_edit)

        main_layout.addWidget(token_group)
        main_layout.addStretch(1) # Push group to the top

    def _load_settings(self):
        """Loads current settings from the config object into the UI."""
        self.backend_combo.setCurrentText(self.config.token_counter_backend)

    def save_settings(self):
        """Saves the current UI settings back to the config object."""
        self.config.token_counter_backend = self.backend_combo.currentText()
        logger.debug(f"Saved token counter backend: {self.config.token_counter_backend}")
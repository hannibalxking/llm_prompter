# promptbuilder/ui/dialogs/settings_dialog.py

from PySide6.QtWidgets import (QDialog, QHBoxLayout, QVBoxLayout, QListWidget,
                               QStackedWidget, QDialogButtonBox, QListWidgetItem)
from PySide6.QtCore import Qt, Slot
from loguru import logger

from ...config.loader import AppConfig
from ..widgets.settings.general_settings_widget import GeneralSettingsWidget
# Import other settings widgets here as they are created
# from ..widgets.settings.appearance_settings_widget import AppearanceSettingsWidget


class SettingsDialog(QDialog):
    """
    Dialog window for application settings with category navigation.
    """

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Settings")
        self.setMinimumSize(600, 400)

        self._setup_ui()
        self._connect_signals()
        self._populate_categories()

        # Select the first category by default
        if self.category_list.count() > 0:
            self.category_list.setCurrentRow(0)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        content_layout = QHBoxLayout()
        main_layout.addLayout(content_layout, 1)

        # Left navigation list
        self.category_list = QListWidget()
        self.category_list.setMaximumWidth(150)
        content_layout.addWidget(self.category_list)

        # Right stacked widget for settings pages
        self.stacked_widget = QStackedWidget()
        content_layout.addWidget(self.stacked_widget, 1)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        main_layout.addWidget(button_box)

        # Connect buttons
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

    def _connect_signals(self):
        self.category_list.currentItemChanged.connect(self._on_category_changed)

    def _populate_categories(self):
        # Add General Settings
        self.general_settings_widget = GeneralSettingsWidget(self.config)
        self.stacked_widget.addWidget(self.general_settings_widget)
        self.category_list.addItem("General")

        # Add Appearance Settings (Example - create AppearanceSettingsWidget later)
        # self.appearance_settings_widget = AppearanceSettingsWidget(self.config)
        # self.stacked_widget.addWidget(self.appearance_settings_widget)
        # self.category_list.addItem("Appearance")

        # Add more categories here...

    @Slot(QListWidgetItem, QListWidgetItem)
    def _on_category_changed(self, current: QListWidgetItem, previous: QListWidgetItem):
        if current:
            self.stacked_widget.setCurrentIndex(self.category_list.row(current))

    def accept(self):
        """Saves changes from all settings widgets before closing."""
        logger.info("Saving settings from dialog...")
        self.general_settings_widget.save_settings()
        # Call save_settings() for other widgets here...
        super().accept()
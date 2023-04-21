# promptbuilder/ui/windows/main_window_ui.py

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QActionGroup
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
                               QTabWidget, QPushButton, QLabel, QStatusBar,
                               QProgressBar, QSizePolicy, QSpacerItem)

from ..widgets.diff_apply_tab.diff_apply_widget import DiffApplyWidget
from ..widgets.prompt_tab.prompt_panel import PromptPanelWidget
from ..widgets.prompt_tab.text_edit import PromptTextEdit
from ...services.theming import Theme # Needed for theme actions

if TYPE_CHECKING:
    from .main_window import MainWindow
    from .main_window_manager import MainWindowManager


class MainWindowUI:
    """Handles the creation and layout of UI elements for MainWindow."""

    def __init__(self, main_window: 'MainWindow'):
        self.window = main_window
        self.manager: 'MainWindowManager' = None # Will be set after manager is created

        self._setup_central_widget()
        self._setup_prompt_tab_ui(self.prompt_tab_layout)
        self._setup_diff_apply_tab_ui()
        self._add_tabs_to_top_level()
        self._setup_menus()
        self._setup_statusbar()

    def set_manager(self, manager: 'MainWindowManager'):
        """Sets the manager instance after it's created."""
        self.manager = manager
        # Connect theme actions now that manager is available
        self.auto_theme_action.triggered.connect(lambda: self.manager.change_theme(Theme.AUTO))
        self.light_theme_action.triggered.connect(lambda: self.manager.change_theme(Theme.LIGHT))
        self.dark_theme_action.triggered.connect(lambda: self.manager.change_theme(Theme.DARK))

    def _setup_central_widget(self):
        """Sets up the main central widget and top-level tabs."""
        self.top_level_tabs = QTabWidget()
        self.window.setCentralWidget(self.top_level_tabs)

        # Create container for "Prompt" tab content
        self.prompt_tab_widget = QWidget()
        self.prompt_tab_layout = QHBoxLayout(self.prompt_tab_widget)
        self.prompt_tab_layout.setContentsMargins(0, 0, 0, 0)

    def _setup_prompt_tab_ui(self, parent_layout: QHBoxLayout):
        """Creates the UI elements for the 'Prompt' tab."""
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        parent_layout.addWidget(main_splitter)

        self.project_tabs = QTabWidget()
        self.project_tabs.setTabsClosable(True)
        self.project_tabs.setMovable(True)

        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 5, 0)

        right_splitter = QSplitter(Qt.Orientation.Vertical)

        self.prompt_panel = PromptPanelWidget(self.window.config.prompt_snippets)
        right_splitter.addWidget(self.prompt_panel)

        preview_container = QWidget()
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(5, 5, 5, 5)
        preview_label = QLabel("Generated Prompt Preview")
        preview_label.setStyleSheet("font-weight: bold;")
        preview_layout.addWidget(preview_label)
        self.prompt_preview_edit = PromptTextEdit()
        preview_layout.addWidget(self.prompt_preview_edit)

        bottom_bar_layout = QHBoxLayout()
        self.clear_button = QPushButton("Clear All")
        self.copy_button = QPushButton("Copy")
        self.token_count_label = QLabel("Tokens: 0")
        bottom_bar_layout.addWidget(self.clear_button)
        bottom_bar_layout.addWidget(self.copy_button)
        bottom_bar_layout.addSpacerItem(QSpacerItem(10, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum))
        bottom_bar_layout.addWidget(self.token_count_label)
        bottom_bar_layout.addStretch(1)
        preview_layout.addLayout(bottom_bar_layout)

        right_splitter.addWidget(preview_container)
        right_layout.addWidget(right_splitter)

        main_splitter.addWidget(self.project_tabs)
        main_splitter.addWidget(right_container)

        # --- Prevent the left panel (project_tabs) from being collapsed ---
        main_splitter.setCollapsible(0, False) # Index 0 is project_tabs

        # Initial sizes will be restored by restoreState or set defaults
        main_splitter.setSizes([int(self.window.width() * 0.4), int(self.window.width() * 0.6)])
        right_splitter.setSizes([int(self.window.height() * 0.25), int(self.window.height() * 0.75)])

    def _setup_diff_apply_tab_ui(self):
        """Creates the UI elements for the 'Diff Apply' tab."""
        self.diff_apply_tab_widget = DiffApplyWidget()

    def _add_tabs_to_top_level(self):
        """Adds the created tab widgets to the main QTabWidget."""
        self.top_level_tabs.addTab(self.prompt_tab_widget, "Prompt")
        self.top_level_tabs.addTab(self.diff_apply_tab_widget, "Diff Apply")

    def _setup_menus(self):
        """Creates the main menu bar and actions."""
        menubar = self.window.menuBar()
        file_menu = menubar.addMenu("&File")
        self.new_tab_action = QAction("&New Project Tab", self.window)
        self.new_tab_action.setShortcut(QKeySequence.StandardKey.New)
        file_menu.addAction(self.new_tab_action)
        self.open_folder_action = QAction("&Open Folder in Tab...", self.window)
        self.open_folder_action.setShortcut(QKeySequence.StandardKey.Open)
        file_menu.addAction(self.open_folder_action)
        self.rename_tab_action = QAction("&Rename Current Tab...", self.window)
        file_menu.addAction(self.rename_tab_action)
        self.close_tab_action = QAction("&Close Current Tab", self.window)
        self.close_tab_action.setShortcut(QKeySequence.StandardKey.Close)
        file_menu.addAction(self.close_tab_action)
        file_menu.addSeparator()
        self.save_config_action = QAction("&Save Configuration", self.window)
        self.save_config_action.setShortcut(QKeySequence.StandardKey.Save)
        file_menu.addAction(self.save_config_action)
        file_menu.addSeparator()
        self.quit_action = QAction("&Quit", self.window)
        self.quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        file_menu.addAction(self.quit_action)

        edit_menu = menubar.addMenu("&Edit")
        self.copy_action = QAction("&Copy Prompt", self.window)
        self.copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        edit_menu.addAction(self.copy_action)
        self.clear_action = QAction("C&lear All Selections", self.window)
        edit_menu.addAction(self.clear_action)
        self.settings_action = QAction("&Settings...", self.window) # Add Settings action
        edit_menu.addAction(self.settings_action)

        view_menu = menubar.addMenu("&View")
        theme_menu = view_menu.addMenu("Theme")
        self.theme_group = QActionGroup(self.window)
        self.theme_group.setExclusive(True)
        self.auto_theme_action = QAction("Auto", self.window, checkable=True)
        self.light_theme_action = QAction("Light", self.window, checkable=True)
        self.dark_theme_action = QAction("Dark", self.window, checkable=True)
        self.theme_group.addAction(self.auto_theme_action)
        self.theme_group.addAction(self.light_theme_action)
        self.theme_group.addAction(self.dark_theme_action)
        theme_menu.addAction(self.auto_theme_action)
        theme_menu.addAction(self.light_theme_action)
        theme_menu.addAction(self.dark_theme_action)
        # Set initial check state based on config
        current_theme_str = self.window.config.theme
        if current_theme_str == Theme.LIGHT.value: self.light_theme_action.setChecked(True)
        elif current_theme_str == Theme.DARK.value: self.dark_theme_action.setChecked(True)
        else: self.auto_theme_action.setChecked(True)

        self.toggle_statusbar_action = QAction("Toggle Status Bar", self.window, checkable=True, checked=True)
        view_menu.addAction(self.toggle_statusbar_action)

        help_menu = menubar.addMenu("&Help")
        self.about_action = QAction("&About", self.window)
        help_menu.addAction(self.about_action)

    def _setup_statusbar(self):
        """Creates the status bar."""
        self.status_bar = QStatusBar(self.window)
        self.window.setStatusBar(self.status_bar)
        self.status_label = QLabel("Ready")
        self.status_progress = QProgressBar()
        self.status_progress.setRange(0, 0)
        self.status_progress.setVisible(False)
        self.status_progress.setFixedWidth(150)
        self.status_bar.addWidget(self.status_label, 1)
        self.status_bar.addPermanentWidget(self.status_progress)
# promptbuilder/ui/widgets/prompt_tab/project_tab.py

from pathlib import Path
from typing import List, Set

from PySide6.QtCore import Qt, Signal, Slot, QTimer, QObject
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                               QLineEdit, QLabel, QCheckBox, QFileDialog, QSizePolicy,
                               QMessageBox, QGridLayout)  # Added QGridLayout
from codemap import GRAPH
from codemap.builder import connected_files, build_codemap
from loguru import logger

from promptbuilder.config.loader import get_config
from promptbuilder.config.schema import TabConfig
# Import the *adapter* task
from promptbuilder.core.fs_scanner import FileScannerTask
from promptbuilder.core.models import FileNode
from promptbuilder.services.async_utils import run_in_background
from .file_tree import FileTreeWidget


class ProjectTabWidget(QWidget):
    """
    Widget contained within each tab, holding file tree and controls,
    including filtering and view options.
    """

    # Signals
    selection_changed = Signal() # Emitted when file selection changes
    scan_started = Signal()
    scan_finished = Signal(list) # Emits root FileNode list
    scan_progress = Signal(str)
    codemap_selection_requested = Signal(FileNode) # Signal for codemap context menu
    scan_error = Signal(str)

    def __init__(self, config: TabConfig, parent: QWidget | None = None):
        """Initializes the project tab."""
        super().__init__(parent)
        self.config = config
        self.current_scan_task_runner: FileScannerTask | None = None # Store the QRunnable adapter

        # Debounce timer for filter changes
        self.filter_debounce_timer = QTimer(self)
        self.filter_debounce_timer.setInterval(300) # ms delay
        self.filter_debounce_timer.setSingleShot(True)
        self.filter_debounce_timer.timeout.connect(self._apply_text_filter_to_tree) # Connect to text filter slot

        self._setup_ui()
        self._connect_signals()

        # Load initial state if directory is set
        if self.config.directory:
            self.directory_label.setText(f"Folder: {self.config.directory}")
            # Initial scan is triggered by MainWindow after tab is added and potentially made current

    def _setup_ui(self):
        """Creates and arranges UI elements."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(3) # Reduce gaps between elements
        self.setLayout(main_layout)

        # --- Top Control Bar ---
        control_bar = QHBoxLayout()
        self.select_folder_button = QPushButton("Select Folder...")
        control_bar.addWidget(self.select_folder_button)

        self.directory_label = QLabel(f"Folder: {self.config.directory or 'None selected'}")
        self.directory_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.directory_label.setWordWrap(True) # Allow long paths to wrap
        control_bar.addWidget(self.directory_label)

        self.refresh_button = QPushButton("Refresh")
        # REMOVED: self.select_codemap_button = QPushButton("Select Codemap")
        self.refresh_button.setEnabled(bool(self.config.directory)) # Enable only if dir is set
        control_bar.addWidget(self.refresh_button)
        # REMOVED: control_bar.addWidget(self.select_codemap_button)
        main_layout.addLayout(control_bar)

        # --- Filter Bar ---
        filter_bar = QHBoxLayout()
        filter_label = QLabel("Filter:")
        filter_bar.addWidget(filter_label)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter files/folders by name...")
        filter_bar.addWidget(self.filter_edit)
        main_layout.addLayout(filter_bar)

        # --- Options Checkbox Grid ---
        options_layout = QGridLayout() # Use grid for 2 columns
        options_layout.setSpacing(5) # Spacing between checkboxes
        options_layout.setContentsMargins(0, 2, 0, 5) # Tweak margins LTRB

        # Create checkboxes
        self.cb_ignore_env = QCheckBox("Ignore Env")
        self.cb_ignore_init = QCheckBox("Ignore __init__")
        self.cb_hide_system = QCheckBox("Hide System") # Note: Logic still pending
        self.cb_hide_unselected = QCheckBox("Hide Unselected") # New
        self.cb_expand_selection = QCheckBox("Expand Selection") # New
        self.cb_collapse_unselected = QCheckBox("Collapse Unselected") # New

        # Set default states
        self.cb_ignore_env.setChecked(True)
        self.cb_ignore_init.setChecked(True) # Changed default to True
        self.cb_hide_system.setChecked(False)
        self.cb_hide_unselected.setChecked(False) # Disabled by default
        self.cb_expand_selection.setChecked(True) # Enabled by default
        self.cb_collapse_unselected.setChecked(True) # Enabled by default

        # Add checkboxes to the grid layout (Row, Column)
        options_layout.addWidget(self.cb_ignore_env, 0, 0)
        options_layout.addWidget(self.cb_ignore_init, 1, 0)
        options_layout.addWidget(self.cb_hide_system, 2, 0)
        options_layout.addWidget(self.cb_hide_unselected, 0, 1)
        options_layout.addWidget(self.cb_expand_selection, 1, 1)
        options_layout.addWidget(self.cb_collapse_unselected, 2, 1)
        # Add stretch to the right column if needed, or adjust column stretch factors
        options_layout.setColumnStretch(0, 0) # Column 0 takes minimum space
        options_layout.setColumnStretch(1, 0) # Column 1 takes minimum space
        options_layout.setColumnStretch(2, 1) # Add a stretch column at the end

        main_layout.addLayout(options_layout) # Add the grid layout

        # --- File Tree ---
        self.file_tree = FileTreeWidget() # The actual tree view
        self.file_tree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        main_layout.addWidget(self.file_tree)

        # Set stretch factor for the tree to take up remaining space
        main_layout.setStretchFactor(self.file_tree, 1)


    def _connect_signals(self):
        """Connects UI element signals to appropriate slots."""
        self.select_folder_button.clicked.connect(self.select_directory)
        self.refresh_button.clicked.connect(self.scan_directory)
        # REMOVED: self.select_codemap_button.clicked.connect(self._select_codemap_slice)
        # Connect filter text changes to the debounce timer
        self.filter_edit.textChanged.connect(self.filter_debounce_timer.start)

        # Connect file tree's internal signal to this widget's signal AND local handlers
        self.file_tree.item_selection_changed.connect(self.selection_changed.emit)
        self.file_tree.item_selection_changed.connect(self._handle_selection_change_effects) # Handles view options

        # Connect scan option checkbox signals
        self.cb_ignore_env.stateChanged.connect(self._on_scan_option_changed)
        self.cb_ignore_init.stateChanged.connect(self._on_scan_option_changed)
        self.cb_hide_system.stateChanged.connect(self._on_scan_option_changed) # Connect even if logic not implemented

        # Connect view option checkbox signals
        self.cb_hide_unselected.stateChanged.connect(self._on_view_option_changed)
        self.cb_expand_selection.stateChanged.connect(self._on_view_option_changed)
        self.cb_collapse_unselected.stateChanged.connect(self._on_view_option_changed)

        # Connect codemap request signal from file tree
        self.file_tree.codemap_requested.connect(self._select_codemap_slice)

    # --- Public API (No changes needed) ---

    def get_config(self) -> TabConfig:
        """Returns the current configuration state of this tab."""
        # TODO: Potentially store view option states in TabConfig if persistence is needed
        return self.config

    def set_directory(self, directory: Path):
        """Sets the root directory for this tab and triggers a scan."""
        if not directory.is_dir():
             logger.error(f"Invalid directory selected: {directory}")
             QMessageBox.warning(self, "Invalid Folder", f"The selected path is not a valid folder:\n{directory}")
             return

        resolved_dir = str(directory.resolve())
        self.config.directory = resolved_dir
        self.directory_label.setText(f"Folder: {resolved_dir}")
        self.directory_label.setToolTip(resolved_dir) # Show full path on hover
        self.refresh_button.setEnabled(True)
        logger.info(f"Directory set for tab: {resolved_dir}")
        self.scan_directory() # Automatically scan when directory is set

    @Slot()
    def scan_directory(self):
        """Initiates a file scan for the configured directory using the adapter task."""
        if not self.config.directory:
            logger.warning("Scan requested but no directory is set for this tab.")
            return

        if self.current_scan_task_runner:
            logger.warning("Scan already in progress, cancelling previous.")
            self.cancel_scan()
            QTimer.singleShot(50, self._start_scan_task) # Short delay to allow cancellation processing
        else:
             self._start_scan_task()


    def _start_scan_task(self):
        """Internal helper to create and run the scan task."""
        if not self.config.directory: return # Should not happen if called correctly

        root_path = Path(self.config.directory)
        logger.info(f"Starting scan task for: {root_path}")
        self.scan_started.emit()
        self.file_tree.clear_tree() # Clear tree before scan
        self.file_tree.show_loading_indicator(True) # Show loading state

        # Get ignore patterns from global config
        ignore_patterns = get_config().ignore_patterns

        # Get state of ignore checkboxes
        ignore_env_flag = self.cb_ignore_env.isChecked()
        ignore_init_flag = self.cb_ignore_init.isChecked()
        hide_system_flag = self.cb_hide_system.isChecked() # Get state

        logger.debug(f"Scan options: ignore_env={ignore_env_flag}, ignore_init={ignore_init_flag}, hide_system={hide_system_flag}")

        # Create the *adapter* task, passing the flags
        scan_task = FileScannerTask(
            root_path=root_path,
            ignore_patterns=ignore_patterns,
            ignore_env=ignore_env_flag,
            ignore_init=ignore_init_flag,
            hide_system=hide_system_flag # Pass flag
        )
        self.current_scan_task_runner = scan_task # Store reference

        # Connect signals for this specific task run
        scan_task.signals.finished.connect(
            lambda nodes, task=scan_task: self._on_scan_task_finished(nodes, task)
        )
        scan_task.signals.error.connect(
            lambda msg, task=scan_task: self._on_scan_task_error(msg, task)
        )
        scan_task.signals.progress.connect(self.scan_progress.emit) # Pass progress through

        # Run the adapter task in the background
        run_in_background(scan_task)


    def cancel_scan(self):
        """Requests cancellation of the current scan task adapter."""
        if self.current_scan_task_runner:
            logger.info("Requesting scan cancellation via adapter.")
            self.current_scan_task_runner.cancel() # Call cancel on the adapter
            # Do not clear reference here, let the signal handlers do it


    def get_selected_nodes(self) -> List[FileNode]:
        """Returns a list of the currently selected FileNode objects."""
        return self.file_tree.get_selected_nodes()

    def get_selected_file_paths(self) -> Set[Path]:
        """Returns a set of paths for all selected *files* (recursive for dirs)."""
        return self.file_tree.get_selected_file_paths() # Delegate to tree widget


    def clear_selection(self):
        """Clears the selection in the file tree."""
        self.file_tree.uncheck_all_items() # Use the specific method


    # --- Slots ---

    @Slot()
    def select_directory(self):
        """Opens the folder selection dialog."""
        current_dir = self.config.directory or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Select Project Folder", current_dir)
        if folder:
            self.set_directory(Path(folder))

    @Slot()
    def _apply_text_filter_to_tree(self):
        """Applies the text filter to the file tree (called by debounce timer)."""
        logger.debug("Applying debounced text filter.")
        # Trigger the combined filter update in the tree
        self.file_tree.apply_filters(
            text_filter=self.filter_edit.text(),
            hide_unselected=self.cb_hide_unselected.isChecked()
        )

    @Slot(int)
    def _on_scan_option_changed(self, state: int):
        """Triggers a rescan when an ignore checkbox changes state."""
        sender = self.sender()
        if isinstance(sender, QCheckBox):
            logger.info(f"Scan option '{sender.text()}' changed state. Triggering rescan.")
            # Trigger a rescan only if a directory is actually selected
            if self.config.directory:
                self.scan_directory()
            else:
                logger.debug("Scan option changed, but no directory selected. Scan not triggered.")

    @Slot(int)
    def _on_view_option_changed(self, state: int):
        """Applies view changes (filtering, expanding/collapsing) when view checkboxes change."""
        sender = self.sender()
        if isinstance(sender, QCheckBox):
            logger.info(f"View option '{sender.text()}' changed state. Applying effects.")
            # Apply relevant view effects immediately
            self._handle_selection_change_effects()


    @Slot()
    def _handle_selection_change_effects(self):
        """Applies filtering/expansion/collapsing based on checkbox states."""
        logger.debug("Handling selection change effects (filter/expand/collapse).")
        # Apply hide unselected filter if active
        self.file_tree.apply_filters(
            text_filter=self.filter_edit.text(), # Pass current text filter
            hide_unselected=self.cb_hide_unselected.isChecked()
        )
        # Apply expand selection if active
        if self.cb_expand_selection.isChecked():
            self.file_tree.expand_selected_parents()
        # Apply collapse unselected if active
        if self.cb_collapse_unselected.isChecked():
            self.file_tree.collapse_unselected_items()


    @Slot(list, QObject) # Receives list[FileNode], Task instance
    def _on_scan_task_finished(self, root_nodes: List[FileNode], task: FileScannerTask):
        """Handles the successful completion of the scan task adapter."""
        if task != self.current_scan_task_runner:
             logger.warning("Received 'finished' signal from an outdated scan task. Ignoring.")
             return

        logger.info("Scan task finished successfully.")
        self.file_tree.show_loading_indicator(False)
        self.current_scan_task_runner = None # Clear task reference
        if root_nodes:
            self.file_tree.populate_tree(root_nodes[0]) # Populate with the first root
            # Apply initial filter/expand/collapse state after population
            self._handle_selection_change_effects()
        else:
             logger.warning("Scan finished but returned no root nodes (possibly all ignored).")
             self.file_tree.clear_tree() # Ensure tree is empty
        self.scan_finished.emit(root_nodes) # Forward the result

    @Slot(str, QObject) # Receives error_message, Task instance
    def _on_scan_task_error(self, error_message: str, task: FileScannerTask):
        """Handles errors from the scan task adapter."""
        if task != self.current_scan_task_runner:
             logger.warning("Received 'error' signal from an outdated scan task. Ignoring.")
             return

        logger.error(f"Scan task failed: {error_message}")
        self.file_tree.show_loading_indicator(False)
        self.current_scan_task_runner = None # Clear task reference
        self.file_tree.clear_tree() # Clear tree on error
        self.scan_error.emit(error_message) # Forward the error

    # ------------------------------------------------------------------
    @Slot(FileNode) # Accept FileNode from signal
    def _select_codemap_slice(self, seed_node: FileNode):
        """
        Selects files based on codemap slice and applies view options.
        Triggered by context menu action via signal.
        """
        if not seed_node or seed_node.is_dir:
            logger.warning("Codemap slice requested for invalid node.")
            # Should not happen if context menu logic is correct
            QMessageBox.warning(self, "Codemap Error", "Codemap selection requires a file.")
            return
        seed = seed_node.path # Get the path from the node

        project_root = Path(self.config.directory)
        if not GRAPH:
            try:
                potential_src_dir = project_root / "src" # Example common src dir
                codemap_target = project_root
                if (project_root / "core").is_dir():
                     codemap_target = project_root / "core"
                elif potential_src_dir.is_dir():
                     codemap_target = potential_src_dir

                logger.info(f"Building codemap for target: {codemap_target}")
                build_codemap(codemap_target)
            except Exception as e:
                logger.exception(f"Failed to build codemap: {e}")
                QMessageBox.warning(self, "Codemap error", f"Failed to build codemap:\n{e}")
                return

        try:
            slice_paths = connected_files(seed)
        except KeyError as e:
            logger.warning(f"Codemap key error for seed '{seed}': {e}")
            QMessageBox.warning(self, "Codemap selection", f"File not found in codemap index:\n{e}\n\nTry rebuilding the codemap if files changed.")
            return
        except Exception as e:
             logger.exception(f"Error getting connected files from codemap: {e}")
             QMessageBox.warning(self, "Codemap Error", f"Error retrieving file connections:\n{e}")
             return


        # Tick every file in the slice
        checked_count = 0
        # Block tree signals temporarily during bulk check state changes
        self.file_tree.blockSignals(True)
        try:
            for p in slice_paths:
                # Ensure path exists in the node map before trying to check it
                item = self.file_tree._node_map.get(p)
                if item:
                     if item.checkState(0) != Qt.CheckState.Checked:
                         # Use the internal method to ensure propagation if needed
                         self.file_tree._set_item_checked_state(item, Qt.CheckState.Checked)
                         checked_count += 1
                else:
                     logger.warning(f"Path from codemap slice not found in file tree: {p}")
        finally:
            self.file_tree.blockSignals(False) # Re-enable signals

        logger.info(f"Codemap selection added {checked_count} file(s) based on slice from '{seed.name}'. Slice contained {len(slice_paths)} paths total.")
        if checked_count < len(slice_paths):
             logger.warning(f"{len(slice_paths) - checked_count} path(s) from codemap slice were not found in the current file tree view.")

        # Explicitly trigger selection change effects after codemap selection
        self._handle_selection_change_effects()
        # Also emit the main selection changed signal so the prompt rebuilds
        self.selection_changed.emit()
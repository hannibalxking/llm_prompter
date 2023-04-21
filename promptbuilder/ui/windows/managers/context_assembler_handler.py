# promptbuilder/ui/windows/managers/context_assembler_handler.py

import html
from pathlib import Path
from typing import TYPE_CHECKING, Set

from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QMessageBox
from loguru import logger

from ....core.context_assembler import ContextAssemblerTask
from ....core.models import ContextResult
from ....core.token_counter import UnifiedTokenCounter
from ...widgets.prompt_tab.project_tab import ProjectTabWidget

if TYPE_CHECKING:
    from ..main_window import MainWindow
    from ....config.loader import AppConfig
    from ....core.prompt_engine import PromptEngine
    from .status_manager import StatusManager

from ....services.async_utils import run_in_background # Import the utility function


class ContextAssemblerHandler(QObject):
    """Handles the logic for assembling prompt context."""

    def __init__(self, window: 'MainWindow', config: 'AppConfig', prompt_engine: 'PromptEngine', ui, status_manager: 'StatusManager'):
        super().__init__(window)
        self.window = window
        self.config = config
        self.prompt_engine = prompt_engine
        self.ui = ui
        self.status_manager = status_manager
        self.current_context_task_runner: ContextAssemblerTask | None = None
        # No longer need a token counter instance here, it's created in the core/task

    def reinitialize_token_counter(self):
        """Creates a new token counter instance based on current config."""
        # This method is now redundant here but kept for compatibility with manager calls
        # The actual counter used is created in the task/core
        logger.debug("ContextAssemblerHandler.reinitialize_token_counter called (no-op).")
        pass


    def is_task_running(self) -> bool:
        """Checks if a context assembly task is currently active."""
        return self.current_context_task_runner is not None

    def cancel_task(self):
        """Cancels the currently running context assembly task."""
        if self.current_context_task_runner:
            self.current_context_task_runner.cancel()

    @Slot()
    def trigger_context_assembly(self):
        """Gathers selections and triggers context assembly task."""
        if self.current_context_task_runner:
            logger.warning("Cancelling previous context assembly task.")
            self.current_context_task_runner.cancel()
            # Task runner reference will be cleared by its finish/error signal handler

        current_widget = self.ui.project_tabs.currentWidget()
        current_index = self.ui.project_tabs.currentIndex()

        if current_index == -1 or not isinstance(current_widget, ProjectTabWidget):
            logger.warning(f"No active ProjectTabWidget found for context assembly. Index: {current_index}, Widget: {type(current_widget)}")
            self.ui.prompt_preview_edit.setPlainText("<instructions>\n</instructions>\n\n<context>\n    <error>No active project tab selected.</error>\n</context>")
            self.status_manager.update_token_count("")
            self.status_manager.show_status_message("Error: No active project tab", 5000)
            return

        selected_paths: Set[Path] = current_widget.get_selected_file_paths()
        selected_snippets, _ = self.ui.prompt_panel.get_selected_items()
        instructions_xml = self.prompt_engine.build_instructions_xml(selected_snippets, set())

        if not selected_paths:
            logger.debug("No files selected in the current project tab.")
            final_prompt = instructions_xml + "\n\n<context>\n</context>"
            self.ui.prompt_preview_edit.setPlainText(final_prompt)
            self.status_manager.update_token_count(final_prompt)
            self.status_manager.show_status_message("Ready (No files selected)", 5000, show_progress=False)
            current_widget.file_tree.clear_token_counts()
            self.current_context_task_runner = None # Ensure runner is cleared
            return

        project_root_str = current_widget.get_config().directory
        if not project_root_str:
             logger.error("Cannot assemble context: Project root directory not set.")
             QMessageBox.critical(self.window, "Error", "Project folder not set for the current tab.")
             self.status_manager.show_status_message("Error: Project folder not set", 0)
             return
        project_root_path = Path(project_root_str)

        logger.info(f"Starting context assembly task for {len(selected_paths)} files from tab '{self.ui.project_tabs.tabText(self.ui.project_tabs.currentIndex())}'.")
        self.status_manager.show_status_message("Assembling context...", 0, show_progress=True)
        current_widget.file_tree.clear_token_counts()

        context_task = ContextAssemblerTask(
            project_root_path=project_root_path,
            selected_paths=selected_paths,
            max_tokens=self.config.max_context_tokens,
            secret_patterns=self.config.secret_patterns,
            # --- NEW: Pass current token counter settings ---
            token_counter_backend=self.config.token_counter_backend,
            token_counter_model_openai=self.config.token_counter_model_openai,
            token_counter_model_gemini=self.config.token_counter_model_gemini
        )
        self.current_context_task_runner = context_task

        context_task.signals.finished.connect(self.on_context_assembly_finished)
        context_task.signals.error.connect(self.on_context_assembly_error)
        context_task.signals.progress.connect(self.status_manager.show_status_message) # Connect progress directly
        run_in_background(context_task) # Use the imported utility function

    @Slot(object) # Receives ContextResult
    def on_context_assembly_finished(self, result: ContextResult):
        """Handles successful context assembly."""
        logger.info(f"Context assembly finished. Tokens: {result.total_tokens}. Budget: {result.budget_details}")
        self.current_context_task_runner = None
        self.status_manager.show_status_message(f"Context ready. {result.budget_details or 'All files included.'}", 5000, show_progress=False)

        selected_snippets, _ = self.ui.prompt_panel.get_selected_items()
        instructions_xml = self.prompt_engine.build_instructions_xml(selected_snippets, set())
        final_prompt = instructions_xml + "\n\n" + result.context_xml

        self.ui.prompt_preview_edit.setPlainText(final_prompt)
        # Pass the known_tokens from the result (calculated by the correct counter in the task)
        self.status_manager.update_token_count(final_prompt, result.total_tokens)

        current_widget = self.ui.project_tabs.currentWidget()
        if isinstance(current_widget, ProjectTabWidget):
            current_widget.file_tree.update_token_counts(result)
        else: logger.warning("Could not update token counts: No active ProjectTabWidget found.")

    @Slot(str) # Receives error_message
    def on_context_assembly_error(self, error_message: str):
        """Handles context assembly errors."""
        logger.error(f"Context assembly failed: {error_message}")
        self.current_context_task_runner = None
        self.status_manager.show_status_message(f"Error: {error_message}", 0, show_progress=False) # Show error, hide progress

        is_cancel = "cancel" in error_message.lower()
        if not is_cancel:
            QMessageBox.warning(self.window, "Context Error", f"Failed to assemble context:\n{error_message}")
        else:
            self.status_manager.show_status_message("Context assembly cancelled.", 4000) # Override error message for cancel

        selected_snippets, _ = self.ui.prompt_panel.get_selected_items()
        instructions_xml = self.prompt_engine.build_instructions_xml(selected_snippets, set())
        safe_error = html.escape(error_message)
        error_context = f"\n\n<context>\n    <error>{safe_error}</error>\n</context>"
        final_prompt = instructions_xml + error_context
        self.ui.prompt_preview_edit.setPlainText(final_prompt)
        # Use the StatusManager's counter for the full prompt text estimate
        self.status_manager.update_token_count(final_prompt)

        current_widget = self.ui.project_tabs.currentWidget()
        if isinstance(current_widget, ProjectTabWidget):
            current_widget.file_tree.clear_token_counts()
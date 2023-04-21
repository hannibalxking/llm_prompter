# promptbuilder/ui/windows/managers/status_manager.py

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Slot
from loguru import logger

from ....core.token_counter import UnifiedTokenCounter

if TYPE_CHECKING:
    from ..main_window import MainWindow


class StatusManager(QObject):
    """Manages updates to the status bar."""

    def __init__(self, window: 'MainWindow', ui):
        super().__init__(window)
        self.window = window
        self.ui = ui
        self.token_counter: UnifiedTokenCounter | None = None
        self.reinitialize_token_counter() # Initialize on creation

    def reinitialize_token_counter(self):
        """Creates a new token counter instance based on current config."""
        backend = self.window.config.token_counter_backend # Access config via window
        model = self.window.config.token_counter_model_openai if backend == "openai" else self.window.config.token_counter_model_gemini
        self.token_counter = UnifiedTokenCounter(backend=backend, model_name=model)
        logger.info(f"Reinitialized StatusManager token counter. Backend: {backend}, Model: {model}")

    def check_tiktoken_availability(self):
        """Checks if tiktoken is available and shows a status bar warning if not."""
        # The UnifiedTokenCounter logs warnings internally if tiktoken is unavailable.
        # We no longer need to show a persistent status bar message here.
        pass # Keep the method signature for now, but logic is removed.


    @Slot(str)
    @Slot(str, int)
    def show_status_message(self, message: str, timeout: int = 0, show_progress: bool | None = None):
        """Displays a message in the status bar."""
        # Prevent transient messages from overwriting the persistent tiktoken warning
        # if self._tiktoken_warning_shown and "Token counts are estimated" in self.ui.status_label.text() and timeout > 0:
        #     logger.trace(f"Skipping transient status message '{message}' due to active tiktoken warning.")
        #     return

        self.ui.status_label.setText(message)
        if timeout <= 0: self.ui.status_bar.clearMessage() # Clear any previous timed message
        else: self.ui.status_bar.showMessage(message, timeout) # Show new timed message

        if show_progress is True: self.ui.status_progress.setVisible(True)
        elif show_progress is False: self.ui.status_progress.setVisible(False)

    def update_token_count(self, text: str, known_tokens: int | None = None):
        """Update token count label in the UI."""
        prefix = "Tokens:"
        if known_tokens is not None:
            count_str = f"{known_tokens:,}"
        else:
            try:
                count_str = f"{self.token_counter.count(text):,}" if self.token_counter else "N/A" # Use counter instance
            except Exception as e:
                logger.error(f"Token count failed: {e}")
                count_str = "Error"
        self.ui.token_count_label.setText(f"{prefix} {count_str}")
# promptbuilder/ui/widgets/prompt_tab/text_edit.py

from PySide6.QtCore import Slot
from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import QTextEdit, QSizePolicy

# Import the new highlighter
from .syntax_highlighter import PythonHighlighter


class PromptTextEdit(QTextEdit):
    """
    Text edit for displaying the generated prompt, with syntax highlighting.
    Allows manual editing.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # self.setReadOnly(True) # Allow editing
        self.setAcceptRichText(False) # Work with plain text
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth) # Wrap lines

        # Ensure long lines without spaces can wrap (useful for editable text too)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAnywhere)

        # Optional: Slightly adjust background for visual distinction if needed
        # pal = self.palette()
        # pal.setColor(QPalette.ColorRole.Base, pal.color(QPalette.ColorRole.AlternateBase))
        # self.setPalette(pal)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # --- Add Syntax Highlighter ---
        # Create an instance of the highlighter and associate it with this widget's document
        self.highlighter = PythonHighlighter(self.document())
        # -----------------------------


    @Slot(str)
    def setPlainText(self, text: str):
        """Sets the plain text content, ensuring read-only state and cursor position."""
        # Ensure read-only state just in case it was changed elsewhere
        # self.setReadOnly(True) # Already set in __init__
        super().setPlainText(text)
        # Move cursor to the beginning after setting text for consistent view
        cursor = self.textCursor()
        cursor.movePosition(cursor.MoveOperation.Start)
        self.setTextCursor(cursor)
        # Note: The highlighter will automatically re-highlight when text is set.
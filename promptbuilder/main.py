# promptbuilder/main.py
"""
Entry point for the PromptBuilder GUI application.

Ensures the project root is in sys.path when run directly,
sets up logging, and launches the Qt application via application.run().
"""
import sys
import os
# Moved imports to top after standard libs
from promptbuilder.ui.application import run
from promptbuilder.services.logging import setup_logging

# Ensure the package root is discoverable, especially when run with `python -m`
# or potentially from a PyInstaller bundle where paths can be tricky.
if __package__ is None and not hasattr(sys, "frozen"):
    # Direct execution: add project root to sys.path
    path = os.path.realpath(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(path)))
if __name__ == "__main__":
    setup_logging(verbose=True) # Configure logging early
    run(sys.argv)
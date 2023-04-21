# promptbuilder/services/logging.py
import sys
from loguru import logger
from pathlib import Path

from ..config.paths import get_user_log_dir, is_frozen

def setup_logging(level="INFO", verbose=False):
    """Configures logging using Loguru."""
    log_level = "DEBUG" if verbose else level
    log_dir = get_user_log_dir()
    log_file_path = log_dir / "promptbuilder_{time:YYYY-MM-DD}.log"
    log_file_str = str(log_file_path)

    # Remove default handler
    logger.remove()

    # --- FIX: Check if sys.stderr exists before adding console handler ---
    if sys.stderr:
        # Use simplified format for console, full format for file
        fmt_console = "<level>{level: <8}</level> | <cyan>{name}:{function}:{line}</cyan> - <level>{message}</level>"
        logger.add(
            sys.stderr,
            level=log_level,
            format=fmt_console,
            colorize=True,
            enqueue=True # Make logging calls non-blocking
        )
        logger.debug("Console logger added.")
    else:
        logger.info("sys.stderr not available, skipping console logger setup.")
        # Optionally, add a fallback handler here if console output is critical
        # e.g., logging to a specific fallback file or using a different mechanism.
    # --- END FIX ---

    # --- DELETE THIS DUPLICATED BLOCK ---
    # Console handler (colored)
    # Use simplified format for console, full format for file
    # fmt_console = "<level>{level: <8}</level> | <cyan>{name}:{function}:{line}</cyan> - <level>{message}</level>"
    # Only add console logger if not running frozen (e.g., in dev) or if explicitly enabled?
    # For now, always add it.
    # logger.add(
    #     sys.stderr,
    #     level=log_level,
    #     format=fmt_console,
    #     colorize=True,
    #     enqueue=True # Make logging calls non-blocking
    # )
    # --- END DELETED BLOCK ---


    # File handler (remains the same)
    fmt_file = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {process} | {thread} | {name}:{function}:{line} - {message}"  # Use {thread} (ID) instead of {thread_name}
    try:
        logger.add(
            log_file_str, level="DEBUG", format=fmt_file, rotation="1 day",
            retention="7 days", compression="zip", enqueue=False, encoding="utf-8"
        )
        logger.info(f"File logging initialized. Level: {log_level}. Log file: {log_file_str}")
    except Exception as e:
         logger.error(f"Could not configure file logging to {log_file_str}: {e}")
         logger.warning("File logging disabled.")
# promptbuilder/services/async_utils.py
from PySide6.QtCore import QThreadPool, QRunnable, QTimer
from typing import Callable
from loguru import logger

_thread_pool: QThreadPool | None = None

def get_global_thread_pool() -> QThreadPool:
    """Gets the global QThreadPool instance, creating if necessary."""
    global _thread_pool
    if _thread_pool is None:
        _thread_pool = QThreadPool.globalInstance()
        # Configure pool (optional)
        # _thread_pool.setMaxThreadCount(4)
        logger.info(f"Initialized global QThreadPool. Max threads: {_thread_pool.maxThreadCount()}")
    return _thread_pool

def run_in_background(runnable: QRunnable):
    """Submits a QRunnable task to the global thread pool."""
    pool = get_global_thread_pool()
    logger.debug(f"Submitting task {type(runnable).__name__} to thread pool. Active threads: {pool.activeThreadCount()}")
    # QThreadPool takes ownership and deletes the runnable when done by default
    pool.start(runnable)

# --- Debounce Decorator ---
# Be careful with decorators on methods in Qt classes due to metaclass interactions
# A helper function might be safer sometimes.

def debounce(interval_ms: int):
    """
    Decorator to debounce a function call using QTimer.
    Only the last call within the interval will execute.
    Assumes the decorated function/method is called from the Qt main thread.
    """
    def decorator(func: Callable):
        timer = None
        last_args = []
        last_kwargs = {}

        def trigger(*args, **kwargs):
            nonlocal timer, last_args, last_kwargs
            last_args = args
            last_kwargs = kwargs

            if timer is None:
                # Create timer on first call
                timer = QTimer()
                timer.setSingleShot(True)
                timer.setInterval(interval_ms)
                # Use a lambda to capture the correct args/kwargs at timeout
                timer.timeout.connect(lambda: func(*last_args, **last_kwargs)) # type: ignore

            # (Re)start the timer
            timer.start()

        # If decorating a method, need to handle 'self'
        # This basic version might not work perfectly on methods without adjustments
        # Consider using a helper class instance stored on the object if needed.
        return trigger
    return decorator
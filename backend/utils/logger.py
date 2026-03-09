"""
Logging configuration for Person Detection System
"""
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from datetime import datetime


class WindowsSafeRotatingFileHandler(RotatingFileHandler):
    """
    Windows-compatible RotatingFileHandler that handles file locking issues
    when multiple processes write to the same log file.
    """
    def doRollover(self):
        """
        Override doRollover to handle Windows file locking gracefully
        """
        try:
            super().doRollover()
        except (OSError, PermissionError) as e:
            # Log rotation failed - continue logging to current file
            # This can happen on Windows when multiple processes hold the file
            pass


def setup_logger(name: str = "person_detection", log_dir: str = "logs", level: str = "INFO") -> logging.Logger:
    """
    Setup logger with console and file handlers

    Args:
        name: Logger name
        log_dir: Directory for log files
        level: Logging level (DEBUG, INFO, WARNING, ERROR)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    # Create log directory
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Formatter
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler with UTF-8 encoding for Windows emoji support
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    # Force UTF-8 encoding on Windows to support emoji
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass  # Ignore if reconfigure fails
    logger.addHandler(console_handler)

    # File handler with size-based rotation (Windows compatible)
    # Use daily log file name but rotate by size instead of time
    log_file = log_path / f"detection_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = WindowsSafeRotatingFileHandler(
        log_file,
        maxBytes=50 * 1024 * 1024,  # 50MB per file
        backupCount=30,
        encoding='utf-8',
        delay=True  # Delay file opening to avoid permission issues
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


# Global logger instance
logger = setup_logger()

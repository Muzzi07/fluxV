"""
Logging utilities for fluxV
"""
import logging
import sys
from typing import Optional
from datetime import datetime


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for console output"""
    
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
        'RESET': '\033[0m'        # Reset
    }
    
    def format(self, record):
        levelname = record.levelname
        if levelname in self.COLORS:
            color = self.COLORS[levelname]
            reset = self.COLORS['RESET']
            record.levelname = f"{color}{levelname}{reset}"
        return super().format(record)


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    colored: bool = True
):
    """
    Setup logging configuration.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (optional)
        colored: Use colored output for console
    """
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, level.upper()))
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    if colored:
        formatter = ColoredFormatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    # Suppress noisy third-party logs
    logging.getLogger('MetaTrader5').setLevel(logging.WARNING)


class AsyncLogger:
    """Async-safe logger wrapper"""
    
    def __init__(self, name: str):
        self._logger = logging.getLogger(name)
    
    async def debug(self, message: str, *args, **kwargs):
        """Async debug log"""
        self._logger.debug(message, *args, **kwargs)
    
    async def info(self, message: str, *args, **kwargs):
        """Async info log"""
        self._logger.info(message, *args, **kwargs)
    
    async def warning(self, message: str, *args, **kwargs):
        """Async warning log"""
        self._logger.warning(message, *args, **kwargs)
    
    async def error(self, message: str, *args, **kwargs):
        """Async error log"""
        self._logger.error(message, *args, **kwargs)
    
    async def critical(self, message: str, *args, **kwargs):
        """Async critical log"""
        self._logger.critical(message, *args, **kwargs)
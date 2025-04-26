# Sets up consistent logging across all scripts
# Supports both file and console logging
# Includes automatic log file naming and directory creation
# Provides utility functions for tracking execution time
# Flexible configuration for different logging needs

import logging
import os
import sys
from datetime import datetime

# Constants
DEFAULT_LOG_LEVEL = logging.INFO
DEFAULT_LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
DEFAULT_LOG_DIR = 'logs'

def setup_logger(name, log_level=None, log_file=None, log_format=None, console_output=True):
    """Configure and return a logger with file and/or console handlers.

    Args:
        name: Logger name, typically the module name
        log_level: Logging level (default: INFO)
        log_file: Optional log file path. If None, uses 'logs/{name}_{date}.log'
        log_format: Log message format
        console_output: Whether to output to console

    Returns:
        logging.Logger: Configured logger
    """
    # Create logger
    logger = logging.getLogger(name)

    # Set log level
    level = log_level or DEFAULT_LOG_LEVEL
    logger.setLevel(level)

    # Clear existing handlers (to avoid duplicates if called multiple times)
    if logger.handlers:
        logger.handlers.clear()

    # Log format
    formatter = logging.Formatter(log_format or DEFAULT_LOG_FORMAT)

    # Add console handler if requested
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # Add file handler if log_file provided or DEFAULT_LOG_DIR exists
    if log_file or os.path.exists(DEFAULT_LOG_DIR) or os.makedirs(DEFAULT_LOG_DIR, exist_ok=True):
        # Generate default log filename if not provided
        if not log_file:
            date_str = datetime.now().strftime('%Y%m%d_%H%M%S')
            log_file = os.path.join(DEFAULT_LOG_DIR, f"{name}_{date_str}.log")

        # Ensure directory exists
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        # Add file handler
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        logger.info(f"Logging to file: {log_file}")

    return logger

def get_log_level_from_string(level_str):
    """Convert string log level to logging module constant.

    Args:
        level_str: String log level ('DEBUG', 'INFO', etc.)

    Returns:
        int: Logging level constant
    """
    levels = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL,
    }

    return levels.get(level_str.upper(), DEFAULT_LOG_LEVEL)

def configure_root_logger(log_level=None, log_file=None):
    """Configure the root logger (affects all unconfigured loggers).

    Args:
        log_level: Logging level
        log_file: Log file path

    Returns:
        logging.Logger: Root logger
    """
    return setup_logger('root', log_level, log_file)

def log_execution_time(logger, start_time, description="Operation"):
    """Log the execution time of an operation.

    Args:
        logger: Logger instance
        start_time: Start time from datetime.now()
        description: Description of the operation
    """
    elapsed = datetime.now() - start_time
    logger.info(f"{description} completed in {elapsed.total_seconds():.2f} seconds")
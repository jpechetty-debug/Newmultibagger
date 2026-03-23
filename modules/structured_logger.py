import logging
import json
import datetime
import os
import sys

class JSONFormatter(logging.Formatter):
    """Custom JSON Formatter for structured logging."""
    def format(self, record):
        log_record = {
            "timestamp": datetime.datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "func": record.funcName,
            "message": record.getMessage()
        }
        # Include extra context if provided
        if hasattr(record, "extra_context"):
            log_record.update(record.extra_context)
            
        # Include exception info if present
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_record)

class ConsoleFormatter(logging.Formatter):
    """Clean color-coded formatter for terminal output."""
    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    format_str = "%(asctime)s - %(levelname)s - %(message)s"

    FORMATS = {
        logging.DEBUG: grey + format_str + reset,
        logging.INFO: grey + format_str + reset,
        logging.WARNING: yellow + format_str + reset,
        logging.ERROR: red + format_str + reset,
        logging.CRITICAL: bold_red + format_str + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt="%H:%M:%S")
        return formatter.format(record)

def get_structured_logger(name="sovereign", log_file="logs/sovereign.json"):
    """Initialize and return a structured logger."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    # Ensure log directory exists
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    # 1. JSON File Handler (Machine Readable)
    fh = logging.FileHandler(log_file)
    fh.setFormatter(JSONFormatter())
    logger.addHandler(fh)
    
    # 2. Console Handler (Human Readable)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(ConsoleFormatter())
    logger.addHandler(ch)
    
    return logger

class SovereignLogger:
    """Wrapper class to simplify extra context logging."""
    def __init__(self, name="sovereign"):
        self._logger = get_structured_logger(name)

    def _log(self, level, msg, **kwargs):
        if kwargs:
            self._logger.log(level, msg, extra={"extra_context": kwargs})
        else:
            self._logger.log(level, msg)

    def info(self, msg, **kwargs):
        self._log(logging.INFO, msg, **kwargs)

    def error(self, msg, **kwargs):
        self._log(logging.ERROR, msg, **kwargs)

    def warning(self, msg, **kwargs):
        self._log(logging.WARNING, msg, **kwargs)

    def debug(self, msg, **kwargs):
        self._log(logging.DEBUG, msg, **kwargs)

# Global default instance
logger = SovereignLogger()

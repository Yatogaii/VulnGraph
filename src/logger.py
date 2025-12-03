from __future__ import annotations

import sys
from loguru import logger as _logger

from src.settings import settings

# Configure a single Loguru logger instance for the entire project
_logger.remove()
_logger.add(
    sys.stdout,
    level="DEBUG" if settings.debug else "INFO",
    colorize=True,
    enqueue=True,
    backtrace=settings.debug,
    diagnose=settings.debug,
)

logger = _logger

__all__ = ["logger"]

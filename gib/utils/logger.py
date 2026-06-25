"""Logging utilities."""
from __future__ import annotations

import logging
import sys
from pathlib import Path


def get_logger(name: str) -> logging.Logger:
    """Get a named logger with consistent formatting."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
    return logger


def setup_file_logging(log_dir: Path, level: str = "INFO") -> None:
    """Set up file logging for all gib loggers."""
    log_file = log_dir / "gib.log"
    handler = logging.FileHandler(log_file)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
    )
    root = logging.getLogger("gib")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.addHandler(handler)

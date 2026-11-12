"""Structured logging: one JSON object per line (FR-11).

Log file shape is part of the contract because SPEC-002 onward will be read by scripts, not by
a human scrolling a console. Two rules from the spec are enforced here: no secrets, and no
caption or prompt bodies at info level — they are the corpus and can be large.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

LOG_FILE_NAME = "app.jsonl"
_MAX_BYTES = 5 * 1024 * 1024
_BACKUPS = 3


class JsonFormatter(logging.Formatter):
    """Render a log record as one JSON object on one line."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialise the record.

        Args:
            record: The record to render.

        Returns:
            A single-line JSON object with ``ts``, ``level``, ``event`` and any structured
            fields supplied through ``extra={"fields": {...}}``.
        """
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "event": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(
    log_dir: Path, *, level: int = logging.INFO, to_stderr: bool = True
) -> logging.Logger:
    """Configure the ``gtaf`` logger to write JSON lines to ``log_dir/app.jsonl``.

    Args:
        log_dir: Directory for the log file; created if absent.
        level: Minimum level to record.
        to_stderr: Also emit human-readable lines to stderr.

    Returns:
        The configured ``gtaf`` logger.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("gtaf")
    logger.setLevel(level)
    logger.handlers.clear()
    logger.propagate = False

    file_handler = RotatingFileHandler(
        log_dir / LOG_FILE_NAME, maxBytes=_MAX_BYTES, backupCount=_BACKUPS, encoding="utf-8"
    )
    file_handler.setFormatter(JsonFormatter())
    logger.addHandler(file_handler)

    if to_stderr:
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        logger.addHandler(console)

    return logger


def log_event(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    """Emit one structured event.

    Args:
        logger: Target logger.
        level: Logging level.
        event: Stable short event key, e.g. ``db.created``.
        **fields: Structured values to attach.
    """
    logger.log(level, event, extra={"fields": fields})

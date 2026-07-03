"""Application logger setup.

This module configures a named logger `autostart` and a stream handler.
Log level is controlled via the `LOG_LEVEL` environment variable.
Adds a `RequestIDLogFilter` to inject a request id when running under Flask.
"""

from flask import g, has_request_context
import logging
import os


REQUEST_ID_KEY = "request_id"
DEFAULT_LOG_LEVEL = "DEBUG"
LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
    "NOTSET": logging.NOTSET,
}


class RequestIDLogFilter(logging.Filter):
    """Inject request id into log records when available in Flask request context."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = (
            g.request_id if has_request_context() and hasattr(g, REQUEST_ID_KEY) else "SYSTEM"
        )
        return True


def _resolve_level(name: str | None) -> int:
    if not name:
        return logging.DEBUG
    return LEVELS.get(name.upper(), logging.DEBUG)


# Configure logger
_env_level = os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL)
_numeric_level = _resolve_level(_env_level)

logger = logging.getLogger("autostart")
logger.setLevel(_numeric_level)
logger.propagate = False

# Stream handler with same level and request-id formatter
_handler = logging.StreamHandler()
_handler.setLevel(_numeric_level)
_handler.setFormatter(
    logging.Formatter(
        "[%(asctime)s] [%(request_id)s] %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
)
_handler.addFilter(RequestIDLogFilter())

logger.addHandler(_handler)

# Reduce noise from werkzeug/Flask server logs
logging.getLogger("werkzeug").setLevel(logging.ERROR)

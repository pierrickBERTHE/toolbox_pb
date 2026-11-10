"""Interface-neutral text output for core operations."""

from __future__ import annotations

import builtins
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
from typing import Any


MessageSink = Callable[[str], object]
_message_sink: MessageSink = lambda message: builtins.print(message, end="")
_logger = logging.getLogger("toolbox_pb")
_logger.setLevel(logging.INFO)
_logger.propagate = False
_file_handler: logging.FileHandler | None = None
_write_to_file: ContextVar[bool] = ContextVar("write_to_file", default=True)


def _resolve_log_level(level: str | int) -> int:
    """Return a valid logging level, rejecting misspelled textual values."""
    if isinstance(level, int):
        return level
    try:
        return logging.getLevelNamesMapping()[level.upper()]
    except KeyError as exc:
        raise ValueError(f"Niveau de log invalide : {level}") from exc


def configure_file_logging(
    log_dir: Path,
    enabled: bool = True,
    level: str | int = logging.INFO,
) -> None:
    """Write toolbox messages to ``process_log.txt`` when logging is enabled."""
    global _file_handler
    _logger.setLevel(_resolve_log_level(level))

    if _file_handler is not None:
        same_path = enabled and Path(_file_handler.baseFilename) == (
            log_dir / "process_log.txt"
        ).resolve()
        if same_path:
            return
        _logger.removeHandler(_file_handler)
        _file_handler.close()
        _file_handler = None

    if not enabled:
        return

    log_path = log_dir / "process_log.txt"
    log_dir.mkdir(parents=True, exist_ok=True)
    _file_handler = logging.FileHandler(log_path, encoding="utf-8")
    _file_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    _logger.addHandler(_file_handler)


def emit(
    *values: object,
    sep: str = " ",
    end: str = "\n",
    level: int = logging.INFO,
    log: bool = True,
    **_: Any,
) -> None:
    """Record a text event, then send it to the active interface."""
    message = sep.join(str(value) for value in values)
    if log and _write_to_file.get() and message.strip():
        _logger.log(level, message.strip())
    _message_sink(message + end)


def ui_only(function: Callable[..., Any]) -> Callable[..., Any]:
    """Keep a verbose display helper out of the persistent process log."""
    @wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        token = _write_to_file.set(False)
        try:
            return function(*args, **kwargs)
        finally:
            _write_to_file.reset(token)

    return wrapper


@contextmanager
def use_message_sink(sink: MessageSink) -> Iterator[None]:
    """Temporarily select the recipient for core text events."""
    global _message_sink
    previous_sink = _message_sink
    _message_sink = sink
    try:
        yield
    finally:
        _message_sink = previous_sink

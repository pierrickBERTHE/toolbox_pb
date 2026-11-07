"""Interface-neutral text output for core operations."""

from __future__ import annotations

import builtins
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any


MessageSink = Callable[[str], object]
_message_sink: MessageSink = lambda message: builtins.print(message, end="")


def emit(*values: object, sep: str = " ", end: str = "\n", **_: Any) -> None:
    """Send a text event to the active UI without knowing that UI."""
    _message_sink(sep.join(str(value) for value in values) + end)


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

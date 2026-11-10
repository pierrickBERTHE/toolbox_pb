"""Cooperative cancellation shared by interactive interfaces and core tools."""

from __future__ import annotations

import subprocess
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Event
from typing import Iterator


class ProcessingCancelled(RuntimeError):
    """Raised when the user asks to stop the active treatment."""


_active_cancel_event: ContextVar[Event | None] = ContextVar(
    "active_cancel_event", default=None
)


@contextmanager
def use_cancellation_event(cancel_event: Event) -> Iterator[None]:
    """Make ``cancel_event`` available to the processing code in this context."""
    token = _active_cancel_event.set(cancel_event)
    try:
        yield
    finally:
        _active_cancel_event.reset(token)


def is_cancelled() -> bool:
    """Return whether the active treatment has been asked to stop."""
    event = _active_cancel_event.get()
    return event is not None and event.is_set()


def raise_if_cancelled(proc: subprocess.Popen | None = None) -> None:
    """Stop a child process, then interrupt processing when cancellation is set."""
    if not is_cancelled():
        return
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    raise ProcessingCancelled("Traitement arrêté à la demande de l’utilisateur.")

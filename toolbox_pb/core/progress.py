"""Interface-neutral progress reporting for toolbox operations."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from typing import Any


class SilentProgress:
    """Progress object used when an interface does not supply a renderer."""

    def __init__(self, iterable: Iterable[Any] | None = None, total: float | None = None, **_: Any) -> None:
        self.iterable = iterable
        self.total = total if total is not None else self._get_length(iterable)
        self.n = 0.0

    @staticmethod
    def _get_length(iterable: Iterable[Any] | None) -> int | None:
        try:
            return len(iterable) if iterable is not None else None
        except TypeError:
            return None

    def update(self, increment: float = 1) -> None:
        self.n += increment

    def __iter__(self) -> Iterator[Any]:
        if self.iterable is None:
            return iter(())
        for item in self.iterable:
            yield item
            self.update()

    def __enter__(self) -> "SilentProgress":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        return None


ProgressFactory = Callable[..., Any]
_progress_factory: ProgressFactory = SilentProgress


def progress(*args: Any, **kwargs: Any) -> Any:
    """Create a progress reporter supplied by the active user interface."""
    return _progress_factory(*args, **kwargs)


@contextmanager
def use_progress_factory(factory: ProgressFactory) -> Iterator[None]:
    """Temporarily select the progress renderer for a UI invocation."""
    global _progress_factory
    previous_factory = _progress_factory
    _progress_factory = factory
    try:
        yield
    finally:
        _progress_factory = previous_factory

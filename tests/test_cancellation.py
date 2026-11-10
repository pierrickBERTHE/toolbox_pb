"""Tests for cooperative treatment cancellation."""

from threading import Event
from unittest import mock

import pytest

from toolbox_pb.core.cancellation import (
    ProcessingCancelled,
    is_cancelled,
    raise_if_cancelled,
    use_cancellation_event,
)


def test_cancellation_context_is_scoped_to_its_event():
    event = Event()
    assert is_cancelled() is False

    with use_cancellation_event(event):
        assert is_cancelled() is False
        event.set()
        assert is_cancelled() is True

    assert is_cancelled() is False


def test_raise_if_cancelled_leaves_an_active_process_alone_without_request():
    process = mock.Mock()
    with use_cancellation_event(Event()):
        raise_if_cancelled(process)
    process.terminate.assert_not_called()


def test_raise_if_cancelled_terminates_a_running_process():
    event = Event()
    event.set()
    process = mock.Mock()
    process.poll.return_value = None

    with use_cancellation_event(event), pytest.raises(ProcessingCancelled):
        raise_if_cancelled(process)

    process.terminate.assert_called_once_with()
    process.wait.assert_called_once_with(timeout=5)
    process.kill.assert_not_called()


def test_raise_if_cancelled_kills_a_process_that_does_not_stop():
    event = Event()
    event.set()
    process = mock.Mock()
    process.poll.return_value = None
    process.wait.side_effect = [__import__("subprocess").TimeoutExpired("ffmpeg", 5), None]

    with use_cancellation_event(event), pytest.raises(ProcessingCancelled):
        raise_if_cancelled(process)

    process.kill.assert_called_once_with()
    assert process.wait.call_count == 2

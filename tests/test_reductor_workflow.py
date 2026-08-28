"""Unit tests for the image/video complementary reduction workflow."""

from io import StringIO
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest import mock

import pytest

# Add the application directory so the standalone workflow module is importable.
sys.path.append(str(Path(__file__).resolve().parents[1] / "toolbox_pb"))

import reductor_workflow as workflow


@pytest.mark.parametrize(
    ("answer", "expected"),
    [("n", False), ("non", False), ("o", True), ("unexpected", True), (None, True)],
)
def test_ask_to_run_complementary_reductor_handles_answers(monkeypatch, answer, expected):
    """Only explicit negative answers prevent the complementary launch."""
    monkeypatch.setattr(
        workflow, "_read_timed_confirmation", lambda **_: answer
    )

    assert workflow._ask_to_run_complementary_reductor("Image_reductor") is expected


def test_read_timed_confirmation_returns_linux_console_input(monkeypatch):
    """The Linux branch normalizes an answer read from standard input."""
    fake_select = SimpleNamespace(select=lambda *_: ([object()], [], []))
    monkeypatch.setitem(__import__("sys").modules, "select", fake_select)
    monkeypatch.setattr(workflow.sys, "platform", "linux")
    monkeypatch.setattr(workflow.sys, "stdin", StringIO(" Oui \n"))

    assert workflow._read_timed_confirmation(1) == "oui"


def test_read_timed_confirmation_returns_none_when_select_is_unsupported(monkeypatch):
    """Non-interactive standard input is handled as an automatic confirmation."""
    def failing_select(*_):
        raise OSError("unsupported")

    fake_select = SimpleNamespace(select=failing_select)
    monkeypatch.setitem(__import__("sys").modules, "select", fake_select)
    monkeypatch.setattr(workflow.sys, "platform", "linux")

    assert workflow._read_timed_confirmation(1) is None


def test_read_timed_confirmation_reads_and_edits_windows_input(monkeypatch):
    """The Windows branch handles backspace and special keys before Enter."""
    characters = iter(["A", "\b", "O", "\x00", "ignored", "\r"])
    fake_msvcrt = SimpleNamespace(kbhit=lambda: True, getwch=lambda: next(characters))
    monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)
    monkeypatch.setattr(workflow.sys, "platform", "win32")
    monkeypatch.setattr(workflow.time, "monotonic", lambda: 0)
    monkeypatch.setattr(workflow.time, "sleep", lambda _: None)

    assert workflow._read_timed_confirmation(1) == "o"


def test_read_timed_confirmation_returns_none_after_windows_timeout(monkeypatch):
    """Windows input also returns None when no keystroke arrives before timeout."""
    fake_msvcrt = SimpleNamespace(kbhit=lambda: False, getwch=lambda: "")
    clock_values = iter([0, 1])
    monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)
    monkeypatch.setattr(workflow.sys, "platform", "win32")
    monkeypatch.setattr(workflow.time, "monotonic", lambda: next(clock_values))

    assert workflow._read_timed_confirmation(1) is None


def test_read_timed_confirmation_returns_none_after_linux_timeout(monkeypatch):
    """A Linux console with no answer returns None once its deadline is reached."""
    fake_select = SimpleNamespace(select=lambda *_: ([], [], []))
    clock_values = iter([0, 0, 0, 1])
    monkeypatch.setitem(sys.modules, "select", fake_select)
    monkeypatch.setattr(workflow.sys, "platform", "linux")
    monkeypatch.setattr(workflow.time, "monotonic", lambda: next(clock_values))

    assert workflow._read_timed_confirmation(1) is None


@pytest.mark.parametrize(
    ("primary", "expected_extension", "expected_runner"),
    [("image", ".mp4", "video"), ("video", ".jpg", "image")],
)
def test_run_complementary_reductor_runs_matching_tool(
    monkeypatch, primary, expected_extension, expected_runner
):
    """The workflow selects the opposite reducer and forwards the config."""
    cfg = SimpleNamespace(
        INPUT_DIR="input",
        INPUT_ACCEPTED_VIDEO_FILES=[".mp4"],
        INPUT_ACCEPTED_IMAGE_FILES=[".jpg"],
    )
    finder = mock.Mock(return_value=["matching-file"])
    video_runner = mock.Mock(return_value=False)
    image_runner = mock.Mock(return_value=True)
    monkeypatch.setattr(workflow, "_ask_to_run_complementary_reductor", lambda _: True)

    result = workflow._run_complementary_reductor(
        cfg, primary, finder, video_runner, image_runner
    )

    assert finder.call_args.args[1] == [expected_extension]
    selected_runner = video_runner if expected_runner == "video" else image_runner
    selected_runner.assert_called_once_with(cfg)
    assert result is selected_runner.return_value


def test_run_complementary_reductor_skips_prompt_without_matching_file(monkeypatch):
    """No prompt or reducer launch occurs when the other file type is absent."""
    cfg = SimpleNamespace(
        INPUT_DIR="input",
        INPUT_ACCEPTED_VIDEO_FILES=[".mp4"],
        INPUT_ACCEPTED_IMAGE_FILES=[".jpg"],
    )
    prompt = mock.Mock(return_value=True)
    runner = mock.Mock()
    monkeypatch.setattr(workflow, "_ask_to_run_complementary_reductor", prompt)

    result = workflow._run_complementary_reductor(
        cfg, "image", lambda *_: [], runner, runner
    )

    assert result is None
    prompt.assert_not_called()
    runner.assert_not_called()

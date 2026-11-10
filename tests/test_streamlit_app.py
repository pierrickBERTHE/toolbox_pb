"""Tests for Streamlit-specific rendering helpers."""

from types import SimpleNamespace
from unittest import mock
import logging

import pytest

from toolbox_pb.core.cancellation import ProcessingCancelled, use_cancellation_event
import toolbox_pb.ui.streamlit_app as streamlit_app
from toolbox_pb.ui.streamlit_app import (
    QueuedProgress,
    TreatmentJob,
    _drain_treatment_events,
    _run_treatment_worker,
)


class _FakeSessionState(dict):
    """Dictionary supporting Streamlit's attribute-style session state API."""

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc

    def __setattr__(self, key, value):
        self[key] = value


class _FakeContainer:
    """Minimal context-manager capable Streamlit output target."""

    def __init__(self, buttons=None):
        self.buttons = buttons or {}
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __getattr__(self, name):
        if name == "button":
            return lambda label, **kwargs: self.buttons.get(kwargs.get("key"), False)
        if name == "columns":
            return lambda specs, **kwargs: [
                _FakeContainer(self.buttons) for _ in range(specs if isinstance(specs, int) else len(specs))
            ]
        if name == "container" or name == "expander":
            return lambda *args, **kwargs: _FakeContainer(self.buttons)
        if name == "empty":
            return lambda: _FakeContainer(self.buttons)
        return lambda *args, **kwargs: self.calls.append((name, args, kwargs))


class _FakeStreamlit(_FakeContainer):
    def __init__(self, buttons=None, session_state=None):
        super().__init__(buttons)
        self.session_state = session_state if session_state is not None else _FakeSessionState()
        self.sidebar = _FakeContainer(self.buttons)

    def text_input(self, _label, **kwargs):
        return self.session_state.get(kwargs["key"], "")

    def number_input(self, _label, **kwargs):
        return self.session_state.get(kwargs["key"], kwargs.get("value", 0.0))


def test_video_encodor_uses_the_cli_image_reduction_confirmation(monkeypatch):
    """The Streamlit video action delegates to the same CLI workflow."""
    video_runner = mock.Mock(return_value=False)
    complementary_runner = mock.Mock(return_value=False)
    monkeypatch.setattr(streamlit_app, "video_encodor", video_runner)
    monkeypatch.setattr(streamlit_app, "_run_complementary_reductor", complementary_runner)
    cfg = SimpleNamespace()

    result = streamlit_app._run_video_encodor_with_image_reductor(cfg)

    video_runner.assert_called_once_with(cfg)
    assert complementary_runner.call_args.args[1] == "video"
    assert complementary_runner.call_args.kwargs == {}
    assert result is False


def test_queued_progress_stops_before_the_next_file():
    """A stop request must interrupt generic file-by-file treatments."""
    job = TreatmentJob(tool_name="test")
    job.cancel_event.set()

    with use_cancellation_event(job.cancel_event):
        progress = QueuedProgress(job, iterable=["first-file"])
        with pytest.raises(ProcessingCancelled):
            next(iter(progress))


def test_worker_reports_a_validation_error_without_a_traceback():
    """Expected input errors stay readable in the Streamlit treatment panel."""
    job = TreatmentJob(tool_name="pdf_page_alternator")

    def invalid_runner():
        raise ValueError("Les pages des deux PDF ne peuvent pas être alternées.")

    with mock.patch.object(logging.getLogger("toolbox_pb"), "warning") as warning:
        _run_treatment_worker(job, invalid_runner)
    _drain_treatment_events(job)

    assert job.status == "validation_error"
    assert job.error == "Les pages des deux PDF ne peuvent pas être alternées."
    assert "Traceback" not in job.output
    warning.assert_called_once_with(
        "Traitement %s non effectué : %s",
        "pdf_page_alternator",
        "Les pages des deux PDF ne peuvent pas être alternées.",
    )


def test_open_folder_uses_the_foreground_explorer_helper(tmp_path):
    """Opening a configured folder delegates focus to the Windows helper."""
    with mock.patch.object(streamlit_app.subprocess, "Popen") as popen:
        streamlit_app._open_in_file_explorer(tmp_path, "d’entrée")

    command = popen.call_args.args[0]
    assert command[0] == "powershell.exe"
    assert str(streamlit_app.FOCUS_EXPLORER_SCRIPT) in command
    assert str(tmp_path.resolve()) in command
    assert popen.call_args.kwargs["creationflags"] == streamlit_app.subprocess.CREATE_NO_WINDOW
    assert popen.call_args.kwargs["stdout"] is streamlit_app.subprocess.DEVNULL
    assert popen.call_args.kwargs["stderr"] is streamlit_app.subprocess.DEVNULL


def test_queued_progress_and_worker_cover_all_terminal_states(monkeypatch):
    """Worker events remain readable for success, stop and unexpected failure."""
    job = TreatmentJob(tool_name="success")
    _run_treatment_worker(job, lambda: False)
    _drain_treatment_events(job)
    assert job.status == "done"
    assert "Traitement terminé" in job.output

    cancelled = TreatmentJob(tool_name="cancelled")
    cancelled.cancel_event.set()
    _run_treatment_worker(cancelled, lambda: False)
    _drain_treatment_events(cancelled)
    assert cancelled.status == "cancelled"

    failed = TreatmentJob(tool_name="failed")
    _run_treatment_worker(failed, lambda: 1 / 0)
    _drain_treatment_events(failed)
    assert failed.status == "error"
    assert "ZeroDivisionError" in failed.error

    progress_job = TreatmentJob(tool_name="progress")
    progress = QueuedProgress(progress_job, total=2, desc="Fichiers", position=1)
    progress.update()
    progress.update()
    progress.close()
    _drain_treatment_events(progress_job)
    assert progress_job.progress[1][0] == 100


def test_runtime_reports_and_tool_launcher_use_session_values(monkeypatch):
    """Session settings are copied to the runtime config and jobs start once."""
    fake_st = _FakeStreamlit(
        session_state=_FakeSessionState(
            {"flag_LOG_TO_FILE": False, "value_LOG_LEVEL": "DEBUG"}
        )
    )
    monkeypatch.setattr(streamlit_app, "st", fake_st)
    cfg = streamlit_app._runtime_config()
    assert cfg.LOG_TO_FILE is False
    assert cfg.LOG_LEVEL == "DEBUG"

    monkeypatch.setattr(streamlit_app, "configure_file_logging", mock.Mock())
    started = []

    class _Thread:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def start(self):
            started.append(self.kwargs)

    monkeypatch.setattr(streamlit_app, "Thread", _Thread)
    streamlit_app._run_tool("demo", lambda: False)
    assert fake_st.session_state.active_treatment.tool_name == "demo"
    assert started

    streamlit_app._run_tool("other", lambda: False)
    assert len(started) == 1


def test_tool_card_handles_required_input_and_launch(monkeypatch):
    """An expanded tile validates its field before delegating its runner."""
    fake_st = _FakeStreamlit(
        buttons={"demo_run": True}, session_state=_FakeSessionState({"demo_expanded": True})
    )
    monkeypatch.setattr(streamlit_app, "st", fake_st)
    run_tool = mock.Mock()
    monkeypatch.setattr(streamlit_app, "_run_tool", run_tool)

    streamlit_app._tool_card(
        "image_reductor", "description", "before", "after", lambda value: value,
        key="demo", input_label="Valeur", input_required=True,
    )
    assert not run_tool.called

    fake_st = _FakeStreamlit(
        buttons={"demo_run": True}, session_state=_FakeSessionState({"demo_expanded": True, "demo_value": "ok"})
    )
    monkeypatch.setattr(streamlit_app, "st", fake_st)
    streamlit_app._tool_card(
        "image_reductor", "description", "before", "after", lambda value: value,
        key="demo", input_label="Valeur", input_required=True,
    )
    assert run_tool.call_args.args[0] == "image_reductor"
    assert run_tool.call_args.args[1]() == "ok"


def test_categories_register_all_tools_and_main_renders_selected_category(monkeypatch):
    """Category builders expose every treatment and main selects its renderer."""
    cards = []
    monkeypatch.setattr(streamlit_app, "_tool_card", lambda *args, **kwargs: cards.append(args[0]))
    cfg = SimpleNamespace()
    streamlit_app._category_video(cfg)
    streamlit_app._category_image(cfg)
    streamlit_app._category_audio(cfg)
    streamlit_app._category_pdf(cfg)
    streamlit_app._category_file(cfg)
    assert set(cards) == set(streamlit_app.TOOL_NUMBERS)

    fake_st = _FakeStreamlit(session_state=_FakeSessionState({"selected_category": "Audio"}))
    monkeypatch.setattr(streamlit_app, "st", fake_st)
    selected = mock.Mock()
    monkeypatch.setattr(streamlit_app, "_category_audio", selected)
    monkeypatch.setattr(streamlit_app, "_environment_report", lambda: "environment")
    monkeypatch.setattr(streamlit_app, "_startup_report", lambda: "startup")
    streamlit_app.main()
    selected.assert_called_once()


def test_streamlit_helpers_cover_reports_logs_and_process_launch_errors(monkeypatch, tmp_path):
    """Small UI helpers keep their output local and turn OS errors into alerts."""
    fake_st = _FakeStreamlit(session_state=_FakeSessionState())
    monkeypatch.setattr(streamlit_app, "st", fake_st)

    monkeypatch.setattr(streamlit_app.func_global_module, "print_system_info", lambda: print("Python test"))
    assert streamlit_app._environment_report() == "Python test"
    monkeypatch.setattr(streamlit_app.func_global_module, "get_git_version", lambda: "v1")
    monkeypatch.setattr(streamlit_app.func_global_module, "format_git_version", lambda value: f"Version {value}")
    assert "Version v1" in streamlit_app._startup_report()

    unknown = tmp_path / "unknown"
    streamlit_app._open_in_file_explorer(unknown, "de sortie")
    assert any(call[0] == "error" for call in fake_st.calls)

    existing = tmp_path / "existing"
    existing.mkdir()
    monkeypatch.setattr(streamlit_app.subprocess, "Popen", mock.Mock(side_effect=OSError("blocked")))
    streamlit_app._open_in_file_explorer(existing, "de sortie")
    streamlit_app._launch_cli()
    assert sum(call[0] == "error" for call in fake_st.calls) >= 3


def test_progress_helpers_handle_unknown_lengths_and_context_managers():
    """Queued progress gracefully supports generators and completed contexts."""
    job = TreatmentJob(tool_name="queue")
    with QueuedProgress(job, iterable=(value for value in [1])) as progress:
        assert list(progress) == [1]
    assert list(QueuedProgress(job, iterable=None)) == []

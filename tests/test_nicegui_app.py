"""Tests for the NiceGUI adapter without starting a web server."""

from dataclasses import replace
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest import mock

import pytest

from toolbox_pb.core import events
from toolbox_pb.core.cancellation import ProcessingCancelled
from toolbox_pb.ui import nicegui_app


def test_recent_folder_entries_hides_gitkeep_and_sorts_by_modification(
    tmp_path,
):
    """The workspace preview hides markers and sorts visible files."""
    marker = tmp_path / ".gitkeep"
    older = tmp_path / "older.txt"
    newer = tmp_path / "newer.mp4"
    marker.write_text("", encoding="utf-8")
    older.write_text("old", encoding="utf-8")
    newer.write_text("new", encoding="utf-8")
    newer.touch()

    entries = nicegui_app._recent_folder_entries(tmp_path)

    assert [entry.name for entry in entries] == ["newer.mp4", "older.txt"]
    assert nicegui_app._recent_folder_entries(tmp_path / "missing") == []


def test_clear_folder_content_preserves_gitkeep_and_removes_nested_content(
    tmp_path,
):
    """The destructive action never removes the repository marker."""
    (tmp_path / ".gitkeep").write_text("", encoding="utf-8")
    (tmp_path / "result.mp4").write_text("video", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "child.txt").write_text("child", encoding="utf-8")

    removed = nicegui_app._clear_folder_content(tmp_path)

    assert removed == 2
    assert (tmp_path / ".gitkeep").is_file()
    assert list(tmp_path.iterdir()) == [tmp_path / ".gitkeep"]


def test_clear_folder_content_ignores_a_missing_workspace(tmp_path):
    assert nicegui_app._clear_folder_content(tmp_path / "missing") == 0


def test_tool_icons_match_all_declared_tool_specs():
    """Every tool card has the supplied project artwork."""
    assert len(nicegui_app.TOOLS) == 22
    assert all(
        nicegui_app._tool_icon(tool) is not None for tool in nicegui_app.TOOLS
    )


def test_cache_cleaner_runner_does_not_pass_runtime_config(monkeypatch):
    cleaner = mock.Mock()
    monkeypatch.setattr(nicegui_app, "cache_nettoyor", cleaner)
    tool = next(tool for tool in nicegui_app.TOOLS if tool.key == "cache_clean")

    tool.runner(nicegui_app.APP_CONFIG, None)

    cleaner.assert_called_once_with()


def test_environment_and_startup_reports_reuse_the_existing_diagnostics(
    monkeypatch,
):
    monkeypatch.setattr(
        nicegui_app.func_global_module, "get_git_version", lambda: "v-test"
    )
    monkeypatch.setattr(
        nicegui_app.func_global_module,
        "format_git_version",
        lambda version: f"Version : {version}",
    )
    monkeypatch.setattr(
        nicegui_app.func_global_module,
        "print_system_info",
        lambda: print("Python          : test"),
    )

    assert "Version : v-test" in nicegui_app._startup_report()
    assert nicegui_app._environment_report() == "Python          : test"


def test_runtime_config_applies_every_session_control():
    settings = {
        flag: SimpleNamespace(value=False)
        for flag in nicegui_app.SESSION_FLAGS
    }
    settings["LOG_TO_FILE"].value = True
    settings["AUDIO_COMPRESSOR_MP3_BITRATE_KBPS"] = SimpleNamespace(value=192)
    settings["LOG_LEVEL"] = SimpleNamespace(value="DEBUG")

    config = nicegui_app._runtime_config(settings)

    assert config.LOG_TO_FILE is True
    assert config.ADD_CODEC_NAME_IN_OUTPUT is False
    assert config.AUDIO_COMPRESSOR_MP3_BITRATE_KBPS == 192
    assert config.LOG_LEVEL == "DEBUG"


def test_open_folder_notifies_for_a_missing_path(monkeypatch, tmp_path):
    notify = mock.Mock()
    monkeypatch.setattr(nicegui_app.ui, "notify", notify)

    nicegui_app._open_folder(tmp_path / "missing")

    notify.assert_called_once()
    assert notify.call_args.kwargs["type"] == "negative"


def test_open_folder_starts_windows_explorer(monkeypatch, tmp_path):
    popen = mock.Mock()
    monkeypatch.setattr(nicegui_app.subprocess, "Popen", popen)

    nicegui_app._open_folder(tmp_path)

    popen.assert_called_once_with(["explorer", str(tmp_path)])


def test_data_segment_directory_can_be_opened_from_the_workspace(monkeypatch):
    popen = mock.Mock()
    monkeypatch.setattr(nicegui_app.subprocess, "Popen", popen)

    nicegui_app._open_folder(nicegui_app.APP_CONFIG.SEGMENT_DIR)

    popen.assert_called_once_with(
        ["explorer", str(nicegui_app.APP_CONFIG.SEGMENT_DIR)]
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", False),
        ("0", False),
        ("true", True),
        ("YES", True),
    ],
)
def test_development_reload_requires_an_explicit_environment_flag(
    monkeypatch, value, expected
):
    monkeypatch.setenv("TOOLBOX_RELOAD", value)

    assert nicegui_app._development_reload_enabled() is expected


def test_open_process_log_uses_notepad_plus_plus(monkeypatch, tmp_path):
    log_file = tmp_path / "process_log.txt"
    log_file.write_text("message", encoding="utf-8")
    notepad = tmp_path / "notepad++.exe"
    notepad.write_text("", encoding="utf-8")
    popen = mock.Mock()
    monkeypatch.setattr(
        nicegui_app,
        "APP_CONFIG",
        replace(nicegui_app.APP_CONFIG, LOG_DIR=tmp_path),
    )
    monkeypatch.setattr(nicegui_app, "NOTEPAD_PLUS_PLUS_PATHS", (notepad,))
    monkeypatch.setattr(nicegui_app.subprocess, "Popen", popen)

    nicegui_app._open_process_log()

    popen.assert_called_once_with([str(notepad), str(log_file)])


def test_open_process_log_notifies_when_no_log_or_notepad_is_available(
    monkeypatch, tmp_path
):
    notify = mock.Mock()
    monkeypatch.setattr(nicegui_app.ui, "notify", notify)
    monkeypatch.setattr(
        nicegui_app,
        "APP_CONFIG",
        replace(nicegui_app.APP_CONFIG, LOG_DIR=tmp_path),
    )

    nicegui_app._open_process_log()
    assert notify.call_args.kwargs["type"] == "warning"

    (tmp_path / "process_log.txt").write_text("message", encoding="utf-8")
    monkeypatch.setattr(nicegui_app, "NOTEPAD_PLUS_PLUS_PATHS", ())
    nicegui_app._open_process_log()
    assert notify.call_args.kwargs["type"] == "negative"


def test_export_output_files_copies_tree_and_rejects_its_own_folder(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    (output / ".gitkeep").write_text("", encoding="utf-8")
    nested = output / "nested"
    nested.mkdir()
    (nested / "result.txt").write_text("result", encoding="utf-8")
    destination = tmp_path / "export"
    destination.mkdir()

    assert nicegui_app._export_output_files(output, destination) == 1
    assert (destination / "nested" / "result.txt").read_text(
        encoding="utf-8"
    ) == "result"
    with pytest.raises(ValueError):
        nicegui_app._export_output_files(output, output)
    with pytest.raises(FileNotFoundError):
        nicegui_app._export_output_files(tmp_path / "missing", destination)


def test_select_export_folder_returns_the_selected_local_path(
    monkeypatch, tmp_path
):
    root = mock.Mock()
    tkinter = SimpleNamespace(
        Tk=lambda: root,
        filedialog=SimpleNamespace(
            askdirectory=lambda **_kwargs: str(tmp_path)
        ),
    )
    monkeypatch.setitem(sys.modules, "tkinter", tkinter)

    assert nicegui_app._select_export_folder(tmp_path) == tmp_path
    root.destroy.assert_called_once()


def test_queued_progress_reports_percentages_and_supports_iterables():
    job = nicegui_app.Job()
    progress = nicegui_app.QueuedProgress(
        job, [1, 2], desc="Copies", unit="fichier"
    )

    assert list(progress) == [1, 2]
    events = [
        job.events.get_nowait(),
        job.events.get_nowait(),
        job.events.get_nowait(),
    ]
    assert events[0] == (
        "progress",
        (0, "Copies — 0/2 fichier — écoulé : 00:00"),
    )
    assert events[-1][1][0] == 100


def test_queued_progress_handles_unknown_totals_and_context_manager():
    job = nicegui_app.Job()

    with nicegui_app.QueuedProgress(
        job, iterable=(item for item in [1])
    ) as progress:
        assert list(progress) == [1]

    assert job.events.get_nowait()[1][0] == 0
    assert list(nicegui_app.QueuedProgress(job)) == []

    with nicegui_app.QueuedProgress(job, [1]) as completed:
        assert list(completed) == [1]


def test_video_encoder_runs_the_complementary_image_reducer(
    monkeypatch, tmp_path
):
    config = replace(nicegui_app.APP_CONFIG, INPUT_DIR=tmp_path)
    calls = []
    monkeypatch.setattr(
        nicegui_app,
        "video_encodor",
        lambda _cfg: calls.append("video") or False,
    )
    monkeypatch.setattr(
        nicegui_app,
        "image_reductor",
        lambda _cfg: calls.append("image") or False,
    )
    monkeypatch.setattr(
        nicegui_app,
        "find_files_by_extensions",
        lambda *_args: [tmp_path / "photo.jpg"],
    )

    assert nicegui_app._run_video_encodor_with_image_reductor(config) is False
    assert calls == ["video", "image"]

    calls.clear()
    monkeypatch.setattr(
        nicegui_app, "find_files_by_extensions", lambda *_args: []
    )
    assert nicegui_app._run_video_encodor_with_image_reductor(config) is False
    assert calls == ["video"]


def test_legacy_cli_launches_in_a_new_console(monkeypatch):
    popen = mock.Mock()
    monkeypatch.setattr(nicegui_app.subprocess, "Popen", popen)

    nicegui_app._launch_legacy_cli()

    assert popen.call_args.args[0] == (
        "cmd.exe",
        "/k",
        "poetry run python -m toolbox_pb.ui.cli",
    )
    assert popen.call_args.kwargs["cwd"] == nicegui_app.PROJECT_DIR


def test_run_job_forwards_core_messages_and_marks_completion(monkeypatch):
    monkeypatch.setattr(nicegui_app, "configure_file_logging", mock.Mock())
    job = nicegui_app.Job()

    def runner():
        events.emit("NiceGUI worker message")

    nicegui_app._run_job(job, "demo", runner, nicegui_app.APP_CONFIG)
    assert job.thread is not None
    job.thread.join(timeout=2)

    assert job.finished is True
    assert job.failed is False
    assert job.events.get_nowait() == ("log", "NiceGUI worker message\n")


def test_run_job_opens_output_after_success_when_enabled(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(nicegui_app, "configure_file_logging", mock.Mock())
    open_output = mock.Mock()
    monkeypatch.setattr(nicegui_app, "_open_folder_native", open_output)
    job = nicegui_app.Job()
    config = replace(
        nicegui_app.APP_CONFIG,
        OUTPUT_DIR=tmp_path,
        OPEN_OUTPUT_DIR_AFTER_TREATMENT=True,
    )

    nicegui_app._run_job(job, "demo", lambda: None, config)
    assert job.thread is not None
    job.thread.join(timeout=2)

    open_output.assert_called_once_with(tmp_path)


def test_run_job_parses_youtube_progress_and_reports_output_open_errors(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(nicegui_app, "configure_file_logging", mock.Mock())
    monkeypatch.setattr(
        nicegui_app,
        "_open_folder_native",
        mock.Mock(side_effect=OSError("blocked")),
    )
    job = nicegui_app.Job()
    config = replace(
        nicegui_app.APP_CONFIG,
        OUTPUT_DIR=tmp_path,
        OPEN_OUTPUT_DIR_AFTER_TREATMENT=True,
    )

    nicegui_app._run_job(
        job,
        "youtube",
        lambda: events.emit("[download] 42.5% of 10MiB"),
        config,
    )
    assert job.thread is not None
    job.thread.join(timeout=2)

    received = list(job.events.queue)
    assert (
        "progress",
        (42, "Téléchargement YouTube — 42.5 % — 10MiB"),
    ) in received
    assert any(
        "Impossible d’ouvrir OUTPUT" in message
        for event, message in received
        if event == "log"
    )


def test_run_job_marks_expected_cancellation(monkeypatch):
    monkeypatch.setattr(nicegui_app, "configure_file_logging", mock.Mock())
    job = nicegui_app.Job()

    nicegui_app._run_job(
        job,
        "cancelled",
        lambda: (_ for _ in ()).throw(ProcessingCancelled()),
        nicegui_app.APP_CONFIG,
    )
    assert job.thread is not None
    job.thread.join(timeout=2)

    assert job.finished is True
    assert job.failed is False
    event, message = job.events.get_nowait()
    assert event == "log"
    assert "arrêté" in message


def test_run_job_captures_an_unexpected_error(monkeypatch):
    monkeypatch.setattr(nicegui_app, "configure_file_logging", mock.Mock())
    job = nicegui_app.Job()

    nicegui_app._run_job(
        job,
        "broken",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        nicegui_app.APP_CONFIG,
    )
    assert job.thread is not None
    job.thread.join(timeout=2)

    assert job.finished is True
    assert job.failed is True
    assert job.error is not None and "RuntimeError: boom" in job.error


def test_job_active_reflects_the_worker_liveness():
    job = nicegui_app.Job()
    assert job.active is False

    job.thread = SimpleNamespace(is_alive=lambda: True)
    assert job.active is True


def test_page_builds_with_diagnostics_stubbed(monkeypatch):
    """Cover the page layout without opening a browser or probing FFmpeg."""
    monkeypatch.setattr(
        nicegui_app, "_startup_report", lambda: "Version : test"
    )
    monkeypatch.setattr(
        nicegui_app, "_environment_report", lambda: "Python : test"
    )

    nicegui_app.toolbox_page()


def test_page_builds_a_text_input_and_icon_fallback(monkeypatch):
    """A custom tool still renders when its artwork is not available."""
    text_tool = nicegui_app.ToolSpec(
        category="Vidéo",
        title="custom_tool",
        key="custom_tool",
        description="Test tool",
        before="Before",
        after="After",
        runner=lambda _config, _value: None,
        input_label="Custom value",
    )
    monkeypatch.setattr(nicegui_app, "TOOLS", (text_tool,))
    monkeypatch.setattr(nicegui_app, "_tool_icon", lambda _tool: None)
    monkeypatch.setattr(
        nicegui_app, "_startup_report", lambda: "Version : test"
    )
    monkeypatch.setattr(
        nicegui_app, "_environment_report", lambda: "Python : test"
    )

    nicegui_app.toolbox_page()

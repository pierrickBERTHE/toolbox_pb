"""Tests for Streamlit-specific rendering helpers."""

from types import SimpleNamespace
from unittest import mock
import logging
import os
from pathlib import Path

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


class _FakeYoutubeStreamlit(_FakeStreamlit):
    """Fake Streamlit surface dedicated to the YouTube form tests."""

    def __init__(self, *, output_type, submitted, session_state, subtitles=False):
        super().__init__(session_state=session_state)
        self.output_type = output_type
        self.submitted = submitted
        self.subtitles = subtitles

    def segmented_control(self, *_args, **_kwargs):
        return self.output_type

    def selectbox(self, label, options, **_kwargs):
        return "160" if "audio" in label.casefold() else "720"

    def form_submit_button(self, *_args, **_kwargs):
        return self.submitted

    def checkbox(self, *_args, **_kwargs):
        return self.subtitles

    def form(self, *_args, **_kwargs):
        return _FakeContainer(self.buttons)


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


def test_youtube_console_keeps_a_single_mp3_conversion_announcement():
    """Duplicate yt-dlp post-processor notices remain readable in Streamlit."""
    job = TreatmentJob(tool_name="youtube_downloader")
    log = streamlit_app.QueuedLog(job)

    log.write(
        "Conversion du flux audio en MP3…\n"
        "Conversion du flux audio en MP3…\n"
    )
    _drain_treatment_events(job)

    assert job.output.count("Conversion du flux audio en MP3…") == 1


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
    status = mock.Mock()
    result = SimpleNamespace(
        returncode=0,
        stdout="Explorateur Windows ouvert",
        stderr="",
    )
    with (
        mock.patch.object(streamlit_app.st, "empty", return_value=status),
        mock.patch.object(streamlit_app.subprocess, "run", return_value=result) as run,
    ):
        streamlit_app._open_in_file_explorer(tmp_path, "d’entrée")

    command = run.call_args.args[0]
    assert command[0] == "powershell.exe"
    assert streamlit_app.FOCUS_EXPLORER_SCRIPT == (
        Path(streamlit_app.__file__).resolve().parent / "focus_explorer.ps1"
    )
    assert str(streamlit_app.FOCUS_EXPLORER_SCRIPT) in command
    assert str(tmp_path.resolve()) in command
    assert run.call_args.kwargs["creationflags"] == streamlit_app.subprocess.CREATE_NO_WINDOW
    assert run.call_args.kwargs["capture_output"] is True
    assert run.call_args.kwargs["timeout"] == 8
    status.success.assert_called_once_with("Explorateur Windows ouvert")


def test_folder_icon_click_callback_opens_the_requested_folder(monkeypatch, tmp_path):
    """The SVG-looking native button must directly open Explorer."""
    open_folder = mock.Mock()
    monkeypatch.setattr(streamlit_app.st, "html", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(streamlit_app.st, "button", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(streamlit_app, "_open_in_file_explorer", open_folder)

    streamlit_app._folder_open_icon("input", tmp_path, "INPUT")

    open_folder.assert_called_once_with(tmp_path, "INPUT")


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


def test_worker_logs_unexpected_errors_without_a_traceback(monkeypatch):
    """The UI keeps diagnostics, while process_log.txt receives one line only."""
    logger = mock.Mock()
    original_get_logger = logging.getLogger

    def get_logger(name=None):
        return logger if name == "toolbox_pb" else original_get_logger(name)

    monkeypatch.setattr(streamlit_app.logging, "getLogger", get_logger)
    job = TreatmentJob(tool_name="failed")

    _run_treatment_worker(job, lambda: 1 / 0)
    _drain_treatment_events(job)

    logger.error.assert_called_once()
    logger.exception.assert_not_called()
    assert "ZeroDivisionError" in job.error


def test_queued_log_hides_download_details_and_keeps_the_final_file_line():
    """yt-dlp's console details stay out of the UI without hiding the result."""
    job = TreatmentJob(tool_name="youtube_downloader")
    log = streamlit_app.QueuedLog(job)

    log.write("[download] 100% Fichier téléchargé : video.webm")

    event, message = job.events.get_nowait()
    assert event == "log"
    assert message == "Fichier téléchargé : video.webm"
    assert "[download]" not in message


def test_queued_log_turns_youtube_console_percentage_into_ui_progress():
    """yt-dlp's displayed percentage remains visible in Streamlit's bar."""
    job = TreatmentJob(tool_name="youtube_downloader")
    log = streamlit_app.QueuedLog(job)

    log.write("[download] 47.7% of 40MiB at 10MiB/s ETA 00:02\n")

    event, payload = job.events.get_nowait()
    assert event == "progress"
    assert payload[1] == 48
    assert "47.7 %" in payload[2]


def test_queued_log_keeps_only_one_blank_line_between_youtube_messages():
    job = TreatmentJob(tool_name="youtube_downloader")
    log = streamlit_app.QueuedLog(job)

    log.write("Démarrage du traitement : youtube_downloader\n")
    for _ in range(10):
        log.write("\r")
    log.write("Fichier téléchargé : first.mp4\n")
    for _ in range(10):
        log.write("\r")
    log.write("Fichier téléchargé : second.m4a\n")

    messages = []
    while not job.events.empty():
        event, payload = job.events.get_nowait()
        if event == "log":
            messages.append(payload)
    assert "".join(messages) == (
        "Démarrage du traitement : youtube_downloader\n\n"
        "Fichier téléchargé : first.mp4\n\n"
        "Fichier téléchargé : second.m4a\n"
    )


def test_completed_treatment_opens_output_folder_once(monkeypatch, tmp_path):
    """Every successful UI treatment reveals its output exactly once."""
    job = TreatmentJob(tool_name="demo", output_dir=tmp_path)
    job.events.put(("done", False))
    open_output = mock.Mock()
    monkeypatch.setattr(streamlit_app, "_open_in_file_explorer", open_output)

    _drain_treatment_events(job)
    _drain_treatment_events(job)

    open_output.assert_called_once_with(tmp_path, "de sortie")
    assert job.output_folder_opened is True


def test_completed_treatment_keeps_output_folder_closed_when_disabled(
    monkeypatch, tmp_path
):
    """The session flag can suppress automatic Explorer launch."""
    job = TreatmentJob(
        tool_name="demo",
        output_dir=tmp_path,
        open_output_on_success=False,
    )
    job.events.put(("done", False))
    open_output = mock.Mock()
    monkeypatch.setattr(streamlit_app, "_open_in_file_explorer", open_output)

    _drain_treatment_events(job)

    open_output.assert_not_called()
    assert job.output_folder_opened is False


def test_completion_waits_ten_seconds_before_an_optional_follow_up(monkeypatch):
    """The generic follow-up flow remains available to other treatments."""
    follow_up = mock.Mock()
    job = TreatmentJob(
        tool_name="video_pipeline",
        follow_up_label="video_encodor",
        follow_up_runner=follow_up,
    )
    job.events.put(("done", False))
    monkeypatch.setattr(streamlit_app, "perf_counter", lambda: 100.0)

    _drain_treatment_events(job)

    assert job.status == "awaiting_follow_up"
    assert job.follow_up_deadline == 110.0
    follow_up.assert_not_called()


def test_completion_skips_an_unneeded_follow_up():
    """A treatment can opt out of its generic follow-up."""
    job = TreatmentJob(
        tool_name="video_pipeline",
        follow_up_label="video_encodor",
        follow_up_runner=mock.Mock(),
        follow_up_required=lambda: False,
    )
    job.events.put(("done", False))

    _drain_treatment_events(job)

    assert job.status == "done"
    assert job.follow_up_deadline is None


def test_follow_up_keeps_its_origin_for_the_console(monkeypatch):
    """The originating tool remains available to a generic follow-up."""
    run_tool = mock.Mock()
    monkeypatch.setattr(streamlit_app, "_run_tool", run_tool)
    job = TreatmentJob(
        tool_name="video_pipeline",
        follow_up_label="video_encodor",
        follow_up_runner=lambda: False,
    )

    streamlit_app._launch_follow_up(job)

    assert run_tool.call_args.args[0] == "video_encodor"
    assert run_tool.call_args.kwargs["origin_tool_name"] == "video_pipeline"


def test_youtube_video_codec_detection_recognizes_hevc(monkeypatch, tmp_path):
    video = tmp_path / "download.mp4"
    video.write_bytes(b"video")
    monkeypatch.setattr(
        streamlit_app,
        "get_all_metadata",
        lambda _path: {
            "streams": [
                {"codec_type": "audio", "codec_name": "aac"},
                {"codec_type": "video", "codec_name": "hevc"},
            ]
        },
    )

    codec = streamlit_app._youtube_video_codec(video)

    assert codec == "hevc"


def test_youtube_video_specs_are_ready_for_the_streamlit_console(monkeypatch, tmp_path):
    video = tmp_path / "download.mp4"
    video.write_bytes(b"video" * 100)
    monkeypatch.setattr(
        streamlit_app,
        "get_all_metadata",
        lambda _path: {
            "format": {"duration": "65", "bit_rate": "2000000"},
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080,
                }
            ],
        },
    )

    codec, specs, height = streamlit_app._youtube_video_specs(video)

    assert codec == "h264"
    assert height == 1080
    assert "Fichier : download.mp4" in specs
    assert "Taille :" in specs
    assert "Codec vidéo : H264" in specs
    assert "Durée : 00:01:05" in specs
    assert "Résolution : 1920×1080" in specs
    assert "Débit : 2000 kb/s" in specs


def test_youtube_requested_level_notice_reports_the_actual_fallback_level():
    assert streamlit_app._youtube_requested_level_notice(
        "MP4", "1080", "160", actual_video_height=720
    ) == (
        "Définition demandée : 1080p indisponible ; définition utilisée : 720p."
    )
    assert streamlit_app._youtube_requested_level_notice(
        "MP3", "1080", "160", actual_audio_bitrate=128.2
    ) == (
        "Débit audio demandé : 160 kb/s indisponible ; débit utilisé : 128 kb/s."
    )
    assert streamlit_app._youtube_requested_level_notice(
        "MP4", "1080", "160", actual_video_height=1080
    ) is None


def test_category_web_submits_an_mp3_download_without_a_real_streamlit_server(
    monkeypatch, tmp_path
):
    """The Web card submits the selected MP3 settings to the shared runner."""
    fake_st = _FakeYoutubeStreamlit(
        output_type="MP3",
        submitted=True,
        session_state=_FakeSessionState(
            youtube_downloader_expanded=True,
            youtube_downloader_url="https://youtu.be/example",
        ),
    )
    cfg = streamlit_app.replace(streamlit_app.APP_CONFIG, OUTPUT_DIR=tmp_path)
    downloaded = tmp_path / "example_download.mp3"
    captured = {}

    monkeypatch.setattr(streamlit_app, "st", fake_st)
    monkeypatch.setattr(
        streamlit_app, "download_youtube_media", lambda options: captured.setdefault("options", options) and [downloaded]
    )
    monkeypatch.setattr(streamlit_app, "probe_audio_bitrate_kbps", lambda _path: 160)
    monkeypatch.setattr(
        streamlit_app,
        "_run_tool",
        lambda tool_name, runner, **kwargs: (
            captured.update(tool_name=tool_name, result=runner(), kwargs=kwargs)
        ),
    )

    streamlit_app._category_web(cfg)

    assert captured["tool_name"] == "youtube_downloader"
    assert captured["result"] is False
    assert captured["options"].media_format == "MP3"
    assert captured["options"].mp3_bitrate == "160"
    assert captured["kwargs"]["open_output_on_success"] is True


def test_category_web_submits_an_mp4_download_and_starts_postprocessing(
    monkeypatch, tmp_path
):
    """The Web card follows the MP4 path, including its post-download action."""
    fake_st = _FakeYoutubeStreamlit(
        output_type="MP4",
        submitted=True,
        session_state=_FakeSessionState(
            youtube_downloader_expanded=True,
            youtube_downloader_url="https://youtu.be/example",
        ),
        subtitles=True,
    )
    cfg = streamlit_app.replace(streamlit_app.APP_CONFIG, OUTPUT_DIR=tmp_path)
    downloaded = tmp_path / "example_download.mp4"
    captured = {}
    encoded = mock.Mock(return_value=False)

    monkeypatch.setattr(streamlit_app, "st", fake_st)
    monkeypatch.setattr(
        streamlit_app, "download_youtube_media", lambda options: captured.setdefault("options", options) and [downloaded]
    )
    monkeypatch.setattr(
        streamlit_app, "_youtube_video_specs", lambda _path: ("h264", "Spécifications", 720)
    )
    monkeypatch.setattr(streamlit_app, "_encode_downloaded_youtube_videos", encoded)
    monkeypatch.setattr(
        streamlit_app,
        "_run_tool",
        lambda tool_name, runner, **kwargs: captured.update(
            tool_name=tool_name, result=runner(), kwargs=kwargs
        ),
    )

    streamlit_app._category_web(cfg)

    assert captured["result"] is False
    assert captured["options"].media_format == "MP4"
    assert captured["options"].video_quality == "720"
    assert captured["options"].download_subtitles is True
    encoded.assert_called_once_with([downloaded], cfg)


def test_category_web_recovers_a_video_when_a_stale_worker_hits_subtitle_429(
    monkeypatch, tmp_path
):
    """A legacy subtitle-only error must not turn an existing MP4 into a failure."""
    fake_st = _FakeYoutubeStreamlit(
        output_type="MP4",
        submitted=True,
        session_state=_FakeSessionState(
            youtube_downloader_expanded=True,
            youtube_downloader_url="https://youtu.be/example",
        ),
        subtitles=True,
    )
    cfg = streamlit_app.replace(streamlit_app.APP_CONFIG, OUTPUT_DIR=tmp_path)
    downloaded = tmp_path / "example_download.mp4"
    captured = {}
    encoded = mock.Mock(return_value=False)

    def stale_downloader(_options):
        downloaded.write_bytes(b"video")
        raise ValueError(
            "Téléchargement YouTube impossible : ERROR: Unable to download "
            "video subtitles for 'fr': HTTP Error 429: Too Many Requests"
        )

    monkeypatch.setattr(streamlit_app, "st", fake_st)
    monkeypatch.setattr(streamlit_app, "download_youtube_media", stale_downloader)
    monkeypatch.setattr(
        streamlit_app, "_youtube_video_specs", lambda _path: ("h264", "Spécifications", 720)
    )
    monkeypatch.setattr(streamlit_app, "_encode_downloaded_youtube_videos", encoded)
    monkeypatch.setattr(
        streamlit_app,
        "_run_tool",
        lambda _tool_name, runner, **_kwargs: captured.update(result=runner()),
    )

    streamlit_app._category_web(cfg)

    assert captured["result"] is False
    encoded.assert_called_once_with([downloaded], cfg)
    assert streamlit_app._is_youtube_subtitle_download_error(
        ValueError("Unable to download video subtitles for 'fr': HTTP Error 429")
    )


def test_youtube_video_postprocessing_reports_the_before_after_size(
    monkeypatch, tmp_path
):
    downloaded = tmp_path / "clip_download.mp4"
    downloaded.write_bytes(b"x" * 1_000)
    cfg = streamlit_app.replace(streamlit_app.APP_CONFIG, OUTPUT_DIR=tmp_path)
    messages = []

    def fake_video_encodor(staging_cfg):
        staging_cfg.OUTPUT_DIR.mkdir()
        (staging_cfg.OUTPUT_DIR / "clip.mp4").write_bytes(b"x" * 400)
        return False

    monkeypatch.setattr(streamlit_app, "video_encodor", fake_video_encodor)
    monkeypatch.setattr(
        streamlit_app,
        "emit",
        lambda message, **kwargs: messages.append((message, kwargs)),
    )
    monkeypatch.setattr(
        streamlit_app,
        "_youtube_video_encodor_preflight",
        lambda *_: (True, "Encodage recommandé : réduction estimée."),
    )

    streamlit_app._encode_downloaded_youtube_videos([downloaded], cfg)

    assert any(
        "Lancement de Video_encodor" in message for message, _ in messages
    )
    assert any("Taille Video_encodor" in message for message, _ in messages)
    assert any(
        message.startswith("\nEncodage recommandé") and kwargs == {"log": False}
        for message, kwargs in messages
    )


def test_youtube_video_preflight_skips_an_efficient_source_codec():
    should_encode, message = streamlit_app._youtube_video_encodor_preflight_from_metadata(
        {
            "format": {"bit_rate": "391000"},
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "av1",
                    "height": 360,
                    "bit_rate": "350000",
                }
            ],
        },
        streamlit_app.APP_CONFIG,
    )

    assert should_encode is False
    assert "Codec source : AV1" in message
    assert "déjà encodée avec AV1" in message


def test_youtube_video_preflight_encodes_a_high_bitrate_h264_source():
    should_encode, message = streamlit_app._youtube_video_encodor_preflight_from_metadata(
        {
            "format": {"bit_rate": "6000000"},
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "height": 1080,
                    "bit_rate": "5800000",
                }
            ],
        },
        streamlit_app.APP_CONFIG,
    )

    assert should_encode is True
    assert "Débit H.265 estimé : 2800 kb/s" in message
    assert "Encodage recommandé" in message


def test_youtube_video_preflight_skips_a_low_bitrate_h264_source():
    should_encode, message = streamlit_app._youtube_video_encodor_preflight_from_metadata(
        {
            "format": {"bit_rate": "2900000"},
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "height": 1080,
                }
            ],
        },
        streamlit_app.APP_CONFIG,
    )

    assert should_encode is False
    assert "la taille augmenterait probablement" in message


def test_legacy_youtube_download_result_finds_the_new_final_file(tmp_path):
    """A boolean legacy result can still continue with the downloaded MP3."""
    existing = tmp_path / "older.mp3"
    existing.write_bytes(b"old")
    downloaded = tmp_path / "new_download.mp3"
    downloaded.write_bytes(b"new")

    files = streamlit_app._find_new_youtube_files(
        tmp_path, {existing}, "MP3"
    )

    assert files == [downloaded]


def test_folder_preview_helpers_sort_recent_entries_and_choose_icons(tmp_path):
    older = tmp_path / "older.txt"
    newer = tmp_path / "newer.mp3"
    gitkeep = tmp_path / ".gitkeep"
    older.write_text("old", encoding="utf-8")
    newer.write_bytes(b"audio")
    gitkeep.write_text("", encoding="utf-8")
    os.utime(older, (1, 1))
    os.utime(newer, (2, 2))
    os.utime(gitkeep, (3, 3))

    entries = streamlit_app._recent_folder_entries(tmp_path)

    assert entries[0] == newer
    assert gitkeep not in entries
    assert streamlit_app._folder_entry_icon(newer) == "audio_file"
    assert streamlit_app._folder_entry_icon(tmp_path) == "folder"


def test_folder_preview_builds_a_synthetic_counter_and_media_details(
    monkeypatch, tmp_path
):
    video = tmp_path / "clip.mp4"
    audio = tmp_path / "podcast.mp3"
    image = tmp_path / "photo.jpg"
    subfolder = tmp_path / "archive"
    video.write_bytes(b"v" * 1_000)
    audio.write_bytes(b"a" * 500)
    image.write_bytes(b"i" * 250)
    subfolder.mkdir()
    monkeypatch.setattr(
        streamlit_app,
        "_cached_folder_media_metadata",
        lambda *_: {
            "format": {"duration": "65", "bit_rate": "2000000"},
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "hevc",
                    "width": 1920,
                    "height": 1080,
                }
            ],
        },
    )

    summary = streamlit_app._folder_summary(tmp_path)
    details = streamlit_app._folder_entry_details(video)

    assert "4 élément(s)" in summary
    assert "1 vidéo(s)" in summary
    assert "1 audio(s)" in summary
    assert "1 image(s)" in summary
    assert "1 dossier(s)" in summary
    assert "00:01:05" in details
    assert "HEVC" in details
    assert "1920×1080" in details
    assert "2000 kb/s" in details


def test_clear_folder_content_removes_everything_except_gitkeep(tmp_path):
    """Folder cleanup preserves the repository placeholder and clears contents."""
    gitkeep = tmp_path / ".gitkeep"
    gitkeep.write_text("", encoding="utf-8")
    (tmp_path / "file.txt").write_text("delete me", encoding="utf-8")
    nested_folder = tmp_path / "nested"
    nested_folder.mkdir()
    (nested_folder / "child.txt").write_text("delete me too", encoding="utf-8")

    deleted_count = streamlit_app._clear_folder_content(tmp_path)

    assert deleted_count == 2
    assert gitkeep.exists()
    assert list(tmp_path.iterdir()) == [gitkeep]


def test_clear_folder_content_rejects_a_missing_folder(tmp_path):
    with pytest.raises(FileNotFoundError, match="Dossier introuvable"):
        streamlit_app._clear_folder_content(tmp_path / "missing")


def test_import_copy_preserves_the_source_and_avoids_overwriting(tmp_path):
    source_folder = tmp_path / "source"
    source_folder.mkdir()
    source = source_folder / "video.mp4"
    source.write_bytes(b"new")
    input_folder = tmp_path / "input"
    input_folder.mkdir()
    (input_folder / "video.mp4").write_bytes(b"existing")

    copied_count = streamlit_app._copy_files_to_folder([source], input_folder)

    assert copied_count == 1
    assert source.read_bytes() == b"new"
    assert (input_folder / "video.mp4").read_bytes() == b"existing"
    assert (input_folder / "video (1).mp4").read_bytes() == b"new"


def test_export_output_files_skips_gitkeep_and_copies_files(tmp_path):
    output_folder = tmp_path / "output"
    export_folder = tmp_path / "export"
    output_folder.mkdir()
    export_folder.mkdir()
    (output_folder / ".gitkeep").write_text("", encoding="utf-8")
    (output_folder / "clip.mp4").write_bytes(b"video")
    (output_folder / "nested").mkdir()

    copied_count = streamlit_app._export_output_files(output_folder, export_folder)

    assert copied_count == 1
    assert (export_folder / "clip.mp4").read_bytes() == b"video"
    assert not (export_folder / ".gitkeep").exists()


def test_export_output_files_rejects_output_as_its_own_destination(tmp_path):
    output_folder = tmp_path / "output"
    output_folder.mkdir()

    with pytest.raises(ValueError, match="différent d’OUTPUT"):
        streamlit_app._export_output_files(output_folder, output_folder)


def test_folder_shortcuts_import_and_export_through_the_sidebar_controls(
    monkeypatch, tmp_path
):
    """Sidebar actions call the native pickers' copy workflows independently."""
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    export_dir = tmp_path / "export"
    input_dir.mkdir()
    output_dir.mkdir()
    export_dir.mkdir()
    source = tmp_path / "source.mp4"
    source.write_bytes(b"input")
    (output_dir / "result.mp4").write_bytes(b"output")
    fake_st = _FakeStreamlit(
        buttons={"import_input_files": True, "export_output_files": True}
    )
    cfg = streamlit_app.replace(
        streamlit_app.APP_CONFIG,
        INPUT_DIR=input_dir,
        OUTPUT_DIR=output_dir,
    )

    monkeypatch.setattr(streamlit_app, "st", fake_st)
    monkeypatch.setattr(streamlit_app, "_select_files_to_import", lambda: [source])
    monkeypatch.setattr(streamlit_app, "_select_export_folder", lambda _path: export_dir)
    monkeypatch.setattr(streamlit_app, "_render_folder_preview", mock.Mock())
    monkeypatch.setattr(streamlit_app, "_folder_open_icon", mock.Mock())

    streamlit_app._render_folder_shortcuts.__wrapped__(cfg)

    assert (input_dir / source.name).read_bytes() == b"input"
    assert (export_dir / "result.mp4").read_bytes() == b"output"


def test_active_treatment_panel_can_skip_a_pending_follow_up(monkeypatch, tmp_path):
    """The countdown panel lets a user decline the automatic next treatment."""
    fake_st = _FakeStreamlit(buttons={"skip_download_follow_up": True})
    job = TreatmentJob(
        tool_name="youtube_downloader",
        status="awaiting_follow_up",
        output_dir=tmp_path,
        follow_up_label="video_encodor",
        follow_up_runner=mock.Mock(),
    )
    fake_st.session_state.active_treatment = job
    open_folder = mock.Mock()

    monkeypatch.setattr(streamlit_app, "st", fake_st)
    monkeypatch.setattr(streamlit_app, "_open_in_file_explorer", open_folder)
    monkeypatch.setattr(streamlit_app, "perf_counter", lambda: 100.0)

    streamlit_app._render_active_treatment.__wrapped__()

    assert job.status == "done"
    assert job.follow_up_runner is None
    open_folder.assert_called_once_with(tmp_path, "de sortie")


def test_active_treatment_panel_renders_running_progress_and_completion(monkeypatch):
    """The active panel renders a live bar and the successful completion state."""
    fake_st = _FakeStreamlit()
    job = TreatmentJob(
        tool_name="video_assemblor",
        status="running",
        output="Encodage en cours",
        progress={0: (42, "Assemblage")},
    )
    fake_st.session_state.active_treatment = job
    monkeypatch.setattr(streamlit_app, "st", fake_st)

    streamlit_app._render_active_treatment.__wrapped__()

    job.status = "done"
    streamlit_app._render_active_treatment.__wrapped__()
    assert job.cancel_event.is_set() is False


def test_runtime_reports_and_tool_launcher_use_session_values(monkeypatch):
    """Session settings are copied to the runtime config and jobs start once."""
    fake_st = _FakeStreamlit(
        session_state=_FakeSessionState(
            {
                "flag_LOG_TO_FILE": False,
                "flag_OPEN_OUTPUT_DIR_AFTER_TREATMENT": False,
                "value_LOG_LEVEL": "DEBUG",
            }
        )
    )
    monkeypatch.setattr(streamlit_app, "st", fake_st)
    cfg = streamlit_app._runtime_config()
    assert cfg.LOG_TO_FILE is False
    assert cfg.LOG_LEVEL == "DEBUG"
    assert cfg.OPEN_OUTPUT_DIR_AFTER_TREATMENT is False

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
    assert (
        fake_st.session_state.active_treatment.output_dir
        == streamlit_app.APP_CONFIG.OUTPUT_DIR
    )
    assert fake_st.session_state.active_treatment.open_output_on_success is False
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

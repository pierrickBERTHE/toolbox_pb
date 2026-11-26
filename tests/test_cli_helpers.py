"""Tests for the terminal-only option prompts."""

from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

import toolbox_pb.ui.cli_helpers as cli_helpers


def test_image_defilor_reprompts_then_uses_the_entered_options(
    monkeypatch, capsys
):
    monkeypatch.setattr(
        "builtins.input",
        mock.Mock(side_effect=["maybe", "oui", "--height 720"]),
    )
    runner = mock.Mock(return_value=False)
    monkeypatch.setattr(cli_helpers, "image_defilor", runner)

    assert (
        cli_helpers.run_image_defilor_interactive(mock.sentinel.config)
        is False
    )
    runner.assert_called_once_with(
        mock.sentinel.config, extra_args="--height 720"
    )
    assert "Réponse invalide" in capsys.readouterr().out


def test_image_defilor_uses_no_extra_options_and_handles_invalid_arguments(
    monkeypatch, capsys
):
    monkeypatch.setattr("builtins.input", mock.Mock(return_value="n"))
    runner = mock.Mock(side_effect=ValueError("option inconnue"))
    monkeypatch.setattr(cli_helpers, "image_defilor", runner)

    assert (
        cli_helpers.run_image_defilor_interactive(mock.sentinel.config) is True
    )
    runner.assert_called_once_with(mock.sentinel.config, extra_args=None)
    assert "option inconnue" in capsys.readouterr().out


def test_audio_decalator_reprompts_after_invalid_number(monkeypatch, capsys):
    monkeypatch.setattr(
        "builtins.input", mock.Mock(side_effect=["invalid", "-0.5"])
    )
    runner = mock.Mock(return_value=True)
    monkeypatch.setattr(cli_helpers, "video_audio_decalator", runner)

    assert (
        cli_helpers.run_video_audio_decalator_interactive(mock.sentinel.config)
        is True
    )
    runner.assert_called_once_with(mock.sentinel.config, -0.5)
    assert "Format invalide" in capsys.readouterr().out


def test_youtube_downloader_uses_default_mp3_settings(monkeypatch, tmp_path):
    """The CLI forwards the same MP3 defaults as the graphical interface."""
    answers = iter(["https://youtu.be/example", "", ""])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    downloader = mock.Mock(return_value=[tmp_path / "example_download.mp3"])
    monkeypatch.setattr(cli_helpers, "download_youtube_media", downloader)

    cfg = SimpleNamespace(OUTPUT_DIR=tmp_path)
    assert cli_helpers.run_youtube_downloader_interactive(cfg) is False

    options = downloader.call_args.args[0]
    assert options.url == "https://youtu.be/example"
    assert options.output_dir == tmp_path
    assert options.media_format == "MP3"
    assert options.mp3_bitrate == "160"
    assert options.video_quality == "1080"


def test_youtube_downloader_uses_selected_mp4_quality(monkeypatch, tmp_path):
    """The CLI forwards a selected MP4 maximum quality to the core."""
    answers = iter(["https://www.youtube.com/watch?v=example", "2", "720"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    downloader = mock.Mock(
        return_value=[Path(tmp_path / "example_download.mp4")]
    )
    monkeypatch.setattr(cli_helpers, "download_youtube_media", downloader)

    cfg = SimpleNamespace(OUTPUT_DIR=tmp_path)
    assert cli_helpers.run_youtube_downloader_interactive(cfg) is False

    options = downloader.call_args.args[0]
    assert options.media_format == "MP4"
    assert options.video_quality == "720"
    assert options.mp3_bitrate == "160"


@pytest.mark.parametrize(
    ("answers", "message"),
    [
        (["q"], "annulé"),
        ([""], "ne peut pas être vide"),
        (["https://youtu.be/example", "3"], "Format invalide"),
        (["https://youtu.be/example", "1", "999"], "Débit MP3 invalide"),
        (["https://youtu.be/example", "2", "999"], "Qualité vidéo invalide"),
    ],
)
def test_youtube_downloader_rejects_cancelled_or_invalid_answers(
    monkeypatch, capsys, answers, message
):
    monkeypatch.setattr("builtins.input", mock.Mock(side_effect=answers))

    assert (
        cli_helpers.run_youtube_downloader_interactive(mock.sentinel.config)
        is None
    )
    assert message in capsys.readouterr().out


def test_youtube_downloader_displays_core_validation_errors(
    monkeypatch, capsys, tmp_path
):
    monkeypatch.setattr(
        "builtins.input",
        mock.Mock(side_effect=["https://youtu.be/example", "1", "160"]),
    )
    monkeypatch.setattr(
        cli_helpers,
        "download_youtube_media",
        mock.Mock(side_effect=ValueError("yt-dlp indisponible")),
    )

    assert (
        cli_helpers.run_youtube_downloader_interactive(
            SimpleNamespace(OUTPUT_DIR=tmp_path)
        )
        is None
    )
    assert "yt-dlp indisponible" in capsys.readouterr().out

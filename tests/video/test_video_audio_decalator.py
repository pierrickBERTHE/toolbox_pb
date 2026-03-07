"""Unit tests for video_audio_decalator."""

import sys
from pathlib import Path
from unittest import mock

import pytest

# Add the toolbox_pb directory to sys.path for imports
sys.path.append(str(Path(__file__).resolve().parents[2] / "toolbox_pb"))

from config_global import AppConfig
from video.main_video import video_audio_decalator


@pytest.fixture
def fake_config(tmp_path):
    """Minimal isolated configuration used for unit tests."""
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    segment_dir = tmp_path / "segment"
    input_dir.mkdir()
    output_dir.mkdir()
    segment_dir.mkdir()

    return AppConfig(
        INPUT_ACCEPTED_FILES=[".mp4", ".mov", ".avi"],
        INPUT_ACCEPTED_VIDEO_FILES=[".mp4", ".mov", ".avi"],
        INPUT_ACCEPTED_IMAGE_FILES=[".jpg", ".png"],
        INPUT_ACCEPTED_PDF_FILES=[".pdf"],
        CODEC_VIDEO_LIST=["libx264", "libx265"],
        CODEC_VIDEO="libx265",
        CODEC_AUDIO="aac",
        SUFFIX_OUTPUT=[".mp4", ".jpg", ".pdf"],
        SUFFIX_OUTPUT_VIDEO=".mp4",
        SUFFIX_OUTPUT_IMAGE=".jpg",
        SUFFIX_OUTPUT_PDF=".pdf",
        ROOT=tmp_path,
        LOG_DIR=tmp_path / "log",
        INPUT_DIR=input_dir,
        OUTPUT_DIR=output_dir,
        SEGMENT_DIR=segment_dir,
        LOG_TO_FILE=False,
        ADD_CODEC_NAME_IN_OUTPUT=False,
        PRINT_ALL_KEYS_IN_METADATA_SUMMARY=False,
    )


def test_processes_video_file(fake_config):
    """A valid video file is processed with the parsed delay."""
    input_file = fake_config.INPUT_DIR / "video.mp4"
    input_file.touch()

    output_path = fake_config.OUTPUT_DIR / "video.mp4"

    with (
        mock.patch("builtins.input", return_value="0.5"),
        mock.patch("video.main_video.func_glob.build_output_subdir_from_input", return_value=fake_config.OUTPUT_DIR),
        mock.patch("video.main_video.func_glob.build_output_path", return_value=output_path),
        mock.patch("video.main_video.func_vid.shift_audio_no_reencode") as shift_mock,
    ):
        result = video_audio_decalator(fake_config)

    shift_mock.assert_called_once_with(
        input_video=input_file,
        output_video=output_path,
        delay=0.5,
    )
    assert result is False


def test_skips_already_processed_file(fake_config, capsys):
    """An already processed file is skipped."""
    input_file = fake_config.INPUT_DIR / "video.mp4"
    input_file.touch()

    output_path = fake_config.OUTPUT_DIR / "video.mp4"
    output_path.touch()

    with (
        mock.patch("builtins.input", return_value="0.5"),
        mock.patch("video.main_video.func_glob.build_output_subdir_from_input", return_value=fake_config.OUTPUT_DIR),
        mock.patch("video.main_video.func_glob.build_output_path", return_value=output_path),
        mock.patch("video.main_video.func_vid.shift_audio_no_reencode") as shift_mock,
    ):
        result = video_audio_decalator(fake_config)

    shift_mock.assert_not_called()
    assert result is False
    captured = capsys.readouterr()
    assert "Décalage déjà réalisé." in captured.out


def test_empty_folder_returns_true(fake_config):
    """An empty input folder returns True."""
    with mock.patch("builtins.input", return_value="0.5"):
        result = video_audio_decalator(fake_config)
    assert result is True


def test_ignores_non_video_files(fake_config):
    """Non-video files are ignored."""
    (fake_config.INPUT_DIR / "image.jpg").touch()
    (fake_config.INPUT_DIR / "document.pdf").touch()

    with (
        mock.patch("builtins.input", return_value="0.5"),
        mock.patch("video.main_video.func_vid.shift_audio_no_reencode") as shift_mock,
    ):
        result = video_audio_decalator(fake_config)

    shift_mock.assert_not_called()
    assert result is True


def test_invalid_delay_then_valid(fake_config, capsys):
    """Invalid delay input loops until a valid float is provided."""
    with mock.patch("builtins.input", side_effect=["abc", "xyz", "-0.5"]):
        result = video_audio_decalator(fake_config)

    assert result is True
    captured = capsys.readouterr()
    assert "Format invalide" in captured.out


def test_negative_delay(fake_config):
    """A negative delay is accepted and passed through."""
    input_file = fake_config.INPUT_DIR / "video.mp4"
    input_file.touch()
    output_path = fake_config.OUTPUT_DIR / "video.mp4"

    with (
        mock.patch("builtins.input", return_value="-0.5"),
        mock.patch("video.main_video.func_glob.build_output_subdir_from_input", return_value=fake_config.OUTPUT_DIR),
        mock.patch("video.main_video.func_glob.build_output_path", return_value=output_path),
        mock.patch("video.main_video.func_vid.shift_audio_no_reencode") as shift_mock,
    ):
        video_audio_decalator(fake_config)

    shift_mock.assert_called_once_with(
        input_video=input_file,
        output_video=output_path,
        delay=-0.5,
    )

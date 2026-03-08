"""Unit tests for video_volume_adjust."""

import sys
from pathlib import Path
from unittest import mock

import pytest

# Add the toolbox_pb directory to sys.path for imports
sys.path.append(str(Path(__file__).resolve().parents[2] / "toolbox_pb"))

from config_global import AppConfig
from video.main_video import video_volume_adjust


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


def test_missing_boosts_csv_returns_true(fake_config, capsys):
    """If boosts.csv is missing, function returns True and prints warning."""
    with mock.patch("video.main_video.func_vid.apply_audio_boosts_ffmpeg") as boost_mock:
        result = video_volume_adjust(fake_config)

    assert result is True
    boost_mock.assert_not_called()
    captured = capsys.readouterr()
    assert "Fichier de segments introuvable" in captured.out


def test_empty_input_with_boosts_csv_returns_true(fake_config):
    """If no input video exists, function returns True."""
    (fake_config.SEGMENT_DIR / "boosts.csv").write_text(
        "start,end,gain_db\n00:00:01,00:00:03,3\n",
        encoding="utf-8",
    )

    with mock.patch("video.main_video.func_vid.apply_audio_boosts_ffmpeg") as boost_mock:
        result = video_volume_adjust(fake_config)

    assert result is True
    boost_mock.assert_not_called()


def test_ignores_non_video_files(fake_config):
    """Non-video files are ignored."""
    (fake_config.SEGMENT_DIR / "boosts.csv").write_text(
        "start,end,gain_db\n00:00:01,00:00:03,3\n",
        encoding="utf-8",
    )
    (fake_config.INPUT_DIR / "notes.txt").touch()
    (fake_config.INPUT_DIR / "image.jpg").touch()

    with mock.patch("video.main_video.func_vid.apply_audio_boosts_ffmpeg") as boost_mock:
        result = video_volume_adjust(fake_config)

    assert result is True
    boost_mock.assert_not_called()


def test_processes_video_when_output_not_exists(fake_config):
    """A valid input video is processed when output does not exist."""
    boosts_csv = fake_config.SEGMENT_DIR / "boosts.csv"
    boosts_csv.write_text("start,end,gain_db\n00:00:01,00:00:03,3\n", encoding="utf-8")

    input_video = fake_config.INPUT_DIR / "clip.mp4"
    input_video.touch()
    expected_output = fake_config.OUTPUT_DIR / "clip.mp4"

    with mock.patch("video.main_video.func_vid.apply_audio_boosts_ffmpeg") as boost_mock:
        result = video_volume_adjust(fake_config)

    assert result is False
    boost_mock.assert_called_once_with(
        input_video=input_video,
        output_video=expected_output,
        csv_path=boosts_csv,
    )


def test_skips_already_adjusted_file(fake_config, capsys):
    """If output exists, adjustment is skipped."""
    (fake_config.SEGMENT_DIR / "boosts.csv").write_text(
        "start,end,gain_db\n00:00:01,00:00:03,3\n",
        encoding="utf-8",
    )
    input_video = fake_config.INPUT_DIR / "clip.mp4"
    input_video.touch()
    (fake_config.OUTPUT_DIR / "clip.mp4").touch()

    with mock.patch("video.main_video.func_vid.apply_audio_boosts_ffmpeg") as boost_mock:
        result = video_volume_adjust(fake_config)

    assert result is False
    boost_mock.assert_not_called()
    captured = capsys.readouterr()
    assert "Ajustement déjà réalisé." in captured.out


def test_processes_only_missing_outputs_in_mixed_case(fake_config):
    """Only videos without output are processed in a mixed input/output scenario."""
    boosts_csv = fake_config.SEGMENT_DIR / "boosts.csv"
    boosts_csv.write_text("start,end,gain_db\n00:00:01,00:00:03,3\n", encoding="utf-8")

    v1 = fake_config.INPUT_DIR / "a.mp4"
    v2 = fake_config.INPUT_DIR / "b.mov"
    v1.touch()
    v2.touch()
    (fake_config.OUTPUT_DIR / "a.mp4").touch()

    with mock.patch("video.main_video.func_vid.apply_audio_boosts_ffmpeg") as boost_mock:
        result = video_volume_adjust(fake_config)

    assert result is False
    boost_mock.assert_called_once_with(
        input_video=v2,
        output_video=fake_config.OUTPUT_DIR / "b.mp4",
        csv_path=boosts_csv,
    )

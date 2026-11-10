"""Tests for the video_rotator feature."""

from unittest import mock

import pytest

from toolbox_pb.core.video.func_video import (
    rotate_video_ffmpeg,
    validate_rotation_angle,
)
from toolbox_pb.core.video.main_video import video_rotator
from toolbox_pb.core.config_global import AppConfig


@pytest.fixture
def fake_config(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    return AppConfig(
        INPUT_ACCEPTED_FILES=[".mp4", ".mov"],
        INPUT_ACCEPTED_VIDEO_FILES=[".mp4", ".mov"],
        INPUT_ACCEPTED_IMAGE_FILES=[".jpg"],
        INPUT_ACCEPTED_PDF_FILES=[".pdf"],
        CODEC_VIDEO_LIST=["libx264"],
        CODEC_VIDEO="libx264",
        CODEC_AUDIO="aac",
        SUFFIX_OUTPUT=[".mp4", ".jpg", ".pdf"],
        SUFFIX_OUTPUT_VIDEO=".mp4",
        SUFFIX_OUTPUT_IMAGE=".jpg",
        SUFFIX_OUTPUT_PDF=".pdf",
        ROOT=tmp_path,
        LOG_DIR=tmp_path / "log",
        INPUT_DIR=input_dir,
        OUTPUT_DIR=output_dir,
        SEGMENT_DIR=tmp_path / "segment",
        LOG_TO_FILE=False,
    )


@pytest.mark.parametrize("angle", [90, 180, 270, "90", "180", "270"])
def test_validate_rotation_angle_accepts_only_quarter_turns(angle):
    assert validate_rotation_angle(angle) == int(angle)


@pytest.mark.parametrize("angle", [None, 0, 360, -90, 90.0, "90°", "45"])
def test_validate_rotation_angle_rejects_other_values(angle):
    with pytest.raises(ValueError, match="90, 180 ou 270"):
        validate_rotation_angle(angle)


def test_rotate_video_ffmpeg_builds_a_clockwise_rotation_command(tmp_path, monkeypatch):
    input_video = tmp_path / "input.mp4"
    output_video = tmp_path / "output.mp4"
    input_video.touch()
    runner = mock.Mock()
    monkeypatch.setattr(
        "toolbox_pb.core.video.func_video.probe_video_duration", lambda _: 12.0
    )
    monkeypatch.setattr(
        "toolbox_pb.core.video.func_video._run_ffmpeg_with_progress", runner
    )

    rotate_video_ffmpeg(
        input_video, output_video, 90, "libx264", "video_rotator comment"
    )

    command = runner.call_args.args[0]
    assert command[command.index("-vf") + 1] == "transpose=1"
    assert command[command.index("-c:a") + 1] == "copy"
    assert command[command.index("-metadata:s:v:0") + 1] == "rotate=0"
    assert runner.call_args.args[1:] == (12.0, "input.mp4")


def test_video_rotator_preserves_the_exact_input_filename(fake_config):
    input_video = fake_config.INPUT_DIR / "nested" / "clip.mov"
    input_video.parent.mkdir()
    input_video.touch()

    with mock.patch(
        "toolbox_pb.core.video.main_video.func_vid.rotate_video_ffmpeg"
    ) as rotate:
        assert video_rotator(fake_config, "270") is False

    rotate.assert_called_once_with(
        input_video=input_video,
        output_video=fake_config.OUTPUT_DIR / "nested" / "clip.mov",
        angle=270,
        codec_video="libx264",
        processing_comment=mock.ANY,
    )
    assert "Rotation image : 270°" in rotate.call_args.kwargs["processing_comment"]


def test_video_rotator_rejects_invalid_angle_before_processing(fake_config):
    with pytest.raises(ValueError, match="90, 180 ou 270"):
        video_rotator(fake_config, 45)

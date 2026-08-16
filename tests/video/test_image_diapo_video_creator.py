"""Unit tests for the image slideshow video creator."""

import sys
from dataclasses import replace
from pathlib import Path
from unittest import mock

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2] / "toolbox_pb"))

from config_global import APP_CONFIG
from video.main_video import image_diapo_video_creator


@pytest.fixture
def slideshow_config(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    return replace(
        APP_CONFIG,
        LOG_TO_FILE=False,
        INPUT_DIR=input_dir,
        OUTPUT_DIR=tmp_path / "output",
        IMAGE_DIAPO_DURATION_SECONDS=2.5,
    )


def test_image_diapo_returns_true_without_images(slideshow_config):
    """No image means no output video is created."""
    assert image_diapo_video_creator(slideshow_config) is True


def test_image_diapo_accepts_jpeg_extension(slideshow_config):
    """JPEG images are included regardless of the extension's case."""
    image = slideshow_config.INPUT_DIR / "photo.JPEG"
    image.touch()

    with mock.patch(
        "video.main_video.func_vid.get_image_size", return_value=(100, 100)
    ), mock.patch(
        "video.main_video.func_vid.create_image_diapo_ffmpeg"
    ) as create_diapo:
        assert image_diapo_video_creator(slideshow_config) is False

    assert create_diapo.call_args.kwargs["image_paths"] == [image]


def test_image_diapo_rejects_non_positive_duration(slideshow_config):
    """The configured display duration must be positive."""
    with pytest.raises(ValueError, match="strictement positif"):
        image_diapo_video_creator(
            replace(slideshow_config, IMAGE_DIAPO_DURATION_SECONDS=0)
        )


def test_image_diapo_rejects_non_positive_fps(slideshow_config):
    """The configured slideshow frame rate must be positive."""
    with pytest.raises(ValueError, match="IMAGE_DIAPO_FPS"):
        image_diapo_video_creator(replace(slideshow_config, IMAGE_DIAPO_FPS=0))


def test_image_diapo_rejects_non_positive_max_height(slideshow_config):
    """The configured maximum output height must be positive."""
    with pytest.raises(ValueError, match="IMAGE_DIAPO_MAX_HEIGHT"):
        image_diapo_video_creator(
            replace(slideshow_config, IMAGE_DIAPO_MAX_HEIGHT=0)
        )


def test_image_diapo_rejects_multiple_audio_files(slideshow_config):
    """Selecting an audio track is unambiguous when only one is supplied."""
    (slideshow_config.INPUT_DIR / "slide.jpg").touch()
    (slideshow_config.INPUT_DIR / "a.mp3").touch()
    (slideshow_config.INPUT_DIR / "b.wav").touch()

    with pytest.raises(ValueError, match="Un seul fichier audio"):
        image_diapo_video_creator(slideshow_config)


def test_image_diapo_creates_ordered_video_with_audio(slideshow_config):
    """Images are assembled at the configured duration and receive audio."""
    nested = slideshow_config.INPUT_DIR / "nested"
    nested.mkdir()
    first = slideshow_config.INPUT_DIR / "a.jpg"
    second = nested / "b.png"
    audio = slideshow_config.INPUT_DIR / "sound.mp3"
    for path in (first, second, audio):
        path.touch()

    with mock.patch(
        "video.main_video.func_vid.get_image_size",
        side_effect=[(1600, 900), (900, 1600)],
    ) as get_size, mock.patch(
        "video.main_video.func_vid.create_image_diapo_ffmpeg"
    ) as create_diapo:
        assert image_diapo_video_creator(slideshow_config) is False

    assert get_size.call_args_list == [mock.call(first), mock.call(second)]
    create_diapo.assert_called_once_with(
        image_paths=[first, second],
        input_dir=slideshow_config.INPUT_DIR,
        audio_path=audio,
        output_path=slideshow_config.OUTPUT_DIR /
        "image_diapo_video_v-libx265_a-aac.mp4",
        duration=2.5,
        fps=24,
        frame_size=(2844, 1600),
        codec_video="libx265",
        codec_audio="aac",
    )


def test_image_diapo_creates_video_without_audio(slideshow_config):
    """Audio attachment is skipped when the input directory has no audio file."""
    image = slideshow_config.INPUT_DIR / "slide.jpg"
    image.touch()
    with mock.patch(
        "video.main_video.func_vid.get_image_size", return_value=(100, 100)
    ), mock.patch(
        "video.main_video.func_vid.create_image_diapo_ffmpeg"
    ) as create_diapo:
        assert image_diapo_video_creator(slideshow_config) is False

    assert create_diapo.call_args.kwargs["audio_path"] is None
    assert create_diapo.call_args.kwargs["output_path"].name.startswith(
        "image_diapo_video_v-"
    )

"""
Unit tests for the image.func_image module
"""
# Imports standard
import sys
import json
import subprocess
from pathlib import Path
from unittest import mock
import pytest

# Add the toolbox_pb directory to sys.path for imports
sys.path.append(str(Path(__file__).resolve().parents[2] / "toolbox_pb"))

# Import the module to test
from image.func_image import (
    parse_defilor_extra_args,
    get_image_size,
    build_scroll_expression,
    generate_image_defilor,
)


class DummyProc:
    """Simple fake subprocess.Popen result for ffmpeg calls."""

    def __init__(self, returncode=0):
        self.returncode = returncode
        self.stdout = mock.MagicMock()

    def wait(self):
        return self.returncode


def test_parse_defilor_extra_args_defaults():
    """It should return default values when no args are provided."""
    args = parse_defilor_extra_args(None)
    assert args.height == 1080
    assert args.speed == 35.0
    assert args.fps == 60
    assert args.hold_start == 5.0
    assert args.hold_end == 5.0
    assert args.codec == "libx265"
    assert args.crf == 18


def test_parse_defilor_extra_args_custom_values():
    """It should parse all custom values correctly."""
    raw = "--height 720 --speed 50 --fps 30 --hold-start 2 --hold-end 3 --codec libx264 --crf 20"
    args = parse_defilor_extra_args(raw)
    assert args.height == 720
    assert args.speed == 50
    assert args.fps == 30
    assert args.hold_start == 2
    assert args.hold_end == 3
    assert args.codec == "libx264"
    assert args.crf == 20


def test_parse_defilor_extra_args_unknown_arg():
    """It should raise ValueError when unknown args are present."""
    with pytest.raises(ValueError, match="Unknown arguments"):
        parse_defilor_extra_args("--unknown 1")


def test_get_image_size_missing_file(tmp_path):
    """It should raise FileNotFoundError for a missing image path."""
    missing = tmp_path / "missing.jpg"
    with pytest.raises(FileNotFoundError):
        get_image_size(missing)


def test_get_image_size_success(tmp_path):
    """It should parse width/height from ffprobe JSON output."""
    # Create a dummy image file
    image = tmp_path / "img.jpg"
    image.touch()
    
    # Mock subprocess.run to return a successful ffprobe output
    payload = {"streams": [{"width": 1920, "height": 1080}]}
    completed = subprocess.CompletedProcess(
        args=["ffprobe"],
        returncode=0,
        stdout=json.dumps(payload),
        stderr="",
    )
    with mock.patch("image.func_image.subprocess.run", return_value=completed):
        width, height = get_image_size(image)

    # Assert the returned dimensions match the mocked output
    assert (width, height) == (1920, 1080)


def test_get_image_size_no_streams(tmp_path):
    """It should fail when ffprobe returns no streams."""
    # Create a dummy image file
    image = tmp_path / "img.jpg"
    image.touch()

    # Mock subprocess.run to return ffprobe output with no streams
    completed = subprocess.CompletedProcess(
        args=["ffprobe"],
        returncode=0,
        stdout=json.dumps({"streams": []}),
        stderr="",
    )
    with mock.patch("image.func_image.subprocess.run", return_value=completed):
        with pytest.raises(RuntimeError, match="No image stream detected"):
            get_image_size(image)


def test_build_scroll_expression_no_travel():
    """It should keep y=0 and add 1s minimum body when no scroll is needed."""
    expr, total = build_scroll_expression(
        image_height=720,
        output_height=720,
        hold_start=2.0,
        hold_end=3.0,
        scroll_speed_px_s=40.0,
    )
    assert expr == "0"
    assert total == 6.0


def test_build_scroll_expression_with_travel():
    """It should build a piecewise expression and proper duration."""
    expr, total = build_scroll_expression(
        image_height=1080,
        output_height=720,
        hold_start=2.0,
        hold_end=3.0,
        scroll_speed_px_s=60.0,
    )
    assert "if(lt(t,2.0)" in expr
    assert total == 11.0


def test_generate_image_defilor_calls_ffmpeg_and_progress(tmp_path):
    """It should call ffmpeg and shared progress parser in nominal flow."""
    # Create a dummy image file
    image = tmp_path / "img.jpg"
    image.touch()
    output = tmp_path / "out.mp4"

    # Mock several functions to isolate the ffmpeg call and progress parsing
    fake_proc = DummyProc(returncode=0)
    with mock.patch("image.func_image.get_image_size", return_value=(1200, 2000)), \
        mock.patch("image.func_image.consume_ffmpeg_progress", return_value=[]), \
        mock.patch("image.func_image.subprocess.Popen", return_value=fake_proc) as popen_mock:

        # Act
        generate_image_defilor(
            image_path=image,
            output_path=output,
            output_height=1080,
            fps=60,
            scroll_speed_px_s=35.0,
            hold_start=1.0,
            hold_end=1.0,
            codec="libx265",
            crf=18,
        )

    # Assert
    popen_mock.assert_called_once()
    cmd = popen_mock.call_args.args[0]
    assert "ffmpeg" in cmd[0]
    assert "-progress" in cmd
    assert str(output) in cmd


@pytest.mark.parametrize(
    "kwargs, expected_message",
    [
        (
            {"output_height": 0, "fps": 60, "scroll_speed_px_s": 35.0},
            "output_height must be > 0"
        ),
        (
            {"output_height": 100, "fps": 0, "scroll_speed_px_s": 35.0},
            "fps must be > 0"
        ),
        (
            {"output_height": 100, "fps": 60, "scroll_speed_px_s": 0},
            "scroll_speed_px_s must be > 0"
        ),
    ],
)
def test_generate_image_defilor_validation_errors(tmp_path, kwargs, expected_message):
    """It should fail fast on invalid numeric inputs."""
    image = tmp_path / "img.jpg"
    image.touch()
    output = tmp_path / "out.mp4"
    with mock.patch("image.func_image.get_image_size", return_value=(800, 600)):
        with pytest.raises(ValueError, match=expected_message):
            generate_image_defilor(
                image_path=image,
                output_path=output,
                hold_start=1.0,
                hold_end=1.0,
                codec="libx265",
                crf=18,
                **kwargs,
            )


def test_generate_image_defilor_height_larger_than_image(tmp_path):
    """It should reject output height larger than image height."""
    image = tmp_path / "img.jpg"
    image.touch()
    output = tmp_path / "out.mp4"
    with mock.patch("image.func_image.get_image_size", return_value=(800, 600)):
        with pytest.raises(ValueError, match="image height"):
            generate_image_defilor(
                image_path=image,
                output_path=output,
                output_height=700,
                fps=60,
                scroll_speed_px_s=35.0,
                hold_start=1.0,
                hold_end=1.0,
                codec="libx265",
                crf=18,
            )


def test_generate_image_defilor_raises_runtimeerror_on_ffmpeg_failure(tmp_path):
    """It should wrap ffmpeg process failure as RuntimeError."""
    # Create a dummy image file
    image = tmp_path / "img.jpg"
    image.touch()
    output = tmp_path / "out.mp4"
    
    # Mock several functions to simulate an ffmpeg failure with error messages
    fake_proc = DummyProc(returncode=1)
    with mock.patch("image.func_image.get_image_size", return_value=(1200, 2000)), \
        mock.patch("image.func_image.consume_ffmpeg_progress", return_value=["error one", "error two"]), \
        mock.patch("image.func_image.subprocess.Popen", return_value=fake_proc):
        with pytest.raises(RuntimeError, match="ffmpeg failed"):
            generate_image_defilor(
                image_path=image,
                output_path=output,
                output_height=1080,
                fps=60,
                scroll_speed_px_s=35.0,
                hold_start=1.0,
                hold_end=1.0,
                codec="libx265",
                crf=18,
            )

"""
Unit tests for image.main_image.
"""
# Imports standard
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

# Add the toolbox_pb directory to sys.path for imports
sys.path.append(str(Path(__file__).resolve().parents[2] / "toolbox_pb"))

# Imports local
from image.main_image import image_defilor, run_image_defilor_interactive


def build_fake_cfg(tmp_path):
    """Create a minimal config object compatible with image_defilor."""
    return SimpleNamespace(
        INPUT_ACCEPTED_IMAGE_FILES={".jpg", ".png"},
        INPUT_ACCEPTED_PDF_FILES={".pdf"},
        SUFFIX_OUTPUT_VIDEO=".mp4",
        INPUT_DIR=tmp_path / "input",
        OUTPUT_DIR=tmp_path / "output",
    )


def test_image_defilor_processes_only_images_and_skips_existing(tmp_path):
    """It should process accepted images and skip already generated output."""
    # Build a fake config with input and output directories
    cfg = build_fake_cfg(tmp_path)
    cfg.INPUT_DIR.mkdir(parents=True)
    cfg.OUTPUT_DIR.mkdir(parents=True)

    img_1 = cfg.INPUT_DIR / "a.jpg"
    img_2 = cfg.INPUT_DIR / "b.png"
    txt_1 = cfg.INPUT_DIR / "notes.txt"
    img_1.touch()
    img_2.touch()
    txt_1.touch()

    out_1 = cfg.OUTPUT_DIR / "a_scrolled.mp4"
    out_1.touch()

    # Define params to be returned by the parser
    params = SimpleNamespace(
        height=720,
        fps=30,
        speed=50.0,
        hold_start=2.0,
        hold_end=2.0,
        codec="libx264",
        crf=20,
    )

    # Mock the parser to return our params, and the output subdir builder to return our output dir
    with mock.patch("image.main_image.func_ima.parse_defilor_extra_args", return_value=params), \
        mock.patch(
            "image.main_image.func_glob.build_output_subdir_from_input",
            return_value=cfg.OUTPUT_DIR
        ), \
        mock.patch("image.main_image.func_ima.get_image_size", return_value=(800, 600)), \
        mock.patch("image.main_image.func_ima.generate_image_defilor") as generate_mock:
        image_defilor(cfg)

    # Assert
    generate_mock.assert_called_once()
    assert generate_mock.call_args.kwargs["image_path"] == img_2
    assert generate_mock.call_args.kwargs["output_height"] == 600


def test_image_defilor_passes_extra_args_to_parser(tmp_path):
    """It should forward extra args to parse_defilor_extra_args."""
    # Build a fake config with input and output directories
    cfg = build_fake_cfg(tmp_path)
    cfg.INPUT_DIR.mkdir(parents=True)
    cfg.OUTPUT_DIR.mkdir(parents=True)
    (cfg.INPUT_DIR / "a.jpg").touch()

    # Define params to be returned by the parser
    params = SimpleNamespace(
        height=1080,
        fps=60,
        speed=35.0,
        hold_start=5.0,
        hold_end=5.0,
        codec="libx265",
        crf=18,
    )
    raw = "--height 720 --speed 50"

    # Mock the parser to return our params, and the output subdir builder to return our output dir
    with mock.patch("image.main_image.func_ima.parse_defilor_extra_args", return_value=params) as parse_mock, \
        mock.patch(
            "image.main_image.func_glob.build_output_subdir_from_input",
            return_value=cfg.OUTPUT_DIR
        ), \
        mock.patch("image.main_image.func_ima.generate_image_defilor"):
        image_defilor(cfg, extra_args=raw)

    # Assert
    parse_mock.assert_called_once_with(raw)


def test_image_defilor_keeps_explicit_height(tmp_path):
    """It should not clamp height when the user explicitly provides --height."""
    # Build a fake config with input and output directories
    cfg = build_fake_cfg(tmp_path)
    cfg.INPUT_DIR.mkdir(parents=True)
    cfg.OUTPUT_DIR.mkdir(parents=True)
    (cfg.INPUT_DIR / "a.jpg").touch()

    # Define params to be returned by the parser
    params = SimpleNamespace(
        height=1080,
        fps=60,
        speed=35.0,
        hold_start=5.0,
        hold_end=5.0,
        codec="libx265",
        crf=18,
    )

    # Mock the parser to return our params, and the output subdir builder to return our output dir
    with mock.patch("image.main_image.func_ima.parse_defilor_extra_args", return_value=params), \
        mock.patch(
            "image.main_image.func_glob.build_output_subdir_from_input",
            return_value=cfg.OUTPUT_DIR
        ), \
        mock.patch("image.main_image.func_ima.get_image_size") as size_mock, \
        mock.patch("image.main_image.func_ima.generate_image_defilor") as generate_mock:
        image_defilor(cfg, extra_args="--height 1080")

    # Assert
    size_mock.assert_not_called()
    assert generate_mock.call_args.kwargs["output_height"] == 1080


def test_image_defilor_extracts_pdf_images(tmp_path):
    """It should extract PDF images and generate one scrolling video per image."""
    # Build a fake config with input and output directories
    cfg = build_fake_cfg(tmp_path)
    cfg.INPUT_DIR.mkdir(parents=True)
    cfg.OUTPUT_DIR.mkdir(parents=True)

    pdf = cfg.INPUT_DIR / "document.pdf"
    pdf.touch()
    page_1 = tmp_path / "page_001.png"
    page_2 = tmp_path / "page_002.png"

    # Define params to be returned by the parser
    params = SimpleNamespace(
        height=1080,
        fps=60,
        speed=35.0,
        hold_start=5.0,
        hold_end=5.0,
        codec="libx265",
        crf=18,
    )

    # Mock PDF image extraction and video generation to avoid side effects
    with mock.patch("image.main_image.func_ima.parse_defilor_extra_args", return_value=params), \
        mock.patch(
            "image.main_image.func_glob.build_output_subdir_from_input",
            return_value=cfg.OUTPUT_DIR
        ), \
        mock.patch(
            "image.main_image.func_ima.extract_pdf_images_to_files",
            return_value=[page_1, page_2],
        ) as extract_mock, \
        mock.patch("image.main_image.func_ima.get_image_size", return_value=(800, 600)), \
        mock.patch("image.main_image.func_ima.generate_image_defilor") as generate_mock:
        is_empty = image_defilor(cfg)

    # Assert
    assert is_empty is False
    extract_mock.assert_called_once()
    assert generate_mock.call_count == 2
    assert generate_mock.call_args_list[0].kwargs["image_path"] == page_1
    assert generate_mock.call_args_list[0].kwargs["output_path"] == (
        cfg.OUTPUT_DIR / "document_image_001_scrolled.mp4"
    )
    assert generate_mock.call_args_list[1].kwargs["image_path"] == page_2
    assert generate_mock.call_args_list[1].kwargs["output_path"] == (
        cfg.OUTPUT_DIR / "document_image_002_scrolled.mp4"
    )


def test_run_image_defilor_interactive_without_extra_args(monkeypatch):
    """It should call image_defilor with None when user declines extra args."""
    cfg = object()
    answers = iter(["n"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    with mock.patch("image.main_image.image_defilor") as image_defilor_mock:
        run_image_defilor_interactive(cfg)
    image_defilor_mock.assert_called_once_with(cfg, extra_args=None)


def test_run_image_defilor_interactive_with_extra_args(monkeypatch):
    """It should call image_defilor with user provided extra args."""
    cfg = object()
    answers = iter(["o", "--height 720 --speed 50"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    with mock.patch("image.main_image.image_defilor") as image_defilor_mock:
        run_image_defilor_interactive(cfg)
    image_defilor_mock.assert_called_once_with(
        cfg,
        extra_args="--height 720 --speed 50",
    )


def test_run_image_defilor_interactive_catches_value_error(monkeypatch, capsys):
    """It should catch ValueError from image_defilor and print a message."""
    cfg = object()
    answers = iter(["n"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    with mock.patch(
        "image.main_image.image_defilor",
        side_effect=ValueError("bad args"),
    ):
        run_image_defilor_interactive(cfg)
    captured = capsys.readouterr()
    assert "Arguments invalides pour Image_defilor" in captured.out

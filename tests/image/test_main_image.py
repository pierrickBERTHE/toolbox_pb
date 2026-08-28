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
from image.main_image import (
    image_defilor, image_reductor, run_image_defilor_interactive
)


def build_fake_cfg(tmp_path):
    """Create a minimal config object compatible with image_defilor."""
    return SimpleNamespace(
        INPUT_ACCEPTED_IMAGE_FILES={".jpg", ".png"},
        INPUT_ACCEPTED_VIDEO_FILES={".mp4"},
        INPUT_ACCEPTED_PDF_FILES={".pdf"},
        SUFFIX_OUTPUT_VIDEO=".mp4",
        ADD_CODEC_NAME_IN_OUTPUT=True,
        ADD_COMPRESSED_IN_NAME_IN_OUTPUT=True,
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


def test_image_reductor_mirrors_subdirectories_and_skips_existing(tmp_path):
    """It should process supported images through the reduction helper."""
    cfg = build_fake_cfg(tmp_path)
    cfg.INPUT_DIR.mkdir(parents=True)
    source = cfg.INPUT_DIR / "nested" / "photo.jpg"
    source.parent.mkdir()
    source.touch()
    (cfg.INPUT_DIR / "notes.txt").write_bytes(b"notes to preserve")
    existing = cfg.OUTPUT_DIR / "nested" / "already_Compressed.jpg"
    existing.parent.mkdir(parents=True)
    existing.touch()

    with mock.patch(
        "image.main_image.func_ima.reduce_image_for_screen",
        return_value=(1000, 400),
    ) as reduce_mock, \
        mock.patch(
            "image.main_image.func_vid.compute_size_reduction", return_value={}
        ) as compute_mock, \
        mock.patch("image.main_image.func_vid.print_size_reduction") as print_mock:
        is_empty = image_reductor(cfg)

    assert is_empty is False
    reduce_mock.assert_called_once_with(
        input_path=source,
        output_path=cfg.OUTPUT_DIR / "nested" / "photo_Compressed.jpg",
        quality=95,
    )
    compute_mock.assert_called_once_with(
        {"format": {"size": 1000}}, {"format": {"size": 400}}
    )
    print_mock.assert_called_once_with({})
    assert (cfg.OUTPUT_DIR / "notes.txt").read_bytes() == b"notes to preserve"


def test_image_reductor_copies_unreducible_images_and_other_files(tmp_path, capsys):
    """Every input file should have an output counterpart when not reduced."""
    cfg = build_fake_cfg(tmp_path)
    cfg.INPUT_DIR.mkdir(parents=True)
    image = cfg.INPUT_DIR / "album" / "photo.jpg"
    document = cfg.INPUT_DIR / "album" / "document.pdf"
    video = cfg.INPUT_DIR / "album" / "video.mp4"
    image.parent.mkdir()
    image.write_bytes(b"original image")
    document.write_bytes(b"original document")
    video.write_bytes(b"original video")

    with mock.patch(
        "image.main_image.func_ima.reduce_image_for_screen", return_value=None
    ):
        is_empty = image_reductor(cfg)

    assert is_empty is False
    assert (cfg.OUTPUT_DIR / "album" / "photo.jpg").read_bytes() == image.read_bytes()
    assert (cfg.OUTPUT_DIR / "album" / "document.pdf").read_bytes() == document.read_bytes()
    assert not (cfg.OUTPUT_DIR / "album" / "video.mp4").exists()
    assert "0 image(s) compressée(s), 1 laissée(s) intacte(s)" in capsys.readouterr().out


def test_image_reductor_skips_failed_images_and_continues(tmp_path, capsys):
    """A broken image should not stop the whole batch."""
    cfg = build_fake_cfg(tmp_path)
    cfg.INPUT_DIR.mkdir(parents=True)
    broken_image = cfg.INPUT_DIR / "photo noel.jpg"
    broken_image.write_bytes(b"truncated image bytes")

    with mock.patch(
        "image.main_image.func_ima.reduce_image_for_screen",
        side_effect=RuntimeError(
            "Impossible de réduire l'image 'photo noel.jpg': "
            "image file is truncated"
        ),
    ):
        is_empty = image_reductor(cfg)

    captured = capsys.readouterr()
    assert is_empty is False
    assert (cfg.OUTPUT_DIR / "photo noel.jpg").read_bytes() == broken_image.read_bytes()
    assert "Image ignorée : photo noel.jpg" in captured.out
    assert "1 ignorée(s) après erreur" in captured.out

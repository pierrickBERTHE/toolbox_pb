"""
Unit tests for pdf.main_pdf.
"""
# Imports standard
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

# Add the toolbox_pb directory to sys.path for imports
sys.path.append(str(Path(__file__).resolve().parents[2] / "toolbox_pb"))

# Imports local
from pdf.main_pdf import build_filigranor_text, pdf_filigranor


# -----------------------------
# Fixtures helpers
# -----------------------------

def build_fake_cfg(tmp_path):
    """
    Create a minimal isolated configuration compatible with pdf_filigranor.
    """

    # Return a simple config object with only the fields needed by PDF tests
    return SimpleNamespace(
        INPUT_ACCEPTED_PDF_FILES={".pdf"},
        SUFFIX_OUTPUT_PDF=".pdf",
        INPUT_DIR=tmp_path / "input",
        OUTPUT_DIR=tmp_path / "output",
    )


# -----------------------------
# Main tests
# -----------------------------

def test_pdf_filigranor_processes_only_pdfs_and_skips_existing(tmp_path):
    """
    PDF files must be processed, non-PDF files ignored, and existing outputs skipped.
    """
    # Build a fake config with input and output directories
    cfg = build_fake_cfg(tmp_path)
    cfg.INPUT_DIR.mkdir(parents=True)
    cfg.OUTPUT_DIR.mkdir(parents=True)

    # Create input files with mixed extensions
    pdf_1 = cfg.INPUT_DIR / "a.pdf"
    pdf_2 = cfg.INPUT_DIR / "b.pdf"
    txt_1 = cfg.INPUT_DIR / "notes.txt"
    pdf_1.touch()
    pdf_2.touch()
    txt_1.touch()

    # Create an existing output file to verify it is skipped
    out_1 = cfg.OUTPUT_DIR / "a_filigrane.pdf"
    out_1.touch()

    # Mock filesystem helper and watermark generation to avoid PDF side effects
    with mock.patch(
        "pdf.main_pdf.func_glob.build_output_subdir_from_input",
        return_value=cfg.OUTPUT_DIR
    ), mock.patch("pdf.main_pdf.func_pdf.add_text_watermark_to_pdf") as watermark_mock:

        # Run the function under test
        is_empty = pdf_filigranor(cfg, watermark_text="CONFIDENTIEL")

    # Ensure that at least one PDF was found
    assert is_empty is False

    # Ensure only the PDF without existing output was processed
    watermark_mock.assert_called_once()
    assert watermark_mock.call_args.kwargs["input_path"] == pdf_2
    assert watermark_mock.call_args.kwargs["output_path"] == cfg.OUTPUT_DIR / "b_filigrane.pdf"

    # Ensure the mandatory sentence is added before the user-provided text
    assert (
        watermark_mock.call_args.kwargs["text"]
        == "document exclusivement destiné à CONFIDENTIEL"
    )


def test_pdf_filigranor_returns_true_when_no_pdf(tmp_path):
    """
    The function must report an empty folder when no PDF is found.
    """
    # Build a fake config with input and output directories
    cfg = build_fake_cfg(tmp_path)
    cfg.INPUT_DIR.mkdir(parents=True)
    cfg.OUTPUT_DIR.mkdir(parents=True)

    # Create only a non-PDF file
    (cfg.INPUT_DIR / "notes.txt").touch()

    # Mock watermark generation to ensure it is not called
    with mock.patch("pdf.main_pdf.func_pdf.add_text_watermark_to_pdf") as watermark_mock:

        # Run the function under test
        is_empty = pdf_filigranor(cfg, watermark_text="CONFIDENTIEL")

    # Ensure the folder is considered empty for this feature
    assert is_empty is True

    # Ensure no watermark generation was triggered
    watermark_mock.assert_not_called()


def test_pdf_filigranor_rejects_empty_watermark_text(tmp_path):
    """
    Empty destination text must be rejected before processing files.
    """
    # Build a fake config with input and output directories
    cfg = build_fake_cfg(tmp_path)
    cfg.INPUT_DIR.mkdir(parents=True)
    cfg.OUTPUT_DIR.mkdir(parents=True)

    # Run the function with an invalid destination and verify the error
    try:
        pdf_filigranor(cfg, watermark_text="   ")
    except ValueError as exc:
        assert "destinataire" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_build_filigranor_text_adds_mandatory_prefix():
    """
    The mandatory sentence must always be added before the destination.
    """

    # Build the final watermark text from a destination only
    assert (
        build_filigranor_text("Pierrick")
        == "document exclusivement destiné à Pierrick"
    )

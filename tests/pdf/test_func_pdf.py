"""Unit tests for the low-level PDF watermark helpers."""

from pathlib import Path
import builtins
import sys
from unittest import mock

import pytest

# Add the application directory so tests use the same import style as main.
sys.path.append(str(Path(__file__).resolve().parents[2] / "toolbox_pb"))

from pdf import func_pdf


class FakeCanvas:
    """Minimal canvas recording the text positions used by draw_wavy_string."""

    def __init__(self):
        self.calls = []

    def drawString(self, x, y, text):
        self.calls.append((x, y, text))

    def stringWidth(self, text, font_name, font_size):
        return len(text) * font_size


def test_import_pdf_dependencies_returns_expected_objects():
    """PDF dependencies are available through the lazy import helper."""
    reader, writer, color, canvas = func_pdf._import_pdf_dependencies()

    assert reader.__name__ == "PdfReader"
    assert writer.__name__ == "PdfWriter"
    assert color.__name__ == "Color"
    assert canvas.__name__ == "reportlab.pdfgen.canvas"


def test_import_pdf_dependencies_explains_missing_dependency(monkeypatch):
    """A missing optional PDF dependency must produce an actionable error."""
    original_import = builtins.__import__

    def failing_import(name, *args, **kwargs):
        if name == "pypdf":
            raise ImportError("pypdf unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", failing_import)

    with pytest.raises(RuntimeError, match="Dépendances PDF manquantes"):
        func_pdf._import_pdf_dependencies()


def test_draw_wavy_string_draws_each_word_at_distinct_positions():
    """Each whitespace-delimited text chunk is drawn with a wave offset."""
    canvas = FakeCanvas()

    func_pdf.draw_wavy_string(canvas, 10, 20, "un deux", "Helvetica", 10)

    assert [call[2] for call in canvas.calls] == ["un ", "deux"]
    assert canvas.calls[1][0] > canvas.calls[0][0]
    assert canvas.calls[0][1] != canvas.calls[1][1]


def test_build_watermark_page_returns_a_mergeable_pdf_page():
    """The generated in-memory overlay is a valid page of the requested size."""
    page = func_pdf.build_watermark_page(200, 100, "CONFIDENTIEL", spacing=100)

    assert float(page.mediabox.width) == 200
    assert float(page.mediabox.height) == 100


def test_add_text_watermark_rejects_invalid_input_paths(tmp_path):
    """Missing files and non-PDF inputs must be rejected before PDF parsing."""
    with pytest.raises(FileNotFoundError):
        func_pdf.add_text_watermark_to_pdf(
            tmp_path / "missing.pdf", tmp_path / "output.pdf", "texte"
        )

    text_file = tmp_path / "input.txt"
    text_file.write_text("not a PDF", encoding="utf-8")
    with pytest.raises(ValueError, match="n'est pas un PDF"):
        func_pdf.add_text_watermark_to_pdf(
            text_file, tmp_path / "output.pdf", "texte"
        )


def test_add_text_watermark_writes_a_watermarked_pdf(tmp_path):
    """Every input page receives an overlay and the output directories are made."""
    _, PdfWriter, _, _ = func_pdf._import_pdf_dependencies()
    input_path = tmp_path / "input.pdf"
    output_path = tmp_path / "nested" / "output.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=100)
    with input_path.open("wb") as output_file:
        writer.write(output_file)

    func_pdf.add_text_watermark_to_pdf(input_path, output_path, "  CONFIDENTIEL  ")

    PdfReader, _, _, _ = func_pdf._import_pdf_dependencies()
    assert output_path.is_file()
    assert len(PdfReader(str(output_path)).pages) == 1

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


def test_merge_pdf_files_preserves_document_and_page_order(tmp_path):
    """Merged pages must follow exactly the supplied input-file order."""
    _, PdfWriter, _, _ = func_pdf._import_pdf_dependencies()
    first_input = tmp_path / "first.pdf"
    second_input = tmp_path / "second.pdf"

    first_writer = PdfWriter()
    first_writer.add_blank_page(width=101, height=201)
    first_writer.add_blank_page(width=102, height=202)
    with first_input.open("wb") as output_file:
        first_writer.write(output_file)

    second_writer = PdfWriter()
    second_writer.add_blank_page(width=103, height=203)
    with second_input.open("wb") as output_file:
        second_writer.write(output_file)

    output_path = tmp_path / "nested" / "assembled.pdf"
    func_pdf.merge_pdf_files([first_input, second_input], output_path)

    PdfReader, _, _, _ = func_pdf._import_pdf_dependencies()
    output_pages = PdfReader(str(output_path)).pages
    assert [(float(page.mediabox.width), float(page.mediabox.height)) for page in output_pages] == [
        (101.0, 201.0),
        (102.0, 202.0),
        (103.0, 203.0),
    ]


def test_merge_pdf_files_rejects_an_empty_input_list(tmp_path):
    """An empty merge request must not produce an empty PDF."""
    with pytest.raises(ValueError, match="Au moins un PDF"):
        func_pdf.merge_pdf_files([], tmp_path / "assembled.pdf")


def test_alternate_pdf_pages_orders_pages_and_keeps_last_odd(tmp_path):
    """The result starts with odd pages and retains a final unpaired page."""
    PdfReader, PdfWriter, _, _ = func_pdf._import_pdf_dependencies()
    for name, widths in (("impaire.pdf", [101, 103, 105]), ("paire.pdf", [102, 104])):
        writer = PdfWriter()
        for width in widths:
            writer.add_blank_page(width=width, height=200)
        with (tmp_path / name).open("wb") as stream:
            writer.write(stream)
    output = tmp_path / "output.pdf"
    func_pdf.alternate_pdf_pages(
        tmp_path / "impaire.pdf",
        tmp_path / "paire.pdf",
        output
    )
    assert [
        float(page.mediabox.width) for page in PdfReader(str(output)).pages
    ] == [101, 102, 103, 104, 105]


def test_alternate_pdf_pages_rejects_inconsistent_counts(tmp_path):
    _, PdfWriter, _, _ = func_pdf._import_pdf_dependencies()
    for name, count in (("impaire.pdf", 1), ("paire.pdf", 2)):
        writer = PdfWriter()
        for _ in range(count):
            writer.add_blank_page(width=100, height=100)
        with (tmp_path / name).open("wb") as stream:
            writer.write(stream)
    with pytest.raises(ValueError, match="autant de pages"):
        func_pdf.alternate_pdf_pages(
            tmp_path / "impaire.pdf",
            tmp_path / "paire.pdf",
            tmp_path / "out.pdf"
        )
    assert not (tmp_path / "out.pdf").exists()

"""
Ce fichier contient des fonctions pour les actions sur les PDF.

Auteurs :
Pierrick BERTHE
mail : pierrick.berthe@gmx.fr
Mai 2026
"""
# Imports standard
from io import BytesIO
import math
from pathlib import Path
import re


def _import_pdf_dependencies():
    """
    Import PDF dependencies lazily so the main toolbox can still start even if
    PDF extras are not installed yet.
    """

    # Import heavy PDF libraries only when the PDF feature is used
    try:
        from pypdf import PdfReader, PdfWriter
        from reportlab.lib.colors import Color
        from reportlab.pdfgen import canvas

    # Raise a clear error message if dependencies are missing
    except ImportError as exc:
        raise RuntimeError(
            "Dépendances PDF manquantes. Installe-les avec : "
            "poetry install ou poetry add pypdf reportlab"
        ) from exc

    # Return imported objects to callers
    return PdfReader, PdfWriter, Color, canvas


def draw_wavy_string(
    pdf_canvas,
    x: float,
    y: float,
    text: str,
    font_name: str,
    font_size: int,
    phase: float = 0.0,
) -> None:
    """
    Draw a text string word by word on a subtle sine wave.
    """

    # Define the wave shape according to the font size
    amplitude = font_size * 0.18
    wavelength = font_size * 5.5
    current_x = x

    # Draw each word/chunk with a small vertical offset
    for chunk in re.findall(r"\S+\s*", text):
        y_offset = amplitude * math.sin((current_x / wavelength) + phase)
        pdf_canvas.drawString(current_x, y + y_offset, chunk)
        current_x += pdf_canvas.stringWidth(chunk, font_name, font_size)


def build_watermark_page(
    page_width: float,
    page_height: float,
    text: str,
    font_size: int = 22,
    opacity: float = 0.16,
    spacing: int = 360,
):
    """
    Build one transparent PDF page containing repeated diagonal watermark text.
    """

    # ------------- IMPORT DEPENDENCIES -------------
    PdfReader, _, Color, canvas = _import_pdf_dependencies()

    # ------------- CREATE TRANSPARENT WATERMARK PAGE -------------
    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=(page_width, page_height))

    # ------------- TEXT STYLE -------------
    font_name = "Helvetica-Bold"
    c.setFont(font_name, font_size)

    # Define pale colors used alternately for the watermark phrases
    watermark_colors = [
        Color(0.25, 0.25, 0.25, alpha=opacity),
        Color(0.20, 0.42, 0.52, alpha=opacity * 0.9),
        Color(0.48, 0.34, 0.18, alpha=opacity * 0.85),
        Color(0.42, 0.32, 0.48, alpha=opacity * 0.85),
    ]

    # ------------- DIAGONAL COORDINATE SYSTEM -------------
    # Cover the full page by drawing on a rotated coordinate system.
    c.saveState()
    c.translate(page_width / 2, page_height / 2)
    c.rotate(45)

    # ------------- WATERMARK GRID -------------
    # Use a large virtual area so the rotated text covers the whole page.
    diagonal_span = page_width + page_height
    x_min = -diagonal_span
    x_max = diagonal_span
    y_min = -diagonal_span
    y_max = diagonal_span

    # Adapt horizontal spacing to long sentences to avoid overlapping
    text_width = c.stringWidth(text, font_name, font_size)
    x_spacing = max(spacing, int(text_width + font_size * 8))

    # Keep vertical spacing tighter to display more watermark lines
    y_spacing = max(spacing // 2, int(font_size * 7))

    # Anchor the first visible text near the bottom-left of the PDF page
    margin = font_size * 0.75
    anchor_x = ((margin - page_width / 2) + (margin - page_height / 2)) / math.sqrt(2)
    anchor_y = ((margin - page_height / 2) - (margin - page_width / 2)) / math.sqrt(2)

    # ------------- DRAW WATERMARK TEXT -------------
    row_index = 0
    y = anchor_y - diagonal_span
    while y <= y_max:

        # Keep each line anchored from the visible left side of the page.
        x = anchor_x + (y - anchor_y)
        col_index = 0
        while x <= x_max:

            # Alternate pale colors depending on the row and column
            color_index = (row_index + col_index) % len(watermark_colors)
            c.setFillColor(watermark_colors[color_index])

            # Draw one phrase with a subtle wave effect
            draw_wavy_string(
                pdf_canvas=c,
                x=x,
                y=y,
                text=text,
                font_name=font_name,
                font_size=font_size,
                phase=(row_index * 0.7) + (col_index * 0.35),
            )
            x += x_spacing
            col_index += 1
        y += y_spacing
        row_index += 1

    # ------------- SAVE WATERMARK PAGE -------------
    c.restoreState()
    c.save()
    packet.seek(0)

    # Return the generated overlay page
    return PdfReader(packet).pages[0]


def add_text_watermark_to_pdf(
    input_path: Path,
    output_path: Path,
    text: str,
    font_size: int = 22,
    opacity: float = 0.16,
    spacing: int = 360,
) -> None:
    """
    Add a repeated diagonal text watermark to every page of a PDF.
    """

    # ------------- IMPORT DEPENDENCIES -------------
    PdfReader, PdfWriter, _, _ = _import_pdf_dependencies()

    # ------------- VALIDATION -------------
    # Check that the input file exists
    if not input_path.exists() or not input_path.is_file():
        raise FileNotFoundError(f"PDF introuvable : {input_path}")

    # Check that the input file is a PDF
    if input_path.suffix.lower() != ".pdf":
        raise ValueError(f"Le fichier n'est pas un PDF : {input_path}")

    # ------------- LOAD INPUT PDF -------------
    reader = PdfReader(str(input_path))
    writer = PdfWriter()

    # ------------- ADD WATERMARK TO EACH PAGE -------------
    for page in reader.pages:

        # Get page dimensions to generate a matching watermark overlay
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)

        # Build the watermark page for the current PDF page size
        watermark_page = build_watermark_page(
            page_width=width,
            page_height=height,
            text=text.strip(),
            font_size=font_size,
            opacity=opacity,
            spacing=spacing,
        )

        # Merge the watermark overlay into the original page
        page.merge_page(watermark_page)
        writer.add_page(page)

    # ------------- WRITE OUTPUT PDF -------------
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as output_file:
        writer.write(output_file)

    # Print success message
    print(f"Filigrane ajouté : {output_path}")

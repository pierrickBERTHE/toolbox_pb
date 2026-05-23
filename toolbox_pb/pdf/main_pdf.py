"""
Ce fichier contient les fonctions principales pour le traitement PDF de
la toolbox_pb.

Auteurs :
Pierrick BERTHE
mail : pierrick.berthe@gmx.fr
Mai 2026
"""
# Imports standard

# Import custom librairies
from config_global import AppConfig
import toolbox_pb.pdf.func_pdf as func_pdf
import func_global as func_glob
from config_global import WATERMARK_PREFIX

def build_filigranor_text(destination_text: str) -> str:
    """
    Build the final watermark sentence from the user-provided destination.
    """
    # Clean the user input before building the final sentence
    destination_text = destination_text.strip()

    # Validate that the destination is not empty
    if not destination_text:
        raise ValueError("Le destinataire du filigrane ne peut pas être vide.")

    # Add the mandatory sentence before the user-provided destination
    return f"{WATERMARK_PREFIX}{destination_text}"


def pdf_filigranor(cfg: AppConfig, watermark_text: str | None = None) -> bool:
    """
    Add a repeated diagonal text watermark to every PDF in the input directory.
    """

    # ------------- CONFIGURATION -------------
    config = {
        "accepted_file": cfg.INPUT_ACCEPTED_PDF_FILES,
        "suffix": cfg.SUFFIX_OUTPUT_PDF,
        "input_dir": cfg.INPUT_DIR,
        "output_dir": cfg.OUTPUT_DIR,
    }

    # ------------- USER INPUT -------------
    # Ask only for the destination part; the mandatory prefix is added after.
    if watermark_text is None:
        raise ValueError(
            "Le watermark_text ne peut pas être None."
            "Veuillez fournir un texte de filigrane dans le fichier de config."
        )

    # Build the final watermark text
    watermark_text = build_filigranor_text(watermark_text)

    # ------------- LOOP THROUGH ALL FILES IN INPUT DIR -------------
    is_empty_folder = True
    for input_file in config["input_dir"].rglob("*"):

        # ------- IGNORE NON-PDF FILES AND DIRECTORIES -------
        if not input_file.is_file() or input_file.suffix.lower() not in config["accepted_file"]:
            continue

        # --- CREATE OUTPUT SUBDIR STRUCTURE BASED ON INPUT FILE PATH ---
        output_subdir = func_glob.build_output_subdir_from_input(
            input_file,
            config["input_dir"],
            config["output_dir"],
        )

        # ------------- FILENAME FOR OUTPUT PDF -------------
        output_path = (
            output_subdir / f"{input_file.stem}_filigrane{config['suffix']}"
        )

        # ------------- ADD WATERMARK IF NOT ALREADY DONE -------------
        if output_path.exists():
            print("PDF_filigranor déjà réalisé.")
        else:
            func_pdf.add_text_watermark_to_pdf(
                input_path=input_file,
                output_path=output_path,
                text=watermark_text,
            )

        # If we reach this point, it means we found at least one PDF file
        is_empty_folder = False

    return is_empty_folder

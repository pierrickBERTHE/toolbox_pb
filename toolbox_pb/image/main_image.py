"""
Ce fichier contient les fonctions principales pour le traitement image
la toolbox_pb.

Auteurs :
Pierrick BERTHE
mail : pierrick.berthe@gmx.fr
Février 2026
"""
# import custom librairies
from pathlib import Path
import shlex
from tempfile import TemporaryDirectory

from config_global import AppConfig
import toolbox_pb.image.func_image as func_ima
import func_global as func_glob


def _defilor_height_is_explicit(extra_args: str | None) -> bool:
    """
    Return True when the user explicitly provided --height.
    """
    if not extra_args:
        return False
    return any(
        token == "--height" or token.startswith("--height=")
        for token in shlex.split(extra_args)
    )


def image_defilor(cfg: AppConfig, extra_args: str | None = None) -> bool:
    """
    Main function to generate scrolling videos from images in a directory.
    """
    # ------------- CONFIGURATION -------------
    is_empty_folder = True
    config = {
        "accepted_image_file": cfg.INPUT_ACCEPTED_IMAGE_FILES,
        "accepted_pdf_file": cfg.INPUT_ACCEPTED_PDF_FILES,
        "suffix": cfg.SUFFIX_OUTPUT_VIDEO,
        "input_dir": cfg.INPUT_DIR,
        "output_dir": cfg.OUTPUT_DIR,
    }
    params = func_ima.parse_defilor_extra_args(extra_args)
    height_is_explicit = _defilor_height_is_explicit(extra_args)

    # --------- LOOP THROUGH ALL FILES IN INPUT DIR ---------
    for input_file in config["input_dir"].rglob('*'):

        # -------- IGNORE UNSUPPORTED FILES ---------
        if not input_file.is_file():
            continue

        # --- CREATE OUTPUT SUBDIR STRUCTURE BASED ON INPUT FILE PATH ---
        output_subdir = func_glob.build_output_subdir_from_input(
            input_file, config["input_dir"], config["output_dir"]
        )

        input_suffix = input_file.suffix.lower()
        if input_suffix in config["accepted_image_file"]:

            # ------------- FILENAME FOR OUTPUT VIDEO -------------
            output_path = output_subdir / f"{input_file.stem}_scrolled{config['suffix']}"

            # ------------- GENERATION OF SCROLLING VIDEO -------------
            _generate_defilor_video(
                input_file=input_file,
                output_path=output_path,
                params=params,
                height_is_explicit=height_is_explicit,
            )
            is_empty_folder = False

        # special handling for PDF files: extract images from PDF and generate one video per page image
        elif input_suffix in config["accepted_pdf_file"]:
            with TemporaryDirectory() as temp_dir:
                extracted_images = func_ima.extract_pdf_images_to_files(
                    pdf_path=input_file,
                    output_dir=Path(temp_dir),
                )

                # Generate one video per page image, with a filename indicating the page number
                for image_index, page_image in enumerate(extracted_images, start=1):
                    output_path = (
                        output_subdir
                        / f"{input_file.stem}_image_{image_index:03d}_scrolled{config['suffix']}"
                    )
                    _generate_defilor_video(
                        input_file=page_image,
                        output_path=output_path,
                        params=params,
                        height_is_explicit=height_is_explicit,
                    )
            is_empty_folder = False

    return is_empty_folder


def _generate_defilor_video(
    input_file,
    output_path,
    params,
    height_is_explicit: bool,
) -> None:
    """
    Generate one defilor video from an image path, unless it already exists.
    """
    # Check if already encoded
    if output_path.exists():
        print("image_defilor déjà réalisé.")
        return

    output_height = params.height
    if not height_is_explicit:
        _, image_height = func_ima.get_image_size(input_file)
        output_height = min(output_height, image_height)

    func_ima.generate_image_defilor(
        image_path=input_file,
        output_path=output_path,
        output_height=output_height,
        fps=params.fps,
        scroll_speed_px_s=params.speed,
        hold_start=params.hold_start,
        hold_end=params.hold_end,
        codec=params.codec,
        crf=params.crf,
    )


def run_image_defilor_interactive(cfg: AppConfig) -> bool:
    """
    Interactive wrapper for image_defilor with user input for extra parameters.
    """
    while True:
        # Print the menu and ask for input parameters
        print(
            "\nOptions disponibles: "
            "--height --speed --fps --hold-start --hold-end --codec --crf"
        )
        answer = input("Ajouter des options ? (o/n) : ").strip().lower()
        # Validate the answer
        if answer not in {"o", "oui", "y", "yes", "n", "non", "no"}:
            print("Réponse invalide, veuillez entrer 'o' ou 'n'.\n")
            continue
        # If user wants to add options, ask for them
        extra_args = None
        if answer in {"o", "oui", "y", "yes"}:
            extra_args = input(
                "Entrez les options (ex: --height 720 --speed 50): "
            ).strip()
        # TRY run the image_defilor
        try:
            is_empty_folder = image_defilor(
                cfg, extra_args=extra_args
            )
            break
        except ValueError as exc:
            print(f"Arguments invalides pour Image_defilor: {exc}")
            print("Veuillez réessayer.\n")
            is_empty_folder = True
            break

    return is_empty_folder

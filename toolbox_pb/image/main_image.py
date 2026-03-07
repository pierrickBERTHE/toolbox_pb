"""
Ce fichier contient les fonctions principales pour le traitement image
la toolbox_pb.

Auteurs :
Pierrick BERTHE
mail : pierrick.berthe@gmx.fr
Février 2026
"""
# import custom librairies
from config_global import AppConfig
import toolbox_pb.image.func_image as func_ima
import func_global as func_glob


def image_defilor(cfg: AppConfig, extra_args: str | None = None) -> bool:
    """
    Main function to generate scrolling videos from images in a directory.
    """
    # ------------- CONFIGURATION -------------
    is_empty_folder = True
    config = {
        "accepted_file": cfg.INPUT_ACCEPTED_IMAGE_FILES,
        "suffix": cfg.SUFFIX_OUTPUT_VIDEO,
        "input_dir": cfg.INPUT_DIR,
        "output_dir": cfg.OUTPUT_DIR,
    }
    params = func_ima.parse_defilor_extra_args(extra_args)

    # --------- LOOP THROUGH ALL FILES IN INPUT DIR ---------
    for input_file in config["input_dir"].rglob('*'):

        # -------- IGNORE NON-IMAGE FILES ---------
        if not input_file.is_file() or input_file.suffix.lower() not in config["accepted_file"]:
            continue

        # --- CREATE OUTPUT SUBDIR STRUCTURE BASED ON INPUT FILE PATH ---
        output_subdir = func_glob.build_output_subdir_from_input(
            input_file, config["input_dir"], config["output_dir"]
        )

        # ------------- FILENAME FOR OUTPUT VIDEO -------------
        output_path = output_subdir / f"{input_file.stem}_scrolled{config['suffix']}"

        # ------------- GENERATION OF SCROLLING VIDEO -------------
        # Check if already encoded
        if output_path.exists():
            print("image_defilor déjà réalisé.")
        else:
            func_ima.generate_image_defilor(
                image_path=input_file,
                output_path=output_path,
                output_height=params.height,
                fps=params.fps,
                scroll_speed_px_s=params.speed,
                hold_start=params.hold_start,
                hold_end=params.hold_end,
                codec=params.codec,
                crf=params.crf,
            )
        is_empty_folder = False

    return is_empty_folder


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

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
import shutil
from tempfile import TemporaryDirectory
from tqdm import tqdm

from config_global import AppConfig
import toolbox_pb.image.func_image as func_ima
import toolbox_pb.video.func_video as func_vid
import func_global as func_glob


def _copy_unchanged_file(input_path: Path, output_path: Path) -> None:
    """
    Copy one file with metadata unless the destination is already present.
    """
    if output_path.exists():
        return
    shutil.copy2(input_path, output_path)


def image_reductor(cfg: AppConfig, quality: int = 95) -> bool:
    """
    Reduce eligible photos for screen use while retaining their pixels.

    JPEG files remain JPEG (quality 95); PNG files remain PNG and are optimized
    losslessly. The directory layout is mirrored in the output folder, and a
    file is only kept when it is actually smaller than its source. Non-image,
    non-video files are copied unchanged; videos are left to Video_encodor.
    """
    # ------------ CONFIGURATION -------------
    is_empty_folder = True
    reduced_sizes: list[tuple[int, int]] = []
    compressed_images = 0
    unchanged_images = 0
    already_compressed_images = 0
    failed_images = 0

    # ----------- LOOP THROUGH ALL FILES IN INPUT DIR -------------
    input_files = sorted(
        (path for path in cfg.INPUT_DIR.rglob("*") if path.is_file()),
        key=lambda path: str(path.relative_to(cfg.INPUT_DIR)).lower(),
    )

    # Use tqdm to display a progress bar for the file processing
    for input_file in tqdm(input_files, desc="Image_reductor", unit="fichier"):

        # create the output subdirectory structure based on the input file path
        is_empty_folder = False
        output_subdir = func_glob.build_output_subdir_from_input(
            input_file, cfg.INPUT_DIR, cfg.OUTPUT_DIR
        )
        unchanged_output_path = output_subdir / input_file.name

        # if the file is not an accepted, copy it unchanged to the output folder
        if input_file.suffix.lower() not in cfg.INPUT_ACCEPTED_IMAGE_FILES:
            if input_file.suffix.lower() in cfg.INPUT_ACCEPTED_VIDEO_FILES:
                continue
            _copy_unchanged_file(input_file, unchanged_output_path)
            continue

        # modify the output filename to indicate compression if configured
        compression_suffix = (
            "_Compressed" if cfg.ADD_COMPRESSED_IN_NAME_IN_OUTPUT else ""
        )

        # Determine the output path for the reduced image
        output_path = output_subdir / (
            f"{input_file.stem}{compression_suffix}{input_file.suffix}"
        )
        # Check if the output file already exists; if so, skip processing
        if output_path.exists():
            print(f"Réduction déjà réalisée : {input_file.name}")
            already_compressed_images += 1
            continue

        # Attempt to reduce the image and handle any exceptions that may occur
        try:
            result = func_ima.reduce_image_for_screen(
                input_path=input_file,
                output_path=output_path,
                quality=quality,
            )
        except RuntimeError as exc:
            failed_images += 1
            _copy_unchanged_file(input_file, unchanged_output_path)
            print(f"Image ignorée : {input_file.name} ({exc})")
            continue

        # If the image was not reduced, copy the original
        if result is None:
            unchanged_images += 1
            _copy_unchanged_file(input_file, unchanged_output_path)
            continue

        # If the image was successfully reduced, record the sizes and print the reduction percentage
        input_size, output_size = result
        reduced_sizes.append((input_size, output_size))
        compressed_images += 1
        reduction = (1 - output_size / input_size) * 100
        print(
            f"Image réduite : {input_file.name} -> {output_path.name} "
            f"({reduction:.1f} % de gain)"
        )

    # if any images were reduced, print a summary of the size reduction
    if reduced_sizes:
        func_glob.print_step(2, "Comparaison des fichiers avant/après")
        total_before = sum(size_before for size_before, _ in reduced_sizes)
        total_after = sum(size_after for _, size_after in reduced_sizes)
        stats = func_vid.compute_size_reduction(
            {"format": {"size": total_before}},
            {"format": {"size": total_after}},
        )
        func_vid.print_size_reduction(stats)

    # Print a summary of the number of images states processed
    processed_image_count = (
        compressed_images
        + unchanged_images
        + already_compressed_images
        + failed_images
    )
    if processed_image_count:
        print(
            "\nRésumé Image_reductor : "
            f"{compressed_images} image(s) compressée(s), "
            f"{unchanged_images} laissée(s) intacte(s), "
            f"{already_compressed_images} déjà traitée(s), "
            f"{failed_images} ignorée(s) après erreur."
        )

    return is_empty_folder


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

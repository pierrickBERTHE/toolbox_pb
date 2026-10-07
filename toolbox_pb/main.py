"""
Ce fichier contient le script principal de la toolbox_pb

Auteurs :
Pierrick BERTHE
mail : pierrick.berthe@gmx.fr
Décembre 2025
"""
# Imports standard
import sys
import datetime

# Import custom librairies
from video.main_video import (
    video_encodor,
    video_assemblor,
    video_audio_decalator,
    video_srt_extractor,
    video_srt_date_filtrator,
    video_ass_hard_integrator,
    video_volume_adjust,
    video_srt_integrator,
    image_diapo_video_creator,
)
from video.func_video import find_files_by_extensions
from image.main_image import (
    image_reductor,
    run_image_defilor_interactive,
    image_withoutbg,
)
from pdf.main_pdf import pdf_assemblor, pdf_filigranor
from file.main_file import file_str_remover, file_timeline_sorter, folder_date_renammer
from config_global import APP_CONFIG, AppConfig
import func_global as func
import reductor_workflow


def main(cfg : AppConfig):
    """ 
    Point d'entrée principal de la toolbox_pb
    """
    
    # Redirect all prints to a log file
    if cfg.LOG_TO_FILE:
        log_path = cfg.LOG_DIR / "process_log.txt"
        sys.stdout = func.Logger(str(log_path))


    # Print startup message
    print("""
        *****************************************
        *                                       *
        *          PPPPP    BBBBB               *
        *          P   P    B   B               *
        *          PPPPP    BBBBB               *
        *          P        B   B               *
        *          P        BBBBB               *
        *                                       *
        *****************************************
        """
    )
    # print the git version
    git_version = func.get_git_version()
    print(func.format_git_version(git_version))
    
    # Print python and library versions
    func.print_system_info()

    # Print all flags
    func.print_config_flags(cfg, flag_names=[
        "LOG_TO_FILE",
        "ADD_CODEC_NAME_IN_OUTPUT",
        "ADD_WITHOUTBG_IN_NAME_IN_OUTPUT",
        "ADD_COMPRESS_TO_IMAGE_NAME_IN_OUTPUT",
        "VIDEO_ASSEMBLOR_ADD_DATE_SUBTITLES",
        "VIDEO_ASSEMBLOR_EXTRACT_AND_FILTER_DATES",
        "PRINT_ALL_KEYS_IN_METADATA_SUMMARY"
    ])

    # Print time
    now = datetime.datetime.now().isoformat()
    print("\nCode lancé le : " + now)

    # Print the menu
    print("\nMenu principal : ")
    print("\n-- VIDEO --")
    print("01. Vidéo_encodor")
    print("02. Vidéo_assemblor")
    print("03. Vidéo_audio_decalator")
    print("04. Vidéo_volume_adjust")
    print("05. Vidéo_srt_extractor")
    print("06. Vidéo_srt_integrator")
    print("07. Vidéo_srt_date_filtrator")
    print("08. Vidéo_ass_hard_integrator")
    print("\n-- IMAGE --")
    print("09. Image_defilor")
    print("10. Image_reductor")
    print("11. Image_diapo_video_creator")
    print("12. Image_withoutbg")
    print("\n-- PDF --")
    print("13. PDF_filigranor")
    print("14. PDF_assemblor")
    print("\n-- FILE --")
    print("15. File_timeline_sorter")
    print("16. File_str_remover")
    print("17. Folder_date_renammer")
    print("\n18. Quitter")

    # Get user choice
    choix = input("\nSélectionnez une option (1-18) : ")
    # choix = "5"

    # Default value if selected action does not return a folder-state flag.
    is_empty_folder = False

    # Match the case by the input
    match choix:
        case "1":
            print("\nLancement du Vidéo_encodor...")
            is_empty_folder = video_encodor(cfg)
            complementary_is_empty = reductor_workflow._run_complementary_reductor(
                cfg, "video", find_files_by_extensions, video_encodor, image_reductor
            )
            if complementary_is_empty is not None:
                is_empty_folder = is_empty_folder and complementary_is_empty

        case "2":
            print("\nLancement du Vidéo_assemblor...")
            is_empty_folder = video_assemblor(cfg)

        case "3":
            print("\nLancement du Vidéo_audio_decalator...")
            is_empty_folder = video_audio_decalator(cfg)

        case "4":
            print("\nLancement du Vidéo_volume_adjust...")
            is_empty_folder = video_volume_adjust(cfg)

        case "5":
            print("\nLancement du video_srt_extractor...\n")
            is_empty_folder = video_srt_extractor(cfg)

            # Check if complementary reductor should be run
            extracted_srt_files = [
                cfg.OUTPUT_DIR / f"{video_path.stem}.srt"
                for video_path in find_files_by_extensions(
                    cfg.INPUT_DIR, cfg.INPUT_ACCEPTED_VIDEO_FILES
                )
            ]
            extracted_srt_files = [
                path for path in extracted_srt_files if path.is_file()
            ]
            # If there are extracted SRT files, ask to run video_srt_date_filtrator
            if (
                extracted_srt_files
                and reductor_workflow._ask_to_run_complementary_reductor(
                    "Vidéo_srt_date_filtrator"
                )
            ):
                print("\nLancement du Vidéo_srt_date_filtrator...")
                video_srt_date_filtrator(
                    cfg,
                    source_files=extracted_srt_files,
                    output_dir=cfg.OUTPUT_DIR,
                    overwrite=True,
                )

        case "6":
            print("\nLancement du Video_srt_integrator...")
            is_empty_folder = video_srt_integrator(cfg)

        case "7":
            print("\nLancement du Vidéo_srt_date_filtrator...")
            is_empty_folder = video_srt_date_filtrator(cfg)

        case "8":
            print("\nLancement du Vidéo_ass_hard_integrator...")
            is_empty_folder = video_ass_hard_integrator(cfg)

        case "9":
            print("\nLancement du Image_defilor...")
            is_empty_folder = run_image_defilor_interactive(cfg)

        case "10":
            print("\nLancement du Image_reductor...")
            is_empty_folder = image_reductor(cfg)
            complementary_is_empty = reductor_workflow._run_complementary_reductor(
                cfg, "image", find_files_by_extensions, video_encodor, image_reductor
            )
            if complementary_is_empty is not None:
                is_empty_folder = is_empty_folder and complementary_is_empty

        case "11":
            print("\nLancement du Image_diapo_video_creator...")
            is_empty_folder = image_diapo_video_creator(cfg)

        case "12":
            print("\nLancement du Image_withoutbg...")
            is_empty_folder = image_withoutbg(cfg)

        case "13":
            print("\nLancement du PDF_filigranor...")
            watermark_recipient = input(
                "\nEntrez le nom du destinataire du filigrane: "
            ).strip()
            is_empty_folder = pdf_filigranor(cfg, watermark_recipient)

        case "14":
            print("\nLancement du PDF_assemblor...")
            is_empty_folder = pdf_assemblor(cfg)

        case "15":
            print("\nLancement du File_timeline_sorter...")
            is_empty_folder = file_timeline_sorter(cfg)

        case "16":
            print("\nLancement du File_str_remover...")
            string_to_remove = input(
                "\nEntrez la chaîne à supprimer des noms de fichiers : "
            )
            if not string_to_remove:
                print("La chaîne à supprimer ne peut pas être vide.")
                return
            is_empty_folder = file_str_remover(cfg, string_to_remove)

        case "17":
            print("\nLancement du Folder_date_renammer...")
            is_empty_folder = folder_date_renammer(cfg)

        case "18":
            print("Quitter l'application. Au revoir !")
            sys.exit(0)

        case _:
            print("Choix invalide, recommencez.")

    # Check if no video was found in the input directory
    if is_empty_folder is True:
        print("\n⚠️ Aucun fichier compatible trouvé dans le dossier d'entrée.\n")
        sys.exit()

    # Print the summarize of files before and after
    func.summarize_files(cfg.INPUT_DIR, label="INPUT")
    func.summarize_files(cfg.OUTPUT_DIR, label="OUTPUT")
    
    # Print final message
    print("\n✅ Tous les fichiers ont été traités.\n")

# Main entry point
if __name__ == "__main__":
    main(APP_CONFIG)

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
from video.main_video import video_encodor, video_assemblor, video_audio_decalator
from image.main_image import run_image_defilor_interactive
from config_global import APP_CONFIG, AppConfig
import func_global as func

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
        "PRINT_ALL_KEYS_IN_METADATA_SUMMARY"
    ])

    # Print time
    now = datetime.datetime.now().isoformat()
    print("\nCode lancé le : " + now)

    # Print the menu
    print("\nMenu principal : ")
    print("1. Vidéo_encodor")
    print("2. Vidéo_assemblor")
    print("3. Vidéo_audio_decalator")
    print("4. Image_defilor")
    print("5. Image_reductor")
    print("6. PDF_filigranor")
    print("7. PDF_assemblor")
    print("8. Flatten_directory_tree")
    print("9. Sport_garmin_recoltor")
    print("10. Quitter")

    # Get user choice
    choix = input("Sélectionnez une option (1-10) : ")
    # choix = "2"

    # Default value if selected action does not return a folder-state flag.
    is_empty_folder = False

    # Match the case by the input
    match choix:
        case "1":
            print("\nLancement du Vidéo_encodor...")
            is_empty_folder = video_encodor(cfg)

        case "2":
            print("\nLancement du Vidéo_assemblor...")
            is_empty_folder = video_assemblor(cfg)

        case "3":
            print("\nLancement du Vidéo_audio_decalator...")
            is_empty_folder = video_audio_decalator(cfg)

        case "4":
            print("\nLancement du Image_defilor...")
            is_empty_folder = run_image_defilor_interactive(cfg)

        case "5":
            print("\nLancement du Image_reductor...")
            # A FAIRE

        case "6":
            print("\nLancement du PDF_filigranor...")
            # A FAIRE

        case "7":
            print("\nLancement du PDF_assemblor...")
            # A FAIRE

        case "8":
            print("\nLancement du Flatten_directory_tree...")
            # A FAIRE

        case "9":
            print("\nLancement du Sport_garmin_recoltor...")
            # A FAIRE

        case "10":
            print("Quitter l'application. Au revoir !")
            sys.exit(0)

        case _:
            print("Choix invalide, recommencez.")

    # Check if no video was found in the input directory
    if is_empty_folder is True:
        print("\n⚠️ Aucun fichier vidéo trouvé dans le dossier d'entrée.\n")
        sys.exit()

    # Print the summarize of files before and after
    func.summarize_files(cfg.INPUT_DIR, label="INPUT")
    func.summarize_files(cfg.OUTPUT_DIR, label="OUTPUT")
    
    # Print final message
    print("\n✅ Tous les fichiers ont été traités.\n")

# Main entry point
if __name__ == "__main__":
    main(APP_CONFIG)

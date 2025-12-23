"""
Ce fichier contient les fonctions principales pour le traitement vidéo de 
la toolbox_pb.

Auteurs :
Pierrick BERTHE
mail : pierrick.berthe@gmx.fr
Décembre 2025
"""
# import custom librairies
from config_global import AppConfig
import toolbox_pb.video.func_video as func_vid
import func_global as func_glob


def video_encodor(cfg: AppConfig) -> None:
    """
    Encodage vidéo + comparaison métadonnées avant/après.
    """

    # ------------- CONFIGURATION -------------
    accepted_file = cfg.INPUT_ACCEPTED_FILES
    codec_v = cfg.CODEC_VIDEO
    codec_a = cfg.CODEC_AUDIO
    suffix = cfg.SUFFIX_OUTPUT
    input_dir = cfg.INPUT_DIR
    output_dir = cfg.OUTPUT_DIR
    add_codec_in_output = cfg.ADD_CODEC_NAME_IN_OUTPUT
    print_all_keys = cfg.PRINT_ALL_KEYS_IN_METADATA_SUMMARY

    # ------------- BOUCLE SUR LES FICHIERS D'ENTRÉE -------------
    for input_file in input_dir.iterdir():

        # ------------- IGNORER LES FICHIERS NON VIDÉO -------------
        if input_file.suffix.lower() not in accepted_file:
            continue

        # ------------- NOM DU FICHIER ENCODE -------------
        if add_codec_in_output:
            output_name = (
                f"{input_file.stem}_v-{codec_v}_a-{codec_a}{suffix}"
            )
        else:
            output_name = (f"{input_file.stem}{suffix}")
        output_path = output_dir / output_name

        # ------------- ENCODAGE SI PAS DÉJÀ FAIT -------------
        func_glob.print_step(1, f"Encodage de la vidéo : {input_file.name}")

        # Check if already encoded
        if output_path.exists():
            print("Encodage déjà réalisé.")
        else:
            func_vid.encode_full_video(
                input_path=input_file,
                output_path=output_path,
                codec_video=codec_v,
                codec_audio=codec_a
            )

        # ------------- COMPARAISON MÉTADONNÉES AVANT/APRÈS -------------
        func_glob.print_step(2, "Comparaison des fichiers avant/après")
        
        # Get metadata before and after encoding
        meta_before = func_vid.get_all_metadata(input_file)
        meta_after = func_vid.get_all_metadata(output_path)

        # Print all metadata if flag is set
        if print_all_keys:
            print("Méta avant l'encodage :")
            func_vid.print_metadata_summary_all_keys(meta_before)
            
            print("\nMéta après l'encodage :")
            func_vid.print_metadata_summary_all_keys(meta_after)
        
        # Print metadata differences
        func_vid.print_metadata_diff_summary(meta_before, meta_after)
        
        # Get size reduction stats and print them
        stats = func_vid.compute_size_reduction(meta_before, meta_after)
        func_vid.print_size_reduction(stats)

    print("\n✅ Tous les fichiers ont été traités.\n")

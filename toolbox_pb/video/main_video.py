"""
Ce fichier contient les fonctions principales pour le traitement vidéo de 
la toolbox_pb.

Auteurs :
Pierrick BERTHE
mail : pierrick.berthe@gmx.fr
Décembre 2025
"""
# import custom librairies
import sys
from config_global import AppConfig
import toolbox_pb.video.func_video as func_vid
import func_global as func_glob


def video_encodor(cfg: AppConfig) -> bool:
    """
    Encode video files in the input directory according to the specified
    configuration and compares metadata before and after encoding.
    1. Loops through all accepted video files and subdirectories.
    2. Encodes each video file using the specified video and audio codecs.
    3. Preserves the input directory structure in the output directory.
    4. Compares and prints metadata differences before and after encoding.
    5. Prints size reduction statistics.
    """

    # ------------- CONFIGURATION -------------
    config = func_glob.parse_config(cfg)

    # ------------- LOOP THROUGH ALL FILES IN INPUT DIR -------------
    is_empty_folder = True
    for input_file in config["input_dir"].rglob('*'):

        # ------- IGNORE NON-VIDEO FILES AND DIRECTORIES -------
        if not input_file.is_file() or input_file.suffix.lower() not in config["accepted_file"]:
            continue

        # If we reach this point, it means we found at least one video file
        is_empty_folder = False

        # --- CREATE OUTPUT SUBDIR STRUCTURE BASED ON INPUT FILE PATH ---
        output_subdir = func_glob.build_output_subdir_from_input(
                input_file, config["input_dir"], config["output_dir"]
        )

        # ------------- FILENAME FOR OUTPUT VIDEO -------------
        output_path = func_glob.build_output_path(
            input_file,
            output_subdir,
            config["suffix"],
            config["codec_v"],
            config["codec_a"],
            config["add_codec"]
        )


        # ------------- ENCODE VIDEO IF NOT ALREADY DONE -------------
        func_glob.print_step(1, f"Encodage de la vidéo : {input_file.name}")

        # Check if already encoded
        if output_path.exists():
            print("Encodage déjà réalisé.")
        else:
            func_vid.encode_full_video(
                input_path=input_file,
                output_path=output_path,
                codec_video=config["codec_v"],
                codec_audio=config["codec_a"]
            )

        # ------------- COMPARE METADATA BEFORE/AFTER -------------
        func_glob.print_step(2, "Comparaison des fichiers avant/après")
        
        # Get metadata before and after encoding
        meta_before = func_vid.get_all_metadata(input_file)
        meta_after = func_vid.get_all_metadata(output_path)

        # Print all metadata if flag is set
        if config["print_all_keys"]:
            print("Méta avant l'encodage :")
            func_vid.print_metadata_summary_all_keys(meta_before)
            
            print("\nMéta après l'encodage :")
            func_vid.print_metadata_summary_all_keys(meta_after)
        
        # Print metadata differences
        func_vid.print_metadata_diff_summary(meta_before, meta_after)
        
        # Get size reduction stats and print them
        stats = func_vid.compute_size_reduction(meta_before, meta_after)
        func_vid.print_size_reduction(stats)

    return is_empty_folder


def video_assemblor(cfg: AppConfig) -> bool:
    """
    Assemble videos based on segments.csv if present,
    otherwise assemble all videos found in input directory.
    """
    # Import configuration
    config = func_glob.parse_config(cfg)

    # create file output path
    output_path = (
        config["output_dir"] / 
        f"assembled_v-{config['codec_v']}_a-{config['codec_a']}{config['suffix']}"
    )

    # ------------- ENCODE AND ASSEMBLE VIDEOS -------------
    func_glob.print_step(1, f"Encodage des vidéos à assembler")

    # Check if already encoded
    if output_path.exists():
        print("Encodage déjà réalisé.")
    else:
        # Vérifier s'il y a des fichiers vidéo dans le dossier d'entrée
        video_files = list(cfg.INPUT_DIR.rglob('*'))
        video_files = [
            f for f in video_files if f.is_file() 
            and f.suffix.lower() in cfg.INPUT_ACCEPTED_FILES
        ]

        # If no video files found, return early with is_empty_folder = True
        if not video_files:
            is_empty_folder = True
            return is_empty_folder

        # Load segments if they exist
        segments = None
        segments_csv = cfg.SEGMENT_DIR / "segments.csv"
        if segments_csv.exists():
            segments = func_vid.load_segments_csv(segments_csv)
            print(f"\nSegments chargés depuis '{segments_csv}'.\n")
        else:
            print(
                "\nFichier 'segments.csv' non trouvé,"
                "tous les fichiers sont assemblés.\n"
            )

        # Resolve which videos to process and in which order
        sequence = func_vid.resolve_video_sequence(
            input_dir=cfg.INPUT_DIR,
            accepted_ext=cfg.INPUT_ACCEPTED_FILES,
            segments=segments
        )
        
        # print input files used
        input_files = []
        for file in sequence:
            if file["path"].name not in input_files:
                input_files.append(file["path"].name)
        print(f"input_files used :")
        for file in input_files:
            print(f"- {file}")
        print ()

        # Load clips
        clips = []
        for item in sequence:
            clips.append(
                func_vid.load_and_trim_clip(
                    item["path"],
                    item["start"],
                    item["end"]
                )
            )

        # Audio safety
        clips = func_vid.normalize_audio(clips)

        # Concatenate
        final_clip = func_vid.concatenate_videoclips(clips, method="compose")

        # Write the final video file
        func_vid.write_video_file(
            final_clip=final_clip,
            output_path=output_path,
            codec_video=config['codec_v'],
            codec_audio=config['codec_a']
        )
        is_empty_folder = False

        # Cleanup
        for clip in clips:
            clip.close()
        final_clip.close()

        # ------------- COMPARE METADATA BEFORE/AFTER -------------
        func_glob.print_step(2, "Comparaison des fichiers avant/après")
        
        # isolate first input file for metadata comparison
        input_file = sequence[0]["path"]
        print(f"input_file pour la comparaison : {input_file.name}\n")
        
        # Get metadata before and after encoding
        meta_before = func_vid.get_all_metadata(input_file)
        meta_after = func_vid.get_all_metadata(output_path)
        
        # Print metadata differences
        func_vid.print_metadata_diff_summary(meta_before, meta_after)

        # Get metadata for all inputs before assembly and after
        metas_before = func_vid.get_inputs_metadata(
            sequence=sequence,
            get_metadata_fn=func_vid.get_all_metadata
        )
        meta_after = func_vid.get_all_metadata(output_path)

        # Get size reduction stats and print them
        stats = func_vid.compute_size_reduction_from_inputs(
            metas_before=metas_before,
            meta_after=meta_after
        )

        # Print size reduction stats
        func_vid.print_size_reduction(stats)

    return is_empty_folder


def video_audio_decalator(cfg: AppConfig) -> bool:
    """
    Shift audio of video files in the input directory by a specified delay
    without re-encoding the video stream.
    """
    # Import configuration
    config = func_glob.parse_config(cfg)
    
    # Input the delay in seconds
    while True:
        user_input = input(
            "Entrez le délai de décalage audio en secondes"
            "(ex: -0.5 pour avancer de 0.5s, 0.5 pour retarder de 0.5s) : "
            )
        try:
            delay = float(user_input)
            break
        except ValueError:
            print("Format invalide. Entrer un nombre valide (ex : -0.5, 0.5).")

    # ------------- LOOP THROUGH ALL FILES IN INPUT DIR -------------
    is_empty_folder = True
    for input_file in config["input_dir"].rglob('*'):

        # ------- IGNORE NON-VIDEO FILES AND DIRECTORIES -------
        if not input_file.is_file() or input_file.suffix.lower() not in config["accepted_file"]:
            continue

        # --- CREATE OUTPUT SUBDIR STRUCTURE BASED ON INPUT FILE PATH ---
        output_subdir = func_glob.build_output_subdir_from_input(
                input_file, config["input_dir"], config["output_dir"]
        )

        # ------------- FILENAME FOR OUTPUT VIDEO -------------
        output_path = func_glob.build_output_path(
            input_file,
            output_subdir,
            config["suffix"],
            config["codec_v"],
            config["codec_a"],
            config["add_codec"]
        )

        # Check if already decalated
        if output_path.exists():
            print("Décalage déjà réalisé.")
        else:
            func_vid.shift_audio_no_reencode(
            input_video= input_file,
            output_video= output_path,
            delay=delay
        )
        is_empty_folder = False

    return is_empty_folder

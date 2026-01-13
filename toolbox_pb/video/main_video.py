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
    Encode video files in the input directory according to the specified
    configuration and compares metadata before and after encoding.
    1. Loops through all accepted video files in the input directory.
    2. Encodes each video file using the specified video and audio codecs.
    3. Compares and prints metadata differences before and after encoding.
    4. Prints size reduction statistics.
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


def video_assemblor(cfg: AppConfig) -> None:
    """
    Assemble videos based on segments.csv if present,
    otherwise assemble all videos found in input directory.
    """
    # Import configuration
    codec_v = cfg.CODEC_VIDEO
    codec_a = cfg.CODEC_AUDIO
    suffix = cfg.SUFFIX_OUTPUT

    # create file output path
    output_path = cfg.OUTPUT_DIR / f"assembled_v-{codec_v}_a-{codec_a}{suffix}"
        
    # ------------- ENCODAGE SI PAS DÉJÀ FAIT -------------
    func_glob.print_step(1, f"Encodage des vidéos à assembler")
    
    # Check if already encoded
    if output_path.exists():
        print("Encodage déjà réalisé.")
    else:

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
            codec_video=codec_v,
            codec_audio=codec_a
        )

        # Cleanup
        for clip in clips:
            clip.close()
        final_clip.close()
        
        # ------------- COMPARAISON MÉTADONNÉES AVANT/APRÈS -------------
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

    print("\n✅ La vidéo assemblée a été créée.\n")

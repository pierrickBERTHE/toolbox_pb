"""
Ce fichier contient les fonctions principales pour le traitement vidéo de 
la toolbox_pb.

Auteurs :
Pierrick BERTHE
mail : pierrick.berthe@gmx.fr
Décembre 2025
"""
# import custom librairies
import filecmp
import subprocess
from tqdm import tqdm
from config_global import AppConfig
import toolbox_pb.video.func_video as func_vid
import func_global as func_glob


def _is_unchanged_input_copy(input_path, output_path) -> bool:
    """
    Return True only for an output created by shutil.copy2 from its input.
    """
    if not output_path.exists() or input_path.stat().st_size != output_path.stat().st_size:
        return False
    if input_path.stat().st_mtime_ns != output_path.stat().st_mtime_ns:
        return False
    return filecmp.cmp(input_path, output_path, shallow=False)


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
    video_files = func_vid.find_files_by_extensions(
        config["input_dir"], config["accepted_file"]
    )
    is_empty_folder = not video_files
    encoded_videos = 0
    unchanged_videos = 0
    already_encoded_videos = 0
    failed_videos = 0
    for input_file in tqdm(video_files, desc="Video_encodor", unit="vidéo"):

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
            config["add_codec"],
            name_suffix="_Compressed" if config["add_compressed"] else "",
        )


        # ------------- ENCODE VIDEO IF NOT ALREADY DONE -------------
        func_glob.print_step(1, f"Encodage de la vidéo : {input_file.name}")

        # Check if already encoded
        if output_path.exists() and not _is_unchanged_input_copy(input_file, output_path):
            print("Encodage déjà réalisé.")
            already_encoded_videos += 1
        else:
            if output_path.exists():
                print("Copie intacte détectée. Encodage de la vidéo...")
            try:
                func_vid.encode_full_video(
                    input_path=input_file,
                    output_path=output_path,
                    codec_video=config["codec_v"],
                    codec_audio=config["codec_a"]
                )
            except (subprocess.CalledProcessError, RuntimeError, OSError) as exc:
                failed_videos += 1
                if output_path.exists():
                    output_path.unlink()
                print(f"Vidéo ignorée : {input_file.name} ({exc})")
                continue
            encoded_videos += 1

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

    # print summary of encoding results
    if video_files:
        print(
            "\nRésumé Video_encodor : "
            f"{encoded_videos} vidéo(s) compressée(s), "
            f"{unchanged_videos} laissée(s) intacte(s), "
            f"{already_encoded_videos} déjà traitée(s), "
            f"{failed_videos} ignorée(s) après erreur."
        )

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


def video_volume_adjust(cfg: AppConfig) -> bool:
    """
    Adjust the audio volume of video files in the input directory
    based on boost segments defined in a CSV file.
    """
    # Import configuration
    config = func_glob.parse_config(cfg)

    # Check if segments CSV exists
    segments_csv = cfg.SEGMENT_DIR / "boosts.csv"
    if not segments_csv.exists():
        print(f"⚠️ Fichier de segments introuvable : {segments_csv}")
        return True

    # ------------- LOOP THROUGH ALL FILES IN INPUT DIR -------------
    is_empty_folder = True
    for input_file in config["input_dir"].rglob('*'):

        # ------- IGNORE NON-VIDEO FILES AND DIRECTORIES -------
        if not input_file.is_file() or input_file.suffix.lower() not in config["accepted_file"]:
            continue

        # create file output path
        stem_file = input_file.stem
        output_path = (
            config["output_dir"] / f"{stem_file}{config['suffix']}"
        )

        # Check if already boosted
        if output_path.exists():
            print("Ajustement déjà réalisé.")
        else:
            func_vid.apply_audio_boosts_ffmpeg(
                input_video=input_file,
                output_video=output_path,
                csv_path=segments_csv,
            )
        is_empty_folder = False

    return is_empty_folder


def video_srt_integrator(cfg: AppConfig) -> bool:
    """
    Integrate SRT subtitles into video files in the input directory.
    """
    # Import configuration
    config = func_glob.parse_config(cfg)

    # Check if segments CSV exists
    segments_csv = cfg.SEGMENT_DIR / "sous_titre.srt"
    if not segments_csv.exists():
        print(f"⚠️ Fichier de sous_titre introuvable : {segments_csv}")
        return True

    # ------------- LOOP THROUGH ALL FILES IN INPUT DIR -------------
    is_empty_folder = True
    for input_file in config["input_dir"].rglob('*'):

        # ------- IGNORE NON-VIDEO FILES AND DIRECTORIES -------
        if not input_file.is_file() or input_file.suffix.lower() not in config["accepted_file"]:
            continue

        # create file output path
        stem_file = input_file.stem
        output_path = (
            config["output_dir"] / f"{stem_file}{config['suffix']}"
        )

        # Check if already boosted
        if output_path.exists():
            print("Ajout de sous-titres déjà réalisé.")
        else:
            func_vid.apply_video_srt_ffmpeg(
                input_video=input_file,
                output_video=output_path,
                srt_path=segments_csv,
            )
        is_empty_folder = False

    return is_empty_folder


def image_diapo_video_creator(cfg: AppConfig) -> bool:
    """Create one slideshow that displays every image at full frame height.

    Images are ordered by their relative path, each remains visible for the
    configured duration. The output width is set from the widest image after
    height normalization; the single audio file found in input is attached
    when present.
    """
    # extract configuration values
    duration = cfg.IMAGE_DIAPO_DURATION_SECONDS
    
    # Validate configuration values
    if duration <= 0:
        raise ValueError("IMAGE_DIAPO_DURATION_SECONDS doit être strictement positif.")
    if cfg.IMAGE_DIAPO_FPS <= 0:
        raise ValueError("IMAGE_DIAPO_FPS doit être strictement positif.")
    if cfg.IMAGE_DIAPO_MAX_HEIGHT <= 0:
        raise ValueError("IMAGE_DIAPO_MAX_HEIGHT doit être strictement positif.")

    # ------------ FIND IMAGE AND AUDIO FILES -------------
    image_files = func_vid.find_files_by_extensions(
        cfg.INPUT_DIR, cfg.INPUT_ACCEPTED_IMAGE_FILES
    )
    if not image_files:
        return True

    audio_files = func_vid.find_files_by_extensions(
        cfg.INPUT_DIR, cfg.INPUT_ACCEPTED_AUDIO_FILES
    )
    if len(audio_files) > 1:
        raise ValueError("Un seul fichier audio est autorisé dans le dossier d'entrée.")

    # ----------- CALCULATE FRAME SIZE -------------
    image_dimensions = [
        (image_path, *func_vid.get_image_size(image_path))
        for image_path in image_files
    ]
    frame_height = min(
        max(height for _, _, height in image_dimensions),
        cfg.IMAGE_DIAPO_MAX_HEIGHT,
    )
    frame_height = max(2, frame_height - frame_height % 2)
    frame_width = max(
        func_vid.fit_image_size_in_frame((width, height), (0, frame_height))[0]
        for _, width, height in image_dimensions
    )

    # create output path for the slideshow video
    cfg.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = cfg.OUTPUT_DIR / (
        f"image_diapo_video_v-{cfg.CODEC_VIDEO}_a-{cfg.CODEC_AUDIO}"
        f"{cfg.SUFFIX_OUTPUT_VIDEO}"
    )

    # check if output video already exists, else delete existing SRT file if present
    srt_output_path = output_path.with_suffix(".srt")
    if srt_output_path.exists():
        srt_output_path.unlink()
    if output_path.exists():
        print("\nCréation du diaporama déjà réalisée.")
        return False

    # ------------ CREATE SLIDESHOW VIDEO -------------
    func_vid.create_image_diapo_ffmpeg(
        image_paths=image_files,
        input_dir=cfg.INPUT_DIR,
        audio_path=audio_files[0] if audio_files else None,
        output_path=output_path,
        duration=duration,
        fps=cfg.IMAGE_DIAPO_FPS,
        frame_size=(frame_width, frame_height),
        codec_video=cfg.CODEC_VIDEO,
        codec_audio=cfg.CODEC_AUDIO,
    )

    return False

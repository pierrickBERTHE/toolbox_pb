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
import tempfile
from pathlib import Path
from tqdm import tqdm
from config_global import AppConfig
import toolbox_pb.video.func_video as func_vid
import toolbox_pb.image.func_image as func_ima
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


def _extract_and_filter_assembled_srt(assembled_video: Path) -> None:
    """Extract, de-duplicate and save the first subtitle stream of an assembly."""
    # launch the extraction of SRT subtitles if the flag is set
    print(
        "\n✅ VIDEO_ASSEMBLOR_EXTRACT_AND_FILTER_DATES activé : "
        "extraction puis filtrage des sous-titres."
    )
    with tempfile.TemporaryDirectory(prefix="video_assemblor_srt_") as temp_name:
        temp_dir = Path(temp_name)
        extracted_video = temp_dir / assembled_video.name
        extracted_srt = temp_dir / f"{assembled_video.stem}.srt"

        print("Lancement du Vidéo_srt_extractor après l'assemblage...")
        func_vid.extract_video_srt_ffmpeg(
            input_video=assembled_video,
            output_video=extracted_video,
            srt_output_path=extracted_srt,
            processing_comment=func_glob.build_video_processing_comment(
                assembled_video,
                "video_srt_extractor | video_srt_date_filtrator",
            ),
        )
        if not extracted_srt.exists() or not extracted_video.exists():
            print("⚠️ Aucune piste de sous-titres n'a pu être extraite.")
            return

        # launch the filtering of SRT subtitles
        print("Lancement du Vidéo_srt_date_filtrator après l'extraction...")
        subtitles = func_vid.parse_srt_cues(
            extracted_srt.read_text(encoding="utf-8-sig")
        )
        
        # print statistics before and after filtering
        func_vid.print_srt_date_statistics(
            "Avant filtrage", func_vid.get_srt_date_statistics(subtitles)
        )
        func_vid.print_duplicate_srt_dates(subtitles)
        filtered_subtitles = func_vid.filter_duplicate_srt_dates(subtitles)

        print()
        func_vid.print_srt_date_statistics(
            "Après filtrage", func_vid.get_srt_date_statistics(filtered_subtitles)
        )
        func_vid.print_duplicate_srt_dates(filtered_subtitles)

        # write the filtered subtitles to the temporary SRT file
        extracted_srt.write_text(
            func_vid.format_srt_cues(filtered_subtitles), encoding="utf-8"
        )
        
        # replace the original files with the filtered ones
        extracted_video.replace(assembled_video)
        extracted_srt.replace(assembled_video.with_suffix(".srt"))
        print("✅ Extraction et filtrage des sous-titres terminés.")


@func_glob.measure_time
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
            config["add_codec"],
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
                    codec_audio=config["codec_a"],
                    processing_comment=func_glob.build_video_processing_comment(
                        input_file, "video_encodor", config["codec_v"], config["codec_a"]
                    ),
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


@func_glob.measure_time
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
        is_empty_folder = False
    else:
        # Check for video files in the input directory
        video_files = list(cfg.INPUT_DIR.rglob('*'))
        video_files = [
            f for f in video_files if func_glob.is_processable_file(f)
            and f.suffix.lower() in cfg.INPUT_ACCEPTED_VIDEO_FILES
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
            accepted_ext=cfg.INPUT_ACCEPTED_VIDEO_FILES,
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
        print()

        # Create a temporary directory for intermediate files
        source_temp_dir = tempfile.TemporaryDirectory(
            prefix="video_assembly_source_"
        )
        
        # Prepare each video for assembly: normalize FPS, codec, and audio stream
        prepared_paths = [
            func_vid.prepare_video_for_assembly(
                item["path"],
                Path(source_temp_dir.name),
                index,
                config["codec_v"],
                config["codec_a"],
            )
            for index, item in enumerate(sequence)
        ]

        # Probe shared frame size and target FPS via FFprobe only, no MoviePy load
        frame_size = func_vid.get_video_frame_size_from_paths(
            prepared_paths, max_height=cfg.IMAGE_DIAPO_MAX_HEIGHT
        )

        # Probe shared output FPS via FFprobe only, no MoviePy load
        output_fps = func_vid.get_video_output_fps_from_paths(prepared_paths)

        normalized_paths = []
        duration_clips = []
        try:
            # Outer bar counts finished videos, one step per source
            with tqdm(
                total=len(sequence),
                unit="vidéo",
                desc="Progression globale",
                position=1,
                leave=True,
                bar_format="{l_bar}{bar}| {n:.0f}/{total:.0f} [{elapsed}<{remaining}]",
            ) as global_progress_bar:

                # Render one source at a time: only one FFmpeg encode at
                # once, so peak memory stays bounded regardless of count
                for index, (item, prepared_path) in enumerate(
                    zip(sequence, prepared_paths)
                ):
                    # Render the normalized source clip to a temporary file
                    normalized_path = (
                        Path(source_temp_dir.name)
                        / f"assembled_source_{index:03d}.mp4"
                    )
                    # Render the normalized source clip and get its duration
                    duration = func_vid.render_normalized_source_clip(
                        prepared_path,
                        item["start"],
                        item["end"],
                        frame_size or (0, 0),
                        output_fps or 30.0,
                        config["codec_v"],
                        config["codec_a"],
                        normalized_path,
                    )
                    normalized_paths.append(normalized_path)
                    duration_clips.append(
                        func_vid.DurationOnlyClip(duration=duration)
                    )
                    global_progress_bar.update(1)

            # Optionally create a temporary date subtitle file
            with tempfile.TemporaryDirectory(prefix="video_assemblor_") as temp_dir_name:
                subtitle_paths = []
                preserved_subtitles_path = Path(temp_dir_name) / "input_subtitles.srt"

                # Write preserved input subtitles if they exist
                if func_vid.write_video_assemblor_input_subtitles_srt(
                    sequence, duration_clips, preserved_subtitles_path,
                    Path(temp_dir_name)
                ):
                    subtitle_paths.append(preserved_subtitles_path)

                # If flag is set, create a temporary date subtitle file
                if cfg.VIDEO_ASSEMBLOR_ADD_DATE_SUBTITLES:
                    candidate_path = Path(temp_dir_name) / "dates.srt"
                    if func_vid.write_video_assemblor_date_srt(
                        sequence, duration_clips, candidate_path,
                        display_duration=cfg.SRT_DURATION_SECONDS
                    ):
                        subtitle_paths.append(candidate_path)
                    else:
                        print("Aucune date valide trouvée dans les noms des vidéos.")

                # Stream-copy every normalized source into the final file
                func_vid.concat_normalized_clips_ffmpeg(
                    normalized_paths,
                    subtitle_paths,
                    output_path,
                    func_glob.build_video_processing_comment(
                        sequence[0]["path"],
                        "video_assemblor",
                        config["codec_v"],
                        config["codec_a"]
                    )
                )

        finally:
            # Clean up the temporary directory for normalized source clips
            source_temp_dir.cleanup()

        is_empty_folder = False

        # ------------- COMPARE METADATA BEFORE/AFTER -------------
        func_glob.print_step(2, "Comparaison des fichiers avant/après")

        # isolate first input file for metadata comparison
        input_file = sequence[0]["path"]
        print(f"input_file pour la comparaison : {input_file.name}\n")

        # Get metadata before and after encoding
        meta_before = func_vid.get_all_metadata(input_file)
        meta_after = func_vid.get_all_metadata(output_path)
        func_vid.print_metadata_diff_summary(meta_before, meta_after)

        # Get metadata for all inputs before assembly and after
        metas_before = func_vid.get_inputs_metadata(
            sequence=sequence, get_metadata_fn=func_vid.get_all_metadata
        )
        meta_after = func_vid.get_all_metadata(output_path)

        # Get size reduction stats and print them
        stats = func_vid.compute_size_reduction_from_inputs(
            metas_before=metas_before, meta_after=meta_after
        )

        # Print size reduction stats
        func_vid.print_size_reduction(stats)

    # extract and filter SRT if flag is set and output exists
    if (
        not is_empty_folder
        and cfg.VIDEO_ASSEMBLOR_EXTRACT_AND_FILTER_DATES
        and output_path.exists()
    ):
        _extract_and_filter_assembled_srt(output_path)

    return is_empty_folder


@func_glob.measure_time
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
        if not func_glob.is_processable_file(input_file) or input_file.suffix.lower() not in config["accepted_file"]:
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
            config["add_codec"]
        )

        # Check if already decalated
        if output_path.exists():
            print("Décalage déjà réalisé.")
        else:
            func_vid.shift_audio_no_reencode(
                input_video=input_file,
                output_video=output_path,
                delay=delay,
                processing_comment=func_glob.build_video_processing_comment(
                    input_file,
                    f"video_audio_decalator | Décalage audio : {delay:+g} s",
                ),
            )
        is_empty_folder = False

    return is_empty_folder


@func_glob.measure_time
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

    boosts = func_vid.load_boost_csv(segments_csv)
    volume_feature = "video_volume_adjust"
    if len(boosts) == 1:
        volume_feature += f" | Gain audio : {boosts[0].gain_db:+g} dB"

    # ------------- LOOP THROUGH ALL FILES IN INPUT DIR -------------
    is_empty_folder = True
    for input_file in config["input_dir"].rglob('*'):

        # ------- IGNORE NON-VIDEO FILES AND DIRECTORIES -------
        if not func_glob.is_processable_file(input_file) or input_file.suffix.lower() not in config["accepted_file"]:
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
                processing_comment=func_glob.build_video_processing_comment(
                    input_file,
                    volume_feature,
                ),
            )
        is_empty_folder = False

    return is_empty_folder


@func_glob.measure_time
def video_srt_extractor(cfg: AppConfig) -> bool:
    """
    Extract SRT subtitles from video files in the input directory.

    Each video with an embedded subtitle stream is copied to the output
    directory without that stream, and the subtitles are saved as a
    standalone .srt file with the same name next to it. Videos without any
    subtitle stream are skipped entirely (nothing written to output).
    """
    # Import configuration
    config = func_glob.parse_config(cfg)

    # ------------- LOOP THROUGH ALL FILES IN INPUT DIR -------------
    is_empty_folder = True
    for input_file in config["input_dir"].rglob('*'):

        # ------- IGNORE NON-VIDEO FILES AND DIRECTORIES -------
        if not func_glob.is_processable_file(input_file) or input_file.suffix.lower() not in config["accepted_file"]:
            continue

        # create file output paths (video + sidecar SRT)
        stem_file = input_file.stem
        output_path = (
            config["output_dir"] / f"{stem_file}{config['suffix']}"
        )
        srt_output_path = config["output_dir"] / f"{stem_file}.srt"

        # Check if already extracted
        if output_path.exists():
            print("Extraction des sous-titres déjà réalisée.")
        else:
            func_vid.extract_video_srt_ffmpeg(
                input_video=input_file,
                output_video=output_path,
                srt_output_path=srt_output_path,
                processing_comment=func_glob.build_video_processing_comment(
                    input_file,
                    "video_srt_extractor",
                ),
            )
        is_empty_folder = False

    return is_empty_folder


@func_glob.measure_time
def video_srt_date_filtrator(
    cfg: AppConfig,
    source_files: list[Path] | None = None,
    output_dir: Path | None = None,
    overwrite: bool = False,
) -> bool:
    """Keep only the first subtitle occurrence of every date in SRT input files.

    Both standard ``.srt`` files and SRT files saved with a ``.txt`` extension
    are supported. The filtered counterpart is written to ``data/output`` with
    the same filename. ``source_files`` is used by the extractor follow-up
    workflow to filter newly generated SRT files in place.
    """
    is_empty_folder = True

    # for each SRT file in the input directory (or provided source files)
    subtitle_files = source_files if source_files is not None else sorted(
        path
        for path in cfg.INPUT_DIR.rglob("*")
        if path.suffix.lower() in {".srt", ".txt"}
    )
    destination_dir = output_dir or cfg.OUTPUT_DIR
    for input_file in subtitle_files:
        if not func_glob.is_processable_file(input_file):
            continue

        output_path = destination_dir / input_file.name
        subtitles = func_vid.parse_srt_cues(
            input_file.read_text(encoding="utf-8-sig")
        )

        # print statistics before filtering
        func_vid.print_srt_date_statistics(
            "Avant filtrage", func_vid.get_srt_date_statistics(subtitles)
        )
        func_vid.print_duplicate_srt_dates(subtitles)

        # if the output file already exists and overwrite is False, skip filtering
        if output_path.exists() and not overwrite:
            print("Filtrage des dates déjà réalisé.")
            filtered_subtitles = func_vid.parse_srt_cues(
                output_path.read_text(encoding="utf-8-sig")
            )
        else:
            filtered_subtitles = func_vid.filter_duplicate_srt_dates(subtitles)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                func_vid.format_srt_cues(filtered_subtitles), encoding="utf-8"
            )

        # print statistics after filtering
        print()
        func_vid.print_srt_date_statistics(
            "Après filtrage", func_vid.get_srt_date_statistics(filtered_subtitles)
        )
        func_vid.print_duplicate_srt_dates(filtered_subtitles)
        is_empty_folder = False

    return is_empty_folder


@func_glob.measure_time
def video_convert_srt_to_ass(cfg: AppConfig) -> bool:
    """Convert input SRT files to ASS using ``data/template/template_sous_titre.ass``."""
    # Check if template ASS file exists
    template_path = cfg.ROOT / "data" / "template" / "template_sous_titre.ass"
    if not template_path.is_file():
        print(f"⚠️ Modèle ASS introuvable : {template_path}")
        return True

    # loop through all SRT files in the input directory and convert them to ASS
    is_empty_folder = True
    for input_file in sorted(cfg.INPUT_DIR.rglob("*.srt")):
        if not func_glob.is_processable_file(input_file):
            continue

        output_path = cfg.OUTPUT_DIR / f"{input_file.stem}.ass"
        if output_path.exists():
            print("Conversion SRT vers ASS déjà réalisée.")
        else:
            func_vid.convert_srt_to_ass(
                input_file,
                template_path,
                output_path,
                title_duration_seconds=cfg.ASS_TITLE_DURATION_SECONDS,
                subtitle_duration_seconds=cfg.ASS_SUBTITLE_DURATION_SECONDS,
                title_fade_duration_ms=cfg.ASS_TITLE_FADE_DURATION_MS,
                subtitle_fade_duration_ms=cfg.ASS_SUBTITLE_FADE_DURATION_MS,
            )
        is_empty_folder = False

    return is_empty_folder


@func_glob.measure_time
def video_ass_hard_integrator(cfg: AppConfig) -> bool:
    """Convert input SRT files to ASS when needed, then burn them into videos."""
    # Import configuration
    config = func_glob.parse_config(cfg)
    
    # Find all SRT, ASS, and video files in the input directory
    srt_files = func_vid.find_files_by_extensions(cfg.INPUT_DIR, [".srt"])
    ass_files = func_vid.find_files_by_extensions(cfg.INPUT_DIR, [".ass"])
    video_files = func_vid.find_files_by_extensions(
        cfg.INPUT_DIR, cfg.INPUT_ACCEPTED_VIDEO_FILES
    )
    if not video_files:
        return True
    if not srt_files and not ass_files:
        print("⚠️ Aucun fichier SRT ou ASS trouvé dans le dossier d'entrée.")
        return True

    # Create a mapping of subtitle files by their stem (filename without extension)
    subtitle_files = srt_files or ass_files
    subtitle_by_stem = {
        subtitle_file.stem.lower(): subtitle_file for subtitle_file in subtitle_files
    }
    shared_subtitle_path = subtitle_files[0] if len(subtitle_files) == 1 else None
    template_path = cfg.ROOT / "data" / "template" / "template_sous_titre.ass"
    if srt_files and not template_path.is_file():
        print(f"⚠️ Modèle ASS introuvable : {template_path}")
        return True

    # loop through all video files and integrate the corresponding ASS subtitles
    processed_video = False
    with tempfile.TemporaryDirectory(prefix="video_ass_hard_integrator_") as temp_name:
        temp_dir = Path(temp_name)
        converted_ass_paths = {}

        # If there are SRT files, convert them to ASS using the template
        if srt_files:
            print("\n    ==> Lancement intégré du Vidéo_convert_srt_to_ass...\n")
            for srt_file in srt_files:
                ass_path = temp_dir / f"{srt_file.stem}.ass"
                func_vid.convert_srt_to_ass(
                    srt_file,
                    template_path,
                    ass_path,
                    title_duration_seconds=cfg.ASS_TITLE_DURATION_SECONDS,
                    subtitle_duration_seconds=cfg.ASS_SUBTITLE_DURATION_SECONDS,
                    title_fade_duration_ms=cfg.ASS_TITLE_FADE_DURATION_MS,
                    subtitle_fade_duration_ms=cfg.ASS_SUBTITLE_FADE_DURATION_MS,
                )
                converted_ass_paths[srt_file] = ass_path
            print("    ✅ Conversion SRT vers ASS terminée.\n")

        for input_file in video_files:
            subtitle_path = shared_subtitle_path or subtitle_by_stem.get(
                input_file.stem.lower()
            )
            if subtitle_path is None:
                print(f"⚠️ Aucun fichier SRT ou ASS associé à : {input_file.name}")
                continue
            ass_path = converted_ass_paths.get(subtitle_path, subtitle_path)

            # build output subdirectory structure based on input file path
            output_subdir = func_glob.build_output_subdir_from_input(
                input_file, config["input_dir"], config["output_dir"]
            )
            output_path = func_glob.build_output_path(
                input_file,
                output_subdir,
                config["suffix"],
                config["codec_v"],
                config["add_codec"],
            )
            # integrate ASS subtitles into the video using FFmpeg
            if output_path.exists():
                print("Incrustation ASS déjà réalisée.")
            else:
                func_vid.integrate_ass_hard_ffmpeg(
                    input_video=input_file,
                    ass_path=ass_path,
                    output_video=output_path,
                    codec_video=config["codec_v"],
                    codec_audio=config["codec_a"],
                    processing_comment=func_glob.build_video_processing_comment(
                        input_file, "video_ass_hard_integrator",
                        config["codec_v"], config["codec_a"],
                    ),
                )
            processed_video = True

    return not processed_video


@func_glob.measure_time
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
        if not func_glob.is_processable_file(input_file) or input_file.suffix.lower() not in config["accepted_file"]:
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
                processing_comment=func_glob.build_video_processing_comment(
                    input_file,
                    "video_srt_integrator",
                ),
            )
        is_empty_folder = False

    return is_empty_folder


@func_glob.measure_time
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
        processing_comment=func_ima.build_image_processing_comment(
            image_files[0],
            "image_diapo_video_creator",
            image_codec=cfg.CODEC_VIDEO,
        ),
    )

    return False

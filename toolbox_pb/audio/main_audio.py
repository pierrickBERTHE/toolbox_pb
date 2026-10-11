"""
Ce fichier contient la fonctionnalité principale audio_compressor.

Auteurs :
Pierrick BERTHE
mail : pierrick.berthe@gmx.fr
Octobre 2026
"""

import subprocess
from collections import Counter
from pathlib import Path
import shutil

from config_global import AppConfig
from func_global import (
    build_output_subdir_from_input,
    format_bytes,
    measure_time,
)
from audio.func_audio import (
    build_audio_processing_comment,
    compress_audio_to_mp3,
    find_audio_files,
    probe_audio_bitrate_kbps,
)


def artwork_priority(jpeg_path: Path) -> tuple[int, str]:
    """Return the selection priority and normalized name of JPEG artwork.

    Lower priority values are preferred; the name makes equal priorities
    deterministic.
    """
    name = jpeg_path.name.casefold()
    if any(word in name for word in ("jaquette", "cover", "front")):
        return 0, name
    if name in {"folder.jpg", "folder.jpeg"}:
        return 1, name
    if not name.startswith("albumart"):
        return 2, name
    if "large" in name:
        return 3, name
    return 4, name


def copy_jpeg_files_from_audio_folders(
    cfg: AppConfig, audio_files: list[Path]
) -> int:
    """Copy only the most relevant visible JPEG artwork for each audio folder."""
    # if AUDIO_COMPRESSOR_COPY_JPEG_FILES is False, do not copy any JPEG files
    if not cfg.AUDIO_COMPRESSOR_COPY_JPEG_FILES:
        return 0

    # for each audio folder
    copied_files = 0
    audio_folders = {audio_file.parent for audio_file in audio_files}
    for audio_folder in sorted(audio_folders, key=lambda path: str(path).lower()):
        jpeg_paths = [
            path for path in audio_folder.iterdir()
            if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg"}
        ]
        if not jpeg_paths:
            continue

        # Select the JPEG file with the highest priority (lowest value)
        jpeg_path = min(jpeg_paths, key=artwork_priority)

        # Copy the selected JPEG file to the corresponding output folder
        output_folder = build_output_subdir_from_input(
            jpeg_path, cfg.INPUT_DIR, cfg.OUTPUT_DIR
        )
        output_path = output_folder / jpeg_path.name

        # Create the output folder if it doesn't exist
        if output_path.exists():
            print(f"JPEG déjà copié : {jpeg_path.name}")
            continue
        shutil.copy2(jpeg_path, output_path)
        copied_files += 1
        print(f"JPEG copié intact : {jpeg_path.name}")
    return copied_files


@measure_time
def audio_compressor(cfg: AppConfig) -> bool:
    """Compress every supported audio file from input into MP3 output files.

    The input directory hierarchy is recreated under ``data/output``. Source
    files are only read and are never overwritten. Existing output files are
    left untouched so a previously completed batch remains safe to rerun.
    """
    # Check that the configured MP3 bitrate is positive
    bitrate_kbps = cfg.AUDIO_COMPRESSOR_MP3_BITRATE_KBPS
    if bitrate_kbps <= 0:
        raise ValueError("AUDIO_COMPRESSOR_MP3_BITRATE_KBPS doit être positif.")

    # Find all audio files in the input directory
    audio_files = find_audio_files(cfg.INPUT_DIR, cfg.INPUT_ACCEPTED_AUDIO_FILES)
    if not audio_files:
        return True

    # Copy JPEG files from audio folders to the output directory
    copied_jpeg_files = copy_jpeg_files_from_audio_folders(cfg, audio_files)

    # Initialize counters for processed files and byte sizes
    compressed_files = 0
    already_processed = 0
    failed_files = 0
    copied_mp3_files = 0
    bytes_before = 0
    bytes_after = 0
    relative_stems = [
        input_path.relative_to(cfg.INPUT_DIR).with_suffix("").as_posix()
        for input_path in audio_files
    ]
    duplicate_stems = {
        stem for stem, count in Counter(relative_stems).items() if count > 1
    }

    # Process each audio file
    for input_path in audio_files:

        # Determine the input bitrate and output subdirectory
        input_bitrate_kbps = probe_audio_bitrate_kbps(input_path)

        # Determine the output subdirectory based on the input path
        output_subdir = build_output_subdir_from_input(
            input_path, cfg.INPUT_DIR, cfg.OUTPUT_DIR
        )

        # if the input file is an MP3 and its bitrate is less than or equal 
        # to the configured bitrate, copy it without re-encoding
        if (
            input_path.suffix.lower() == ".mp3"
            and input_bitrate_kbps is not None
            and input_bitrate_kbps <= bitrate_kbps
        ):
            intact_output_path = output_subdir / input_path.name
            if intact_output_path.exists():
                already_processed += 1
                print(f"MP3 déjà copié : {input_path.name}")
            else:
                intact_output_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(input_path, intact_output_path)
                copied_mp3_files += 1
                print(
                    f"Copié intact (débit source "
                    f"{input_bitrate_kbps:.0f} kb/s inférieur ou égal au réglage MP3 "
                    f"{bitrate_kbps} kb/s) : "
                    f"{input_path.name}"
                )
            continue

        # Determine the output file name, adding a suffix if there are duplicates
        relative_stem = input_path.relative_to(cfg.INPUT_DIR).with_suffix("").as_posix()
        
        # If there are duplicate stems, append the original file extension to the output name
        if relative_stem in duplicate_stems:
            output_name = f"{input_path.stem}_{input_path.suffix[1:].lower()}.mp3"
        else:
            output_name = f"{input_path.stem}.mp3"
        output_path = output_subdir / output_name

        # If the output file already exists, skip processing and count it as already processed
        if output_path.exists():
            already_processed += 1
            print(f"MP3 déjà traité : {input_path.name}")
            continue

        # try to compress the audio file to MP3, handling any errors that may occur
        print(
            f"\033[92mCompression MP3 {bitrate_kbps} kb/s : "
            f"{input_path.name}\033[0m"
        )
        try:
            processing_comment = build_audio_processing_comment(
                input_path, bitrate_kbps
            )
            compress_audio_to_mp3(
                input_path=input_path,
                output_path=output_path,
                bitrate_kbps=bitrate_kbps,
                processing_comment=processing_comment,
            )
        except (FileNotFoundError, subprocess.CalledProcessError, OSError) as exc:
            output_path.unlink(missing_ok=True)
            failed_files += 1
            print(f"Audio ignoré : {input_path.name} ({exc})")
            continue

        # Update counters and byte sizes after successful compression
        compressed_files += 1
        bytes_before += input_path.stat().st_size
        bytes_after += output_path.stat().st_size

    # Print a summary of the audio compression results
    print(
        "\nRésumé Audio_compressor : "
        f"{compressed_files} fichier(s) compressé(s), "
        f"{copied_mp3_files} MP3 copié(s) intact(s), "
        f"{copied_jpeg_files} JPEG copié(s) intact(s), "
        f"{already_processed} déjà traité(s), "
        f"{failed_files} ignoré(s) après erreur."
    )
    if compressed_files:
        gain = bytes_before - bytes_after
        percentage = (gain / bytes_before * 100) if bytes_before else 0
        print(
            f"Taille : {format_bytes(bytes_before)} → {format_bytes(bytes_after)} "
            f"(gain : {format_bytes(gain)}, {percentage:.1f} %)."
        )

    return False

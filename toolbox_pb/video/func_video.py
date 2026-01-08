"""
Ce fichier contient des fonctions pour les actions sur les vidéos

Auteurs :
Pierrick BERTHE
mail : pierrick.berthe@gmx.fr
Décembre 2025
"""
# Imports standard
from moviepy import VideoFileClip, concatenate_videoclips
from pathlib import Path
import json
import subprocess
import os
import csv
from typing import Iterable

# Import custom librairies
from func_global import measure_time


def count_cpu_threads() -> int:
    """
    Returns the number of CPU threads available on the machine.
    """
    max_threads = os.cpu_count()
    print(f"Nombre de threads disponibles : {max_threads}\n")
    return max_threads


@measure_time
def encode_full_video(input_path, output_path, codec_video, codec_audio):
    """
    Full video encoding with specified video and audio codecs.
    """
    #  Find max threads available
    max_threads = count_cpu_threads()
    
    # Load video and write with new codecs
    clip = VideoFileClip(str(input_path))
    clip.write_videofile(
        str(output_path),
        codec= codec_video,
        audio_codec = codec_audio,
        threads=max_threads,
        logger="bar"
    )
    clip.close()


def format_duration_hms(duration_sec) -> str:
    """
    Convert duration in seconds to HH:MM:SS format.
    """
    try:
        total_seconds = int(float(duration_sec))
    except (TypeError, ValueError):
        return "N/A"

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def get_all_metadata(video_path: Path) -> dict:
    """
    Keep all metadata from FFprobe as a dict.
    """
    # Check if file exists
    if not video_path.exists():
        raise FileNotFoundError(f"Fichier vidéo introuvable : {video_path}")

    # Build FFprobe command
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(video_path)
    ]

    # Execute FFprobe and parse JSON output
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
            errors="replace"
        )

    # Handle errors
    except FileNotFoundError as exc:
        raise RuntimeError(
            "FFprobe introuvable. Installe FFmpeg et "
            "ajoute-le au PATH : https://ffmpeg.org/download.html"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"Erreur ffprobe sur {video_path}\n"
            f"stout: {exc.stdout}\n"
            f"stderr: {exc.stderr}"
        ) from exc

    # Check output
    if not proc.stdout:
        raise RuntimeError(f"ffprobe failed for {video_path}\n{proc.stderr}")

    # Return parsed metadata
    return json.loads(proc.stdout)


def print_metadata_summary_all_keys(meta: dict):
    """
    Print ALL metadata keys and values from ffprobe output,
    clearly separated by format / streams / stream type.
    """

    def print_recursive(obj, indent=0):
        """Recursively print dicts and lists with indentation."""
        space = "  " * indent

        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    print(f"{space}[{k}]")
                    print_recursive(v, indent + 1)
                else:
                    print(f"{space}- {k}: {v}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                print(f"{space}[index_{i}]")
                print_recursive(item, indent + 1)
        else:
            print(f"{space}{obj}")

    # ================= HEADER =================

    print("\n======= MÉTADONNÉES COMPLÈTES =======")

    # ================= FORMAT =================

    print("\n[format]")
    format_block = meta.get("format", meta)  # fallback safety
    print_recursive(format_block, indent=1)

    # ================= STREAMS =================

    streams = meta.get("streams", [])

    for idx, stream in enumerate(streams):
        stream_type = stream.get("codec_type", "unknown")
        print(f"\n[stream_{idx}] ({stream_type})")
        print_recursive(stream, indent=1)


def print_metadata_diff_summary(meta_before: dict, meta_after: dict):
    """
    Print a concise summary of key differences between two video metadata dicts.
    Adds units and thousand separators for better readability.
    """
    # Helper functions
    def safe_get(d, keys, default=None):
        for key in keys:
            d = d.get(key, {})
        return d if d else default

    # Format values with units and separators
    def format_value(key, val):
        """Format numbers with separators and units when applicable."""
        try:
            val_num = float(val)
        except (TypeError, ValueError):
            return val
        if key == "bit_rate":
            return f"{int(val_num):,} bps"
        elif key == "sample_rate":
            return f"{int(val_num):,} Hz"
        elif key in ["width", "height", "nb_frames"]:
            return f"{int(val_num):,}"
        elif key == "duration":
            return f"{val_num:.1f} s"
        elif key == "size":
            return f"{int(val_num):,} octets"
        else:
            return val
    
    # Helper to split streams by type
    def split_streams_by_type(streams: list[dict]) -> dict:
        """
        Separate streams into video and audio lists.
        """
        out = {"video": [], "audio": [], "other": []}
        for s in streams:
            t = s.get("codec_type")
            if t in out:
                out[t].append(s)
            else:
                out["other"].append(s)
        return out

    # header
    print("======= DIFFÉRENCES MÉTADONNÉES =======")

    # Print format-level differences
    print("[format]")
    format_keys = ["filename", "duration", "size", "bit_rate"]
    
    # Print duration every time
    print(
        f" ■  - duration: "
        f"{format_duration_hms(meta_before['format'].get('duration'))} → "
        f"{format_duration_hms(meta_after['format'].get('duration'))}"
    )

    
    for k in format_keys:
        before = meta_before.get(k)
        after = meta_after.get(k)
        if before != after:
            print(
                f"  - {k}: {format_value(k, before)} → {format_value(k, after)}"
            )

    # Print tag differences
    tags_before = safe_get(meta_before, ["tags"], {})
    tags_after = safe_get(meta_after, ["tags"], {})
    if tags_before != tags_after:
        print("  [tags]")
        for tag, val_before in tags_before.items():
            val_after = tags_after.get(tag)
            if val_before != val_after:
                print(f"    - {tag}: {val_before} → {val_after}")

    # Print stream-level differences
    print("[streams]")

    # Split streams by type
    before_by_type = split_streams_by_type(meta_before.get("streams", []))
    after_by_type = split_streams_by_type(meta_after.get("streams", []))

    # Loop over video and audio streams
    for stream_type in ["video", "audio"]:
        before_list = before_by_type[stream_type]
        after_list = after_by_type[stream_type]

        # Check if number of streams differ
        for idx, (b, a) in enumerate(zip(before_list, after_list)):
            print(f"  [{stream_type}]")

            # Codec
            print(
                f" ■  - codec_name: {b.get('codec_name')}"
                f"→ {a.get('codec_name')}"
            )

            # Video-specific info
            if stream_type == "video":
                dim_before = f"{b.get('width')}x{b.get('height')}"
                dim_after = f"{a.get('width')}x{a.get('height')}"
                print(f" ■  - dimensions: {dim_before} → {dim_after}")

            # Common numeric fields
            for key in ["bit_rate", "duration", "sample_rate", "nb_frames"]:
                vb = b.get(key)
                va = a.get(key)
                if vb != va:
                    print(
                        f"    - {key}: {format_value(key, vb)} → "
                        f"{format_value(key, va)}"
                    )


def compute_size_reduction(meta_before: dict, meta_after: dict) -> dict:
    """
    Computes file size reduction and compression factor from FFprobe metadata.
    """
    # Retrieve sizes from metadata
    size_before = meta_before.get("format", {}).get("size")
    size_after = meta_after.get("format", {}).get("size")

    # Convert strings to integers safely
    try:
        size_before = int(size_before)
        size_after = int(size_after)
    except (TypeError, ValueError):
        return {
            "size_before": None,
            "size_after": None,
            "reduction_percent": None,
            "compression_factor": None
        }

    # Avoid division by zero
    if size_before == 0:
        return {
            "size_before": size_before,
            "size_after": size_after,
            "reduction_percent": None,
            "compression_factor": None
        }

    # Calculate reduction and compression factor
    reduction_percent = 100 * (1 - size_after / size_before)
    compression_factor = size_before / size_after if size_after > 0 else None

    return {
        "size_before": size_before,
        "size_after": size_after,
        "reduction_percent": reduction_percent,
        "compression_factor": compression_factor
    }

def format_bytes(size_bytes: int) -> str:
    """ 
    Format bytes into human-readable string with units.
    """
    if size_bytes >= 1_000_000_000:
        return f"{size_bytes / 1_000_000_000:.2f} Go"
    if size_bytes >= 1_000_000:
        return f"{size_bytes / 1_000_000:.2f} Mo"
    if size_bytes >= 1_000:
        return f"{size_bytes / 1_000:.2f} Ko"
    return f"{size_bytes} octets"


def print_size_reduction(stats: dict):
    """
    Pretty display of size reduction and compression ratio with units in 
    MB or GB.
    """
    # Extract stats
    before = stats.get("size_before")
    after = stats.get("size_after")
    red = stats.get("reduction_percent")
    factor = stats.get("compression_factor")

    # Header
    print("\n======= RÉDUCTION DE TAILLE =======")

    # Check if sizes are available
    if before is None or after is None:
        print("Impossible de calculer : tailles non disponibles.")
        return

    # Print sizes
    print(f"Avant  : {format_bytes(before)}")
    print(f"Après  : {format_bytes(after)}")

    # Print reduction and factor if available
    if red is not None:
        print(f"Réduction : {red:.2f} %")
    if factor is not None:
        print(f"Facteur de compression : x{factor:.2f}")
    
    # Print delimiter
    print("\n"* 5)
    print("=" * 100 + "\n")
    print("=" * 100)
    print("\n"* 3)


# def parse_time(value, field, line_num) -> float | None:
#     if value is None or value.strip() == "":
#         return None
#     try:
#         t = float(value)
#     except ValueError:
#         raise ValueError(
#             f"Invalid {field} value at line {line_num}: {value}"
#         )
#     if t < 0:
#         raise ValueError(
#             f"{field} must be >= 0 at line {line_num}"
#         )
#     return t


def to_seconds(time_str: str) -> float:
    """Convertit HH:MM:SS en secondes."""
    h, m, s = map(float, time_str.split(":"))
    return h * 3600 + m * 60 + s


def load_segments_csv(csv_path: Path) -> list[dict[str, float | str | None]]:
    """
    Load and validate a segments.csv file.
    Preserves row order and allows duplicate filenames.
    """

    # Check if file exists
    if not csv_path.exists():
        raise FileNotFoundError(f"segments.csv not found: {csv_path}")

    segments: list[dict] = []

    # Read CSV file
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        # Validate required columns
        required_fields = {"filename", "start", "end"}
        if not required_fields.issubset(reader.fieldnames):
            raise ValueError(
                f"segments.csv must contain columns: {required_fields}"
            )

        # Process each row
        for line_num, row in enumerate(reader, start=2):
            filename = row["filename"].strip()

            # Validate filename
            if not filename:
                raise ValueError(f"Empty filename at line {line_num}")

            # Parse start and end times
            start = to_seconds(row["start"]) if row["start"].strip() else None
            end = to_seconds(row["end"]) if row["end"].strip() else None

            # Validate start/end logic
            if start is not None and end is not None and end <= start:
                raise ValueError(
                    f"end must be > start at line {line_num}"
                )

            # Append segment
            segments.append({
                "filename": filename,
                "start": start,
                "end": end,
            })

    return segments


def resolve_video_sequence(
    input_dir: Path,
    accepted_ext: list[str],
    segments: list[dict] | None
) -> list[dict]:
    """
    Returns an ordered list of videos to process.
    Each item contains: path, start, end.
    """

    # Case 1: segments.csv exists
    if segments:
        sequence = []

        for row in segments:
            video_path = input_dir / row["filename"]

            if not video_path.exists():
                raise FileNotFoundError(
                    f"{row['filename']} not found in input_dir"
                    )

            sequence.append({
                "path": video_path,
                "start": row.get("start", 0),
                "end": row.get("end")
            })

        return sequence

    # Case 2: no segments.csv → all videos
    sequence = []
    for video_path in sorted(input_dir.iterdir()):
        if video_path.suffix.lower() in accepted_ext:
            sequence.append({
                "path": video_path,
                "start": None,
                "end": None
            })

    if not sequence:
        raise RuntimeError("No video files found to assemble.")

    return sequence


def load_and_trim_clip(video_path: Path, start: float | None, end: float | None) -> VideoFileClip:
    """
    Load a clip and optionally trim it.
    """
    clip = VideoFileClip(str(video_path))

    # No trimming needed
    if start is None and end is None:
        return clip

    # Validate and apply trimming
    start = float(start or 0)
    duration = clip.duration
    end = float(end) if end is not None else duration

    # Validate boundaries
    if start < 0 or end <= start or end > duration:
        clip.close()
        raise ValueError(
            f"Invalid segment [{start}, {end}] for {video_path.name}"
            f"(duration={duration})"
        )

    return clip.subclipped(start, end)


def normalize_audio(clips: list[VideoFileClip]) -> list[VideoFileClip]:
    """
    Ensure all clips have a valid audio track or none.
    """
    clean_clips = []

    # Remove audio from clips if not present
    for clip in clips:
        if clip.audio is None or clip.audio.reader is None:
            clip = clip.without_audio()
        clean_clips.append(clip)

    return clean_clips


def get_inputs_metadata(
    sequence: Iterable[dict],
    get_metadata_fn
) -> list[dict]:
    """
    Retrieve FFprobe metadata for each input video in a sequence.
    """
    metas = []

    # Loop over sequence items
    for idx, item in enumerate(sequence):
        path = item.get("path")

        # Validate path
        if path is None:
            raise ValueError(
                f"Sequence item at index {idx} has no 'path'."
            )

        # Validate path type
        if not isinstance(path, Path):
            raise TypeError(
                f"'path' must be a pathlib.Path, got {type(path)}."
            )

        # Get metadata
        metas.append(get_metadata_fn(path))

    return metas


def sum_input_sizes(metas_before: list[dict]) -> int | None:
    """
    Sum file sizes from a list of FFprobe metadata dicts.
    Prints detailed size per input.
    Returns total size in bytes or None if invalid.
    """
    print("\n======= INPUT FILE SIZES =======\n")

    total = 0

    # Loop over metadata dicts
    for idx, meta in enumerate(metas_before, start=1):
        size = meta.get("format", {}).get("size")
        filepath = meta.get("format", {}).get("filename", f"input_{idx}")
        filename = filepath.split("\\")[-1].split("/")[-1]


    # Convert size to int safely and print
        try:
            size = int(size)
        except (TypeError, ValueError):
            print(f"- {filename}: size unavailable")
            return None
        print(f"- {filename}: {format_bytes(size)}")
        total += size

    print(f"\nTOTAL INPUT SIZE: {format_bytes(total)}")
    return total


def compute_size_reduction_from_inputs(
    metas_before: list[dict],
    meta_after: dict
) -> dict:
    """
    Compute size reduction between multiple input videos and one output video.
    """
    # Sum input sizes (with detailed print)
    size_before = sum_input_sizes(metas_before)

    size_after = meta_after.get("format", {}).get("size")
    try:
        size_after = int(size_after)
    except (TypeError, ValueError):
        size_after = None

    # Avoid division by zero
    if size_before is None or size_after is None or size_before == 0:
        return {
            "size_before": size_before,
            "size_after": size_after,
            "reduction_percent": None,
            "compression_factor": None
        }

    # Calculate reduction and compression factor
    reduction_percent = 100 * (1 - size_after / size_before)
    compression_factor = size_before / size_after if size_after > 0 else None

    return {
        "size_before": size_before,
        "size_after": size_after,
        "reduction_percent": reduction_percent,
        "compression_factor": compression_factor
    }

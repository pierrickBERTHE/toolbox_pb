"""
Ce fichier contient des fonctions pour les actions sur les vidéos

Auteurs :
Pierrick BERTHE
mail : pierrick.berthe@gmx.fr
Décembre 2025
"""
# Imports standard
from moviepy import VideoFileClip
from pathlib import Path
import json
import subprocess
import os

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
            f"Error lors de l'exécution de ffprobe sur le fichier {video_path}"
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

    # Function to format bytes into human-readable form
    def format_bytes(size_bytes):
        if size_bytes >= 1_000_000_000:
            return f"{size_bytes / 1_000_000_000:.2f} Go"
        elif size_bytes >= 1_000_000:
            return f"{size_bytes / 1_000_000:.2f} Mo"
        elif size_bytes >= 1_000:
            return f"{size_bytes / 1_000:.2f} Ko"
        else:
            return f"{size_bytes} octets"

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

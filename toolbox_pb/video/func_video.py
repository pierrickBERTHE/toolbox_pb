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
from PIL import Image, ImageOps
import json
import subprocess
import os
import csv
import tempfile
import re
from datetime import date
from typing import Iterable
from dataclasses import dataclass
from tqdm import tqdm

# Import custom librairies
from func_global import (
    measure_time,
    format_bytes,
    consume_ffmpeg_progress,
    convert_hhmmss_to_seconds
)


@dataclass
class AudioBoost:
    start: float
    end: float
    gain_db: float


AAC_SUPPORTED_SAMPLE_RATES = (
    96000,
    88200,
    64000,
    48000,
    44100,
    32000,
    24000,
    22050,
    16000,
    12000,
    11025,
    8000,
    7350,
)


def normalize_audio_sample_rate(sample_rate: str | int, codec_audio: str) -> int | None:
    """
    Return a sample rate accepted by the requested audio encoder.
    """
    try:
        rate = int(sample_rate)
    except (TypeError, ValueError):
        return None

    if codec_audio.lower() != "aac" or rate in AAC_SUPPORTED_SAMPLE_RATES:
        return rate

    return min(AAC_SUPPORTED_SAMPLE_RATES, key=lambda supported: abs(supported - rate))


def find_files_by_extensions(input_dir: Path, extensions: list[str]) -> list[Path]:
    """
    Return input files matching extensions, in deterministic path order.
    """
    accepted_extensions = {extension.lower() for extension in extensions}
    return sorted(
        (
            path for path in input_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in accepted_extensions
        ),
        key=lambda path: str(path.relative_to(input_dir)).lower(),
    )


def get_image_size(image_path: Path) -> tuple[int, int]:
    """
    Return visual dimensions after applying any EXIF orientation metadata.
    """
    with Image.open(image_path) as image:
        return ImageOps.exif_transpose(image).size


def fit_image_size_in_frame(
    image_size: tuple[int, int], frame_size: tuple[int, int]
) -> tuple[int, int]:
    """
    Return an even size that fills the full frame height.
    The returned size preserves the input ratio. Every image occupies the
    entire frame height, so no top or bottom padding is ever introduced.
    """
    # Validate input sizes
    image_width, image_height = image_size
    _, frame_height = frame_size
    if image_width <= 0 or image_height <= 0:
        raise ValueError("Les dimensions de l'image doivent être positives.")

    # Calculate the scaled width to maintain aspect ratio
    scaled_height = frame_height
    scaled_width = max(2, round(image_width * frame_height / image_height))
    scaled_width -= scaled_width % 2
    return scaled_width, scaled_height


def format_srt_timestamp(milliseconds: int) -> str:
    """
    Format a non-negative millisecond offset as an SRT timestamp.
    """
    milliseconds = max(0, milliseconds)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def build_image_subtitle(image_path: Path, input_dir: Path) -> str:
    """
    Build a subtitle from a filename, retaining only its first valid year.
    All other digits (such as month, day, or photo sequence numbers) are
    removed. The filename extension is never included.
    """
    # Validate input paths
    image_name = image_path.relative_to(input_dir).with_suffix("").as_posix()
    valid_year = None

    # Search for the first valid 4-digit year in the filename
    for match in re.finditer(r"(?<!\d)(\d{4})(?!\d)", image_name):
        try:
            date(int(match.group(1)), 1, 1)
        except ValueError:
            continue
        valid_year = match.group(1)
        break

    # Remove all digits and clean up the text
    text = re.sub(r"\d+", "", image_name)
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"[-_\s]{2,}", " ", text).strip(" -_")
    return f"{valid_year} {text}".strip() if valid_year else text


def write_image_diapo_srt(
    image_paths: list[Path],
    input_dir: Path,
    duration: float,
    output_path: Path,
) -> None:
    """
    Write one SRT cue per slideshow image with its display time range.
    """
    entries = []

    # Loop over images and create SRT entries
    for index, image_path in enumerate(image_paths, start=1):

        # Calculate start and end times in milliseconds
        start_ms = round((index - 1) * duration * 1_000)
        end_ms = round(index * duration * 1_000)
        
        # Build the subtitle text from the image filename
        image_name = build_image_subtitle(image_path, input_dir)
        entries.append(
            f"{index}\n"
            f"{format_srt_timestamp(start_ms)} --> {format_srt_timestamp(end_ms)}\n"
            f"{image_name}\n"
        )
    output_path.write_text("\n".join(entries), encoding="utf-8")


def create_image_diapo_ffmpeg(
    image_paths: list[Path],
    input_dir: Path,
    audio_path: Path | None,
    output_path: Path,
    duration: float,
    fps: int,
    frame_size: tuple[int, int],
    codec_video: str,
    codec_audio: str,
) -> None:
    """
    Create a slideshow through one temporary video segment per image.
    Encoding one source image at a time avoids loading all high-resolution
    photos into FFmpeg's filter graph at once. Segments are then remuxed into
    the final video, optionally with the supplied audio track.
    """
    # Validate input parameters
    width, height = frame_size
    total_duration = duration * len(image_paths)
    
    # use tqdm to show a progress bar for the slideshow creation
    with tqdm(
        total=len(image_paths),
        unit="étape",
        desc="Progression globale",
        position=1,
        leave=True,
        bar_format="{l_bar}{bar}| {n:.0f}/{total:.0f} [{elapsed}<{remaining}]",
    ) as global_progress, tempfile.TemporaryDirectory(
        prefix="image_diapo_"
    ) as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        segment_paths = []

        # Loop over each image and create a temporary video segment
        for index, image_path in enumerate(image_paths):

            # Calculate the scaled size for the image to fit in the frame
            scaled_width, scaled_height = fit_image_size_in_frame(
                get_image_size(image_path), frame_size
            )
            segment_path = temp_dir / f"segment_{index:05d}.mp4"

            # Build the FFmpeg command to create a video segment from the image
            command = [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-loop", "1", "-framerate", str(fps), "-t", str(duration),
                "-i", str(image_path),
                "-vf", (
                    f"scale={scaled_width}:{scaled_height},"
                    f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
                    f"setsar=1,fps={fps}"
                ),
                "-an", "-c:v", codec_video, "-pix_fmt", "yuv420p",
                "-r", str(fps), "-threads", "1", "-progress", "pipe:1",
                str(segment_path),
            ]

            # Run FFmpeg command with progress bar for each image segment
            _run_ffmpeg_with_progress(
                command,
                duration,
                f"Création du diaporama ({index + 1}/{len(image_paths)})",
            )
            segment_paths.append(segment_path)
            global_progress.update(1)

        # Create a temporary text file listing all segment paths for FFmpeg concatenation
        concat_file = temp_dir / "segments.txt"
        concat_file.write_text(
            "".join(
                f"file '{path.as_posix().replace("'", "'\\''")}'\n"
                for path in segment_paths
            ),
            encoding="utf-8",
        )

        # Create a temporary SRT file for subtitles
        subtitles_path = temp_dir / "subtitles.srt"
        write_image_diapo_srt(image_paths, input_dir, duration, subtitles_path)
        command = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(concat_file),
        ]

        # Add audio input if provided
        if audio_path is not None:
            command.extend(["-i", str(audio_path)])
        
        # Add subtitles input and map streams for final output
        command.extend(["-i", str(subtitles_path), "-map", "0:v:0"])
        
        # Map audio if provided, else skip audio mapping
        if audio_path is not None:
            command.extend(["-map", "1:a:0?", "-c:a", codec_audio])

        # Determine the index of the subtitle input based on whether audio is present
        subtitle_input_index = 2 if audio_path is not None else 1
        
        # Add subtitles mapping and encoding for final output
        command.extend([
            "-map", f"{subtitle_input_index}:s:0",
            "-c:s", "mov_text",
        ])
        command.extend([
            "-c:v", "copy", "-t", str(total_duration), str(output_path),
        ])

        # Run FFmpeg command to concatenate segments and add audio/subtitles
        _run_ffmpeg_silently(command)


def _run_ffmpeg_with_progress(
    command: list[str],
    duration: float,
    desc: str,
) -> None:
    """
    Run FFmpeg silently while forwarding only progress to tqdm.
    """
    # Run FFmpeg command with subprocess and capture output for progress
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    # Use the consume_ffmpeg_progress function to parse FFmpeg output and update the progress bar
    errors = consume_ffmpeg_progress(
        proc,
        duration=duration,
        desc=desc,
        position=0,
        leave=False,
    )

    # Wait for FFmpeg to finish and check for errors
    return_code = proc.wait()

    # If FFmpeg returned a non-zero exit code, raise an exception with errors
    if return_code != 0:
        raise subprocess.CalledProcessError(
            return_code, command, output="\n".join(errors)
        )


def _run_ffmpeg_silently(command: list[str]) -> None:
    """
    Run a short FFmpeg remux step without adding a progress bar.
    """
    # Run FFmpeg command with subprocess and capture output
    result = subprocess.run(command, capture_output=True, text=True, check=False)

    # If FFmpeg returned a non-zero exit code, raise an exception with stderr or stdout
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, command, output=result.stderr or result.stdout
        )


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
    Preserves the image aspect ratio and video properties.
    """
    # Find max threads available
    max_threads = count_cpu_threads()
    
    # Get metadata to preserve SAR and other properties
    meta = get_all_metadata(input_path)
    video_stream = next(
        (s for s in meta.get("streams", []) if s.get("codec_type") == "video"),
        None
    )
    
    # Get video duration for progress bar
    duration = float(meta.get("format", {}).get("duration", 0))
    
    # Build FFmpeg command
    cmd = [
        "ffmpeg",
        "-i", str(input_path),
        "-c:v", codec_video,
        "-c:a", codec_audio,
        "-threads", str(max_threads),
        "-progress", "pipe:1",
        "-hide_banner",
        "-loglevel", "error",
    ]
    
    # Preserve aspect ratio with video filter
    video_filters = []
    if video_stream:
        sar = video_stream.get("sample_aspect_ratio")
        width = video_stream.get("width")
        height = video_stream.get("height")
        
        # Use scale filter to preserve aspect ratio
        if sar and sar != "1:1" and width and height:
            video_filters.append(
                f"scale={width}:{height}:force_original_aspect_ratio=1:"
                "force_divisible_by=2"
            )
    
    # Add video filters if any
    if video_filters:
        cmd.extend(["-vf", ",".join(video_filters)])
    
    # Preserve color range for tv content
    if video_stream:
        color_range = video_stream.get("color_range", "").lower()
        if color_range == "tv":
            cmd.extend(["-color_range", "tv"])
    
    # Preserve audio sample rate
    audio_stream = next(
        (s for s in meta.get("streams", []) if s.get("codec_type") == "audio"),
        None
    )
    if audio_stream:
        sample_rate = audio_stream.get("sample_rate")
        if sample_rate:
            normalized_sample_rate = normalize_audio_sample_rate(
                sample_rate, codec_audio
            )
            if normalized_sample_rate:
                if str(normalized_sample_rate) != str(sample_rate):
                    print(
                        "Taux audio ajusté pour l'encodeur "
                        f"{codec_audio}: {sample_rate} Hz -> "
                        f"{normalized_sample_rate} Hz"
                    )
                cmd.extend(["-ar", str(normalized_sample_rate)])
    
    # Output file
    cmd.extend(["-y", str(output_path)])
    
    # Execute FFmpeg with progress bar
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        
        # Parse progress from FFmpeg output with a shared progress helper
        filename = Path(input_path).name
        error_lines = consume_ffmpeg_progress(proc, duration=duration, desc=filename)

        # Wait enf of FFmpeg
        proc.wait()
        
        # Handle errors
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(
                proc.returncode,
                cmd,
                output="\n".join(error_lines),
            )
        
        print(f"✅ Encodage réussi : {output_path}\n")
    
    # Handle errors
    except subprocess.CalledProcessError as exc:
        print(f"❌ Erreur lors de l'encodage : {output_path}")
        raise


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


def safe_get(d, keys, default=None):
        for key in keys:
            d = d.get(key, {})
        return d if d else default


def format_value(key, val):
    """
    Format numbers with separators and units when applicable.
    """
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


def print_metadata_diff_summary(meta_before: dict, meta_after: dict):
    """
    Print a concise summary of key differences between two video metadata dicts.
    Adds units and thousand separators for better readability.
    """
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


@measure_time
def write_video_file(
    final_clip: VideoFileClip,
    output_path: Path,
    codec_video: str,
    codec_audio: str,
    fps: int | None = None,
):
    """
    Write the final video file with specified codecs.
    """
    # Find max threads available
    max_threads = count_cpu_threads()

    # Write the final video file
    write_options = {
        "codec": codec_video,
        "audio_codec": codec_audio,
        "threads": max_threads,
        "logger": "bar",
    }
    if fps is not None:
        write_options["fps"] = fps

    final_clip.write_videofile(
        str(output_path),
        **write_options,
    )


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


def shift_audio_no_reencode(input_video: str, output_video: str, delay: float):
    """
    Shift audio without re-encoding using FFmpeg.
    delay > 0 : audio is delayed (starts later)
    delay < 0 : audio is advanced (starts earlier)
    delay == 0 : no change in audio timing
    """
    # Build FFmpeg command based on delay direction
    if delay > 0:
        cmd = [
            "ffmpeg", "-loglevel", "error", "-y",
            "-i", input_video,
            "-itsoffset", str(delay),
            "-i", input_video,
            "-map", "0:v",
            "-map", "1:a",
            "-c", "copy",
            output_video
        ]
    elif delay < 0:
        cmd = [
            "ffmpeg", "-loglevel", "error", "-y",
            "-i", input_video,
            "-ss", str(abs(delay)),
            "-i", input_video,
            "-map", "0:v",
            "-map", "1:a",
            "-c", "copy",
            output_video
        ]
    else:
        cmd = [
            "ffmpeg", "-loglevel", "error", "-y",
            "-i", input_video,
            "-c", "copy",
            output_video
        ]

    # Execute FFmpeg command
    subprocess.run(cmd, check=True)


def load_boost_csv(csv_path: str) -> list[AudioBoost]:
    """
    Load audio boost segments from CSV and validate gain values.
    """
    # Define max gain in dB for safety
    MAX_GAIN_DB = 20

    # Load boosts from CSV and validate gain values
    boosts = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            gain_db = float(row["gain_db"])
            if abs(gain_db) > MAX_GAIN_DB:
                raise ValueError(
                    f"gain_db={gain_db} dépasse la limite de ±{MAX_GAIN_DB} dB"
                )
            boosts.append(AudioBoost(
                start=convert_hhmmss_to_seconds(row["start"]),
                end=convert_hhmmss_to_seconds(row["end"]),
                gain_db=gain_db
            ))
    return boosts


def apply_audio_boosts_ffmpeg(
    input_video: str,
    output_video: str,
    csv_path: str,
) -> None:
    """
    Modify the audio of a video by applying gain boosts to specified segments
    using FFmpeg. The CSV file should have columns: start, end, gain_db.
    gain_db shoudl be between -20 and +20 for safety.
    """
    # Load and validate boosts from CSV
    boosts = load_boost_csv(csv_path)

    # Construct FFmpeg filter complex with volume adjustments for each segment
    filters = []
    for boost in boosts:
        gain_linear = round(10 ** (boost.gain_db / 20), 4)
        filters.append(
            f"volume=enable='between(t,{boost.start},{boost.end})'"
            f":volume={gain_linear}"
        )
        print(
            f"\nApplying audio boost: {boost.start}s to {boost.end}s "
            f"with gain {boost.gain_db} dB"
        )

    # Assemble the filter chain
    audio_filter = ",".join(filters)
    
    # Build FFmpeg command to apply audio boosts without re-encoding video
    cmd = [
        "ffmpeg", "-loglevel", "error", "-y",
        "-i", str(input_video),
        "-af", audio_filter,
        "-c:v", "copy",
        str(output_video),
    ]
    subprocess.run(cmd, check=True)


def apply_video_srt_ffmpeg(
    input_video: str,
    output_video: str,
    srt_path: str,
) -> None:
    """
    Add SRT subtitles to a video as an optional stream without re-encoding.
    Subtitles are added as mov_text codec for MP4 containers.
    """
    # Build FFmpeg command to add SRT without re-encoding
    cmd = [
        "ffmpeg",
        "-i", str(input_video),
        "-i", str(srt_path),
        "-c:v", "copy",
        "-c:a", "copy",
        "-c:s", "mov_text",
        "-map", "0",
        "-map", "1",
        "-y",
        str(output_video),
    ]
    
    # Execute FFmpeg command and handle errors with detailed output
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        
        if result.returncode != 0:
            print(f"⚠️ FFmpeg stdout:\n{result.stdout}")
            print(f"⚠️ FFmpeg stderr:\n{result.stderr}")
            raise subprocess.CalledProcessError(result.returncode, cmd)
        
        print(f"✅ Sous-titres ajoutés : {output_video}\n")
    
    # Handle errors and print FFmpeg output for debugging
    except subprocess.CalledProcessError as exc:
        print(f"❌ Erreur lors de l'ajout des SRT : {output_video}")
        raise

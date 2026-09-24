"""
Ce fichier contient des fonctions communes utilitaires pour la toolbox_pb

Auteurs :
Pierrick BERTHE
mail : pierrick.berthe@gmx.fr
Décembre 2025
"""
# Imports standard
from functools import wraps
import sys
import time
import json
import subprocess
import re
import tempfile
import numpy as np
from pathlib import Path
from collections import defaultdict
from tqdm import tqdm

# Import specialized libraries
import PIL
import moviepy
import onnxruntime
import huggingface_hub
import withoutbg
import pypdf
import reportlab

# Import custom librairies
from toolbox_pb.config_global import AppConfig


class Logger(object):
    """
    Logger class to redirect print statements to a file.
    """
    def __init__(self, log_path):
        self.terminal = sys.stdout
        self.log = open(log_path, "a", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()


def get_git_version():
    """
    Get the current git version.
    """
    try:
        # Get the current git version
        version = subprocess.check_output(
            ["git", "describe", "--tags", "--always"],
            stderr=subprocess.STDOUT
        ).decode().strip()
        return version
    except Exception:
        return "version inconnue"


def format_git_version(version_str):
    """
    Format the git version string.
    """
    # split the version string
    parts = version_str.split('-')

    # Check the number of parts
    if len(parts) == 1:
        return f"Version : {parts[0]}"
    if (
        len(parts) == 3
        and parts[1].isdigit()
        and parts[2].startswith('g')
    ):
        tag, commits, commit_hash = parts
        return (
            f"Version : {tag} ({commits} commits après le tag,"
            f" commit {commit_hash})"
        )
    else:
        return f"Version : {version_str}"


def print_system_info():
    """
    Affiche les versions de Python, des librairies principales
    et des outils externes utilisés par la toolbox.
    """

    print("\n=== ENVIRONNEMENT ===")

    print(f"Python          : {sys.version.split()[0]}")

    print("\n=== LIBRAIRIES ===")

    print(f"HuggingFace Hub : {huggingface_hub.__version__}")
    print(f"MoviePy         : {moviepy.__version__}")
    print(f"NumPy           : {np.__version__}")
    print(f"ONNX Runtime    : {onnxruntime.__version__}")
    print(f"Pillow          : {PIL.__version__}")
    print(f"Pypdf           : {pypdf.__version__}")
    print(f"ReportLab       : {reportlab.Version}")
    print(f"Withoutbg       : {withoutbg.__version__}")

    print("\n=== OUTILS EXTERNES ===")

    try:
        ffmpeg_version = subprocess.check_output(
            ["ffmpeg", "-version"],
            stderr=subprocess.STDOUT,
            text=True,
        ).splitlines()[0]

        print(f"FFmpeg          : {ffmpeg_version}")

    except FileNotFoundError:
        print("FFmpeg          : non disponible")

    except subprocess.CalledProcessError:
        print("FFmpeg          : erreur lors de la détection")

    print("========================\n")


def print_config_flags(config, flag_names: list[str]):
    """
    Print selected configuration flags.
    """
    print("\nFlags de configuration :")
    for name in flag_names:
        value = getattr(config, name, None)
        print(f"{name} = {value}")


def transform_sec_duration_in_min_sec(start, end):
    """
    This function calculates the duration between two time points in 
    minutes and seconds.
    """
    min, sec = divmod(end - start, 60)
    return int(min), int(sec)


def measure_time(func):
    """
    decorator to measure the execution time of a function.
    """
    @wraps((func))
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        duration_sec = time.perf_counter() - start
        min, sec = transform_sec_duration_in_min_sec(0, duration_sec)
        print(
            f"\n⏱️ Temps d'exécution de {func.__name__} : "
            f"{min} min et {sec} sec.")
        return result
    return wrapper


def print_step(step_num, message):
    """
    Print a formatted step message for process reporting.
    """
    print("\n\n" + "*" * 100)
    print(f"==> STEP {step_num} : {message} <==")
    print("*" * 100 + "\n")


def exit_toolbox():
    """
    Print a goodbye message and exit the toolbox.
    """
    print("\nAu revoir !")
    exit()


def print_json(obj, title=None):
    """
    Print a JSON object in a readable format.
    """
    if title:
        print(f"\n===== {title} =====")
    print(json.dumps(obj, indent=4, ensure_ascii=False))


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


def is_processable_file(path: Path) -> bool:
    """Return whether a path is a regular file other than the Git placeholder."""

    return path.is_file() and path.name != ".gitkeep"


def build_processing_comment(
    previous_comment: str | None,
    feature: str,
    video_codec: str | None = None,
    audio_codec: str | None = None,
    image_codec: str | None = None,
) -> str:
    """Build the human-readable processing history shown by Windows Explorer."""
    previous_comment = previous_comment or ""
    lines = previous_comment.splitlines()

    # keep only lines that match the expected format for processing history
    history_lines = [
        line for line in lines if re.match(r"\s*n_\d+\s*:", line)
    ]

    # Number the next processing step based on the last one found in the history
    last_number = 0
    if history_lines:
        match = re.search(r"n_(\d+)", history_lines[-1])
        if match:
            last_number = int(match.group(1))
    processing_count = last_number + 1

    # Build the new line for the current processing step
    fields = [f"n_{processing_count} : {feature}"]
    if video_codec:
        fields.append(f"V : {video_codec}")
    if audio_codec:
        fields.append(f"A : {audio_codec}")
    if image_codec:
        fields.append(f"I : {image_codec}")
    new_line = " | ".join(fields)

    return "\n".join(["toolbox_pb :", *history_lines, new_line])


def _read_video_comment(video_path: Path) -> str | None:
    """Read the standard FFmpeg comment tag from a video file."""
    command = [
        "ffprobe", "-v", "error", "-show_entries", "format_tags=comment",
        "-of", "json", str(video_path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return json.loads(result.stdout).get("format", {}).get("tags", {}).get("comment")


def write_video_processing_comment(
    video_path: Path,
    feature: str,
    video_codec: str | None = None,
    audio_codec: str | None = None,
) -> str | None:
    """Embed an incremented standard comment tag in an output video.

    FFmpeg remuxes the file without re-encoding, keeping the video and audio
    streams intact while making the comment available to media property readers.
    """
    if not video_path.exists():
        return None
    comment = build_processing_comment(
        _read_video_comment(video_path), feature, video_codec, audio_codec
    )
    with tempfile.NamedTemporaryFile(
        suffix=video_path.suffix, dir=video_path.parent, delete=False
    ) as temp_file:
        temporary_path = Path(temp_file.name)
    command = [
        "ffmpeg", "-y", "-i", str(video_path), "-map", "0", "-c", "copy",
        "-movflags", "use_metadata_tags", "-metadata", f"comment={comment}",
        str(temporary_path),
    ]
    try:
        subprocess.run(command, capture_output=True, text=True, check=True)
        temporary_path.replace(video_path)
    except (FileNotFoundError, subprocess.CalledProcessError, OSError) as exc:
        temporary_path.unlink(missing_ok=True)
        print(f"Commentaire de traitement non écrit : {video_path.name} ({exc})")
        return None
    return comment


def build_video_processing_comment(
    source_path: Path | None,
    feature: str,
    video_codec: str,
    audio_codec: str,
) -> str:
    """Build the next video comment before the output file is created."""
    previous_comment = _read_video_comment(source_path) if source_path else None
    return build_processing_comment(
        previous_comment, feature, video_codec, audio_codec
    )


def make_unique_path(path: Path) -> Path:
    """
    Return a unique file path by appending an incremental suffix (__1, __2, ...)
    if a file with the same name already exists anywhere in the target directory
    or its subdirectories.
    """
    parent = path.parent
    stem = path.stem
    suffix = path.suffix

    # Collect all existing filenames (without directory) recursively
    existing_names = {
        p.name
        for p in parent.rglob("*")
        if is_processable_file(p)
    }

    # If the filename is not used anywhere, return it directly
    if path.name not in existing_names:
        return path

    # Otherwise, append an incremental suffix until a free name is found
    index = 1
    while True:
        candidate_name = f"{stem}__{index}{suffix}"
        if candidate_name not in existing_names:
            return parent / candidate_name
        index += 1


def build_output_path(
    input_file: Path,
    output_subdir: Path,
    suffix: str,
    codec_v: str,
    add_codec: bool,
) -> Path:
    """
    Build the output video file path in a safe and deterministic way.
    """

    # Build the output filename
    if add_codec:
        name = f"{input_file.stem}_{codec_v}{suffix}"
    else:
        name = f"{input_file.stem}{suffix}"

    # Build the full output path
    path = output_subdir / name

    # Ensure the path is unique (adds __1, __2, ... if needed)
    return make_unique_path(path)


def build_output_subdir_from_input(
    input_file: Path,
    input_dir: Path,
    output_dir: Path
) -> Path:
    """
    Build and create the output subdirectory that mirrors input_dir structure.
    """
    relative_path = input_file.relative_to(input_dir)
    relative_parent = relative_path.parent
    output_subdir = output_dir / relative_parent
    output_subdir.mkdir(parents=True, exist_ok=True)
    return output_subdir


def summarize_files(dir_path: Path, label: str) -> None:
    """
    Print a summary of files in a directory.

    The summary includes:
    - total number of files
    - number of files per extension
    - total size of all files
    """

    # Check that the directory exists
    if not dir_path.exists():
        print(f"\n[{label}] Directory not found: {dir_path}")
        return

    # Recursively collect all files in the directory
    files = [p for p in dir_path.rglob("*") if is_processable_file(p)]

    # Initialize accumulators
    total_size = 0
    by_ext = defaultdict(int)

    # Iterate over files to compute size and extension stats
    for f in files:

        # Add file size in bytes
        total_size += f.stat().st_size

        # Count files by extension (use 'no_ext' if empty)
        by_ext[f.suffix.lower() or "no_ext"] += 1

    # Print summary header
    print(f"\n======= FILE SUMMARY : {label} =======")
    print(f"Directory : {dir_path}")
    print(f"Total files : {len(files)}")

    # Print breakdown by file extension
    print("\nBy extension:")
    for ext, count in sorted(by_ext.items()):
        print(f" - {ext}: {count}")

    # Print total size in human-readable format
    print(f"\nTotal size : {format_bytes(total_size)}")


def consume_ffmpeg_progress(
    proc: subprocess.Popen,
    duration: float,
    desc: str,
    unit: str = "s",
    progress_bar=None,
    position: int | None = None,
    leave: bool = True,
) -> list[str]:
    """
    Read FFmpeg `-progress pipe:1` output and update a tqdm progress bar.
    Returns collected stderr-like lines containing the word "error".
    """
    # Initialize progress bar and error collection
    error_lines: list[str] = []
    last_time = 0.0
    total = max(float(duration), 0.0)

    # Check that stdout is available
    if proc.stdout is None:
        return error_lines

    # Read lines from FFmpeg output and update progress bar
    tqdm_options = {"total": total, "unit": unit, "desc": desc}
    if position is not None:
        tqdm_options["position"] = position
        tqdm_options["bar_format"] = (
            "{l_bar}{bar}| {n:.0f}/{total:.0f} [{elapsed}<{remaining}]"
        )
    if leave is not True:
        tqdm_options["leave"] = leave

    with tqdm(**tqdm_options) as pbar:
        for line in iter(proc.stdout.readline, ""):
            if not line:
                break

            # Look for lines like "out_time_ms=12345678" to get current progress
            match = re.search(r"out_time_ms=(\d+)", line)
            if match:
                current_time = int(match.group(1)) / 1_000_000
                delta = current_time - last_time
                if delta > 0:
                    remaining = max(total - pbar.n, 0.0)
                    applied_delta = min(delta, remaining)
                    pbar.update(applied_delta)
                    if progress_bar is not None:
                        global_remaining = max(
                            float(progress_bar.total or 0) - progress_bar.n, 0.0
                        )
                        progress_bar.update(min(applied_delta, global_remaining))
                    last_time = current_time
            elif "error" in line.lower():
                error_lines.append(line.strip())

    return error_lines


def get_mobile_video_output_options(codec_video: str) -> list[str]:
    """
    Return FFmpeg options for broadly compatible mobile video output.

    Every supported encoder writes 8-bit 4:2:0 SDR BT.709. This prevents a
    mobile decoder from guessing an incompatible colour interpretation. H.265
    encoders additionally use the widely supported Main profile.
    """
    options = ["-pix_fmt", "yuv420p"]
    if codec_video.lower() in {"libx265", "hevc_amf"}:
        options.extend(["-profile:v", "main"])
    options.extend([
        "-color_range", "tv",
        "-colorspace", "bt709",
        "-color_primaries", "bt709",
        "-color_trc", "bt709",
    ])
    return options


def parse_config(cfg: AppConfig) -> dict:
    """
    Parse the AppConfig object into a dictionary of relevant
    configuration values.
    """
    return {
        "accepted_file": cfg.INPUT_ACCEPTED_VIDEO_FILES,
        "codec_v": cfg.CODEC_VIDEO,
        "codec_a": cfg.CODEC_AUDIO,
        "suffix": cfg.SUFFIX_OUTPUT_VIDEO,
        "input_dir": cfg.INPUT_DIR,
        "output_dir": cfg.OUTPUT_DIR,
        "add_codec": cfg.ADD_CODEC_NAME_IN_OUTPUT,
        "print_all_keys": cfg.PRINT_ALL_KEYS_IN_METADATA_SUMMARY,
    }


def convert_hhmmss_to_seconds(value: str) -> float:
    """
    Convert HH:MM:SS or float string into seconds.
    """
    if ":" in value:
        parts = value.strip().split(":")
        if len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + float(s)
        elif len(parts) == 2:
            m, s = parts
            return int(m) * 60 + float(s)
    return float(value)

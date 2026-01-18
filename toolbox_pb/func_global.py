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
import numpy as np
from pathlib import Path
from collections import defaultdict

# Import specialized libraries
import PIL
import moviepy


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
    Print Python and library versions.
    """
    print("\nInterpréteur python :")
    print("Python            : " + sys.version + "\n")
    print("Version des librairies utilisées :")
    print(f"MoviePy           : {moviepy.__version__}")
    print("Numpy             : " + np.__version__)
    print("Pillow            : " + PIL.__version__)
    try:
        ffmpeg_version = subprocess.check_output(
            ["ffmpeg", "-version"],
            stderr=subprocess.STDOUT
        ).decode().split('\n')[0]
        print(f"FFmpeg version    : {ffmpeg_version}")
    except Exception:
        print("FFmpeg version    : non disponible")


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
        if p.is_file()
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
    codec_a: str,
    add_codec: bool
) -> Path:
    """
    Build the output video file path in a safe and deterministic way.
    """

    # Build the output filename
    if add_codec:
        name = f"{input_file.stem}_v-{codec_v}_a-{codec_a}{suffix}"
    else:
        name = f"{input_file.stem}{suffix}"

    # Build the full output path
    path = output_subdir / name

    # Ensure the path is unique (adds __1, __2, ... if needed)
    return make_unique_path(path)


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
    files = [p for p in dir_path.rglob("*") if p.is_file()]

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

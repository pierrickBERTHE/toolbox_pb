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

# Import specialized libraries
import PIL
import moviepy


class Logger(object):
    """Logger class to redirect print statements to a file.
    """
    def __init__(self, log_path):
        self.terminal = sys.stdout
        self.log = open(log_path, "a", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()

    def flush(self):
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
    Décorateur pour mesurer le temps d'exécution d'une fonction.
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
    print("\nAu revoir !")
    exit()


def print_json(obj, title=None):
    if title:
        print(f"\n===== {title} =====")
    print(json.dumps(obj, indent=4, ensure_ascii=False))


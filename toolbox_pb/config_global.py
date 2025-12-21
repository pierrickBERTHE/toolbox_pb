"""
Fichier de configuration pour le projet toolbox_pb

Auteur :
Pierrick BERTHE
mail : pierrick.berthe@gmx.fr
Décembre 2025
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List

# -----------------------------
# CONFIGURATION TYPÉE
# -----------------------------

@dataclass(frozen=True)
class AppConfig:
    # Codecs
    INPUT_ACCEPTED_FILES: List[str]
    CODEC_VIDEO_LIST: List[str]
    CODEC_VIDEO: str
    CODEC_AUDIO: str
    SUFFIX_OUTPUT: str

    # Paths
    ROOT: Path
    LOG_DIR: Path
    INPUT_DIR: Path
    OUTPUT_DIR: Path

    # Flags
    LOG_TO_FILE: bool
    ADD_CODEC_NAME_IN_OUTPUT: bool
    PRINT_ALL_KEYS_IN_METADATA_SUMMARY: bool


# -----------------------------
# CONSTANTES DE CONFIGURATION
# -----------------------------

# paths
ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "log"
INPUT_DIR = ROOT / "data" / "input"
OUTPUT_DIR = ROOT / "data" / "output"

# Codecs
INPUT_ACCEPTED_FILES = [
    ".avi", ".mkv", ".mov", ".m4v", ".mp4", ".mts", ".webm"
]

CODEC_VIDEO_LIST = ["libx264", "libx265"]
CODEC_VIDEO = CODEC_VIDEO_LIST[1]
CODEC_AUDIO = "aac"
SUFFIX_OUTPUT = ".mp4"

# -----------------------------
# INSTANCE UNIQUE DE CONFIGURATION
# -----------------------------

APP_CONFIG = AppConfig(
    # Codecs
    INPUT_ACCEPTED_FILES=INPUT_ACCEPTED_FILES,
    CODEC_VIDEO_LIST=CODEC_VIDEO_LIST,
    CODEC_VIDEO=CODEC_VIDEO,
    CODEC_AUDIO=CODEC_AUDIO,
    SUFFIX_OUTPUT=SUFFIX_OUTPUT,

    # Paths
    ROOT=ROOT,
    LOG_DIR=LOG_DIR,
    INPUT_DIR=INPUT_DIR,
    OUTPUT_DIR=OUTPUT_DIR,

    # Flags
    LOG_TO_FILE=True,
    ADD_CODEC_NAME_IN_OUTPUT=False,
    PRINT_ALL_KEYS_IN_METADATA_SUMMARY=False
)
"""
Fichier de configuration pour le projet toolbox_pb

Auteur :
Pierrick BERTHE
mail : pierrick.berthe@gmx.fr
Septembre 2026
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

# -----------------------------
# CONFIGURATION TYPÉE
# -----------------------------

@dataclass(frozen=True)
class AppConfig:
    # Accepted files
    INPUT_ACCEPTED_FILES: List[str]
    INPUT_ACCEPTED_VIDEO_FILES: List[str]
    INPUT_ACCEPTED_IMAGE_FILES: List[str]
    INPUT_ACCEPTED_PDF_FILES: List[str]

    # Codecs
    CODEC_VIDEO_LIST: List[str]
    CODEC_VIDEO: str
    CODEC_AUDIO: str

    # Suffix
    SUFFIX_OUTPUT: List[str]
    SUFFIX_OUTPUT_VIDEO: str
    SUFFIX_OUTPUT_IMAGE: str
    SUFFIX_OUTPUT_PDF: str

    # Paths
    ROOT: Path
    LOG_DIR: Path
    INPUT_DIR: Path
    OUTPUT_DIR: Path
    SEGMENT_DIR: Path

    # Flags — valeurs par défaut modifiables ici et uniquement ici
    LOG_TO_FILE: bool = True
    ADD_CODEC_NAME_IN_OUTPUT: bool = False
    PRINT_ALL_KEYS_IN_METADATA_SUMMARY: bool = False
    ADD_WITHOUTBG_IN_NAME_IN_OUTPUT: bool = False
    ADD_COMPRESS_TO_IMAGE_NAME_IN_OUTPUT: bool = True
    IMAGE_REDUCTOR_JPEG_QUALITY: int = 95
    VIDEO_ASSEMBLOR_ADD_DATE_SUBTITLES: bool = True
    SRT_DURATION_SECONDS: float = 10.0

    # Image slideshow
    IMAGE_DIAPO_DURATION_SECONDS: float = 5.0
    IMAGE_DIAPO_FPS: int = 24
    IMAGE_DIAPO_MAX_HEIGHT: int = 2160

    # Accepted files (placé après les flags pour respecter l'ordre du dataclass)
    INPUT_ACCEPTED_AUDIO_FILES: List[str] = field(
        default_factory=lambda: [".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav"]
    )


# -----------------------------
# CONSTANTES DE CONFIGURATION
# -----------------------------
# Constantes qui servent à en composer d'autres ou qui dépendent de l'exécution

# paths (dépendent de l'emplacement du fichier, calculés à l'exécution)
ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "log"
INPUT_DIR = ROOT / "data" / "input"
OUTPUT_DIR = ROOT / "data" / "output"
SEGMENT_DIR = ROOT / "data" / "segment"

# Accepted files
INPUT_ACCEPTED_VIDEO_FILES = [
    ".avi", ".m4v", ".mkv", ".mod", ".mov", ".mp4", ".mpg", ".mts", ".vob", ".webm"
]
INPUT_ACCEPTED_IMAGE_FILES = [".jpeg", ".jpg", ".png"]
INPUT_ACCEPTED_PDF_FILES = [".pdf"]
INPUT_ACCEPTED_AUDIO_FILES = [".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav"]
INPUT_ACCEPTED_FILES = [
    *INPUT_ACCEPTED_VIDEO_FILES,
    *INPUT_ACCEPTED_IMAGE_FILES,
    *INPUT_ACCEPTED_PDF_FILES,
]

# Codecs ("h264_amf", "hevc_amf" sont pour les GPU AMD)
CODEC_VIDEO_LIST = ["libx264", "libx265", "h264_amf", "hevc_amf"]
CODEC_VIDEO = CODEC_VIDEO_LIST[1]
CODEC_AUDIO = "aac"

# suffix
SUFFIX_OUTPUT_VIDEO = ".mp4"
SUFFIX_OUTPUT_IMAGE = ".jpg"
SUFFIX_OUTPUT_PDF = ".pdf"
SUFFIX_OUTPUT = [
    SUFFIX_OUTPUT_VIDEO, SUFFIX_OUTPUT_IMAGE, SUFFIX_OUTPUT_PDF
]

# Define a constant for the mandatory prefix in the watermark text for PDFs
WATERMARK_PREFIX = "document exclusivement destiné à "


# -----------------------------
# INSTANCE UNIQUE DE CONFIGURATION
# -----------------------------
# Les flags et valeurs par défaut (LOG_TO_FILE, etc.) sont définis directement
# dans la classe AppConfig au dessus.

APP_CONFIG = AppConfig(
    # Accepted files
    INPUT_ACCEPTED_FILES=INPUT_ACCEPTED_FILES,
    INPUT_ACCEPTED_VIDEO_FILES=INPUT_ACCEPTED_VIDEO_FILES,
    INPUT_ACCEPTED_IMAGE_FILES=INPUT_ACCEPTED_IMAGE_FILES,
    INPUT_ACCEPTED_PDF_FILES=INPUT_ACCEPTED_PDF_FILES,
    INPUT_ACCEPTED_AUDIO_FILES=INPUT_ACCEPTED_AUDIO_FILES,

    # Codecs
    CODEC_VIDEO_LIST=CODEC_VIDEO_LIST,
    CODEC_VIDEO=CODEC_VIDEO,
    CODEC_AUDIO=CODEC_AUDIO,

    # suffix
    SUFFIX_OUTPUT=SUFFIX_OUTPUT,
    SUFFIX_OUTPUT_VIDEO=SUFFIX_OUTPUT_VIDEO,
    SUFFIX_OUTPUT_IMAGE=SUFFIX_OUTPUT_IMAGE,
    SUFFIX_OUTPUT_PDF=SUFFIX_OUTPUT_PDF,

    # Paths
    ROOT=ROOT,
    LOG_DIR=LOG_DIR,
    INPUT_DIR=INPUT_DIR,
    OUTPUT_DIR=OUTPUT_DIR,
    SEGMENT_DIR=SEGMENT_DIR,
)

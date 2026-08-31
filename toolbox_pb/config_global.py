"""
Fichier de configuration pour le projet toolbox_pb

Auteur :
Pierrick BERTHE
mail : pierrick.berthe@gmx.fr
Février 2026
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

    # Flags
    LOG_TO_FILE: bool
    ADD_CODEC_NAME_IN_OUTPUT: bool
    PRINT_ALL_KEYS_IN_METADATA_SUMMARY: bool
    ADD_COMPRESSED_IN_NAME_IN_OUTPUT: bool = False
    ADD_WITHOUTBG_IN_NAME_IN_OUTPUT: bool = True

    # Image slideshow
    IMAGE_DIAPO_DURATION_SECONDS: float = 4.0
    IMAGE_DIAPO_FPS: int = 24
    IMAGE_DIAPO_MAX_HEIGHT: int = 2160
    INPUT_ACCEPTED_AUDIO_FILES: List[str] = field(
        default_factory=lambda: [".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav"]
    )


# -----------------------------
# CONSTANTES DE CONFIGURATION
# -----------------------------

# paths
ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "log"
INPUT_DIR = ROOT / "data" / "input"
OUTPUT_DIR = ROOT / "data" / "output"
SEGMENT_DIR = ROOT / "data" / "segment"

# -----------------------------
# FLAGS UTILISATEUR — MODIFIER ICI SI BESOIN
# -----------------------------
LOG_TO_FILE = True
ADD_CODEC_NAME_IN_OUTPUT = False
ADD_COMPRESSED_IN_NAME_IN_OUTPUT = True
ADD_WITHOUTBG_IN_NAME_IN_OUTPUT = False
PRINT_ALL_KEYS_IN_METADATA_SUMMARY = False

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

# Image slideshow
IMAGE_DIAPO_DURATION_SECONDS = 5.0
IMAGE_DIAPO_FPS = 24
IMAGE_DIAPO_MAX_HEIGHT = 2160

# Define a constant for the mandatory prefix in the watermark text for PDFs
WATERMARK_PREFIX = "document exclusivement destiné à "


# -----------------------------
# INSTANCE UNIQUE DE CONFIGURATION
# -----------------------------

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

    # Flags
    LOG_TO_FILE=LOG_TO_FILE,
    ADD_CODEC_NAME_IN_OUTPUT=ADD_CODEC_NAME_IN_OUTPUT,
    PRINT_ALL_KEYS_IN_METADATA_SUMMARY=PRINT_ALL_KEYS_IN_METADATA_SUMMARY,
    ADD_COMPRESSED_IN_NAME_IN_OUTPUT=ADD_COMPRESSED_IN_NAME_IN_OUTPUT,
    ADD_WITHOUTBG_IN_NAME_IN_OUTPUT=ADD_WITHOUTBG_IN_NAME_IN_OUTPUT,

    # Image slideshow
    IMAGE_DIAPO_DURATION_SECONDS=IMAGE_DIAPO_DURATION_SECONDS,
    IMAGE_DIAPO_FPS=IMAGE_DIAPO_FPS,
    IMAGE_DIAPO_MAX_HEIGHT=IMAGE_DIAPO_MAX_HEIGHT,
)

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
INPUT_ACCEPTED_AUDIO_FILES = [
    ".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav", ".wma"
]
INPUT_ACCEPTED_MEDIA_FILES = [
    *INPUT_ACCEPTED_VIDEO_FILES,
    *INPUT_ACCEPTED_IMAGE_FILES,
    *INPUT_ACCEPTED_AUDIO_FILES,
]
INPUT_ACCEPTED_PDF_FILES = [".pdf"]

# Codecs ("h264_amf", "hevc_amf" sont pour les GPU AMD)
CODEC_VIDEO_LIST = ["libx264", "libx265", "h264_amf", "hevc_amf"]
CODEC_VIDEO = CODEC_VIDEO_LIST[1]
CODEC_AUDIO = "aac"

# suffix
SUFFIX_OUTPUT_VIDEO = ".mp4"
SUFFIX_OUTPUT_AUDIO = ".mp3"
SUFFIX_OUTPUT_IMAGE = ".jpg"
SUFFIX_OUTPUT_PDF = ".pdf"
SUFFIX_OUTPUT = [
    SUFFIX_OUTPUT_VIDEO, SUFFIX_OUTPUT_IMAGE, SUFFIX_OUTPUT_PDF
]

# Define a constant for the mandatory prefix in the watermark text for PDFs
WATERMARK_PREFIX = "document exclusivement destiné à "

# -----------------------------
# CONFIGURATION TYPÉE
# -----------------------------

@dataclass(frozen=True)
class AppConfig:
    # Accepted files
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

    # Accepted files (legacy fields for backward compatibility)
    INPUT_ACCEPTED_FILES: List[str] | None = None
    INPUT_ACCEPTED_MEDIA_FILES: List[str] | None = None
    INPUT_ACCEPTED_AUDIO_FILES: List[str] = field(
        default_factory=lambda: list(INPUT_ACCEPTED_AUDIO_FILES)
    )

    # Suffix retained as an optional field so legacy AppConfig constructors
    # that predate audio support remain valid.
    SUFFIX_OUTPUT_AUDIO: str = ".mp3"

    # Flags — valeurs par défaut modifiables ici et uniquement ici
    LOG_TO_FILE: bool = True
    ADD_CODEC_NAME_IN_OUTPUT: bool = False
    PRINT_ALL_KEYS_IN_METADATA_SUMMARY: bool = False
    ADD_WITHOUTBG_IN_NAME_IN_OUTPUT: bool = False
    ADD_COMPRESS_TO_IMAGE_NAME_IN_OUTPUT: bool = False
    IMAGE_REDUCTOR_JPEG_QUALITY: int = 75
    VIDEO_ASSEMBLOR_ADD_DATE_SUBTITLES: bool = True
    VIDEO_ASSEMBLOR_EXTRACT_AND_FILTER_DATES: bool = True
    SRT_DURATION_SECONDS: float = 10.0

    # ASS subtitle conversion
    ASS_TITLE_DURATION_SECONDS: float = 5.0
    ASS_SUBTITLE_DURATION_SECONDS: float = 10.0
    ASS_TITLE_FADE_DURATION_MS: int = 1000
    ASS_SUBTITLE_FADE_DURATION_MS: int = 500

    # Image slideshow
    IMAGE_DIAPO_DURATION_SECONDS: float = 5.0
    IMAGE_DIAPO_FPS: int = 24
    IMAGE_DIAPO_MAX_HEIGHT: int = 2160

    def __post_init__(self) -> None:
        """Normalise les alias de configuration conservés pour compatibilité."""
        accepted_files = self.INPUT_ACCEPTED_FILES
        media_files = self.INPUT_ACCEPTED_MEDIA_FILES

        if accepted_files is None:
            accepted_files = media_files or [
                *self.INPUT_ACCEPTED_VIDEO_FILES,
                *self.INPUT_ACCEPTED_IMAGE_FILES,
                *self.INPUT_ACCEPTED_AUDIO_FILES,
            ]
            object.__setattr__(self, "INPUT_ACCEPTED_FILES", accepted_files)

        if media_files is None:
            object.__setattr__(self, "INPUT_ACCEPTED_MEDIA_FILES", accepted_files)


# -----------------------------
# INSTANCE UNIQUE DE CONFIGURATION
# -----------------------------
# Les flags et valeurs par défaut (LOG_TO_FILE, etc.) sont définis directement
# dans la classe AppConfig au dessus.

APP_CONFIG = AppConfig(
    # Accepted files
    INPUT_ACCEPTED_MEDIA_FILES=INPUT_ACCEPTED_MEDIA_FILES,
    INPUT_ACCEPTED_FILES=INPUT_ACCEPTED_MEDIA_FILES,
    INPUT_ACCEPTED_VIDEO_FILES=INPUT_ACCEPTED_VIDEO_FILES,
    INPUT_ACCEPTED_IMAGE_FILES=INPUT_ACCEPTED_IMAGE_FILES,
    INPUT_ACCEPTED_AUDIO_FILES=INPUT_ACCEPTED_AUDIO_FILES,
    INPUT_ACCEPTED_PDF_FILES=INPUT_ACCEPTED_PDF_FILES,

    # Codecs
    CODEC_VIDEO_LIST=CODEC_VIDEO_LIST,
    CODEC_VIDEO=CODEC_VIDEO,
    CODEC_AUDIO=CODEC_AUDIO,

    # suffix
    SUFFIX_OUTPUT=SUFFIX_OUTPUT,
    SUFFIX_OUTPUT_VIDEO=SUFFIX_OUTPUT_VIDEO,
    SUFFIX_OUTPUT_AUDIO=SUFFIX_OUTPUT_AUDIO,
    SUFFIX_OUTPUT_IMAGE=SUFFIX_OUTPUT_IMAGE,
    SUFFIX_OUTPUT_PDF=SUFFIX_OUTPUT_PDF,

    # Paths
    ROOT=ROOT,
    LOG_DIR=LOG_DIR,
    INPUT_DIR=INPUT_DIR,
    OUTPUT_DIR=OUTPUT_DIR,
    SEGMENT_DIR=SEGMENT_DIR,
)

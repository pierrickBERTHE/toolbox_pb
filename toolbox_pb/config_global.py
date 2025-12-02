"""
Fichier de configuration pour le projet toolbox_pb

Auteurs :
Pierrick BERTHE
mail : pierrick.berthe@gmx.fr
Décembre 2025
"""
# Import standard libraries
from pathlib import Path

# Video and audio codecs
INPUT_ACCEPTED_FILES = [".avi", ".mp4", ".mts"]
CODEC_VIDEO = "libx265"
CODEC_AUDIO = "aac"
SUFFIX_OUTPUT = ".mp4"


# Path configuration
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
INPUT_DIR = DATA_DIR / "input"
OUTPUT_DIR = DATA_DIR / "output"

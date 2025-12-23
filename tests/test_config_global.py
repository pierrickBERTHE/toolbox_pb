"""
Tests unitaires pour le module config_global de toolbox_pb.

Ces tests vérifient :
- la création correcte de l'instance APP_CONFIG
- les types et valeurs des champs de configuration (codec, path et flags)
- l'immuabilité de AppConfig (dataclass frozen)

Liste des fonctions testées :
- APP_CONFIG :
    - is instance of AppConfig
    - is frozen (immutable)
- Codec configurations OK
- Path :
    - are path objects
    - structure is logical
- Flags is boolean
- codec video is in video codec list
- no empty critical configuration fields
"""
# general imports
from pathlib import Path
import pytest
import sys
from pathlib import Path

# Add the toolbox_pb directory to sys.path for imports
sys.path.append(str(Path(__file__).resolve().parents[1] / 'toolbox_pb'))

# Import the module to test
from config_global import AppConfig, APP_CONFIG


# -----------------------------
# General tests on AppConfig
# -----------------------------

def test_app_config_is_instance():
    """APP_CONFIG must be an instance of AppConfig."""
    assert isinstance(APP_CONFIG, AppConfig)


def test_app_config_is_frozen():
    """AppConfig must be immutable (frozen dataclass)."""
    with pytest.raises(Exception):
        APP_CONFIG.CODEC_AUDIO = "mp6"


# -----------------------------
# Codec fields tests
# -----------------------------

def test_codecs_configuration():
    """Verify video and audio codec configuration."""
    
    # Verify type and content of INPUT_ACCEPTED_FILES
    assert isinstance(APP_CONFIG.INPUT_ACCEPTED_FILES, list)
    assert ".mp4" in APP_CONFIG.INPUT_ACCEPTED_FILES

    # Verify type and content of CODEC_VIDEO_LIST
    assert isinstance(APP_CONFIG.CODEC_VIDEO_LIST, list)
    assert APP_CONFIG.CODEC_VIDEO in APP_CONFIG.CODEC_VIDEO_LIST

    # Verify CODEC_AUDIO and SUFFIX_OUTPUT values
    assert APP_CONFIG.CODEC_AUDIO == "aac"
    assert APP_CONFIG.SUFFIX_OUTPUT.startswith(".")


# -----------------------------
# Paths tests
# -----------------------------

def test_paths_are_path_objects():
    """All paths must be pathlib.Path instances."""
    assert isinstance(APP_CONFIG.ROOT, Path)
    assert isinstance(APP_CONFIG.LOG_DIR, Path)
    assert isinstance(APP_CONFIG.INPUT_DIR, Path)
    assert isinstance(APP_CONFIG.OUTPUT_DIR, Path)


def test_paths_structure():
    """Verify logical folder structure."""
    assert APP_CONFIG.LOG_DIR.parent == APP_CONFIG.ROOT
    assert APP_CONFIG.INPUT_DIR.parent.name == "data"
    assert APP_CONFIG.OUTPUT_DIR.parent.name == "data"


# -----------------------------
# Flags tests
# -----------------------------

def test_flags_are_booleans():
    """All flags must be boolean values."""
    assert isinstance(APP_CONFIG.LOG_TO_FILE, bool)
    assert isinstance(APP_CONFIG.ADD_CODEC_NAME_IN_OUTPUT, bool)
    assert isinstance(APP_CONFIG.PRINT_ALL_KEYS_IN_METADATA_SUMMARY, bool)


# -----------------------------
# Global consistency tests
# -----------------------------

def test_video_codec_is_in_codec_list():
    """
    The selected video codec must be part
    of the allowed video codec list.
    """
    assert APP_CONFIG.CODEC_VIDEO in APP_CONFIG.CODEC_VIDEO_LIST


def test_no_empty_configuration_fields():
    """No critical configuration field should be empty or None."""
    critical_fields = [
        APP_CONFIG.INPUT_ACCEPTED_FILES,
        APP_CONFIG.CODEC_VIDEO,
        APP_CONFIG.CODEC_AUDIO,
        APP_CONFIG.SUFFIX_OUTPUT,
        APP_CONFIG.ROOT,
        APP_CONFIG.INPUT_DIR,
        APP_CONFIG.OUTPUT_DIR,
    ]

    # Verify fields are not None
    for field in critical_fields:
        assert field is not None

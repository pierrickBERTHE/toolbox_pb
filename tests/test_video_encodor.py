"""
Tests unitaires pour la méthode video_encodor de toolbox_pb.

Liste des fonctions testées (avec création d'une fixture) :
- Ignorer les fichiers non vidéo
- Encoder une vidéo si le fichier de sortie n'existe pas
- Sauter l'encodage si le fichier de sortie existe déjà
- Nom de sortie avec le codec dans le nom si le flag est activé
- Imprimer toutes les métadonnées si le flag est activé
"""
# general imports
import sys
from pathlib import Path
from unittest import mock
import pytest

# Add the toolbox_pb directory to sys.path for imports
sys.path.append(str(Path(__file__).resolve().parents[1] / 'toolbox_pb'))

# local imports
from config_global import AppConfig
from video.main_video import video_encodor


# -----------------------------
# Fixtures
# -----------------------------

@pytest.fixture
def fake_config(tmp_path):
    """
    Minimal isolated configuration used for unit tests.

    - Uses a temporary directory provided by pytest
    - Avoids touching real project data or filesystem
    """

    # Create a temporary input and output directory
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"

    # Physically create the directories on disk
    input_dir.mkdir()
    output_dir.mkdir()

    # Return a fully valid AppConfig instance for testing
    return AppConfig(
        INPUT_ACCEPTED_FILES=[".mp4"],
        CODEC_VIDEO_LIST=["libx264", "libx265"],
        CODEC_VIDEO="libx265",
        CODEC_AUDIO="aac",
        SUFFIX_OUTPUT=".mp4",

        ROOT=tmp_path,
        LOG_DIR=tmp_path / "log",
        INPUT_DIR=input_dir,
        OUTPUT_DIR=output_dir,

        LOG_TO_FILE=False,
        ADD_CODEC_NAME_IN_OUTPUT=False,
        PRINT_ALL_KEYS_IN_METADATA_SUMMARY=False
    )


# -----------------------------
# Main tests
# -----------------------------

def test_ignore_non_video_files(fake_config):
    """
    Non-video files must be ignored and not processed.
    """

    # Create a non-video file in the input directory
    (fake_config.INPUT_DIR / "test.txt").touch()

    with mock.patch("video.main_video.func_vid.encode_full_video") as m_encode, \
        mock.patch("video.main_video.func_vid.get_all_metadata", return_value={}), \
        mock.patch("video.main_video.func_vid.print_metadata_diff_summary"), \
        mock.patch("video.main_video.func_vid.compute_size_reduction", return_value={}), \
        mock.patch("video.main_video.func_vid.print_size_reduction"), \
        mock.patch("func_global.print_step"):

        # Run the function under test
        video_encodor(fake_config)

        # Ensure encoding was never triggered
        m_encode.assert_not_called()


def test_encode_video_when_not_existing(fake_config):
    """
    A video must be encoded if the output file does not exist.
    """

    # Create a fake input video file
    input_video = fake_config.INPUT_DIR / "video.mp4"
    input_video.touch()

    # Mock all functions with side effects
    with mock.patch("video.main_video.func_vid.encode_full_video") as m_encode, \
        mock.patch("video.main_video.func_vid.get_all_metadata", return_value={}), \
        mock.patch("video.main_video.func_vid.print_metadata_diff_summary"), \
        mock.patch("video.main_video.func_vid.compute_size_reduction", return_value={}), \
        mock.patch("video.main_video.func_vid.print_size_reduction"), \
        mock.patch("func_global.print_step"):

        # Run the function under test
        video_encodor(fake_config)

        # Ensure encoding was triggered exactly once
        m_encode.assert_called_once()

        # Retrieve arguments passed to encode_full_video
        args, kwargs = m_encode.call_args

        # Validate correct parameters were passed
        assert kwargs["input_path"] == input_video
        assert kwargs["codec_video"] == fake_config.CODEC_VIDEO
        assert kwargs["codec_audio"] == fake_config.CODEC_AUDIO


def test_skip_encoding_if_output_exists(fake_config, capsys):
    """
    Encoding must be skipped if the output file already exists.
    """

    # Create fake input and output video files
    input_video = fake_config.INPUT_DIR / "video.mp4"
    output_video = fake_config.OUTPUT_DIR / "video.mp4"

    # Physically create the directories on disk
    input_video.touch()
    output_video.touch()

    # Mock all functions with side effects
    with mock.patch("video.main_video.func_vid.encode_full_video") as m_encode, \
        mock.patch("video.main_video.func_vid.get_all_metadata", return_value={}), \
        mock.patch("video.main_video.func_vid.print_metadata_diff_summary"), \
        mock.patch("video.main_video.func_vid.compute_size_reduction", return_value={}), \
        mock.patch("video.main_video.func_vid.print_size_reduction"), \
        mock.patch("func_global.print_step"):

        # Run the function under test
        video_encodor(fake_config)

        # Ensure encoding was not triggered
        m_encode.assert_not_called()

        # Capture printed output
        captured = capsys.readouterr()

        # Ensure the expected message is printed
        assert "Encodage déjà réalisé" in captured.out


def test_output_name_with_codec_flag(fake_config):
    """
    Output filename must include codec names when the flag is enabled.
    """

    # Create a modified config with ADD_CODEC_NAME_IN_OUTPUT enabled
    fake_config = fake_config.__class__(**{
        **fake_config.__dict__,
        "ADD_CODEC_NAME_IN_OUTPUT": True
    })

    # Create a fake input video
    input_video = fake_config.INPUT_DIR / "video.mp4"
    input_video.touch()

    # Mock all functions with side effects
    with mock.patch("video.main_video.func_vid.encode_full_video") as m_encode, \
        mock.patch("video.main_video.func_vid.get_all_metadata", return_value={}), \
        mock.patch("video.main_video.func_vid.print_metadata_diff_summary"), \
        mock.patch("video.main_video.func_vid.compute_size_reduction", return_value={}), \
        mock.patch("video.main_video.func_vid.print_size_reduction"), \
        mock.patch("func_global.print_step"):

        # Run the function under test
        video_encodor(fake_config)

        # Retrieve the output path used for encoding
        output_path = m_encode.call_args.kwargs["output_path"]

        # Ensure codec name is included in filename
        assert "libx264" in output_path.name or "libx265" in output_path.name

        # Ensure output extension is correct
        assert output_path.suffix == ".mp4"


def test_print_all_metadata_when_flag_enabled(fake_config):
    """
    Full metadata must be printed when the corresponding flag is enabled.
    """

    # Enable PRINT_ALL_KEYS_IN_METADATA_SUMMARY as True
    fake_config = fake_config.__class__(**{
        **fake_config.__dict__,
        "PRINT_ALL_KEYS_IN_METADATA_SUMMARY": True
    })

    # Create a fake input video
    input_video = fake_config.INPUT_DIR / "video.mp4"
    input_video.touch()

    # Mock all functions with side effects
    with mock.patch("video.main_video.func_vid.encode_full_video"), \
        mock.patch("video.main_video.func_vid.get_all_metadata", return_value={"size": 123}), \
        mock.patch("video.main_video.func_vid.print_metadata_summary_all_keys") as m_print_all, \
        mock.patch("video.main_video.func_vid.print_metadata_diff_summary"), \
        mock.patch("video.main_video.func_vid.compute_size_reduction", return_value={}), \
        mock.patch("video.main_video.func_vid.print_size_reduction"), \
        mock.patch("func_global.print_step"):

        # Run the function under test
        video_encodor(fake_config)

        # Ensure metadata was printed twice (before and after encoding)
        assert m_print_all.call_count == 2

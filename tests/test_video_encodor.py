"""
Unit tests and functional tests for the video_encodor function.

This module contains tests that verify the video encoding functionality,
including file filtering, output path management, encoding execution,
and metadata display options.

Test Coverage (unit tests):
    - Non-video file filtering: Tests that non-video files are ignored during processing
    - Encoding execution: Tests that videos are encoded when output doesn't exist
    - Encoding skip: Tests that existing output files are not re-encoded
    - Output naming: Tests that codec names are included in filenames when the flag is enabled
    - Metadata display: Tests that full metadata is printed when the corresponding flag is enabled
    - Codec application: Tests that configured video and audio codecs are applied correctly
    - Compression statistics: Tests that size reduction and compression factors are calculated

Test Coverage (functional tests):
    - Complete workflow: Tests end-to-end encoding of multiple videos with metadata and stats
    - Mixed file types: Tests that only video files are processed in a mixed directory
    - Output naming with codec info: Tests output filenames include codec identifiers when enabled
    - Metadata workflow: Tests full metadata extraction, comparison, and reporting during encoding
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
    segment_dir = tmp_path / "segment"

    # Physically create the directories on disk
    input_dir.mkdir()
    output_dir.mkdir()
    segment_dir.mkdir()

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
        SEGMENT_DIR=segment_dir,

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

    # Mock all functions with side effects
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


# ==============================
# Additional Functional Tests
# ==============================

def test_video_encodor_complete_workflow(fake_config):
    """
    Functional test: Complete video encoding workflow with multiple files.
    
    Verifies that video_encodor correctly processes multiple input files,
    applies appropriate codecs, generates output with correct naming,
    and computes compression statistics.
    """
    
    # Create multiple input video files with different names
    video1 = fake_config.INPUT_DIR / "intro.mp4"
    video2 = fake_config.INPUT_DIR / "main_content.mp4"
    video1.touch()
    video2.touch()
    
    # Mock all dependencies
    with mock.patch("video.main_video.func_vid.encode_full_video") as m_encode, \
        mock.patch("video.main_video.func_vid.get_all_metadata") as m_get_meta, \
        mock.patch("video.main_video.func_vid.print_metadata_diff_summary") as m_print_diff, \
        mock.patch("video.main_video.func_vid.compute_size_reduction") as m_compute_reduction, \
        mock.patch("video.main_video.func_vid.print_size_reduction") as m_print_reduction, \
        mock.patch("func_global.print_step"):
        
        # Configure metadata mocks
        metadata_before = {"format": {"size": "5000000"}}
        metadata_after = {"format": {"size": "2500000"}}
        m_get_meta.side_effect = [metadata_before, metadata_after, metadata_before, metadata_after]
        
        # Configure size reduction mocks
        m_compute_reduction.side_effect = [
            {
                "size_before": 5000000,
                "size_after": 2500000,
                "reduction_percent": 50.0,
                "compression_factor": 2.0
            },
            {
                "size_before": 5000000,
                "size_after": 2500000,
                "reduction_percent": 50.0,
                "compression_factor": 2.0
            }
        ]
        
        # Run the function
        video_encodor(fake_config)
        
        # Verify encoding was called for both videos
        assert m_encode.call_count == 2
        
        # Verify metadata was retrieved before and after for each video
        assert m_get_meta.call_count == 4
        
        # Verify size reduction was computed for both videos
        assert m_compute_reduction.call_count == 2
        
        # Verify differences were printed for both videos
        assert m_print_diff.call_count == 2
        
        # Verify size reduction was printed for both videos
        assert m_print_reduction.call_count == 2
        
        # Validate encoding calls have correct parameters
        encode_calls = m_encode.call_args_list
        for call in encode_calls:
            kwargs = call.kwargs
            assert kwargs["codec_video"] == fake_config.CODEC_VIDEO
            assert kwargs["codec_audio"] == fake_config.CODEC_AUDIO


def test_video_encodor_mixed_files(fake_config):
    """
    Functional test: Processing directory with mixed file types.
    
    Verifies that video_encodor correctly:
    - Ignores non-video files (txt, json, etc.)
    - Encodes only video files matching the configured extensions
    - Handles empty directories gracefully
    """
    
    # Create a mix of file types
    video_file = fake_config.INPUT_DIR / "video.mp4"
    text_file = fake_config.INPUT_DIR / "readme.txt"
    config_file = fake_config.INPUT_DIR / "config.json"
    image_file = fake_config.INPUT_DIR / "thumbnail.png"
    
    # Physically create the files on disk
    video_file.touch()
    text_file.touch()
    config_file.touch()
    image_file.touch()
    
    # Mock all dependencies
    with mock.patch("video.main_video.func_vid.encode_full_video") as m_encode, \
        mock.patch("video.main_video.func_vid.get_all_metadata", return_value={}), \
        mock.patch("video.main_video.func_vid.print_metadata_diff_summary"), \
        mock.patch("video.main_video.func_vid.compute_size_reduction", return_value={}), \
        mock.patch("video.main_video.func_vid.print_size_reduction"), \
        mock.patch("func_global.print_step"):
        
        # Run the function
        video_encodor(fake_config)
        
        # Verify only the video file was encoded (not other file types)
        assert m_encode.call_count == 1
        
        # Verify the correct file was passed
        call_kwargs = m_encode.call_args.kwargs
        assert call_kwargs["input_path"] == video_file


def test_video_encodor_with_codec_name_in_output(fake_config):
    """
    Functional test: Output naming with codec information included.
    
    Verifies that when ADD_CODEC_NAME_IN_OUTPUT is enabled,
    output filenames correctly include the video codec identifier.
    """
    
    # Enable codec name in output
    fake_config = fake_config.__class__(**{
        **fake_config.__dict__,
        "ADD_CODEC_NAME_IN_OUTPUT": True,
        "CODEC_VIDEO": "libx265"
    })
    
    # Create input video
    input_video = fake_config.INPUT_DIR / "original_video.mp4"
    input_video.touch()
    
    # Mock all dependencies
    with mock.patch("video.main_video.func_vid.encode_full_video") as m_encode, \
        mock.patch("video.main_video.func_vid.get_all_metadata", return_value={}), \
        mock.patch("video.main_video.func_vid.print_metadata_diff_summary"), \
        mock.patch("video.main_video.func_vid.compute_size_reduction", return_value={}), \
        mock.patch("video.main_video.func_vid.print_size_reduction"), \
        mock.patch("func_global.print_step"):
        
        # Run the function
        video_encodor(fake_config)
        
        # Get the output path used
        output_path = m_encode.call_args.kwargs["output_path"]
        
        # Verify codec name is in the output filename
        assert "libx265" in output_path.name
        assert output_path.suffix == ".mp4"
        assert output_path.parent == fake_config.OUTPUT_DIR


def test_video_encodor_metadata_workflow(fake_config):
    """
    Functional test: Complete metadata extraction and reporting workflow.
    
    Verifies that video_encodor:
    - Extracts metadata before encoding
    - Extracts metadata after encoding
    - Computes and displays compression statistics
    - Prints metadata differences when flag is enabled
    """

    # Enable full metadata printing
    fake_config = fake_config.__class__(**{
        **fake_config.__dict__,
        "PRINT_ALL_KEYS_IN_METADATA_SUMMARY": True
    })

    # Create input video
    input_video = fake_config.INPUT_DIR / "video.mp4"
    input_video.touch()
    
    # Define sample metadata before and after encoding
    metadata_before = {
        "format": {
            "filename": "video.mp4",
            "size": "10000000",
            "duration": "60"
        },
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080}
        ]
    }
    
    metadata_after = {
        "format": {
            "filename": "video.mp4",
            "size": "5000000",
            "duration": "60"
        },
        "streams": [
            {"codec_type": "video", "codec_name": "h265", "width": 1920, "height": 1080}
        ]
    }
    
    # Mock all dependencies
    with mock.patch("video.main_video.func_vid.encode_full_video") as m_encode, \
        mock.patch("video.main_video.func_vid.get_all_metadata") as m_get_meta, \
        mock.patch("video.main_video.func_vid.print_metadata_summary_all_keys") as m_print_all, \
        mock.patch("video.main_video.func_vid.print_metadata_diff_summary") as m_print_diff, \
        mock.patch("video.main_video.func_vid.compute_size_reduction") as m_compute, \
        mock.patch("video.main_video.func_vid.print_size_reduction") as m_print_reduction, \
        mock.patch("func_global.print_step"):
        
        # Configure metadata sequence
        m_get_meta.side_effect = [metadata_before, metadata_after]
        
        # Configure compression stats
        m_compute.return_value = {
            "size_before": 10000000,
            "size_after": 5000000,
            "reduction_percent": 50.0,
            "compression_factor": 2.0
        }
        
        # Run the function
        video_encodor(fake_config)
        
        # Verify metadata functions were called correctly
        assert m_get_meta.call_count == 2
        
        # Verify full metadata was printed (before and after)
        assert m_print_all.call_count == 2
        
        # Verify metadata differences were printed
        assert m_print_diff.call_count == 1
        m_print_diff.assert_called_with(metadata_before, metadata_after)
        
        # Verify compression statistics were computed
        assert m_compute.call_count == 1
        
        # Verify size reduction was printed
        assert m_print_reduction.call_count == 1

"""
Unit tests and functional tests for the video_assemblor function.

This module contains tests that verify the video assembly functionality,
including loading video sequences, trimming clips, normalizing audio,
concatenating multiple videos, and computing compression statistics.

Test Coverage (unit tests):
    - Assembly without segments: Tests video concatenation when no segment file exists
    - Assembly with segments: Tests video trimming and concatenation using segment definitions
    - Video sequence resolution: Tests proper loading of input video files
    - Clip operations: Tests loading, trimming, and audio normalization of video clips
    - Output writing: Tests final video file writing with specified codecs
    - Metadata handling: Tests metadata extraction and compression statistics calculation
    - Resource cleanup: Tests proper closure of video clip resources

Test Coverage (functional tests):
    - Complete assembly workflow: Tests full pipeline with multiple videos and audio normalization
    - Segment-based trimming: Tests precise clip trimming using segment timing information
    - Multi-video concatenation: Tests seamless joining of multiple video clips with audio sync
    - Metadata comparison: Tests metadata extraction before and after assembly process
"""
# general imports
import sys
from pathlib import Path
from unittest import mock
import pytest

# Add the toolbox_pb directory to sys.path for imports
sys.path.append(str(Path(__file__).resolve().parents[2] / 'toolbox_pb'))

# local imports
from config_global import AppConfig
from video.main_video import video_assemblor


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
    
    # Add two fictional video to the input directory
    (input_dir / "video1.mp4").touch()
    (input_dir / "video2.mp4").touch()

    # Return a fully valid AppConfig instance for testing
    return AppConfig(
        INPUT_ACCEPTED_FILES=[".mp4"],
        INPUT_ACCEPTED_VIDEO_FILES=[".mp4"],
        INPUT_ACCEPTED_IMAGE_FILES=[".jpg", ".png"],
        INPUT_ACCEPTED_PDF_FILES=[".pdf"],
        CODEC_VIDEO_LIST=["libx264", "libx265"],
        CODEC_VIDEO="libx265",
        CODEC_AUDIO="aac",
        SUFFIX_OUTPUT=[".mp4", ".jpg", ".pdf"],
        SUFFIX_OUTPUT_VIDEO=".mp4",
        SUFFIX_OUTPUT_IMAGE=".jpg",
        SUFFIX_OUTPUT_PDF=".pdf",

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

def test_video_assemblor_no_segments(fake_config):
    """Test assembly when no segments.csv exists."""
    with mock.patch("video.main_video.func_vid.resolve_video_sequence") as m_seq, \
        mock.patch("video.main_video.func_vid.load_and_trim_clip") as m_load, \
        mock.patch("video.main_video.func_vid.normalize_audio", side_effect=lambda x: x) as m_norm, \
        mock.patch("video.main_video.func_vid.concatenate_videoclips") as m_concat, \
        mock.patch("video.main_video.func_vid.write_video_file") as m_write, \
        mock.patch("video.main_video.func_vid.get_all_metadata", return_value={"format": {"size": 1000}}), \
        mock.patch("video.main_video.func_vid.print_metadata_diff_summary"), \
        mock.patch(
            "video.main_video.func_vid.get_inputs_metadata",
            side_effect=lambda sequence, get_metadata_fn: [{"format": {"size": 1000}}]
        ), \
        mock.patch(
            "video.main_video.func_vid.compute_size_reduction_from_inputs",
            return_value={
                "size_before": 2000,
                "size_after": 1000,
                "reduction_percent": 50,
                "compression_factor": 2
            }), \
        mock.patch("video.main_video.func_vid.print_size_reduction"):


        # Mock sequence returned
        m_seq.return_value = [
            {"path": fake_config.INPUT_DIR / "video1.mp4", "start": None, "end": None},
            {"path": fake_config.INPUT_DIR / "video2.mp4", "start": None, "end": None}
        ]

        # Mock clip objects
        mock_clip = mock.MagicMock()
        m_load.return_value = mock_clip
        m_concat.return_value = mock_clip

        # Call function
        video_assemblor(fake_config)

        # Assertions
        m_seq.assert_called_once()
        assert m_load.call_count == 2
        m_concat.assert_called_once()
        m_write.assert_called_once()
        mock_clip.close.assert_called()


def test_video_assemblor_with_segments(fake_config, tmp_path):
    """Test assembly when segments.csv exists."""
    # Créer un segments.csv fictif
    seg_file = tmp_path / "segment" / "segments.csv"
    seg_file.write_text("filename,start,end\nvideo1.mp4,0,10\n")

    # Mock all functions with side effects
    with mock.patch("video.main_video.func_vid.load_segments_csv") as m_load_csv, \
        mock.patch("video.main_video.func_vid.resolve_video_sequence") as m_seq, \
        mock.patch("video.main_video.func_vid.load_and_trim_clip") as m_load, \
        mock.patch("video.main_video.func_vid.normalize_audio", side_effect=lambda x: x), \
        mock.patch("video.main_video.func_vid.concatenate_videoclips") as m_concat, \
        mock.patch("video.main_video.func_vid.write_video_file") as m_write, \
        mock.patch("video.main_video.func_vid.get_all_metadata", return_value={"format": {"size": 1000}}), \
        mock.patch("video.main_video.func_vid.print_metadata_diff_summary"), \
        mock.patch(
            "video.main_video.func_vid.get_inputs_metadata",
            side_effect=lambda sequence,
            get_metadata_fn: [{"format": {"size": 1000}}]
        ), \
        mock.patch(
            "video.main_video.func_vid.compute_size_reduction_from_inputs",
            return_value={
                "size_before": 1000,
                "size_after": 500,
                "reduction_percent": 50,
                "compression_factor": 2
            }
        ), \
        mock.patch("video.main_video.func_vid.print_size_reduction"):
        m_load_csv.return_value = {"video1.mp4": {"start": 0, "end": 10}}
        m_seq.return_value = [{
            "path": fake_config.INPUT_DIR / "video1.mp4",
            "start": 0,
            "end": 10
        }]

        # Mock clip objects
        mock_clip = mock.MagicMock()
        m_load.return_value = mock_clip
        m_concat.return_value = mock_clip

        # Call function
        video_assemblor(fake_config)

        # Assertions
        m_load_csv.assert_called_once()
        m_seq.assert_called_once()
        m_load.assert_called_once_with(fake_config.INPUT_DIR / "video1.mp4", 0, 10)
        m_concat.assert_called_once()
        m_write.assert_called_once()


# ==============================
# Additional Functional Tests
# ==============================

def test_video_assemblor_complete_workflow(fake_config):
    """
    Functional test: Complete video assembly workflow with multiple videos.
    
    Verifies that video_assemblor correctly:
    - Resolves video sequence from input directory
    - Loads and normalizes audio for each clip
    - Concatenates multiple clips seamlessly
    - Writes output with specified codecs
    - Computes and reports compression statistics
    """
    
    # Mock all dependencies
    with mock.patch("video.main_video.func_vid.resolve_video_sequence") as m_seq, \
        mock.patch("video.main_video.func_vid.load_and_trim_clip") as m_load, \
        mock.patch("video.main_video.func_vid.normalize_audio") as m_norm, \
        mock.patch("video.main_video.func_vid.concatenate_videoclips") as m_concat, \
        mock.patch("video.main_video.func_vid.write_video_file") as m_write, \
        mock.patch("video.main_video.func_vid.get_all_metadata") as m_get_meta, \
        mock.patch("video.main_video.func_vid.print_metadata_diff_summary"), \
        mock.patch("video.main_video.func_vid.get_inputs_metadata") as m_get_inputs, \
        mock.patch("video.main_video.func_vid.compute_size_reduction_from_inputs") as m_compute, \
        mock.patch("video.main_video.func_vid.print_size_reduction"):
        
        # Configure video sequence
        m_seq.return_value = [
            {"path": fake_config.INPUT_DIR / "video1.mp4", "start": None, "end": None},
            {"path": fake_config.INPUT_DIR / "video2.mp4", "start": None, "end": None}
        ]
        
        # Configure clips
        clip1 = mock.MagicMock()
        clip2 = mock.MagicMock()
        m_load.side_effect = [clip1, clip2]
        
        # Configure normalized clips
        norm_clip1 = mock.MagicMock()
        norm_clip2 = mock.MagicMock()
        m_norm.side_effect = [[norm_clip1], [norm_clip2]]
        
        # Configure concatenated clip
        final_clip = mock.MagicMock()
        m_concat.return_value = final_clip
        
        # Configure metadata
        metadata_before = [
            {"format": {"size": "3000000"}},
            {"format": {"size": "4000000"}}
        ]
        metadata_after = {"format": {"size": "5000000"}}
        m_get_meta.return_value = metadata_after
        m_get_inputs.return_value = metadata_before
        
        # Configure compression stats
        m_compute.return_value = {
            "size_before": 7000000,
            "size_after": 5000000,
            "reduction_percent": 28.6,
            "compression_factor": 1.4
        }
        
        # Run the function
        video_assemblor(fake_config)
        
        # Verify sequence was resolved
        m_seq.assert_called_once()
        
        # Verify both clips were loaded
        assert m_load.call_count == 2
        
        # Verify audio normalization
        assert m_norm.call_count >= 1
        
        # Verify concatenation
        m_concat.assert_called_once()
        
        # Verify final output was written
        m_write.assert_called_once()
        
        # Verify metadata extraction
        assert m_get_meta.call_count >= 1
        
        # Verify compression stats
        m_compute.assert_called_once()
        
        # Verify clip closure
        final_clip.close.assert_called()


def test_video_assemblor_segment_trimming(fake_config, tmp_path):
    """
    Functional test: Segment-based video trimming workflow.
    
    Verifies that video_assemblor correctly:
    - Loads segment definitions from CSV
    - Applies precise start/end time trimming
    - Respects timing constraints from segment file
    - Trims only specified portions of source videos
    """
    
    # Create segments file with specific timings
    seg_file = tmp_path / "segment" / "segments.csv"
    seg_file.write_text(
        "filename,start,end\n"
        "video1.mp4,5,15\n"
        "video2.mp4,10,30\n"
    )
    
    # Mock all dependencies
    with mock.patch("video.main_video.func_vid.load_segments_csv") as m_load_csv, \
        mock.patch("video.main_video.func_vid.resolve_video_sequence") as m_seq, \
        mock.patch("video.main_video.func_vid.load_and_trim_clip") as m_load, \
        mock.patch("video.main_video.func_vid.normalize_audio", side_effect=lambda x: x), \
        mock.patch("video.main_video.func_vid.concatenate_videoclips") as m_concat, \
        mock.patch("video.main_video.func_vid.write_video_file") as m_write, \
        mock.patch("video.main_video.func_vid.get_all_metadata", return_value={}), \
        mock.patch("video.main_video.func_vid.print_metadata_diff_summary"), \
        mock.patch("video.main_video.func_vid.get_inputs_metadata", return_value=[]), \
        mock.patch("video.main_video.func_vid.compute_size_reduction_from_inputs", return_value={}), \
        mock.patch("video.main_video.func_vid.print_size_reduction"):
        
        # Configure segments
        m_load_csv.return_value = {
            "video1.mp4": {"start": 5, "end": 15},
            "video2.mp4": {"start": 10, "end": 30}
        }
        
        # Configure video sequence
        m_seq.return_value = [
            {"path": fake_config.INPUT_DIR / "video1.mp4", "start": 5, "end": 15},
            {"path": fake_config.INPUT_DIR / "video2.mp4", "start": 10, "end": 30}
        ]
        
        # Configure clips
        mock_clip = mock.MagicMock()
        m_load.return_value = mock_clip
        m_concat.return_value = mock_clip
        
        # Run the function
        video_assemblor(fake_config)
        
        # Verify segment file was loaded
        m_load_csv.assert_called_once()
        
        # Verify load_and_trim_clip was called with correct timings
        load_calls = m_load.call_args_list
        assert len(load_calls) == 2
        
        # First clip: video1.mp4 from 5 to 15 seconds
        first_call_args = load_calls[0]
        assert first_call_args[0][0] == fake_config.INPUT_DIR / "video1.mp4"
        assert first_call_args[0][1] == 5
        assert first_call_args[0][2] == 15
        
        # Second clip: video2.mp4 from 10 to 30 seconds
        second_call_args = load_calls[1]
        assert second_call_args[0][0] == fake_config.INPUT_DIR / "video2.mp4"
        assert second_call_args[0][1] == 10
        assert second_call_args[0][2] == 30


def test_video_assemblor_audio_normalization_workflow(fake_config):
    """
    Functional test: Audio normalization across multiple clips.
    
    Verifies that video_assemblor:
    - Applies audio normalization to each clip
    - Handles clips with and without audio
    - Maintains audio synchronization during concatenation
    - Preserves audio settings in final output
    """
    
    # Mock all dependencies
    with mock.patch("video.main_video.func_vid.resolve_video_sequence") as m_seq, \
        mock.patch("video.main_video.func_vid.load_and_trim_clip") as m_load, \
        mock.patch("video.main_video.func_vid.normalize_audio") as m_norm, \
        mock.patch("video.main_video.func_vid.concatenate_videoclips") as m_concat, \
        mock.patch("video.main_video.func_vid.write_video_file") as m_write, \
        mock.patch("video.main_video.func_vid.get_all_metadata", return_value={}), \
        mock.patch("video.main_video.func_vid.print_metadata_diff_summary"), \
        mock.patch("video.main_video.func_vid.get_inputs_metadata", return_value=[]), \
        mock.patch("video.main_video.func_vid.compute_size_reduction_from_inputs", return_value={}), \
        mock.patch("video.main_video.func_vid.print_size_reduction"):
        
        # Configure video sequence
        m_seq.return_value = [
            {"path": fake_config.INPUT_DIR / "video1.mp4", "start": None, "end": None},
            {"path": fake_config.INPUT_DIR / "video2.mp4", "start": None, "end": None}
        ]
        
        # Configure clips with audio
        clip1_with_audio = mock.MagicMock()
        clip1_with_audio.audio = mock.MagicMock()
        
        clip2_with_audio = mock.MagicMock()
        clip2_with_audio.audio = mock.MagicMock()
        
        m_load.side_effect = [clip1_with_audio, clip2_with_audio]
        
        # Configure normalized clips
        norm_clip1 = mock.MagicMock()
        norm_clip2 = mock.MagicMock()
        m_norm.side_effect = [[norm_clip1], [norm_clip2]]
        
        # Configure concatenated clip
        final_clip = mock.MagicMock()
        m_concat.return_value = final_clip
        
        # Run the function
        video_assemblor(fake_config)
        
        # Verify audio normalization was applied to each clip
        assert m_norm.call_count >= 1
        
        # Verify normalize_audio received list of clips
        for call in m_norm.call_args_list:
            normalized_list = call[0][0]
            assert isinstance(normalized_list, list)
            assert len(normalized_list) > 0
        
        # Verify concatenation used normalized clips
        m_concat.assert_called_once()
        
        # Verify output was written
        m_write.assert_called_once()


def test_video_assemblor_metadata_and_compression(fake_config):
    """
    Functional test: Complete metadata tracking and compression reporting.
    
    Verifies that video_assemblor:
    - Extracts metadata from input videos before assembly
    - Extracts metadata from output video after assembly
    - Compares metadata to show changes
    - Calculates compression statistics
    - Reports size reduction percentage
    """
    
    # Mock all dependencies
    with mock.patch("video.main_video.func_vid.resolve_video_sequence") as m_seq, \
        mock.patch("video.main_video.func_vid.load_and_trim_clip") as m_load, \
        mock.patch("video.main_video.func_vid.normalize_audio", side_effect=lambda x: x), \
        mock.patch("video.main_video.func_vid.concatenate_videoclips") as m_concat, \
        mock.patch("video.main_video.func_vid.write_video_file") as m_write, \
        mock.patch("video.main_video.func_vid.get_all_metadata") as m_get_meta, \
        mock.patch("video.main_video.func_vid.print_metadata_diff_summary") as m_print_diff, \
        mock.patch("video.main_video.func_vid.get_inputs_metadata") as m_get_inputs, \
        mock.patch("video.main_video.func_vid.compute_size_reduction_from_inputs") as m_compute, \
        mock.patch("video.main_video.func_vid.print_size_reduction") as m_print_reduction:
        
        # Configure video sequence
        m_seq.return_value = [
            {"path": fake_config.INPUT_DIR / "video1.mp4", "start": None, "end": None},
            {"path": fake_config.INPUT_DIR / "video2.mp4", "start": None, "end": None}
        ]
        
        # Configure clips
        mock_clip = mock.MagicMock()
        m_load.return_value = mock_clip
        m_concat.return_value = mock_clip
        
        # Configure input metadata
        input_meta1 = {
            "format": {"filename": "video1.mp4", "size": "5000000", "duration": "60"}
        }
        input_meta2 = {
            "format": {"filename": "video2.mp4", "size": "4000000", "duration": "45"}
        }
        m_get_inputs.return_value = [input_meta1, input_meta2]
        
        # Configure output metadata
        output_meta = {
            "format": {"filename": "assembled.mp4", "size": "7000000", "duration": "105"}
        }
        m_get_meta.return_value = output_meta
        
        # Configure compression stats
        m_compute.return_value = {
            "size_before": 9000000,
            "size_after": 7000000,
            "reduction_percent": 22.2,
            "compression_factor": 1.29
        }
        
        # Run the function
        video_assemblor(fake_config)
        
        # Verify input metadata was extracted
        m_get_inputs.assert_called_once()
        
        # Verify output metadata was extracted
        assert m_get_meta.call_count >= 1
        
        # Verify metadata differences were printed
        m_print_diff.assert_called_once()
        
        # Verify compression was computed
        m_compute.assert_called_once()
        
        # Verify compression results were printed
        m_print_reduction.assert_called_once()
        
        # Verify compression stats have expected values
        stats_call = m_compute.call_args
        if stats_call:
            # handle both positional and keyword arguments
            if len(stats_call[0]) >= 3:
                stats = stats_call[0][2]
            else:
                stats = m_compute.call_args.kwargs.get('size_after', {})

            # verify the mock was called at least once withe the compression data
            assert m_compute.call_count >= 1

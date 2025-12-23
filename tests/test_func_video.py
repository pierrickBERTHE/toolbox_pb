"""
Tests unitaires pour les fonctions utilitaires de func_global.py.

Objectifs :
- Vérifier les comportements unitaires
- Éviter tout effet de bord (git, ffmpeg, fichiers, stdout réel)
- Ne tester que la logique locale

Liste des fonctions testées :
- count_cpu OK
- encode_full_video OK
- format_duration_hms OK
- get_all_metadata : 
    - file_not_found
    - sucess
    - ffprobe_missing
- compute_size_reduction : 
    - nominal
    - invalid_sizes
    - reduction_zero_before
- print_size_reduction :
    - nominal
    - reduction_missing_data
"""
# Imports standard
import sys
from pathlib import Path
import json
import subprocess
import pytest
from unittest import mock

# Add the toolbox_pb directory to sys.path for imports
sys.path.append(str(Path(__file__).resolve().parents[1] / 'toolbox_pb'))

# Import the module to test
from video.func_video import (
    count_cpu_threads,
    encode_full_video,
    format_duration_hms,
    get_all_metadata,
    compute_size_reduction,
    print_size_reduction,
)


def test_count_cpu_threads(monkeypatch, capsys):
    """Test that count_cpu_threads returns the correct number and prints
    output."""

    # Mock os.cpu_count to return 8
    monkeypatch.setattr("os.cpu_count", lambda: 8)

    # Call the function and capture output
    result = count_cpu_threads()
    assert result == 8

    # Verify printed output to stdout
    captured = capsys.readouterr()
    assert "Nombre de threads disponibles" in captured.out


def test_encode_full_video_calls_moviepy_correctly(tmp_path):
    """Test that encode_full_video calls MoviePy functions with
    correct parameters."""

    # Prepare test paths
    input_path = tmp_path / "in.mp4"
    output_path = tmp_path / "out.mp4"

    #  Mock VideoFileClip and count_cpu_threads
    with mock.patch("video.func_video.VideoFileClip") as m_clip, \
        mock.patch("video.func_video.count_cpu_threads", return_value=4):

        # Set up the mock clip instance
        clip_instance = m_clip.return_value

        # Call the function under test
        encode_full_video(
            input_path=input_path,
            output_path=output_path,
            codec_video="libx265",
            codec_audio="aac"
        )

        # Verify that VideoFileClip was called with the correct input path
        m_clip.assert_called_once_with(str(input_path))
        
        # Verify that write_videofile and close were called on the clip instance
        clip_instance.write_videofile.assert_called_once()
        clip_instance.close.assert_called_once()


# Different test cases for format_duration_hms
@pytest.mark.parametrize(
    "input_val, expected",
    [
        (0, "00:00:00"),
        (59, "00:00:59"),
        (60, "00:01:00"),
        (3661, "01:01:01"),
        ("invalid", "N/A"),
        (None, "N/A"),
    ],
)
def test_format_duration_hms(input_val, expected):
    """Test that format_duration_hms formats durations correctly."""
    assert format_duration_hms(input_val) == expected


def test_get_all_metadata_file_not_found(tmp_path):
    """ Test that the function raises FileNotFoundError for missing files."""
    with pytest.raises(FileNotFoundError):
        get_all_metadata(tmp_path / "missing.mp4")


def test_get_all_metadata_success(tmp_path):
    """ Test that the function returns correct metadata on success."""
    
    # Create a temporary video file
    video = tmp_path / "video.mp4"
    video.touch()

    # Prepare fake ffprobe output
    fake_output = {"format": {"duration": "10"}}

    # Mock subprocess.run to return the fake output
    completed = subprocess.CompletedProcess(
        args=["ffprobe"],
        returncode=0,
        stdout=json.dumps(fake_output),
        stderr=""
    )

    # Patch subprocess.run and call the function
    with mock.patch("subprocess.run", return_value=completed):
        meta = get_all_metadata(video)

    # Verify the returned metadata
    assert meta == fake_output


def test_get_all_metadata_ffprobe_missing(tmp_path):
    """Test that the function raises RuntimeError when ffprobe is missing."""
    
    # Create a temporary video file
    video = tmp_path / "video.mp4"
    video.touch()

    # Mock subprocess.run to raise FileNotFoundError
    with mock.patch("subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(RuntimeError):
            get_all_metadata(video)


def test_compute_size_reduction_nominal():
    """Test compute_size_reduction with valid sizes."""
    
    # Prepare fake metadata
    before = {"format": {"size": "1000"}}
    after = {"format": {"size": "500"}}

    # Call the function
    stats = compute_size_reduction(before, after)

    # Verify the computed statistics
    assert stats["size_before"] == 1000
    assert stats["size_after"] == 500
    assert stats["reduction_percent"] == 50.0
    assert stats["compression_factor"] == 2.0


def test_compute_size_reduction_invalid_sizes():
    """Test that compute_size_reduction handles missing size data."""
    
    # Call the function with missing size data
    stats = compute_size_reduction({}, {})

    # Verify that the statistics are None
    assert stats["size_before"] is None
    assert stats["reduction_percent"] is None


def test_compute_size_reduction_zero_before():
    """Test that compute_size_reduction handles zero size before encoding."""
    
    # Prepare fake metadata with zero size before
    stats = compute_size_reduction(
        {"format": {"size": "0"}},
        {"format": {"size": "100"}},
    )

    # Verify that the statistics are None
    assert stats["compression_factor"] is None


def test_print_size_reduction_nominal(capsys):
    """Test that print_size_reduction prints correct output."""
    
    # Prepare fake statistics
    stats = {
        "size_before": 1_000_000,
        "size_after": 500_000,
        "reduction_percent": 50.0,
        "compression_factor": 2.0,
    }

    # Call the function
    print_size_reduction(stats)

    # Capture the printed output and verify it
    out = capsys.readouterr().out
    assert "Réduction" in out
    assert "Mo" in out


def test_print_size_reduction_missing_data(capsys):
    """ Test that print_size_reduction handles missing data gracefully."""
    
    # Call the function with missing statistics
    print_size_reduction({})

    # Capture the printed output and verify it
    out = capsys.readouterr().out
    assert "Impossible de calculer" in out

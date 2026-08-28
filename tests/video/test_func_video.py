"""
Unit tests for the video.func_video module.

This module contains comprehensive tests for video processing utility
functions, including CPU thread detection, video encoding, metadata extraction
and formatting, video sequence resolution, audio normalization, and file
output operations.

Test Coverage:
    - CPU Threads: Tests for detecting available CPU threads
    - Video Encoding: Tests for full video encoding with MoviePy
    - Duration Formatting: Tests for HH:MM:SS time format conversion
    - Metadata Extraction: Tests for retrieving video metadata via ffprobe
    - Metadata Display: Tests for formatting and printing metadata summaries
    - Metadata Comparison: Tests for displaying differences between metadata
    - Value Formatting: Tests for human-readable format conversion (bitrate, 
    size, etc.)
    - Size Reduction: Tests for computing compression statistics
    - Byte Formatting: Tests for converting bytes to human-readable units
    - Segment Loading: Tests for CSV segment file parsing and validation
    - Video Sequence: Tests for resolving video file sequences
    - Clip Operations: Tests for loading, trimming, and audio normalization
    - File Output: Tests for writing video files with specified codecs
    - Input Processing: Tests for metadata collection and size calculation 
    from input sequences
"""
# Imports standard
import sys
from pathlib import Path
import json
import subprocess
import pytest
from unittest import mock
from unittest.mock import patch, MagicMock
from io import StringIO
from PIL import Image

# Add the toolbox_pb directory to sys.path for imports
sys.path.append(str(Path(__file__).resolve().parents[2] / 'toolbox_pb'))

# Import the module to test
from toolbox_pb.video.func_video import shift_audio_no_reencode
from video.func_video import (
    AudioBoost,
    apply_audio_boosts_ffmpeg,
    apply_video_srt_ffmpeg,
    build_image_subtitle,
    create_image_diapo_ffmpeg,
    fit_image_size_in_frame,
    format_srt_timestamp,
    count_cpu_threads,
    load_boost_csv,
    encode_full_video,
    normalize_audio_sample_rate,
    format_duration_hms,
    get_all_metadata,
    get_image_size,
    print_metadata_summary_all_keys,
    print_metadata_diff_summary,
    format_value,
    compute_size_reduction,
    format_bytes,
    print_size_reduction,
    to_seconds,
    load_segments_csv,
    resolve_video_sequence,
    load_and_trim_clip,
    normalize_audio,
    write_video_file,
    get_inputs_metadata,
    sum_input_sizes,
    compute_size_reduction_from_inputs,
    shift_audio_no_reencode,
    write_image_diapo_srt,
)
from func_global import Logger


class DummyFFmpegProcess:
    def __init__(self):
        self.stdout = iter([
            "out_time_ms=1000000\n",
            "out_time_ms=2000000\n",
        ])
        self.returncode = 0

    def wait(self):
        return 0
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


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


def test_encode_full_video_builds_minimal_ffmpeg_command():
    """
    Test that encode_full_video builds and executes a minimal FFmpeg command.
    """
    fake_meta = {"format": {"duration": "12.5"}, "streams": []}
    proc = MagicMock()
    proc.stdout = iter([])
    proc.returncode = 0
    proc.wait.return_value = 0

    with mock.patch("video.func_video.count_cpu_threads", return_value=8), \
        mock.patch("video.func_video.get_all_metadata", return_value=fake_meta), \
        mock.patch("video.func_video.consume_ffmpeg_progress") as m_progress, \
        mock.patch("video.func_video.subprocess.Popen", return_value=proc) as m_popen:

        encode_full_video("in.mp4", "out.mp4", "libx265", "aac")

    cmd = m_popen.call_args.args[0]
    assert cmd[:8] == ["ffmpeg", "-i", "in.mp4", "-c:v", "libx265", "-c:a", "aac", "-threads"]
    assert "8" in cmd
    assert cmd[-2:] == ["-y", "out.mp4"]
    m_progress.assert_called_once_with(proc, duration=12.5, desc="in.mp4")
    proc.wait.assert_called_once()


def test_encode_full_video_adds_optional_video_audio_flags():
    """
    Test that optional SAR/color/audio metadata is translated into FFmpeg flags.
    """
    fake_meta = {
        "format": {"duration": "3.0"},
        "streams": [
            {
                "codec_type": "video",
                "sample_aspect_ratio": "4:3",
                "width": 1920,
                "height": 1080,
                "color_range": "tv",
            },
            {"codec_type": "audio", "sample_rate": "48000"},
        ],
    }
    proc = MagicMock()
    proc.stdout = iter([])
    proc.returncode = 0
    proc.wait.return_value = 0

    with mock.patch("video.func_video.count_cpu_threads", return_value=4), \
        mock.patch("video.func_video.get_all_metadata", return_value=fake_meta), \
        mock.patch("video.func_video.consume_ffmpeg_progress"), \
        mock.patch("video.func_video.subprocess.Popen", return_value=proc) as m_popen:

        encode_full_video("input.mp4", "output.mp4", "libx264", "aac")

    cmd = m_popen.call_args.args[0]
    assert "-vf" in cmd
    vf_idx = cmd.index("-vf")
    assert (
        "scale=1920:1080:force_original_aspect_ratio=1:force_divisible_by=2"
        in cmd[vf_idx + 1]
    )
    assert "-color_range" in cmd
    assert cmd[cmd.index("-color_range") + 1] == "tv"
    assert "-ar" in cmd
    assert cmd[cmd.index("-ar") + 1] == "48000"


def test_normalize_audio_sample_rate_adjusts_unsupported_aac_rate():
    """
    AAC accepts 11025 Hz, but not legacy camera rates like 11024 Hz.
    """
    assert normalize_audio_sample_rate("11024", "aac") == 11025
    assert normalize_audio_sample_rate("48000", "aac") == 48000
    assert normalize_audio_sample_rate("11024", "pcm_s16le") == 11024


def test_encode_full_video_adjusts_unsupported_aac_sample_rate(capsys):
    """
    Unsupported AAC sample rates should be rounded to the nearest valid rate.
    """
    fake_meta = {
        "format": {"duration": "3.0"},
        "streams": [
            {"codec_type": "video"},
            {"codec_type": "audio", "sample_rate": "11024"},
        ],
    }
    proc = MagicMock()
    proc.stdout = iter([])
    proc.returncode = 0
    proc.wait.return_value = 0

    with mock.patch("video.func_video.count_cpu_threads", return_value=4), \
        mock.patch("video.func_video.get_all_metadata", return_value=fake_meta), \
        mock.patch("video.func_video.consume_ffmpeg_progress"), \
        mock.patch("video.func_video.subprocess.Popen", return_value=proc) as m_popen:

        encode_full_video("input.avi", "output.mp4", "libx265", "aac")

    cmd = m_popen.call_args.args[0]
    assert "-ar" in cmd
    assert cmd[cmd.index("-ar") + 1] == "11025"
    assert "11024 Hz -> 11025 Hz" in capsys.readouterr().out


def test_encode_full_video_raises_when_ffmpeg_returns_non_zero():
    """
    Test that a non-zero FFmpeg return code raises CalledProcessError.
    """
    proc = MagicMock()
    proc.stdout = iter([])
    proc.returncode = 1
    proc.wait.return_value = 0

    with mock.patch("video.func_video.count_cpu_threads", return_value=2), \
        mock.patch("video.func_video.get_all_metadata", return_value={"format": {"duration": "1"}, "streams": []}), \
        mock.patch("video.func_video.consume_ffmpeg_progress"), \
        mock.patch("video.func_video.subprocess.Popen", return_value=proc):

        with pytest.raises(subprocess.CalledProcessError):
            encode_full_video("bad_in.mp4", "bad_out.mp4", "libx265", "aac")


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


############ get_all_metadata tests ############

def test_get_all_metadata_file_not_found(tmp_path):
    """Test that the function raises FileNotFoundError for missing files."""
    with pytest.raises(FileNotFoundError):
        get_all_metadata(tmp_path / "missing.mp4")


def test_get_all_metadata_success(tmp_path):
    """Test that the function returns correct metadata on success."""
    
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
            
            import subprocess


def test_get_all_metadata_ffprobe_calledprocesserror(tmp_path):
    """Test that the function raises RuntimeError on ffprobe error."""
    # Create a temporary video file
    video = tmp_path / "video.mp4"
    video.touch()

    # Prepare a CalledProcessError to be raised
    error = subprocess.CalledProcessError(
        1,
        ["ffprobe"],
        "bad stdout",
        "bad stderr"
    )

    # Patch subprocess.run to raise the error
    with mock.patch("subprocess.run", side_effect=error):
        with pytest.raises(RuntimeError) as exc:
            get_all_metadata(video)

    # Verify the exception message contains ffprobe output
    msg = str(exc.value)
    assert "Erreur ffprobe" in msg
    assert "bad stdout" in msg
    assert "bad stderr" in msg


def test_get_all_metadata_empty_stdout(tmp_path):
    """Test that the function raises RuntimeError on empty ffprobe output."""
    # Create a temporary video file
    video = tmp_path / "video.mp4"
    video.touch()

    # Prepare a fake process with empty stdout
    fake_proc = mock.Mock()
    fake_proc.stdout = ""
    fake_proc.stderr = "stderr info"

    # Patch subprocess.run to return the fake process
    with mock.patch(
        "video.func_video.subprocess.run",
        return_value=fake_proc
    ):
        with pytest.raises(RuntimeError) as exc:
            get_all_metadata(video)

    # Verify the exception message
    assert "ffprobe failed" in str(exc.value)


############ Fixtures ############

@pytest.fixture
def temp_log_file(tmp_path):
    """Create a temporary log file and a logger writing stdout into it."""
    log_file = tmp_path / "test_log.txt"
    logger = Logger(str(log_file))
    return logger, log_file


############ print_metadata_summary_all_keys tests ############

def test_print_metadata_summary_all_keys(temp_log_file):
    """
    Test print_metadata_summary_all_keys prints all metadata keys.
    """
    # Prepare logger and log file
    logger, log_file = temp_log_file

    # Replace stdout with the logger
    import sys
    original_stdout = sys.stdout
    sys.stdout = logger

    # Call the function with sample metadata
    try:
        meta = {
            "format": {"filename": "video.mp4", "duration": "10.0", "size": "123456"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080},
                {"codec_type": "audio", "codec_name": "aac", "sample_rate": 48000}
            ]
        }
        print_metadata_summary_all_keys(meta)
    finally:
        sys.stdout = original_stdout
        logger.flush()

    # Read the log file and verify content
    content = log_file.read_text(encoding="utf-8")
    assert "======= MÉTADONNÉES COMPLÈTES =======" in content
    assert "[format]" in content
    assert "[stream_0] (video)" in content
    assert "[stream_1] (audio)" in content


def test_print_metadata_summary_all_isinstance_paths(capsys):
    """Test print_metadata_summary_all_keys handles nested structures."""
    # Prepare sample metadata with nested structures
    meta = {
        "format": {
            "filename": "video.mp4",
            "tags": {
                "encoder": "ffmpeg"
            },
            "chapters": [
                {"id": 1},
                "raw_value"
            ]
        },
        "streams": [
            {
                "codec_type": "video",
                "width": 1920,
                "extra": ["a", {"b": 2}]
            },
            {
                # codec_type absent → "unknown"
                "sample_rate": 44100
            }
        ]
    }

    # Call the function
    print_metadata_summary_all_keys(meta)
    out = capsys.readouterr().out

    # ===== HEADER =====
    assert "======= MÉTADONNÉES COMPLÈTES =======" in out

    # ===== FORMAT =====
    assert "[format]" in out
    assert "- filename: video.mp4" in out
    assert "[tags]" in out
    assert "- encoder: ffmpeg" in out

    # ===== LIST HANDLING =====
    assert "[chapters]" in out
    assert "[index_0]" in out
    assert "- id: 1" in out
    assert "[index_1]" in out
    assert "raw_value" in out

    # ===== STREAMS =====
    assert "[stream_0] (video)" in out
    assert "- width: 1920" in out
    assert "[stream_1] (unknown)" in out
    assert "- sample_rate: 44100" in out


def test_print_metadata_summary_format_fallback(capsys):
    """Test print_metadata_summary_all_keys handles missing 'format' key."""
    # Prepare sample metadata without 'format' key
    meta = {
        "key": "value"
    }

    # Call the function
    print_metadata_summary_all_keys(meta)
    out = capsys.readouterr().out

    # Verify output
    assert "[format]" in out
    assert "- key: value" in out


def test_print_metadata_summary_empty_meta(capsys):
    """Test print_metadata_summary_all_keys handles empty metadata."""
    # Call the function with empty metadata
    print_metadata_summary_all_keys({})
    out = capsys.readouterr().out

    # Verify output
    assert "MÉTADONNÉES COMPLÈTES" in out
    assert "[format]" in out


############ format_value tests ############

def test_format_value_non_numeric():
    """Test that format_value returns non-numeric values unchanged."""
    assert format_value("bit_rate", "abc") == "abc"
    assert format_value("size", None) is None


def test_format_value_bit_rate():
    """Test that format_value formats bit_rate correctly."""
    assert format_value("bit_rate", 1000) == "1,000 bps"
    assert format_value("bit_rate", "2500000") == "2,500,000 bps"


def test_format_value_sample_rate():
    """Test that format_value formats sample_rate correctly."""
    assert format_value("sample_rate", 44100) == "44,100 Hz"


@pytest.mark.parametrize("key", ["width", "height", "nb_frames"])
def test_format_value_dimensions(key):
    """Test that format_value formats dimensions correctly."""
    assert format_value(key, 1920) == "1,920"


def test_format_value_duration():
    """Test that format_value formats duration correctly."""
    assert format_value("duration", 12) == "12.0 s"
    assert format_value("duration", 12.345) == "12.3 s"


def test_format_value_size():
    """Test that format_value formats size correctly."""
    assert format_value("size", 2048) == "2,048 octets"


def test_format_value_unknown_key_numeric():
    """Test that format_value returns numeric values unchanged for 
    unknown keys."""
    assert format_value("unknown_key", 1234) == 1234


############ print_metadata_diff_summary tests ############

def test_print_metadata_diff_summary(temp_log_file):
    """
    Test print_metadata_diff_summary prints differences between metadata.
    """
    # Prepare logger and log file
    logger, log_file = temp_log_file

    # Replace stdout with the logger
    import sys
    original_stdout = sys.stdout
    sys.stdout = logger

    # Call the function with sample metadata before and after
    try:
        meta_before = {
            "format": {"filename": "video.mp4", "duration": 10.0, "size": 1000, "bit_rate": 8000},
            "streams": [{"codec_type": "video", "codec_name": "h264", "width": 1280, "height": 720}]
        }
        meta_after = {
            "format": {"filename": "video.mp4", "duration": 12.0, "size": 900, "bit_rate": 7000},
            "streams": [{"codec_type": "video", "codec_name": "h265", "width": 1280, "height": 720}]
        }
        print_metadata_diff_summary(meta_before, meta_after)
    finally:
        sys.stdout = original_stdout
        logger.flush()

    # Read the log file and verify content
    content = log_file.read_text(encoding="utf-8")
    assert "======= DIFFÉRENCES MÉTADONNÉES =======" in content
    assert "duration" in content
    assert "codec_name" in content


############ compute_size_reduction tests ############

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


############ format_bytes tests ############

@pytest.mark.parametrize(
    "value,expected",
    [
        (2_500_000_000, "2.50 Go"),
        (1_000_000_000, "1.00 Go"),
        (12_345_678, "12.35 Mo"),
        (1_000_000, "1.00 Mo"),
        (12_345, "12.35 Ko"),
        (1_000, "1.00 Ko"),
        (999, "999 octets"),
        (0, "0 octets"),
    ],
)
def test_format_bytes_all_cases(value, expected):
    """Test that format_bytes formats byte sizes correctly."""
    assert format_bytes(value) == expected


############ print_size_reduction tests ############

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
    """Test that print_size_reduction handles missing data gracefully."""
    
    # Call the function with missing statistics
    print_size_reduction({})

    # Capture the printed output and verify it
    out = capsys.readouterr().out
    assert "Impossible de calculer" in out


############ to_seconds tests ############

def test_to_seconds_basic():
    assert to_seconds("00:00:10") == 10.0
    assert to_seconds("01:00:00") == 3600.0
    assert to_seconds("01:02:03") == 3723.0


def test_to_seconds_float_values():
    assert to_seconds("00:00:01.5") == 1.5


############ load_segments_csv tests ############

def test_load_segments_csv_ok(tmp_path):
    """Test loading segments from a valid CSV file."""
    # Create a temporary CSV file
    csv_file = tmp_path / "segments.csv"

    # Write sample data to the CSV file
    csv_file.write_text(
        "filename,start,end\n"
        "a.mp4,00:00:00,00:00:10\n"
        "b.mp4,00:00:05,\n",
        encoding="utf-8"
    )

    # Call the function to load segments
    segments = load_segments_csv(csv_file)

    # Verify the loaded segments
    assert len(segments) == 2
    assert segments[0]["filename"] == "a.mp4"
    assert segments[0]["start"] == 0.0
    assert segments[0]["end"] == 10.0
    assert segments[1]["end"] is None


def test_load_segments_csv_missing_file():
    """Test that loading from a missing CSV file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_segments_csv(Path("missing.csv"))


def test_load_segments_csv_invalid_columns(tmp_path):
    """Test that loading from a CSV with invalid columns raises ValueError."""
    csv_file = tmp_path / "segments.csv"
    csv_file.write_text("file,start,end\nx.mp4,0,1\n")

    with pytest.raises(ValueError):
        load_segments_csv(csv_file)


def test_load_segments_csv_end_before_start(tmp_path):
    """Test that loading from a CSV with end before start raises ValueError."""
    csv_file = tmp_path / "segments.csv"
    csv_file.write_text(
        "filename,start,end\nx.mp4,00:00:10,00:00:05\n"
    )

    with pytest.raises(ValueError):
        load_segments_csv(csv_file)


############ resolve_video_sequence tests ############

def test_resolve_sequence_with_segments(tmp_path):
    """Test resolving video sequence with valid segments."""
    # Create sample video files
    input_dir = tmp_path
    video = input_dir / "a.mp4"
    video.touch()

    # Prepare segments
    segments = [{"filename": "a.mp4", "start": 0, "end": 5}]

    # Call the function to resolve the video sequence
    seq = resolve_video_sequence(input_dir, [".mp4"], segments)

    # Verify the resolved sequence
    assert len(seq) == 1
    assert seq[0]["path"] == video


def test_resolve_sequence_missing_video(tmp_path):
    """Test that resolving with missing video raises FileNotFoundError."""
    segments = [{"filename": "missing.mp4", "start": 0, "end": 5}]

    with pytest.raises(FileNotFoundError):
        resolve_video_sequence(tmp_path, [".mp4"], segments)


def test_resolve_sequence_no_segments(tmp_path):
    """Test resolving video sequence without segments."""
    (tmp_path / "a.mp4").touch()
    (tmp_path / "b.avi").touch()

    seq = resolve_video_sequence(tmp_path, [".mp4", ".avi"], None)

    assert len(seq) == 2


def test_resolve_sequence_no_videos(tmp_path):
    """Test that resolving with no videos raises RuntimeError."""
    with pytest.raises(RuntimeError):
        resolve_video_sequence(tmp_path, [".mp4"], None)


############ load_and_trim_clip tests ############

@patch("video.func_video.VideoFileClip")
def test_load_and_trim_no_trim(mock_clip):
    """Test loading a clip without trimming."""
    clip = MagicMock(duration=10)
    mock_clip.return_value = clip

    out = load_and_trim_clip(Path("a.mp4"), None, None)

    assert out == clip


@patch("video.func_video.VideoFileClip")
def test_load_and_trim_invalid_segment(mock_clip):
    """Test that loading a clip with invalid segment raises ValueError."""
    clip = MagicMock(duration=5)
    mock_clip.return_value = clip

    with pytest.raises(ValueError):
        load_and_trim_clip(Path("a.mp4"), 3, 2)

############# normalize_audio tests ############

def test_normalize_audio():
    """Test normalize_audio processes clips correctly."""
    # Prepare mock clips
    clip_with_audio = MagicMock()
    clip_with_audio.audio = MagicMock()
    clip_with_audio.audio.reader = MagicMock()

    # Mock clip without audio
    clip_no_audio = MagicMock()
    clip_no_audio.audio = None
    clip_no_audio.without_audio.return_value = clip_no_audio

    # Call the function and verify output
    out = normalize_audio([clip_with_audio, clip_no_audio])
    assert len(out) == 2


############# write_video_file tests ############

def test_write_video_file_calls_moviepy_correctly(tmp_path):
    """Test that write_video_file calls MoviePy functions with correct
    parameters."""
    # Prepare mock clip
    input_clip = MagicMock()
    output_path = tmp_path / "out.mp4"

    # Mock count_cpu_threads
    with mock.patch("video.func_video.count_cpu_threads", return_value=4):
        write_video_file(
            final_clip=input_clip,
            output_path=output_path,
            codec_video="libx265",
            codec_audio="aac"
        )

    # Verify that write_videofile was called with correct parameters
    input_clip.write_videofile.assert_called_once_with(
        str(output_path),
        codec="libx265",
        audio_codec="aac",
        threads=4,
        logger="bar"
    )


def test_write_video_file_passes_explicit_fps_when_requested(tmp_path):
    """An explicit frame rate is forwarded to MoviePy for image clips."""
    input_clip = MagicMock()

    with mock.patch("video.func_video.count_cpu_threads", return_value=4):
        write_video_file(
            final_clip=input_clip,
            output_path=tmp_path / "out.mp4",
            codec_video="libx265",
            codec_audio="aac",
            fps=24,
        )

    assert input_clip.write_videofile.call_args.kwargs["fps"] == 24


@patch("video.func_video.subprocess.run")
@patch("video.func_video.subprocess.Popen")
@patch("video.func_video.consume_ffmpeg_progress", return_value=[])
@patch("video.func_video.get_image_size", side_effect=[(4000, 3000), (3000, 4000)])
def test_create_image_diapo_ffmpeg_preserves_ratio_with_padding(
    mock_size, mock_progress, mock_popen, mock_run, tmp_path
):
    """FFmpeg scales images to fit the frame without cropping or stretching."""
    images = [tmp_path / "a.jpg", tmp_path / "b.png"]
    audio = tmp_path / "sound.mp3"
    proc = MagicMock()
    proc.wait.return_value = 0
    mock_popen.return_value = proc
    mock_run.return_value = subprocess.CompletedProcess([], 0, "", "")

    create_image_diapo_ffmpeg(
        image_paths=images,
        input_dir=tmp_path,
        audio_path=audio,
        output_path=tmp_path / "out.mp4",
        duration=2.5,
        fps=24,
        frame_size=(1920, 1080),
        codec_video="libx265",
        codec_audio="aac",
    )

    assert mock_popen.call_count == 2
    first_segment = mock_popen.call_args_list[0].args[0]
    second_segment = mock_popen.call_args_list[1].args[0]
    assert "scale=1440:1080" in first_segment[first_segment.index("-vf") + 1]
    assert "scale=810:1080" in second_segment[second_segment.index("-vf") + 1]
    assert "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black" in first_segment[
        first_segment.index("-vf") + 1
    ]
    final_command = mock_run.call_args.args[0]
    assert "-f" in final_command and "concat" in final_command
    assert "1:a:0?" in final_command
    assert "2:s:0" in final_command
    assert final_command[final_command.index("-c:s") + 1] == "mov_text"
    assert mock_progress.call_count == 2


def test_fit_image_size_in_frame_fills_frame_height():
    """Landscape and portrait images always fill the frame height completely."""
    assert fit_image_size_in_frame((4000, 3000), (1920, 1080)) == (1440, 1080)
    assert fit_image_size_in_frame((3000, 4000), (1920, 1080)) == (810, 1080)


def test_get_image_size_applies_exif_orientation(tmp_path):
    """A rotated JPEG is sized from its displayed orientation, not raw pixels."""
    image_path = tmp_path / "rotated.jpg"
    image = Image.new("RGB", (40, 20), color="white")
    exif = image.getexif()
    exif[274] = 6  # Rotate 90° clockwise.
    image.save(image_path, exif=exif)

    assert get_image_size(image_path) == (20, 40)


def test_write_image_diapo_srt_records_each_image_timing(tmp_path):
    """The SRT file contains ordered image names and precise display ranges."""
    input_dir = tmp_path / "input"
    nested_dir = input_dir / "nested"
    nested_dir.mkdir(parents=True)
    images = [input_dir / "first.jpg", nested_dir / "second.png"]
    output_path = tmp_path / "diapo.srt"

    write_image_diapo_srt(images, input_dir, 2.5, output_path)

    assert output_path.read_text(encoding="utf-8") == (
        "1\n00:00:00,000 --> 00:00:02,500\nfirst\n\n"
        "2\n00:00:02,500 --> 00:00:05,000\nnested/second\n"
    )


def test_build_image_subtitle_keeps_only_the_first_valid_year(tmp_path):
    """Date fragments and sequence numbers are excluded from the subtitle."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    image = input_dir / "1986-08-30- (27)-Marie-Lise  - Philippe.JPG"

    assert build_image_subtitle(image, input_dir) == "1986 Marie-Lise Philippe"


def test_build_image_subtitle_rejects_year_zero_and_removes_all_digits(tmp_path):
    """Only a valid calendar year is retained."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    image = input_dir / "0000-12-31 - photo 42.png"

    assert build_image_subtitle(image, input_dir) == "photo"


############# get_inputs_metadata tests ############

def test_get_inputs_metadata_ok():
    """Test that get_inputs_metadata processes an input sequence correctly."""
    # Prepare input sequence and metadata function
    seq = [{"path": Path("a.mp4")}]
    fn = lambda p: {"format": {"filename": str(p)}}

    # Call the function
    metas = get_inputs_metadata(seq, fn)
    assert metas[0]["format"]["filename"] == "a.mp4"


def test_get_inputs_metadata_missing_path():
    """Test that get_inputs_metadata raises ValueError for missing path."""
    with pytest.raises(ValueError):
        get_inputs_metadata([{}], lambda x: {})


def test_get_inputs_metadata_wrong_type():
    """Test that get_inputs_metadata raises TypeError for wrong path type."""
    with pytest.raises(TypeError):
        get_inputs_metadata([{"path": "a.mp4"}], lambda x: {})


############# sum_input_sizes tests ############

def test_sum_input_sizes_ok(capsys):
    """Test that sum_input_sizes adds input sizes correctly."""
    # Prepare sample metadata
    metas = [
        {"format": {"filename": "a.mp4", "size": 100}},
        {"format": {"filename": "b.mp4", "size": 300}},
    ]

    # Call the function and verify the total size
    total = sum_input_sizes(metas)
    assert total == 400


def test_sum_input_sizes_invalid():
    """Test that sum_input_sizes returns None for invalid sizes."""
    metas = [{"format": {"filename": "a.mp4", "size": "x"}}]
    assert sum_input_sizes(metas) is None


############# compute_size_reduction_from_inputs tests ############

def test_compute_size_reduction_ok():
    """Test compute_size_reduction_from_inputs with valid sizes."""
    # Prepare sample metadata
    before = [
        {"format": {"size": 100}},
        {"format": {"size": 300}},
    ]
    after = {"format": {"size": 200}}

    # Call the function and verify the statistics
    stats = compute_size_reduction_from_inputs(before, after)
    assert stats["size_before"] == 400
    assert stats["size_after"] == 200
    assert stats["reduction_percent"] == 50.0


def test_compute_size_reduction_invalid():
    """Test that compute_size_reduction_from_inputs handles invalid sizes."""
    stats = compute_size_reduction_from_inputs([], {})
    assert stats["reduction_percent"] is None


@patch("video.func_video.subprocess.run")
def test_delay_positive(mock_run):
    """Test that positive delay uses `-itsoffset`."""
    shift_audio_no_reencode("input.mp4", "output.mp4", delay=0.5)
    expected_cmd = [
        "ffmpeg", "-loglevel", "error", "-y",
        "-i", "input.mp4",
        "-itsoffset", "0.5",
        "-i", "input.mp4",
        "-map", "0:v",
        "-map", "1:a",
        "-c", "copy",
        "output.mp4",
    ]
    mock_run.assert_called_once_with(expected_cmd, check=True)


@patch("video.func_video.subprocess.run")
def test_delay_negative(mock_run):
    """Test that negative delay uses `-ss`."""
    shift_audio_no_reencode("input.mp4", "output.mp4", delay=-0.5)
    expected_cmd = [
        "ffmpeg", "-loglevel", "error", "-y",
        "-i", "input.mp4",
        "-ss", "0.5",
        "-i", "input.mp4",
        "-map", "0:v",
        "-map", "1:a",
        "-c", "copy",
        "output.mp4",
    ]
    mock_run.assert_called_once_with(expected_cmd, check=True)


@patch("video.func_video.subprocess.run")
def test_delay_zero(mock_run):
    """Test that zero delay copies streams without `-itsoffset` or `-ss`."""
    shift_audio_no_reencode("input.mp4", "output.mp4", delay=0)
    expected_cmd = [
        "ffmpeg", "-loglevel", "error", "-y",
        "-i", "input.mp4",
        "-c", "copy",
        "output.mp4",
    ]
    mock_run.assert_called_once_with(expected_cmd, check=True)


@patch("video.func_video.subprocess.run")
def test_accepts_pathlib_paths(mock_run):
    """Test that shift_audio_no_reencode accepts `Path` objects."""
    shift_audio_no_reencode(Path("input.mp4"), Path("output.mp4"), delay=1.0)
    cmd_used = mock_run.call_args[0][0]
    assert "1.0" in cmd_used
    assert "-itsoffset" in cmd_used


@patch("video.func_video.subprocess.run")
def test_subprocess_called_with_check_true(mock_run):
    """Test that subprocess.run is always called with `check=True`."""
    shift_audio_no_reencode("input.mp4", "output.mp4", delay=0.5)
    _, kwargs = mock_run.call_args
    assert kwargs.get("check") is True


@patch("video.func_video.subprocess.run", side_effect=subprocess.CalledProcessError(1, "ffmpeg"))
def test_ffmpeg_error_raises(mock_run):
    """
    A FFmpeg error (non-zero exit code) raises a CalledProcessError
    exception that is not caught inside the function.
    """
    with pytest.raises(subprocess.CalledProcessError):
        shift_audio_no_reencode("input.mp4", "output.mp4", delay=0.5)


@patch("video.func_video.subprocess.run")
def test_loglevel_error_always_present(mock_run):
    """
    -loglevel error flag is always present in the ffmpeg command to
    suppress non-error output.
    """
    for delay in [1.0, -1.0, 0]:
        mock_run.reset_mock()
        shift_audio_no_reencode("input.mp4", "output.mp4", delay=delay)
        cmd_used = mock_run.call_args[0][0]
        assert "-loglevel" in cmd_used
        assert "error" in cmd_used


############# load_boost_csv tests ############

def test_load_boost_csv_ok(tmp_path):
    """Test loading valid audio boosts from CSV."""
    csv_file = tmp_path / "boosts.csv"
    csv_file.write_text(
        "start,end,gain_db\n"
        "00:00:01,00:00:03,6\n"
        "00:00:10,00:00:12,-3\n",
        encoding="utf-8",
    )

    boosts = load_boost_csv(str(csv_file))

    assert len(boosts) == 2
    assert boosts[0] == AudioBoost(start=1.0, end=3.0, gain_db=6.0)
    assert boosts[1] == AudioBoost(start=10.0, end=12.0, gain_db=-3.0)


def test_load_boost_csv_rejects_too_high_gain(tmp_path):
    """Test that gain outside +/-20 dB raises ValueError."""
    csv_file = tmp_path / "boosts.csv"
    csv_file.write_text(
        "start,end,gain_db\n"
        "00:00:01,00:00:03,25\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_boost_csv(str(csv_file))


############# apply_audio_boosts_ffmpeg tests ############

@patch("video.func_video.subprocess.run")
@patch("video.func_video.load_boost_csv")
def test_apply_audio_boosts_ffmpeg_builds_command(mock_load_boost_csv, mock_run):
    """Test FFmpeg command construction from boost segments."""
    mock_load_boost_csv.return_value = [
        AudioBoost(start=1.0, end=3.0, gain_db=6.0),
        AudioBoost(start=10.0, end=12.0, gain_db=-3.0),
    ]

    apply_audio_boosts_ffmpeg(
        input_video=Path("input.mp4"),
        output_video=Path("output.mp4"),
        csv_path="boosts.csv",
    )

    mock_load_boost_csv.assert_called_once_with("boosts.csv")
    mock_run.assert_called_once()
    cmd = mock_run.call_args.args[0]

    assert cmd[:8] == ["ffmpeg", "-loglevel", "error", "-y", "-i", "input.mp4", "-af", cmd[7]]
    assert "between(t,1.0,3.0)" in cmd[7]
    assert "volume=1.9953" in cmd[7]
    assert "between(t,10.0,12.0)" in cmd[7]
    assert "volume=0.7079" in cmd[7]
    assert cmd[-2:] == ["-c:v", "copy"] or cmd[-2:] == ["copy", "output.mp4"]
    assert cmd[-1] == "output.mp4"
    assert mock_run.call_args.kwargs["check"] is True


@patch("video.func_video.subprocess.run")
@patch("video.func_video.load_boost_csv", return_value=[])
def test_apply_audio_boosts_ffmpeg_with_no_boosts(mock_load_boost_csv, mock_run):
    """Test command still executes when no boosts are provided."""
    apply_audio_boosts_ffmpeg("input.mp4", "output.mp4", "boosts.csv")
    cmd = mock_run.call_args.args[0]
    assert "-af" in cmd
    assert cmd[cmd.index("-af") + 1] == ""


############# apply_video_srt_ffmpeg tests ############

@patch("video.func_video.subprocess.run")
def test_apply_video_srt_ffmpeg_builds_command(mock_run):
    """Test FFmpeg command construction for SRT subtitle integration."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=["ffmpeg"],
        returncode=0,
        stdout="",
        stderr="",
    )

    apply_video_srt_ffmpeg(
        input_video=Path("input.mp4"),
        output_video=Path("output.mp4"),
        srt_path=Path("subs.srt"),
    )

    mock_run.assert_called_once()
    cmd = mock_run.call_args.args[0]

    assert cmd == [
        "ffmpeg",
        "-i", "input.mp4",
        "-i", "subs.srt",
        "-c:v", "copy",
        "-c:a", "copy",
        "-c:s", "mov_text",
        "-map", "0",
        "-map", "1",
        "-y",
        "output.mp4",
    ]
    assert mock_run.call_args.kwargs["capture_output"] is True
    assert mock_run.call_args.kwargs["text"] is True
    assert mock_run.call_args.kwargs["check"] is False


@patch("video.func_video.subprocess.run")
def test_apply_video_srt_ffmpeg_raises_on_ffmpeg_error(mock_run):
    """Test that a FFmpeg failure raises CalledProcessError."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=["ffmpeg"],
        returncode=1,
        stdout="bad stdout",
        stderr="bad stderr",
    )

    with pytest.raises(subprocess.CalledProcessError):
        apply_video_srt_ffmpeg(
            input_video="input.mp4",
            output_video="output.mp4",
            srt_path="subs.srt",
        )

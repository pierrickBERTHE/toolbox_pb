"""
Unit tests for the video.func_video module.

This module contains comprehensive tests for video processing utility
functions, including CPU thread detection, video encoding, metadata extraction
and formatting, video sequence resolution, audio normalization, and file
output operations.

Test Coverage:
    - CPU Threads: Tests for detecting available CPU threads
    - Video Encoding: Tests for full video encoding with FFmpeg
    - Duration Formatting: Tests for HH:MM:SS time format conversion
    - Metadata Extraction: Tests for retrieving video metadata via ffprobe
    - Metadata Display: Tests for formatting and printing metadata summaries
    - Metadata Comparison: Tests for displaying differences between metadata
    - Value Formatting: Tests for human-readable format conversion
    - Size Reduction: Tests for computing compression statistics
    - Byte Formatting: Tests for converting bytes to human-readable units
    - Segment Loading: Tests for CSV segment file parsing and validation
    - Video Sequence: Tests for resolving video file sequences
    - Clip Operations: Tests for loading, trimming, and audio normalization
    - File Output: Tests for writing video files with specified codecs
    - Input Processing: Tests for metadata collection and size calculation
    - Video Probing: Tests for video dimensions, duration, rotation, and FPS
    - Subtitle Processing: Tests for embedded subtitle extraction and timing
    - FFmpeg Helpers: Tests for FFmpeg command execution and error handling
    - Video Normalization: Tests for source clip normalization and assembly
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
sys.path.append(str(Path(__file__).resolve().parents[2] / "toolbox_pb"))

from video.func_video import (
    AudioBoost,
    apply_audio_boosts_ffmpeg,
    apply_video_srt_ffmpeg,
    extract_video_srt_ffmpeg,
    build_image_subtitle,
    extract_date_from_filename,
    create_image_diapo_ffmpeg,
    # fit_visual_size_in_frame,
    # fit_image_size_in_frame,
    # format_srt_timestamp,
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
    get_inputs_metadata,
    sum_input_sizes,
    compute_size_reduction_from_inputs,
    shift_audio_no_reencode,
    write_image_diapo_srt,
    write_video_assemblor_date_srt,
    parse_srt_cues,
    write_video_assemblor_input_subtitles_srt,

    # Additional video utilities
    get_video_stream_frame_rates,
    prepare_video_for_assembly,
    get_video_subtitle_cues,
    _run_ffmpeg_with_progress,
    _run_ffmpeg_silently,
    safe_get,
    split_streams_by_type,
    probe_video_dimensions,
    probe_video_duration,
    probe_has_audio_stream,
    probe_video_rotation,
    probe_video_display_dimensions,
    get_video_frame_size_from_paths,
    get_video_output_fps_from_paths,
    compute_trim_duration,
    build_rotation_filter,
    probe_stream_durations,
    compute_audio_drift_correction,
    render_normalized_source_clip,
    concat_normalized_clips_ffmpeg,
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


# ============================================================================
# CPU / ENCODING
# ============================================================================


def test_count_cpu_threads(monkeypatch, capsys):
    """Test that count_cpu_threads returns the correct number and prints
    output."""

    monkeypatch.setattr("os.cpu_count", lambda: 8)

    result = count_cpu_threads()

    assert result == 8

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

    with mock.patch(
        "video.func_video.count_cpu_threads",
        return_value=8,
    ), mock.patch(
        "video.func_video.get_all_metadata",
        return_value=fake_meta,
    ), mock.patch(
        "video.func_video.consume_ffmpeg_progress"
    ) as m_progress, mock.patch(
        "video.func_video.subprocess.Popen",
        return_value=proc,
    ) as m_popen:

        encode_full_video(
            "in.mp4",
            "out.mp4",
            "libx265",
            "aac",
        )

    cmd = m_popen.call_args.args[0]

    assert cmd[:7] == [
        "ffmpeg",
        "-i",
        "in.mp4",
        "-c:v",
        "libx265",
        "-c:a",
        "aac",
    ]
    assert "8" in cmd
    assert cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"
    assert cmd[cmd.index("-profile:v") + 1] == "main"
    assert cmd[cmd.index("-colorspace") + 1] == "bt709"
    assert cmd[-2:] == ["-y", "out.mp4"]

    m_progress.assert_called_once_with(
        proc,
        duration=12.5,
        desc="in.mp4",
    )

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
            {
                "codec_type": "audio",
                "sample_rate": "48000",
            },
        ],
    }

    proc = MagicMock()
    proc.stdout = iter([])
    proc.returncode = 0
    proc.wait.return_value = 0

    with mock.patch(
        "video.func_video.count_cpu_threads",
        return_value=4,
    ), mock.patch(
        "video.func_video.get_all_metadata",
        return_value=fake_meta,
    ), mock.patch(
        "video.func_video.consume_ffmpeg_progress"
    ), mock.patch(
        "video.func_video.subprocess.Popen",
        return_value=proc,
    ) as m_popen:

        encode_full_video(
            "input.mp4",
            "output.mp4",
            "libx264",
            "aac",
        )

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
            {
                "codec_type": "audio",
                "sample_rate": "11024",
            },
        ],
    }

    proc = MagicMock()
    proc.stdout = iter([])
    proc.returncode = 0
    proc.wait.return_value = 0

    with mock.patch(
        "video.func_video.count_cpu_threads",
        return_value=4,
    ), mock.patch(
        "video.func_video.get_all_metadata",
        return_value=fake_meta,
    ), mock.patch(
        "video.func_video.consume_ffmpeg_progress"
    ), mock.patch(
        "video.func_video.subprocess.Popen",
        return_value=proc,
    ) as m_popen:

        encode_full_video(
            "input.avi",
            "output.mp4",
            "libx265",
            "aac",
        )

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

    with mock.patch(
        "video.func_video.count_cpu_threads",
        return_value=2,
    ), mock.patch(
        "video.func_video.get_all_metadata",
        return_value={
            "format": {"duration": "1"},
            "streams": [],
        },
    ), mock.patch(
        "video.func_video.consume_ffmpeg_progress"
    ), mock.patch(
        "video.func_video.subprocess.Popen",
        return_value=proc,
    ):

        with pytest.raises(subprocess.CalledProcessError):
            encode_full_video(
                "bad_in.mp4",
                "bad_out.mp4",
                "libx265",
                "aac",
            )


# ============================================================================
# DURATION / TIME FORMATTING
# ============================================================================


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


def test_to_seconds_basic():
    assert to_seconds("00:00:10") == 10.0
    assert to_seconds("01:00:00") == 3600.0
    assert to_seconds("01:02:03") == 3723.0


def test_to_seconds_float_values():
    assert to_seconds("00:00:01.5") == 1.5


# ============================================================================
# METADATA
# ============================================================================


def test_get_all_metadata_file_not_found(tmp_path):
    """Test that the function raises FileNotFoundError for missing files."""
    with pytest.raises(FileNotFoundError):
        get_all_metadata(tmp_path / "missing.mp4")


def test_get_all_metadata_success(tmp_path):
    """Test that the function returns correct metadata on success."""

    video = tmp_path / "video.mp4"
    video.touch()

    fake_output = {"format": {"duration": "10"}}

    completed = subprocess.CompletedProcess(
        args=["ffprobe"],
        returncode=0,
        stdout=json.dumps(fake_output),
        stderr="",
    )

    with mock.patch(
        "subprocess.run",
        return_value=completed,
    ):
        meta = get_all_metadata(video)

    assert meta == fake_output


def test_get_all_metadata_ffprobe_missing(tmp_path):
    """Test that the function raises RuntimeError when ffprobe is missing."""

    video = tmp_path / "video.mp4"
    video.touch()

    with mock.patch(
        "subprocess.run",
        side_effect=FileNotFoundError,
    ):
        with pytest.raises(RuntimeError):
            get_all_metadata(video)


def test_get_all_metadata_ffprobe_calledprocesserror(tmp_path):
    """Test that the function raises RuntimeError on ffprobe error."""

    video = tmp_path / "video.mp4"
    video.touch()

    error = subprocess.CalledProcessError(
        1,
        ["ffprobe"],
        "bad stdout",
        "bad stderr",
    )

    with mock.patch(
        "subprocess.run",
        side_effect=error,
    ):
        with pytest.raises(RuntimeError) as exc:
            get_all_metadata(video)

    msg = str(exc.value)

    assert "Erreur ffprobe" in msg
    assert "bad stdout" in msg
    assert "bad stderr" in msg


def test_get_all_metadata_empty_stdout(tmp_path):
    """Test that the function raises RuntimeError on empty ffprobe output."""

    video = tmp_path / "video.mp4"
    video.touch()

    fake_proc = mock.Mock()
    fake_proc.stdout = ""
    fake_proc.stderr = "stderr info"

    with mock.patch(
        "video.func_video.subprocess.run",
        return_value=fake_proc,
    ):
        with pytest.raises(RuntimeError) as exc:
            get_all_metadata(video)

    assert "ffprobe failed" in str(exc.value)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def temp_log_file(tmp_path):
    """Create a temporary log file and a logger writing stdout into it."""
    log_file = tmp_path / "test_log.txt"
    logger = Logger(str(log_file))
    return logger, log_file


# ============================================================================
# METADATA DISPLAY
# ============================================================================


def test_print_metadata_summary_all_keys(temp_log_file):
    """
    Test print_metadata_summary_all_keys prints all metadata keys.
    """
    logger, log_file = temp_log_file

    original_stdout = sys.stdout
    sys.stdout = logger

    try:
        meta = {
            "format": {
                "filename": "video.mp4",
                "duration": "10.0",
                "size": "123456",
            },
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080,
                },
                {
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "sample_rate": 48000,
                },
            ],
        }

        print_metadata_summary_all_keys(meta)

    finally:
        sys.stdout = original_stdout
        logger.flush()

    content = log_file.read_text(encoding="utf-8")

    assert "======= MÉTADONNÉES COMPLÈTES =======" in content
    assert "[format]" in content
    assert "[stream_0] (video)" in content
    assert "[stream_1] (audio)" in content


def test_print_metadata_summary_all_isinstance_paths(capsys):
    """Test print_metadata_summary_all_keys handles nested structures."""

    meta = {
        "format": {
            "filename": "video.mp4",
            "tags": {
                "encoder": "ffmpeg",
            },
            "chapters": [
                {"id": 1},
                "raw_value",
            ],
        },
        "streams": [
            {
                "codec_type": "video",
                "width": 1920,
                "extra": ["a", {"b": 2}],
            },
            {
                "sample_rate": 44100,
            },
        ],
    }

    print_metadata_summary_all_keys(meta)

    out = capsys.readouterr().out

    assert "======= MÉTADONNÉES COMPLÈTES =======" in out
    assert "[format]" in out
    assert "- filename: video.mp4" in out
    assert "[tags]" in out
    assert "- encoder: ffmpeg" in out
    assert "[chapters]" in out
    assert "[index_0]" in out
    assert "- id: 1" in out
    assert "[index_1]" in out
    assert "raw_value" in out
    assert "[stream_0] (video)" in out
    assert "- width: 1920" in out
    assert "[stream_1] (unknown)" in out
    assert "- sample_rate: 44100" in out


def test_print_metadata_summary_format_fallback(capsys):
    """Test print_metadata_summary_all_keys handles missing 'format' key."""

    meta = {"key": "value"}

    print_metadata_summary_all_keys(meta)

    out = capsys.readouterr().out

    assert "[format]" in out
    assert "- key: value" in out


def test_print_metadata_summary_empty_meta(capsys):
    """Test print_metadata_summary_all_keys handles empty metadata."""

    print_metadata_summary_all_keys({})

    out = capsys.readouterr().out

    assert "MÉTADONNÉES COMPLÈTES" in out
    assert "[format]" in out


def test_print_metadata_diff_summary(temp_log_file):
    """
    Test print_metadata_diff_summary prints differences between metadata.
    """
    logger, log_file = temp_log_file

    original_stdout = sys.stdout
    sys.stdout = logger

    try:
        meta_before = {
            "format": {
                "filename": "video.mp4",
                "duration": 10.0,
                "size": 1000,
                "bit_rate": 8000,
            },
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1280,
                    "height": 720,
                }
            ],
        }

        meta_after = {
            "format": {
                "filename": "video.mp4",
                "duration": 12.0,
                "size": 900,
                "bit_rate": 7000,
            },
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h265",
                    "width": 1280,
                    "height": 720,
                }
            ],
        }

        print_metadata_diff_summary(
            meta_before,
            meta_after,
        )

    finally:
        sys.stdout = original_stdout
        logger.flush()

    content = log_file.read_text(encoding="utf-8")

    assert "======= DIFFÉRENCES MÉTADONNÉES =======" in content
    assert "duration" in content
    assert "codec_name" in content


# ============================================================================
# VALUE / SIZE FORMATTING
# ============================================================================


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


@pytest.mark.parametrize(
    "key",
    ["width", "height", "nb_frames"],
)
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


def test_print_size_reduction_nominal(capsys):
    """Test that print_size_reduction prints correct output."""

    stats = {
        "size_before": 1_000_000,
        "size_after": 500_000,
        "reduction_percent": 50.0,
        "compression_factor": 2.0,
    }

    print_size_reduction(stats)

    out = capsys.readouterr().out

    assert "Réduction" in out
    assert "Mo" in out


def test_print_size_reduction_missing_data(capsys):
    """Test that print_size_reduction handles missing data gracefully."""

    print_size_reduction({})

    out = capsys.readouterr().out

    assert "Impossible de calculer" in out


# ============================================================================
# SIZE REDUCTION
# ============================================================================


def test_compute_size_reduction_nominal():
    """Test compute_size_reduction with valid sizes."""

    before = {"format": {"size": "1000"}}
    after = {"format": {"size": "500"}}

    stats = compute_size_reduction(before, after)

    assert stats["size_before"] == 1000
    assert stats["size_after"] == 500
    assert stats["reduction_percent"] == 50.0
    assert stats["compression_factor"] == 2.0


def test_compute_size_reduction_invalid_sizes():
    """Test that compute_size_reduction handles missing size data."""

    stats = compute_size_reduction({}, {})

    assert stats["size_before"] is None
    assert stats["reduction_percent"] is None


def test_compute_size_reduction_zero_before():
    """Test that compute_size_reduction handles zero size before encoding."""

    stats = compute_size_reduction(
        {"format": {"size": "0"}},
        {"format": {"size": "100"}},
    )

    assert stats["compression_factor"] is None


# ============================================================================
# SEGMENTS / CSV
# ============================================================================


def test_load_segments_csv_ok(tmp_path):
    """Test loading segments from a valid CSV file."""

    csv_file = tmp_path / "segments.csv"

    csv_file.write_text(
        "filename,start,end\n"
        "a.mp4,00:00:00,00:00:10\n"
        "b.mp4,00:00:05,\n",
        encoding="utf-8",
    )

    segments = load_segments_csv(csv_file)

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

    csv_file.write_text(
        "file,start,end\nx.mp4,0,1\n"
    )

    with pytest.raises(ValueError):
        load_segments_csv(csv_file)


def test_load_segments_csv_end_before_start(tmp_path):
    """Test that loading with end before start raises ValueError."""

    csv_file = tmp_path / "segments.csv"

    csv_file.write_text(
        "filename,start,end\n"
        "x.mp4,00:00:10,00:00:05\n"
    )

    with pytest.raises(ValueError):
        load_segments_csv(csv_file)


# ============================================================================
# VIDEO SEQUENCE
# ============================================================================


def test_resolve_sequence_with_segments(tmp_path):
    """Test resolving video sequence with valid segments."""

    input_dir = tmp_path
    video = input_dir / "a.mp4"
    video.touch()

    segments = [
        {
            "filename": "a.mp4",
            "start": 0,
            "end": 5,
        }
    ]

    seq = resolve_video_sequence(
        input_dir,
        [".mp4"],
        segments,
    )

    assert len(seq) == 1
    assert seq[0]["path"] == video


def test_resolve_sequence_missing_video(tmp_path):
    """Test that resolving with missing video raises FileNotFoundError."""

    segments = [
        {
            "filename": "missing.mp4",
            "start": 0,
            "end": 5,
        }
    ]

    with pytest.raises(FileNotFoundError):
        resolve_video_sequence(
            tmp_path,
            [".mp4"],
            segments,
        )


def test_resolve_sequence_no_segments(tmp_path):
    """Test resolving video sequence without segments."""

    (tmp_path / "a.mp4").touch()
    (tmp_path / "b.avi").touch()

    seq = resolve_video_sequence(
        tmp_path,
        [".mp4", ".avi"],
        None,
    )

    assert len(seq) == 2


def test_resolve_sequence_no_videos(tmp_path):
    """Test that resolving with no videos raises RuntimeError."""

    with pytest.raises(RuntimeError):
        resolve_video_sequence(
            tmp_path,
            [".mp4"],
            None,
        )


# ============================================================================
# IMAGE / DIAPORAMA / SRT
# ============================================================================


def test_get_image_size_applies_exif_orientation(tmp_path):
    """A rotated JPEG is sized from its displayed orientation, not raw pixels."""

    image_path = tmp_path / "rotated.jpg"

    image = Image.new(
        "RGB",
        (40, 20),
        color="white",
    )

    exif = image.getexif()
    exif[274] = 6

    image.save(
        image_path,
        exif=exif,
    )

    assert get_image_size(image_path) == (20, 40)


def test_write_image_diapo_srt_records_each_image_timing(tmp_path):
    """The SRT file contains ordered image names and precise display ranges."""

    input_dir = tmp_path / "input"
    nested_dir = input_dir / "nested"

    nested_dir.mkdir(parents=True)

    images = [
        input_dir / "first.jpg",
        nested_dir / "second.png",
    ]

    output_path = tmp_path / "diapo.srt"

    write_image_diapo_srt(
        images,
        input_dir,
        2.5,
        output_path,
    )

    assert output_path.read_text(encoding="utf-8") == (
        "1\n"
        "00:00:00,000 --> 00:00:02,500\n"
        "first\n\n"
        "2\n"
        "00:00:02,500 --> 00:00:05,000\n"
        "nested/second\n"
    )

# ===========================================================================
# VIDEO ASSEMBLOR DATE SRT
# ===========================================================================


def test_write_video_assemblor_date_srt_success(tmp_path):
    # Write one subtitle cue for each dated clip with the correct timeline offset.
    sequence = [
        {"path": Path("IMG_20240115.jpg")},
        {"path": Path("IMG_20240220.jpg")},
    ]

    clip1 = MagicMock(duration=5.0)
    clip2 = MagicMock(duration=8.0)

    output_path = tmp_path / "dates.srt"

    result = write_video_assemblor_date_srt(
        sequence,
        [clip1, clip2],
        output_path,
        display_duration=3.0,
    )

    assert result is True
    assert output_path.exists()

    content = output_path.read_text(encoding="utf-8")

    assert "1\n00:00:00,000 --> 00:00:03,000" in content
    assert "2\n00:00:05,000 --> 00:00:08,000" in content
    assert "15/01/2024" in content
    assert "20/02/2024" in content


def test_write_video_assemblor_date_srt_clip_without_date(tmp_path):
    # Clips without a valid date must not create a subtitle,
    # but their full duration must still be included in the timeline offset.
    sequence = [
        {"path": Path("undated_image.jpg")},
        {"path": Path("IMG_20240220.jpg")},
    ]

    clip1 = MagicMock(duration=5.0)
    clip2 = MagicMock(duration=8.0)

    output_path = tmp_path / "dates.srt"

    result = write_video_assemblor_date_srt(
        sequence,
        [clip1, clip2],
        output_path,
        display_duration=3.0,
    )

    assert result is True

    content = output_path.read_text(encoding="utf-8")

    assert "1\n00:00:05,000 --> 00:00:08,000" in content
    assert "20/02/2024" in content
    assert "undated_image" not in content


def test_write_video_assemblor_date_srt_no_valid_dates(tmp_path):
    # Return False and do not create a file when no clip has a valid date.
    sequence = [
        {"path": Path("first_image.jpg")},
        {"path": Path("second_image.png")},
    ]

    clip1 = MagicMock(duration=5.0)
    clip2 = MagicMock(duration=8.0)

    output_path = tmp_path / "dates.srt"

    result = write_video_assemblor_date_srt(
        sequence,
        [clip1, clip2],
        output_path,
        display_duration=3.0,
    )

    assert result is False
    assert not output_path.exists()


def test_write_video_assemblor_date_srt_mismatched_lengths(tmp_path):
    # The sequence and clips lists must have the same length.
    sequence = [
        {"path": "IMG_20240115.jpg"},
        {"path": "IMG_20240220.jpg"},
    ]

    clips = [MagicMock(duration=5.0)]

    output_path = tmp_path / "dates.srt"

    with pytest.raises(
        ValueError,
        match="La séquence et les clips doivent avoir la même longueur.",
    ):
        write_video_assemblor_date_srt(
            sequence,
            clips,
            output_path,
            display_duration=3.0,
        )


def test_write_video_assemblor_date_srt_invalid_display_duration(tmp_path):
    # The subtitle display duration must be strictly positive.
    sequence = [{"path": "IMG_20240115.jpg"}]
    clips = [MagicMock(duration=5.0)]

    output_path = tmp_path / "dates.srt"

    with pytest.raises(
        ValueError,
        match="La durée d'affichage des sous-titres doit être positive.",
    ):
        write_video_assemblor_date_srt(
            sequence,
            clips,
            output_path,
            display_duration=0,
        )


@pytest.mark.parametrize(
    "duration",
    [None, 0, -1, "5"],
)
def test_write_video_assemblor_date_srt_invalid_clip_duration(
    tmp_path,
    duration,
):
    # Every clip must expose a strictly positive numeric duration.
    sequence = [{"path": "IMG_20240115.jpg"}]
    clips = [MagicMock(duration=duration)]

    output_path = tmp_path / "dates.srt"

    with pytest.raises(
        ValueError,
        match="Chaque clip doit avoir une durée positive.",
    ):
        write_video_assemblor_date_srt(
            sequence,
            clips,
            output_path,
            display_duration=3.0,
        )


def test_write_video_assemblor_date_srt_display_duration_longer_than_clip(
    tmp_path,
):
    # The subtitle must end at the clip end when display_duration
    # is longer than the clip duration.
    sequence = [
        {"path": Path("IMG_20240115.jpg")},
    ]

    clips = [MagicMock(duration=2.0)]

    output_path = tmp_path / "dates.srt"

    result = write_video_assemblor_date_srt(
        sequence,
        clips,
        output_path,
        display_duration=5.0,
    )

    assert result is True

    content = output_path.read_text(encoding="utf-8")

    assert "00:00:00,000 --> 00:00:02,000" in content
    assert "15/01/2024" in content


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("2024-07-03 vacances.mp4", "03/07/2024"),
        ("04_12_2023 anniversaire.mov", "04/12/2023"),
        ("20240105_video.mp4", "05/01/2024"),
        ("2024-99-44 invalide.mp4", None),
    ],
)
def test_extract_date_from_filename(filename, expected):
    """Video filename dates are validated then displayed in French order."""

    assert extract_date_from_filename(
        Path(filename)
    ) == expected


def test_parse_srt_cues_keeps_multiline_text_and_dot_separator():
    """Input subtitle content is normalised without losing text."""

    assert parse_srt_cues(
        "1\n"
        "00:00:01.250 --> 00:00:03,500\n"
        "Bonjour\n"
        "sur deux lignes\n"
    ) == [
        (
            1250,
            3500,
            "Bonjour\nsur deux lignes",
        )
    ]


@patch("video.func_video.get_video_subtitle_cues")
def test_input_subtitles_are_clipped_and_shifted_for_assembly(
    mock_cues,
    tmp_path,
):
    """Existing cues keep the correct timing after trimming and concatenation."""

    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"

    mock_cues.side_effect = [
        [
            (1_000, 4_000, "premier"),
            (8_000, 12_000, "hors segment"),
        ],
        [
            (0, 2_000, "second"),
        ],
    ]

    sequence = [
        {
            "path": first,
            "start": 2.0,
            "end": 6.0,
        },
        {
            "path": second,
            "start": None,
            "end": None,
        },
    ]

    clips = [
        MagicMock(duration=4.0),
        MagicMock(duration=6.0),
    ]

    output_path = tmp_path / "preserved.srt"
    temporary_dir = tmp_path / "temporary"
    temporary_dir.mkdir()

    assert write_video_assemblor_input_subtitles_srt(
        sequence,
        clips,
        output_path,
        temporary_dir,
    ) is True

    assert output_path.read_text(
        encoding="utf-8"
    ) == (
        "1\n"
        "00:00:00,000 --> 00:00:02,000\n"
        "premier\n\n"
        "2\n"
        "00:00:04,000 --> 00:00:06,000\n"
        "second\n"
    )


def test_build_image_subtitle_keeps_only_the_first_valid_year(tmp_path):
    """Date fragments are excluded while unrelated numbers are retained."""

    input_dir = tmp_path / "input"
    input_dir.mkdir()

    image = (
        input_dir
        / "1986-08-30- (27)-Marie-Lise  - Philippe.JPG"
    )

    assert build_image_subtitle(
        image,
        input_dir,
    ) == "1986 (27) Marie-Lise Philippe"


def test_build_image_subtitle_removes_month_from_partial_date_only(tmp_path):
    """A partial year-month date does not hide later numeric text."""

    input_dir = tmp_path / "input"
    input_dir.mkdir()

    image = (
        input_dir
        / "2022-02 anniv 60 ans Pierre.jpg"
    )

    assert build_image_subtitle(
        image,
        input_dir,
    ) == "2022 anniv 60 ans Pierre"


def test_build_image_subtitle_preserves_numbers_that_are_not_a_valid_date(
    tmp_path,
):
    """A number is retained unless it is the month or day of a valid year."""

    input_dir = tmp_path / "input"
    input_dir.mkdir()

    image = (
        input_dir
        / "0000-12-31 - photo 42.png"
    )

    assert build_image_subtitle(
        image,
        input_dir,
    ) == "0000-12-31 photo 42"


def test_build_image_subtitle_preserves_an_age(tmp_path):
    """Ordinary numbers in a filename are displayed in the subtitle."""

    input_dir = tmp_path / "input"
    input_dir.mkdir()

    image = input_dir / "anniv 60 ans Pierre.jpg"

    assert build_image_subtitle(
        image,
        input_dir,
    ) == "anniv 60 ans Pierre"


# ============================================================================
# INPUT METADATA
# ============================================================================


def test_get_inputs_metadata_ok():
    """Test that get_inputs_metadata processes an input sequence correctly."""

    seq = [{"path": Path("a.mp4")}]

    fn = lambda p: {
        "format": {
            "filename": str(p)
        }
    }

    metas = get_inputs_metadata(
        seq,
        fn,
    )

    assert metas[0]["format"]["filename"] == "a.mp4"


def test_get_inputs_metadata_missing_path():
    """Test that get_inputs_metadata raises ValueError for missing path."""

    with pytest.raises(ValueError):
        get_inputs_metadata(
            [{}],
            lambda x: {},
        )


def test_get_inputs_metadata_wrong_type():
    """Test that get_inputs_metadata raises TypeError for wrong path type."""

    with pytest.raises(TypeError):
        get_inputs_metadata(
            [{"path": "a.mp4"}],
            lambda x: {},
        )


def test_sum_input_sizes_ok(capsys):
    """Test that sum_input_sizes adds input sizes correctly."""

    metas = [
        {
            "format": {
                "filename": "a.mp4",
                "size": 100,
            }
        },
        {
            "format": {
                "filename": "b.mp4",
                "size": 300,
            }
        },
    ]

    total = sum_input_sizes(metas)

    assert total == 400


def test_sum_input_sizes_invalid():
    """Test that sum_input_sizes returns None for invalid sizes."""

    metas = [
        {
            "format": {
                "filename": "a.mp4",
                "size": "x",
            }
        }
    ]

    assert sum_input_sizes(metas) is None


def test_compute_size_reduction_from_inputs_ok():
    """Test compute_size_reduction_from_inputs with valid sizes."""

    before = [
        {"format": {"size": 100}},
        {"format": {"size": 300}},
    ]

    after = {
        "format": {
            "size": 200
        }
    }

    stats = compute_size_reduction_from_inputs(
        before,
        after,
    )

    assert stats["size_before"] == 400
    assert stats["size_after"] == 200
    assert stats["reduction_percent"] == 50.0


def test_compute_size_reduction_from_inputs_invalid():
    """Test compute_size_reduction_from_inputs handles invalid sizes."""

    stats = compute_size_reduction_from_inputs(
        [],
        {},
    )

    assert stats["reduction_percent"] is None


# ============================================================================
# AUDIO DELAY
# ============================================================================


@patch("video.func_video.subprocess.run")
def test_delay_positive(mock_run):
    """Test that positive delay uses `-itsoffset`."""

    shift_audio_no_reencode(
        "input.mp4",
        "output.mp4",
        delay=0.5,
    )

    expected_cmd = [
        "ffmpeg",
        "-loglevel",
        "error",
        "-y",
        "-i",
        "input.mp4",
        "-itsoffset",
        "0.5",
        "-i",
        "input.mp4",
        "-map",
        "0:v",
        "-map",
        "1:a",
        "-c",
        "copy",
        "output.mp4",
    ]

    mock_run.assert_called_once_with(
        expected_cmd,
        check=True,
    )


@patch("video.func_video.subprocess.run")
def test_delay_negative(mock_run):
    """Test that negative delay uses `-ss`."""

    shift_audio_no_reencode(
        "input.mp4",
        "output.mp4",
        delay=-0.5,
    )

    expected_cmd = [
        "ffmpeg",
        "-loglevel",
        "error",
        "-y",
        "-i",
        "input.mp4",
        "-ss",
        "0.5",
        "-i",
        "input.mp4",
        "-map",
        "0:v",
        "-map",
        "1:a",
        "-c",
        "copy",
        "output.mp4",
    ]

    mock_run.assert_called_once_with(
        expected_cmd,
        check=True,
    )


@patch("video.func_video.subprocess.run")
def test_delay_zero(mock_run):
    """Test that zero delay copies streams without `-itsoffset` or `-ss`."""

    shift_audio_no_reencode(
        "input.mp4",
        "output.mp4",
        delay=0,
    )

    expected_cmd = [
        "ffmpeg",
        "-loglevel",
        "error",
        "-y",
        "-i",
        "input.mp4",
        "-c",
        "copy",
        "output.mp4",
    ]

    mock_run.assert_called_once_with(
        expected_cmd,
        check=True,
    )


@patch("video.func_video.subprocess.run")
def test_accepts_pathlib_paths(mock_run):
    """Test that shift_audio_no_reencode accepts Path objects."""

    shift_audio_no_reencode(
        Path("input.mp4"),
        Path("output.mp4"),
        delay=1.0,
    )

    cmd_used = mock_run.call_args[0][0]

    assert "1.0" in cmd_used
    assert "-itsoffset" in cmd_used


@patch("video.func_video.subprocess.run")
def test_subprocess_called_with_check_true(mock_run):
    """Test that subprocess.run is always called with check=True."""

    shift_audio_no_reencode(
        "input.mp4",
        "output.mp4",
        delay=0.5,
    )

    _, kwargs = mock_run.call_args

    assert kwargs.get("check") is True


@patch(
    "video.func_video.subprocess.run",
    side_effect=subprocess.CalledProcessError(
        1,
        "ffmpeg",
    ),
)
def test_ffmpeg_error_raises(mock_run):
    """
    A FFmpeg error raises a CalledProcessError exception.
    """

    with pytest.raises(subprocess.CalledProcessError):
        shift_audio_no_reencode(
            "input.mp4",
            "output.mp4",
            delay=0.5,
        )


@patch("video.func_video.subprocess.run")
def test_loglevel_error_always_present(mock_run):
    """
    -loglevel error is always present in the FFmpeg command.
    """

    for delay in [1.0, -1.0, 0]:
        mock_run.reset_mock()

        shift_audio_no_reencode(
            "input.mp4",
            "output.mp4",
            delay=delay,
        )

        cmd_used = mock_run.call_args[0][0]

        assert "-loglevel" in cmd_used
        assert "error" in cmd_used


# ============================================================================
# AUDIO BOOST
# ============================================================================


def test_load_boost_csv_ok(tmp_path):
    """Test loading valid audio boosts from CSV."""

    csv_file = tmp_path / "boosts.csv"

    csv_file.write_text(
        "start,end,gain_db\n"
        "00:00:01,00:00:03,6\n"
        "00:00:10,00:00:12,-3\n",
        encoding="utf-8",
    )

    boosts = load_boost_csv(
        str(csv_file)
    )

    assert len(boosts) == 2

    assert boosts[0] == AudioBoost(
        start=1.0,
        end=3.0,
        gain_db=6.0,
    )

    assert boosts[1] == AudioBoost(
        start=10.0,
        end=12.0,
        gain_db=-3.0,
    )


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


@patch("video.func_video.subprocess.run")
@patch("video.func_video.load_boost_csv")
def test_apply_audio_boosts_ffmpeg_builds_command(
    mock_load_boost_csv,
    mock_run,
):
    """Test FFmpeg command construction from boost segments."""

    mock_load_boost_csv.return_value = [
        AudioBoost(
            start=1.0,
            end=3.0,
            gain_db=6.0,
        ),
        AudioBoost(
            start=10.0,
            end=12.0,
            gain_db=-3.0,
        ),
    ]

    apply_audio_boosts_ffmpeg(
        input_video=Path("input.mp4"),
        output_video=Path("output.mp4"),
        csv_path="boosts.csv",
    )

    mock_load_boost_csv.assert_called_once_with(
        "boosts.csv"
    )

    mock_run.assert_called_once()

    cmd = mock_run.call_args.args[0]

    assert cmd[:8] == [
        "ffmpeg",
        "-loglevel",
        "error",
        "-y",
        "-i",
        "input.mp4",
        "-af",
        cmd[7],
    ]

    assert "between(t,1.0,3.0)" in cmd[7]
    assert "volume=1.9953" in cmd[7]
    assert "between(t,10.0,12.0)" in cmd[7]
    assert "volume=0.7079" in cmd[7]

    assert cmd[-1] == "output.mp4"
    assert mock_run.call_args.kwargs["check"] is True


@patch("video.func_video.subprocess.run")
@patch(
    "video.func_video.load_boost_csv",
    return_value=[],
)
def test_apply_audio_boosts_ffmpeg_with_no_boosts(
    mock_load_boost_csv,
    mock_run,
):
    """Test command still executes when no boosts are provided."""

    apply_audio_boosts_ffmpeg(
        "input.mp4",
        "output.mp4",
        "boosts.csv",
    )

    cmd = mock_run.call_args.args[0]

    assert "-af" in cmd
    assert cmd[cmd.index("-af") + 1] == ""


# ============================================================================
# VIDEO SRT INTEGRATION
# ============================================================================


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
        "-i",
        "input.mp4",
        "-i",
        "subs.srt",
        "-c:v",
        "copy",
        "-c:a",
        "copy",
        "-c:s",
        "mov_text",
        "-map",
        "0",
        "-map",
        "1",
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
        


# ============================================================================
# VIDEO SRT EXTRACTION
# ===========================================================================

def test_extract_video_srt_ffmpeg_success(tmp_path, monkeypatch, capsys):
    # A subtitle stream is detected and extracted in a single FFmpeg pass.
    input_video = tmp_path / "input.mp4"
    output_video = tmp_path / "output_without_subtitles.mp4"
    srt_output = tmp_path / "subtitles.srt"

    input_video.touch()

    subprocess_run_mock = MagicMock(
        side_effect=[
            # ffprobe: subtitle stream index found.
            MagicMock(
                stdout="2\n",
                stderr="",
                returncode=0,
            ),
            # ffmpeg: extraction succeeds.
            MagicMock(
                stdout="",
                stderr="",
                returncode=0,
            ),
        ]
    )

    monkeypatch.setattr(
        "video.func_video.subprocess.run",
        subprocess_run_mock,
    )

    extract_video_srt_ffmpeg(
        str(input_video),
        str(output_video),
        str(srt_output),
    )

    assert subprocess_run_mock.call_count == 2

    # Verify ffprobe command.
    probe_cmd = subprocess_run_mock.call_args_list[0].args[0]

    assert probe_cmd[:8] == [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "s",
        "-show_entries",
        "stream=index",
        "-of",
    ]
    assert probe_cmd[-1] == str(input_video)

    # Verify FFmpeg command.
    ffmpeg_cmd = subprocess_run_mock.call_args_list[1].args[0]

    assert ffmpeg_cmd == [
        "ffmpeg",
        "-i",
        str(input_video),
        "-map",
        "0:v",
        "-map",
        "0:a?",
        "-c",
        "copy",
        "-y",
        str(output_video),
        "-map",
        "0:s:0",
        "-c:s",
        "srt",
        "-y",
        str(srt_output),
    ]

    captured = capsys.readouterr()

    assert "Sous-titres extraits" in captured.out
    assert "Vidéo sans sous-titres" in captured.out


def test_extract_video_srt_ffmpeg_no_subtitle_stream(
tmp_path,
monkeypatch,
capsys,
):
    # Videos without subtitle streams must remain untouched.
    input_video = tmp_path / "input.mp4"
    output_video = tmp_path / "output.mp4"
    srt_output = tmp_path / "subtitles.srt"

    input_video.touch()

    subprocess_run_mock = MagicMock(
        return_value=MagicMock(
            stdout="",
            stderr="",
            returncode=0,
        )
    )

    monkeypatch.setattr(
        "video.func_video.subprocess.run",
        subprocess_run_mock,
    )

    extract_video_srt_ffmpeg(
        str(input_video),
        str(output_video),
        str(srt_output),
    )

    subprocess_run_mock.assert_called_once()

    captured = capsys.readouterr()

    assert "Aucun sous-titre à extraire" in captured.out


def test_extract_video_srt_ffmpeg_probe_error(
    tmp_path,
    monkeypatch,
):
    # ffprobe failures must be propagated to the caller.
    input_video = tmp_path / "input.mp4"
    output_video = tmp_path / "output.mp4"
    srt_output = tmp_path / "subtitles.srt"

    input_video.touch()

    error = subprocess.CalledProcessError(
        returncode=1,
        cmd=["ffprobe"],
    )

    monkeypatch.setattr(
        "video.func_video.subprocess.run",
        MagicMock(side_effect=error),
    )

    with pytest.raises(subprocess.CalledProcessError):
        extract_video_srt_ffmpeg(
            str(input_video),
            str(output_video),
            str(srt_output),
        )


# ============================================================================
# ADDITIONAL VIDEO UTILITY COVERAGE
# ============================================================================


def test_get_video_stream_frame_rates(tmp_path, monkeypatch):
    """Test extraction of declared and average video frame rates."""

    video = tmp_path / "video.mp4"
    video.touch()

    fake_result = subprocess.CompletedProcess(
        args=["ffprobe"],
        returncode=0,
        stdout=json.dumps({
            "streams": [{
                "codec_type": "video",
                "r_frame_rate": "30000/1001",
                "avg_frame_rate": "25/1",
            }]
        }),
        stderr="",
    )

    monkeypatch.setattr(
        "video.func_video.subprocess.run",
        lambda *args, **kwargs: fake_result,
    )

    declared, declared_fps, average = (
        get_video_stream_frame_rates(video)
    )

    assert declared == "30000/1001"
    assert declared_fps == pytest.approx(30000 / 1001)
    assert average == 25.0


def test_get_video_stream_frame_rates_without_video_stream(
    tmp_path,
    monkeypatch,
):
    """Test frame-rate probing when no video stream is present."""

    video = tmp_path / "audio.mp4"
    video.touch()

    result = subprocess.CompletedProcess(
        args=["ffprobe"],
        returncode=0,
        stdout=json.dumps({
            "streams": [{
                "codec_type": "audio",
            }]
        }),
        stderr="",
    )

    monkeypatch.setattr(
        "video.func_video.subprocess.run",
        lambda *args, **kwargs: result,
    )

    declared, declared_fps, average = (
        get_video_stream_frame_rates(video)
    )

    assert declared is None
    assert declared_fps is None
    assert average is None


def test_safe_get():
    # safe_get returns the provided default for missing or falsy values.
    data = {
        "existing": "value",
        "zero": 0,
        "empty": "",
        "false": False,
        "none": None,
    }

    assert safe_get(data, ["existing"], "default") == "value"
    assert safe_get(data, ["missing"], "default") == "default"
    assert safe_get(data, ["zero"], "default") == "default"
    assert safe_get(data, ["empty"], "default") == "default"
    assert safe_get(data, ["false"], "default") == "default"
    assert safe_get(data, ["none"], "default") == "default"


def test_split_streams_by_type():
    # split_streams_by_type groups streams according to the supported stream types.
    streams = [
        {"codec_type": "video", "index": 0},
        {"codec_type": "audio", "index": 1},
        {"codec_type": "video", "index": 2},
        {"codec_type": "audio", "index": 3},
    ]

    result = split_streams_by_type(streams)

    assert result["video"] == [
        {"codec_type": "video", "index": 0},
        {"codec_type": "video", "index": 2},
    ]
    assert result["audio"] == [
        {"codec_type": "audio", "index": 1},
        {"codec_type": "audio", "index": 3},
    ]


# ============================================================================
# PREPARATION FOR VIDEO ASSEMBLY
# ============================================================================


def test_prepare_video_for_assembly_does_not_reencode_normal_fps(
    tmp_path,
    monkeypatch,
):
    # A normal declared/average FPS ratio should keep the original file.
    video_path = tmp_path / "input.mp4"
    video_path.touch()

    monkeypatch.setattr(
        "video.func_video.get_video_stream_frame_rates",
        lambda path: ("30/1", 30.0, 30.0),
    )

    run_ffmpeg_mock = MagicMock()
    monkeypatch.setattr(
        "video.func_video._run_ffmpeg_silently",
        run_ffmpeg_mock,
    )

    result = prepare_video_for_assembly(
        video_path=video_path,
        temporary_dir=tmp_path,
        index=0,
        codec_video="libx264",
        codec_audio="aac",
    )

    assert result == video_path
    run_ffmpeg_mock.assert_not_called()


def test_prepare_video_for_assembly_reencodes_abnormal_declared_fps(
    tmp_path,
    monkeypatch,
):
    # A significantly higher declared FPS should trigger CFR normalization.
    video_path = tmp_path / "input.mp4"
    video_path.touch()

    monkeypatch.setattr(
        "video.func_video.get_video_stream_frame_rates",
        lambda path: ("60/1", 60.0, 30.0),
    )

    run_ffmpeg_mock = MagicMock()
    monkeypatch.setattr(
        "video.func_video._run_ffmpeg_silently",
        run_ffmpeg_mock,
    )

    result = prepare_video_for_assembly(
        video_path=video_path,
        temporary_dir=tmp_path,
        index=0,
        codec_video="libx264",
        codec_audio="aac",
    )

    assert result != video_path
    assert result.suffix == ".mp4"
    run_ffmpeg_mock.assert_called_once()


# ============================================================================
# SUBTITLE EXTRACTION
# ============================================================================


def test_get_video_subtitle_cues_without_subtitles(
    tmp_path,
    monkeypatch,
):
    """Test subtitle extraction when no subtitle stream exists."""

    video = tmp_path / "video.mp4"
    video.touch()

    monkeypatch.setattr(
        "video.func_video.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=["ffprobe"],
            returncode=0,
            stdout=json.dumps({
                "streams": []
            }),
            stderr="",
        ),
    )

    result = get_video_subtitle_cues(
        video,
        tmp_path,
    )

    assert result == []


def test_get_video_subtitle_cues_with_subtitle_stream(
    tmp_path,
    monkeypatch,
):
    """Test extraction of an embedded subtitle stream."""

    video = tmp_path / "video.mp4"
    video.touch()

    ffprobe_result = subprocess.CompletedProcess(
        args=["ffprobe"],
        returncode=0,
        stdout=json.dumps({
            "streams": [{
                "index": 2,
                "codec_type": "subtitle",
            }]
        }),
        stderr="",
    )

    def fake_run(command, *args, **kwargs):
        if command[0] == "ffprobe":
            return ffprobe_result

        output = Path(command[-1])

        output.write_text(
            "1\n"
            "00:00:01,000 --> 00:00:02,000\n"
            "Bonjour\n",
            encoding="utf-8",
        )

        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(
        "video.func_video.subprocess.run",
        fake_run,
    )

    result = get_video_subtitle_cues(
        video,
        tmp_path,
    )

    assert result
    assert result[0][0] == 1000
    assert result[0][1] == 2000
    assert result[0][2] == "Bonjour"


# ============================================================================
# FFMPEG EXECUTION HELPERS
# ============================================================================


def test_run_ffmpeg_with_progress_success(monkeypatch):
    """Test successful FFmpeg execution with progress reporting."""

    process = MagicMock()

    process.stdout = iter([
        "out_time_ms=1000000\n",
        "out_time_ms=2000000\n",
    ])

    process.wait.return_value = 0
    process.returncode = 0

    progress = MagicMock()

    monkeypatch.setattr(
        "video.func_video.subprocess.Popen",
        lambda *args, **kwargs: process,
    )

    monkeypatch.setattr(
        "video.func_video.consume_ffmpeg_progress",
        progress,
    )

    _run_ffmpeg_with_progress(
        [
            "ffmpeg",
            "-i",
            "input.mp4",
            "output.mp4",
        ],
        10.0,
        "test",
    )

    progress.assert_called_once()


def test_run_ffmpeg_with_progress_failure(monkeypatch):
    # The progress runner should raise when ffmpeg exits with a non-zero code.
    class FakeStdout:
        def __init__(self):
            self.lines = iter(
                [
                    "out_time_ms=1000000\n",
                    "ffmpeg error\n",
                ]
            )

        def readline(self):
            try:
                return next(self.lines)
            except StopIteration:
                return ""

    process = MagicMock()
    process.stdout = FakeStdout()
    process.returncode = 1
    process.wait.return_value = 1

    monkeypatch.setattr(
        "video.func_video.subprocess.Popen",
        MagicMock(return_value=process),
    )

    with pytest.raises(subprocess.CalledProcessError):
        _run_ffmpeg_with_progress(
            ["ffmpeg", "-i", "input.mp4"],
            duration=10.0,
            desc="Test",
        )


def test_run_ffmpeg_silently_success(monkeypatch):
    """Test successful silent FFmpeg execution."""

    monkeypatch.setattr(
        "video.func_video.subprocess.run",
        MagicMock(
            return_value=subprocess.CompletedProcess(
                args=["ffmpeg"],
                returncode=0,
                stdout="",
                stderr="",
            )
        ),
    )

    _run_ffmpeg_silently(
        ["ffmpeg", "-version"]
    )


def test_run_ffmpeg_silently_failure(monkeypatch):
    """Test silent FFmpeg execution failure."""

    monkeypatch.setattr(
        "video.func_video.subprocess.run",
        MagicMock(
            side_effect=subprocess.CalledProcessError(
                1,
                ["ffmpeg"],
                stderr="failure",
            )
        ),
    )

    with pytest.raises(subprocess.CalledProcessError):
        _run_ffmpeg_silently(
            ["ffmpeg", "bad"]
        )


# ============================================================================
# VIDEO PROBING
# ============================================================================


def test_probe_video_dimensions(tmp_path, monkeypatch):
    """Test extraction of raw video dimensions."""

    video = tmp_path / "video.mp4"
    video.touch()

    monkeypatch.setattr(
        "video.func_video.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=json.dumps({
                "streams": [{
                    "codec_type": "video",
                    "width": 1920,
                    "height": 1080,
                }]
            }),
            stderr="",
        ),
    )

    assert probe_video_dimensions(video) == (
        1920,
        1080,
    )


def test_probe_video_duration(monkeypatch):
    # ffprobe returns duration through the format section.
    ffprobe_output = {
        "format": {
            "duration": "12.5",
        }
    }

    monkeypatch.setattr(
        "video.func_video.subprocess.run",
        MagicMock(
            return_value=MagicMock(
                stdout=json.dumps(ffprobe_output),
                returncode=0,
            )
        ),
    )

    result = probe_video_duration(Path("video.mp4"))

    assert result == pytest.approx(12.5)


def test_probe_has_audio_stream(tmp_path, monkeypatch):
    """Test detection of an audio stream."""

    video = tmp_path / "video.mp4"
    video.touch()

    monkeypatch.setattr(
        "video.func_video.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="audio\n",
            stderr="",
        ),
    )

    assert probe_has_audio_stream(video) is True


def test_probe_has_audio_stream_without_audio(
    tmp_path,
    monkeypatch,
):
    """Test audio detection when no audio stream exists."""

    video = tmp_path / "video.mp4"
    video.touch()

    monkeypatch.setattr(
        "video.func_video.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="",
            stderr="",
        ),
    )

    assert probe_has_audio_stream(video) is False


# ============================================================================
# ROTATION
# ============================================================================


@pytest.mark.parametrize(
    "rotation,expected",
    [
        (0, None),
        (90, "transpose=2"),
        (180, "transpose=1,transpose=1"),
        (270, "transpose=1"),
        (360, None),
    ],
)
def test_build_rotation_filter(rotation, expected):
    # Rotation values are converted to the ffmpeg transpose filters used
    # by the implementation.
    assert build_rotation_filter(rotation) == expected


def test_probe_video_rotation_from_side_data(monkeypatch):
    # ffprobe returns the rotation value expected by the helper.
    monkeypatch.setattr(
        "video.func_video.subprocess.run",
        MagicMock(
            return_value=MagicMock(
                stdout="90\n",
                returncode=0,
            )
        ),
    )

    result = probe_video_rotation(Path("video.mp4"))

    assert result == pytest.approx(90.0)


def test_probe_video_rotation_from_legacy_tag(monkeypatch):
    # Legacy rotation metadata is normalized to the [0, 360) range.
    monkeypatch.setattr(
        "video.func_video.subprocess.run",
        MagicMock(
            return_value=MagicMock(
                stdout="-90\n",
                returncode=0,
            )
        ),
    )

    result = probe_video_rotation(Path("video.mp4"))

    assert result == pytest.approx(270.0)




def test_probe_video_display_dimensions_rotated(
    tmp_path,
    monkeypatch,
):
    """Test displayed dimensions for a rotated video."""

    video = tmp_path / "video.mp4"
    video.touch()

    monkeypatch.setattr(
        "video.func_video.probe_video_dimensions",
        lambda _: (1920, 1080),
    )

    monkeypatch.setattr(
        "video.func_video.probe_video_rotation",
        lambda _: 90,
    )

    assert probe_video_display_dimensions(video) == (
        1080,
        1920,
    )


def test_probe_video_display_dimensions_without_rotation(
    tmp_path,
    monkeypatch,
):
    """Test displayed dimensions without rotation."""

    video = tmp_path / "video.mp4"
    video.touch()

    monkeypatch.setattr(
        "video.func_video.probe_video_dimensions",
        lambda _: (1920, 1080),
    )

    monkeypatch.setattr(
        "video.func_video.probe_video_rotation",
        lambda _: 0,
    )

    assert probe_video_display_dimensions(video) == (
        1920,
        1080,
    )


# ============================================================================
# MULTI-VIDEO FRAME SIZE / FPS
# ============================================================================


def test_get_video_frame_size_from_paths(
    tmp_path,
    monkeypatch,
):
    """Test computation of the common assembly frame size."""

    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"

    first.touch()
    second.touch()

    values = {
        first: (1920, 1080),
        second: (1280, 720),
    }

    monkeypatch.setattr(
        "video.func_video.probe_video_display_dimensions",
        lambda path: values[path],
    )

    width, height = get_video_frame_size_from_paths(
        [first, second]
    )

    assert height == 1080
    assert width == 1920


def test_get_video_output_fps_from_paths(
    tmp_path,
    monkeypatch,
):
    """Test selection of the highest average input FPS."""

    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"

    first.touch()
    second.touch()

    values = {
        first: (
            "25/1",
            25.0,
            25.0,
        ),
        second: (
            "30000/1001",
            29.97,
            29.97,
        ),
    }

    monkeypatch.setattr(
        "video.func_video.get_video_stream_frame_rates",
        lambda path: values[path],
    )

    assert get_video_output_fps_from_paths(
        [first, second]
    ) == pytest.approx(29.97)


# ============================================================================
# TRIMMING / AUDIO DRIFT
# ============================================================================


@pytest.mark.parametrize(
    ("start", "end", "duration", "expected"),
    [
        (0, None, 10.0, 10.0),
        (2, None, 10.0, 8.0),
        (2, 7, 10.0, 5.0),
        (0, 10, 10.0, 10.0),
    ],
)
def test_compute_trim_duration(
    tmp_path,
    monkeypatch,
    start,
    end,
    duration,
    expected,
):
    """Test duration computation for different trim configurations."""

    video = tmp_path / "video.mp4"
    video.touch()

    monkeypatch.setattr(
        "video.func_video.probe_video_duration",
        lambda _: duration,
    )

    assert compute_trim_duration(
        video,
        start,
        end,
    ) == expected


def test_probe_stream_durations(monkeypatch):
    # Stream durations are extracted from the ffprobe stream list.
    ffprobe_output = {
        "streams": [
            {
                "codec_type": "video",
                "duration": "10.5",
            },
            {
                "codec_type": "audio",
                "duration": "10.2",
            },
        ]
    }

    monkeypatch.setattr(
        "video.func_video.subprocess.run",
        MagicMock(
            return_value=MagicMock(
                stdout=json.dumps(ffprobe_output),
                returncode=0,
            )
        ),
    )

    result = probe_stream_durations(Path("video.mp4"))

    assert result[0] == pytest.approx(10.5)
    assert result[1] == pytest.approx(10.2)


def test_compute_audio_drift_correction_no_correction(monkeypatch):
    # Equal video and audio durations require no correction.
    monkeypatch.setattr(
        "video.func_video.probe_stream_durations",
        lambda path: (10.0, 10.0),
    )

    result = compute_audio_drift_correction(
        Path("video.mp4")
    )

    assert result is None


def test_compute_audio_drift_correction_valid_ratio(monkeypatch):
    # A duration mismatch produces an audio correction ratio.
    monkeypatch.setattr(
        "video.func_video.probe_stream_durations",
        lambda path: (10.0, 10.2),
    )

    result = compute_audio_drift_correction(
        Path("video.mp4")
    )

    assert result == pytest.approx(10.2 / 10.0)


def test_compute_audio_drift_correction_invalid_ratio(monkeypatch):
    # A zero video duration does not require a correction.
    monkeypatch.setattr(
        "video.func_video.probe_stream_durations",
        lambda path: (0.0, 10.0),
    )

    result = compute_audio_drift_correction(
        Path("video.mp4")
    )

    assert result is None


# ============================================================================
# NORMALIZED SOURCE CLIPS
# ============================================================================


def test_render_normalized_source_clip_without_audio(
    tmp_path,
    monkeypatch,
):
    # The ffprobe helpers are mocked so the test only covers command construction.
    prepared_path = tmp_path / "input.mp4"
    output_path = tmp_path / "output.mp4"
    prepared_path.touch()

    monkeypatch.setattr(
        "video.func_video.probe_video_duration",
        lambda path: 10.0,
    )

    monkeypatch.setattr(
        "video.func_video.probe_video_rotation",
        lambda path: 0.0,
    )

    monkeypatch.setattr(
        "video.func_video.probe_video_display_dimensions",
        lambda path: (1920, 1080),
    )

    monkeypatch.setattr(
        "video.func_video.probe_has_audio_stream",
        lambda path: False,
    )

    ffmpeg_mock = MagicMock()

    monkeypatch.setattr(
        "video.func_video._run_ffmpeg_with_progress",
        ffmpeg_mock,
    )

    result = render_normalized_source_clip(
        prepared_path,
        0.0,
        10.0,
        (1920, 1080),
        30.0,
        "libx264",
        "aac",
        output_path,
    )

    assert result == pytest.approx(10.0)
    ffmpeg_mock.assert_called_once()


def test_render_normalized_source_clip_with_audio_drift(
    tmp_path,
    monkeypatch,
):
    # Audio drift correction is exercised when audio and video durations differ.
    prepared_path = tmp_path / "input.mp4"
    output_path = tmp_path / "output.mp4"
    prepared_path.touch()

    monkeypatch.setattr(
        "video.func_video.probe_video_duration",
        lambda path: 10.0,
    )

    monkeypatch.setattr(
        "video.func_video.probe_video_rotation",
        lambda path: 0.0,
    )

    monkeypatch.setattr(
        "video.func_video.probe_video_display_dimensions",
        lambda path: (1920, 1080),
    )

    monkeypatch.setattr(
        "video.func_video.probe_has_audio_stream",
        lambda path: True,
    )

    monkeypatch.setattr(
        "video.func_video.probe_stream_durations",
        lambda path: (10.0, 10.2),
    )

    ffmpeg_mock = MagicMock()

    monkeypatch.setattr(
        "video.func_video._run_ffmpeg_with_progress",
        ffmpeg_mock,
    )

    result = render_normalized_source_clip(
        prepared_path,
        0.0,
        10.0,
        (1920, 1080),
        30.0,
        "libx264",
        "aac",
        output_path,
    )

    assert result == pytest.approx(10.0)
    ffmpeg_mock.assert_called_once()


# ============================================================================
# CONCATENATION
# ============================================================================


def test_concat_normalized_clips_without_subtitles(
    tmp_path,
    monkeypatch,
):
    """Test concatenation of normalized clips without subtitles."""

    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    output = tmp_path / "output.mp4"

    first.touch()
    second.touch()

    run_ffmpeg = MagicMock()

    monkeypatch.setattr(
        "video.func_video._run_ffmpeg_silently",
        run_ffmpeg,
    )

    concat_normalized_clips_ffmpeg(
        [first, second],
        [],
        output,
        "test comment",
    )

    assert run_ffmpeg.call_count >= 1

    commands = [
        call.args[0]
        for call in run_ffmpeg.call_args_list
    ]

    assert any(
        "concat" in " ".join(command)
        for command in commands
    )


def test_concat_normalized_clips_with_subtitles(
    tmp_path,
    monkeypatch,
):
    """Test concatenation of normalized clips with subtitles."""

    first = tmp_path / "first.mp4"
    subtitle = tmp_path / "first.srt"
    output = tmp_path / "output.mp4"

    first.touch()

    subtitle.write_text(
        "1\n"
        "00:00:00,000 --> 00:00:01,000\n"
        "Bonjour\n",
        encoding="utf-8",
    )

    run_ffmpeg = MagicMock()

    monkeypatch.setattr(
        "video.func_video._run_ffmpeg_silently",
        run_ffmpeg,
    )

    concat_normalized_clips_ffmpeg(
        [first],
        [subtitle],
        output,
        "test",
    )

    assert run_ffmpeg.called

    command_text = " ".join(
        run_ffmpeg.call_args.args[0]
    )

    assert "mov_text" in command_text


# ============================================================================
# IMAGE DIAPORAMA FFMPEG
# ============================================================================


def test_create_image_diapo_ffmpeg_builds_segments(
    tmp_path,
    monkeypatch,
):
    """Test FFmpeg command construction for an image slideshow."""

    input_dir = tmp_path / "images"
    input_dir.mkdir()

    image1 = input_dir / "first.jpg"
    image2 = input_dir / "second.jpg"

    Image.new(
        "RGB",
        (800, 600),
        "white",
    ).save(image1)

    Image.new(
        "RGB",
        (1200, 600),
        "white",
    ).save(image2)

    output = tmp_path / "output.mp4"

    run_ffmpeg = MagicMock()

    monkeypatch.setattr(
        "video.func_video._run_ffmpeg_silently",
        run_ffmpeg,
    )

    monkeypatch.setattr(
        "video.func_video._run_ffmpeg_with_progress",
        run_ffmpeg,
    )

    create_image_diapo_ffmpeg(
        [image1, image2],
        input_dir,
        None,
        output,
        2.0,
        25.0,
        (1920, 1080),
        "libx264",
        "aac",
    )

    assert run_ffmpeg.called


# ============================================================================
# ERROR BRANCHES
# ============================================================================


def test_get_video_stream_frame_rates_invalid_ffprobe(
    tmp_path,
    monkeypatch,
):
    """Test propagation of an FFprobe failure during FPS probing."""

    video = tmp_path / "video.mp4"
    video.touch()

    monkeypatch.setattr(
        "video.func_video.subprocess.run",
        MagicMock(
            side_effect=subprocess.CalledProcessError(
                1,
                ["ffprobe"],
                stderr="ffprobe error",
            )
        ),
    )

    with pytest.raises(subprocess.CalledProcessError):
        get_video_stream_frame_rates(video)


def test_probe_video_dimensions_without_video_stream(monkeypatch):
    # A file without a video stream returns the implementation's
    # empty-dimension result.
    ffprobe_output = {
        "streams": [
            {
                "codec_type": "audio",
                "duration": "10.0",
            }
        ]
    }

    monkeypatch.setattr(
        "video.func_video.subprocess.run",
        MagicMock(
            return_value=MagicMock(
                stdout=json.dumps(ffprobe_output),
                returncode=0,
            )
        ),
    )

    result = probe_video_dimensions(Path("audio_only.mp4"))

    assert result is None


def test_probe_video_duration_invalid_output(
    tmp_path,
    monkeypatch,
):
    """Test probing duration when FFprobe returns invalid data."""

    video = tmp_path / "video.mp4"
    video.touch()

    monkeypatch.setattr(
        "video.func_video.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="not-a-duration",
            stderr="",
        ),
    )

    with pytest.raises((ValueError, RuntimeError)):
        probe_video_duration(video)

"""Tests for the low-level MP3 compression helpers."""

from pathlib import Path
import os
import sys
from unittest import mock

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2] / "toolbox_pb"))

from audio.func_audio import (
    build_audio_processing_comment,
    compress_audio_to_mp3,
    copy_star_rating,
    find_audio_files,
    probe_audio_bitrate_kbps,
    read_audio_comment,
    write_id3_processing_comment,
)


def test_find_audio_files_is_recursive_and_sorted(tmp_path):
    """Only accepted audio files are returned in stable relative-path order."""
    (tmp_path / "B.MP3").touch()
    nested = tmp_path / "album"
    nested.mkdir()
    (nested / "A.flac").touch()
    (tmp_path / "notes.txt").touch()

    assert find_audio_files(tmp_path, [".mp3", ".flac"]) == [
        nested / "A.flac", tmp_path / "B.MP3"
    ]


def test_compress_audio_uses_mp3_and_copies_global_metadata(tmp_path):
    """FFmpeg must preserve tags and add the toolbox processing comment."""
    source = tmp_path / "song.flac"
    output = tmp_path / "output" / "song.mp3"
    source.touch()

    with mock.patch("audio.func_audio.subprocess.run") as run:
        compress_audio_to_mp3(source, output, 160, "toolbox_pb :\nn_1 : audio_compressor")

    command = run.call_args.args[0]
    assert ["-map_metadata", "0"] == command[command.index("-map_metadata"):command.index("-map_metadata") + 2]
    assert ["-c:a", "libmp3lame"] == command[command.index("-c:a"):command.index("-c:a") + 2]
    assert ["-b:a", "160k"] == command[command.index("-b:a"):command.index("-b:a") + 2]
    assert output.parent.is_dir()


def test_compress_audio_preserves_source_modification_time(tmp_path):
    """The completed MP3 keeps the source file's modification timestamp."""
    source = tmp_path / "song.flac"
    output = tmp_path / "output" / "song.mp3"
    source.write_bytes(b"source")
    os.utime(source, ns=(source.stat().st_atime_ns, 1_700_000_000_123_456_789))
    stored_source_mtime_ns = source.stat().st_mtime_ns

    def write_output(*_args, **_kwargs):
        output.write_bytes(b"mp3")

    with mock.patch("audio.func_audio.subprocess.run", side_effect=write_output):
        compress_audio_to_mp3(source, output, 160, "comment")

    assert output.stat().st_mtime_ns == stored_source_mtime_ns


def test_read_audio_comment_reads_standard_file_metadata(tmp_path):
    """MP3 comments are stored on the file metadata object."""
    source = tmp_path / "song.mp3"
    source.touch()
    probe_result = mock.Mock(stdout='{"format": {"tags": {"comment": "history"}}}')

    with mock.patch("audio.func_audio.subprocess.run", return_value=probe_result):
        assert read_audio_comment(source) == "history"


def test_read_audio_comment_uses_stream_tag_and_ignores_probe_errors(tmp_path):
    source = tmp_path / "song.mp3"
    stream_result = mock.Mock(
        stdout='{"streams": [{"tags": {"comment": "stream history"}}]}'
    )

    with mock.patch("audio.func_audio.subprocess.run", return_value=stream_result):
        assert read_audio_comment(source) == "stream history"
    with mock.patch(
        "audio.func_audio.subprocess.run", side_effect=FileNotFoundError
    ):
        assert read_audio_comment(source) is None


def test_build_audio_processing_comment_delegates_to_shared_history_builder(tmp_path):
    source = tmp_path / "song.flac"

    with mock.patch(
        "audio.func_audio.build_video_processing_comment", return_value="history"
    ) as builder:
        assert build_audio_processing_comment(source, 192) == "history"

    builder.assert_called_once_with(
        source, "audio_compressor | MP3 : 192 kb/s", audio_codec="libmp3lame"
    )


@pytest.mark.parametrize(
    ("stdout", "expected"),
    [
        ('{"format": {"bit_rate": "192000"}}', 192.0),
        ('{"format": {}}', None),
        ("not json", None),
    ],
)
def test_probe_audio_bitrate_kbps_handles_valid_missing_and_invalid_values(
    tmp_path, stdout, expected
):
    result = mock.Mock(stdout=stdout)

    with mock.patch("audio.func_audio.subprocess.run", return_value=result):
        assert probe_audio_bitrate_kbps(tmp_path / "song.mp3") == expected


def test_copy_star_rating_preserves_popm_frames(tmp_path):
    source = tmp_path / "source.mp3"
    output = tmp_path / "output.mp3"
    rating = mock.Mock(email="rating@example.test", rating=196, count=12)
    input_audio = mock.Mock(tags={"POPM:rating@example.test": rating})
    output_audio = mock.Mock()
    output_audio.tags = mock.Mock()
    copied_frame = object()

    with mock.patch("audio.func_audio.open_audio_file", return_value=input_audio), \
        mock.patch("audio.func_audio.MP3", return_value=output_audio), \
        mock.patch("audio.func_audio.POPM", return_value=copied_frame) as popm:
        copy_star_rating(source, output)

    output_audio.tags.delall.assert_called_once_with("POPM")
    popm.assert_called_once_with(
        email="rating@example.test", rating=196, count=12
    )
    output_audio.tags.add.assert_called_once_with(copied_frame)
    output_audio.save.assert_called_once_with(v2_version=3)


def test_copy_star_rating_ignores_unreadable_files_and_missing_tags(tmp_path):
    source = tmp_path / "source.mp3"
    output = tmp_path / "output.mp3"

    with mock.patch("audio.func_audio.open_audio_file", side_effect=OSError):
        assert copy_star_rating(source, output) is None

    with mock.patch("audio.func_audio.open_audio_file", return_value=None), \
        mock.patch("audio.func_audio.MP3") as output_constructor:
        assert copy_star_rating(source, output) is None

    output_constructor.assert_called_once_with(output)


def test_write_id3_processing_comment_creates_a_windows_visible_comment(tmp_path):
    output = tmp_path / "output.mp3"
    output_audio = mock.Mock()
    output_audio.tags = mock.Mock()
    comment_frame = object()

    with mock.patch("audio.func_audio.MP3", return_value=output_audio), \
        mock.patch("audio.func_audio.COMM", return_value=comment_frame) as comm:
        write_id3_processing_comment(output, "history")

    output_audio.tags.delall.assert_called_once_with("COMM")
    comm.assert_called_once_with(encoding=1, lang="fra", desc="", text="history")
    output_audio.tags.add.assert_called_once_with(comment_frame)
    output_audio.save.assert_called_once_with(v1=1, v2_version=3)


def test_write_id3_processing_comment_handles_tag_write_errors(tmp_path, capsys):
    output = tmp_path / "output.mp3"

    with mock.patch("audio.func_audio.MP3", side_effect=OSError("locked")):
        write_id3_processing_comment(output, "history")

    assert "Commentaire ID3 non écrit : output.mp3 (locked)" in capsys.readouterr().out


def test_compress_audio_rejects_invalid_bitrate(tmp_path):
    with pytest.raises(ValueError, match="AUDIO_COMPRESSOR_MP3_BITRATE_KBPS"):
        compress_audio_to_mp3(tmp_path / "source.flac", tmp_path / "output.mp3", 0, "")

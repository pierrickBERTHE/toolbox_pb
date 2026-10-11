"""Workflow tests for audio_compressor."""

from pathlib import Path
import sys
from unittest import mock

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2] / "toolbox_pb"))

from audio.main_audio import audio_compressor
from config_global import AppConfig


@pytest.fixture
def audio_config(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    return AppConfig(
        INPUT_ACCEPTED_VIDEO_FILES=[".mp4"],
        INPUT_ACCEPTED_IMAGE_FILES=[".jpg"],
        INPUT_ACCEPTED_PDF_FILES=[".pdf"],
        CODEC_VIDEO_LIST=["libx264"], CODEC_VIDEO="libx264", CODEC_AUDIO="aac",
        SUFFIX_OUTPUT=[".mp4", ".jpg", ".pdf"],
        SUFFIX_OUTPUT_VIDEO=".mp4", SUFFIX_OUTPUT_IMAGE=".jpg", SUFFIX_OUTPUT_PDF=".pdf",
        ROOT=tmp_path, LOG_DIR=tmp_path / "log", INPUT_DIR=input_dir,
        OUTPUT_DIR=output_dir, SEGMENT_DIR=tmp_path / "segment",
        INPUT_ACCEPTED_AUDIO_FILES=[".mp3", ".flac"],
        AUDIO_COMPRESSOR_MP3_BITRATE_KBPS=128,
        LOG_TO_FILE=False,
    )


def test_audio_compressor_writes_mp3_in_matching_subdirectory(audio_config):
    album = audio_config.INPUT_DIR / "album"
    album.mkdir()
    source = album / "song.flac"
    source.write_bytes(b"original audio")

    def fake_compress(**kwargs):
        kwargs["output_path"].write_bytes(b"mp3")

    with mock.patch("audio.main_audio.compress_audio_to_mp3", side_effect=fake_compress) as compress, \
        mock.patch("audio.main_audio.build_audio_processing_comment", return_value="comment"):
        assert audio_compressor(audio_config) is False

    assert compress.call_args.kwargs["bitrate_kbps"] == 128
    assert (audio_config.OUTPUT_DIR / "album" / "song.mp3").read_bytes() == b"mp3"


def test_audio_compressor_leaves_existing_output_unchanged(audio_config, capsys):
    """An existing output is neither re-encoded nor amended with metadata."""
    source = audio_config.INPUT_DIR / "song.flac"
    output = audio_config.OUTPUT_DIR / "song.mp3"
    source.write_bytes(b"source")
    output.write_bytes(b"existing mp3")

    with mock.patch("audio.main_audio.compress_audio_to_mp3") as compress:
        assert audio_compressor(audio_config) is False

    compress.assert_not_called()
    assert output.read_bytes() == b"existing mp3"
    assert "MP3 déjà traité : song.flac" in capsys.readouterr().out


def test_audio_compressor_rejects_non_positive_bitrate(audio_config):
    invalid_config = audio_config.__class__(**{
        **audio_config.__dict__, "AUDIO_COMPRESSOR_MP3_BITRATE_KBPS": 0,
    })
    with pytest.raises(ValueError, match="AUDIO_COMPRESSOR_MP3_BITRATE_KBPS"):
        audio_compressor(invalid_config)


def test_audio_compressor_copies_source_at_or_below_configured_bitrate(audio_config, capsys):
    """An equal-or-lower bitrate MP3 is copied unchanged."""
    source = audio_config.INPUT_DIR / "already_small.mp3"
    source.write_bytes(b"source")

    with mock.patch("audio.main_audio.probe_audio_bitrate_kbps", return_value=128):
        assert audio_compressor(audio_config) is False

    assert (audio_config.OUTPUT_DIR / "already_small.mp3").read_bytes() == b"source"
    assert "Copié intact (débit source 128 kb/s inférieur ou égal" in capsys.readouterr().out


def test_audio_compressor_optionally_copies_jpeg_from_audio_folder(audio_config):
    """Album JPEG artwork is copied only when the configuration flag is enabled."""
    album = audio_config.INPUT_DIR / "album"
    album.mkdir()
    audio_file = album / "song.mp3"
    cover_file = album / "cover.jpg"
    audio_file.write_bytes(b"source")
    cover_file.write_bytes(b"jpeg")
    enabled_config = audio_config.__class__(**{
        **audio_config.__dict__, "AUDIO_COMPRESSOR_COPY_JPEG_FILES": True,
    })

    with mock.patch("audio.main_audio.probe_audio_bitrate_kbps", return_value=96):
        audio_compressor(enabled_config)

    assert (enabled_config.OUTPUT_DIR / "album" / "cover.jpg").read_bytes() == b"jpeg"


def test_audio_compressor_prefers_named_cover_over_albumart_cache(audio_config):
    """Only the user-visible cover is copied when a folder has many JPEG files."""
    album = audio_config.INPUT_DIR / "album"
    album.mkdir()
    (album / "song.mp3").write_bytes(b"source")
    (album / "AlbumArtSmall.jpg").write_bytes(b"cache")
    (album / "Folder.jpg").write_bytes(b"folder")
    (album / "Jaquette Album.jpg").write_bytes(b"cover")
    enabled_config = audio_config.__class__(**{
        **audio_config.__dict__, "AUDIO_COMPRESSOR_COPY_JPEG_FILES": True,
    })

    with mock.patch("audio.main_audio.probe_audio_bitrate_kbps", return_value=96):
        audio_compressor(enabled_config)

    output_album = enabled_config.OUTPUT_DIR / "album"
    assert (output_album / "Jaquette Album.jpg").read_bytes() == b"cover"
    assert not (output_album / "AlbumArtSmall.jpg").exists()
    assert not (output_album / "Folder.jpg").exists()

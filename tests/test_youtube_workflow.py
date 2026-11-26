"""Tests for the shared YouTube post-download workflow."""

from dataclasses import replace
from pathlib import Path
from unittest import mock

import pytest

from toolbox_pb.core.web.main_web import YouTubeDownloadOptions
from toolbox_pb.core.config_global import APP_CONFIG
from toolbox_pb.ui import youtube_workflow as workflow


def _config(output_dir: Path):
    return replace(
        APP_CONFIG,
        OUTPUT_DIR=output_dir,
        YOUTUBE_VIDEO_ENCODOR_MIN_EXPECTED_SAVINGS_PERCENT=10.0,
        YOUTUBE_VIDEO_ENCODOR_TARGET_TOTAL_BITRATE_KBPS_BY_HEIGHT=(
            (720, 1_500),
            (1080, 2_800),
        ),
    )


def _options(output_dir: Path, media_format: str = "MP3") -> YouTubeDownloadOptions:
    return YouTubeDownloadOptions(
        url="https://youtu.be/example",
        output_dir=output_dir,
        media_format=media_format,
    )


def test_run_youtube_download_reports_mp3_bitrate_difference(monkeypatch, tmp_path):
    downloaded = tmp_path / "song_download.mp3"
    downloaded.write_bytes(b"mp3")
    emitted = []
    monkeypatch.setattr(workflow, "download_youtube_media", lambda _: [downloaded])
    monkeypatch.setattr(workflow, "probe_audio_bitrate_kbps", lambda _: 128)
    monkeypatch.setattr(workflow, "emit", lambda message, **_: emitted.append(message))

    assert workflow.run_youtube_download(_options(tmp_path), _config(tmp_path)) is False
    assert "Débit audio demandé" in emitted[0]


def test_run_youtube_download_finds_files_when_downloader_has_no_result(
    monkeypatch, tmp_path
):
    downloaded = tmp_path / "video_download.mp4"
    emitted = []
    monkeypatch.setattr(
        workflow,
        "download_youtube_media",
        lambda _: downloaded.write_bytes(b"mp4"),
    )
    monkeypatch.setattr(
        workflow,
        "_youtube_video_specs",
        lambda _: ("h264", "specifications", 720),
    )
    monkeypatch.setattr(
        workflow,
        "encode_downloaded_youtube_videos",
        lambda files, _: files == [downloaded],
    )
    monkeypatch.setattr(
        workflow, "emit", lambda message, **_: emitted.append(message)
    )

    assert workflow.run_youtube_download(_options(tmp_path, "MP4"), _config(tmp_path)) is True
    assert emitted == ["\nspecifications", "Définition demandée : 1080p indisponible ; définition utilisée : 720p."]


def test_run_youtube_download_recovers_media_after_optional_subtitle_error(
    monkeypatch, tmp_path
):
    downloaded = tmp_path / "song_download.mp3"

    def fail_after_creating_media(_):
        downloaded.write_bytes(b"mp3")
        raise ValueError("Unable to download video subtitles: HTTP Error 429")

    emitted = []
    monkeypatch.setattr(workflow, "download_youtube_media", fail_after_creating_media)
    monkeypatch.setattr(workflow, "probe_audio_bitrate_kbps", lambda _: 160)
    monkeypatch.setattr(
        workflow, "emit", lambda message, **_: emitted.append(message)
    )

    assert workflow.run_youtube_download(_options(tmp_path), _config(tmp_path)) is False
    assert "Sous-titres indisponibles" in emitted[0]


def test_run_youtube_download_keeps_unrelated_errors_and_rejects_empty_results(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        workflow,
        "download_youtube_media",
        mock.Mock(side_effect=ValueError("réseau indisponible")),
    )
    with pytest.raises(ValueError, match="réseau indisponible"):
        workflow.run_youtube_download(_options(tmp_path), _config(tmp_path))

    monkeypatch.setattr(workflow, "download_youtube_media", lambda _: [])
    with pytest.raises(ValueError, match="aucun fichier final"):
        workflow.run_youtube_download(_options(tmp_path), _config(tmp_path))


def test_encode_downloaded_videos_validates_input_and_skips_existing_output(
    monkeypatch, tmp_path
):
    cfg = _config(tmp_path)
    with pytest.raises(ValueError, match="Aucun fichier"):
        workflow.encode_downloaded_youtube_videos([], cfg)
    with pytest.raises(FileNotFoundError, match="introuvable"):
        workflow.encode_downloaded_youtube_videos([tmp_path / "missing.mp4"], cfg)

    downloaded = tmp_path / "clip_download.mp4"
    downloaded.write_bytes(b"source")
    (tmp_path / "clip_processed.mp4").write_bytes(b"already processed")
    preflight = mock.Mock()
    monkeypatch.setattr(workflow, "youtube_video_encodor_preflight", preflight)

    assert workflow.encode_downloaded_youtube_videos([downloaded], cfg) is False
    preflight.assert_not_called()


def test_encode_downloaded_videos_skips_or_stages_a_video(monkeypatch, tmp_path):
    cfg = _config(tmp_path)
    downloaded = tmp_path / "clip_download.mp4"
    downloaded.write_bytes(b"source video")
    emitted = []
    monkeypatch.setattr(workflow, "emit", lambda message, **_: emitted.append(message))
    monkeypatch.setattr(
        workflow,
        "youtube_video_encodor_preflight",
        lambda *_: (False, "gain insuffisant"),
    )
    assert workflow.encode_downloaded_youtube_videos([downloaded], cfg) is False
    assert "gain insuffisant" in emitted[0]

    def fake_encoder(staged_cfg):
        staged = next(staged_cfg.INPUT_DIR.glob("*.mp4"))
        staged_cfg.OUTPUT_DIR.mkdir()
        (staged_cfg.OUTPUT_DIR / staged.name).write_bytes(b"small")

    monkeypatch.setattr(workflow, "video_encodor", fake_encoder)
    monkeypatch.setattr(
        workflow,
        "youtube_video_encodor_preflight",
        lambda *_: (True, "encodage recommandé"),
    )
    monkeypatch.setattr(
        workflow.func_global_module, "format_bytes", lambda size: f"{size} B"
    )

    assert workflow.encode_downloaded_youtube_videos([downloaded], cfg) is False
    assert (tmp_path / "clip_processed.mp4").read_bytes() == b"small"
    assert any("réduction de" in message for message in emitted)


def test_encode_downloaded_videos_rejects_encoder_without_output(monkeypatch, tmp_path):
    downloaded = tmp_path / "clip_download.mp4"
    downloaded.write_bytes(b"source")
    monkeypatch.setattr(
        workflow, "youtube_video_encodor_preflight", lambda *_: (True, "go")
    )
    monkeypatch.setattr(workflow, "video_encodor", lambda _: None)

    with pytest.raises(ValueError, match="aucun fichier .mp4"):
        workflow.encode_downloaded_youtube_videos([downloaded], _config(tmp_path))


@pytest.mark.parametrize(
    ("metadata", "expected", "message"),
    [
        (OSError("ffprobe absent"), False, "impossible"),
        ({"streams": "invalid"}, False, "indisponible"),
        ({"streams": []}, False, "Aucun flux"),
        (
            {"streams": [{"codec_type": "video", "codec_name": "hevc", "height": 1080}], "format": {"bit_rate": "6000000"}},
            False,
            "déjà encodée",
        ),
        (
            {"streams": [{"codec_type": "video", "codec_name": "h264", "height": 720}], "format": {}},
            False,
            "débit source indisponible",
        ),
        (
            {"streams": [{"codec_type": "video", "codec_name": "h264", "height": 720}], "format": {"bit_rate": "1600000"}},
            False,
            "gain estimé insuffisant",
        ),
        (
            {"streams": [{"codec_type": "video", "codec_name": "h264", "height": 720}], "format": {"bit_rate": "3000000"}},
            True,
            "Encodage recommandé",
        ),
    ],
)
def test_video_preflight_covers_metadata_outcomes(
    monkeypatch, tmp_path, metadata, expected, message
):
    if isinstance(metadata, Exception):
        monkeypatch.setattr(workflow, "get_all_metadata", mock.Mock(side_effect=metadata))
    else:
        monkeypatch.setattr(workflow, "get_all_metadata", lambda _: metadata)

    should_encode, report = workflow.youtube_video_encodor_preflight(
        tmp_path / "video.mp4", _config(tmp_path)
    )

    assert should_encode is expected
    assert message in report


def test_metadata_helpers_and_video_specs(monkeypatch, tmp_path):
    assert workflow._bitrate_kbps("2000000") == 2_000
    assert workflow._bitrate_kbps("invalid") is None
    assert workflow._bitrate_kbps(0) is None
    assert workflow._total_bitrate_kbps({"bit_rate": "4000000"}, []) == 4_000
    assert workflow._total_bitrate_kbps(
        {}, [{"bit_rate": "1000000"}, {"bit_rate": "500000"}]
    ) == 1_500
    assert workflow._target_bitrate_kbps(None, _config(tmp_path)) == 2_800

    video = tmp_path / "clip.mp4"
    video.write_bytes(b"video")
    monkeypatch.setattr(
        workflow,
        "get_all_metadata",
        lambda _: {
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1280,
                    "height": 720,
                }
            ],
            "format": {"duration": "61"},
        },
    )
    monkeypatch.setattr(workflow, "format_duration_hms", lambda _: "00:01:01")
    monkeypatch.setattr(workflow.func_global_module, "format_bytes", lambda _: "5 B")

    codec, specs, height = workflow._youtube_video_specs(video)
    assert (codec, height) == ("h264", 720)
    assert "00:01:01" in specs and "1280×720" in specs

    monkeypatch.setattr(workflow, "get_all_metadata", lambda _: {"streams": []})
    with pytest.raises(ValueError, match="Aucun flux vidéo"):
        workflow._youtube_video_specs(video)


def test_youtube_notice_and_file_helpers(tmp_path):
    assert workflow._youtube_requested_level_notice(
        "MP4", "1080", "160", actual_video_height=720
    )
    assert workflow._youtube_requested_level_notice(
        "MP3", "1080", "160", actual_audio_bitrate=128
    )
    assert (
        workflow._youtube_requested_level_notice(
            "MP3", "1080", "160", actual_audio_bitrate=160
        )
        is None
    )
    first = tmp_path / "B_download.mp3"
    second = tmp_path / "a_download.mp3"
    ignored = tmp_path / "video.mp4"
    first.touch()
    second.touch()
    ignored.touch()
    assert workflow._find_new_youtube_files(tmp_path, set(), "MP3") == [second, first]
    assert workflow._is_youtube_subtitle_download_error(
        ValueError("subtitle download failed: HTTP Error 429")
    )
    assert not workflow._is_youtube_subtitle_download_error(
        ValueError("HTTP Error 500")
    )

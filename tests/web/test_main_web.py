"""Tests for the local YouTube downloader configuration."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import toolbox_pb.core.web.main_web as main_web
from toolbox_pb.core.web.main_web import (
    YouTubeDownloadOptions,
    _YouTubeProgressReporter,
    _validate_youtube_url,
    download_youtube_media,
)


def test_youtube_url_validation_accepts_youtube_and_rejects_other_hosts():
    assert _validate_youtube_url(" https://youtu.be/abc123 ") == "https://youtu.be/abc123"
    with pytest.raises(ValueError, match="URL YouTube valide"):
        _validate_youtube_url("https://example.org/video")


def test_youtube_defaults_match_the_interface_preferences(tmp_path):
    options = YouTubeDownloadOptions(
        url="https://youtu.be/abc123",
        output_dir=tmp_path,
        media_format="MP3",
    )

    assert options.mp3_bitrate == "160"
    assert options.video_quality == "1080"


def test_mp3_download_uses_audio_extraction_settings(monkeypatch, tmp_path):
    captured = {}
    messages = []

    class FakeYoutubeDL:
        def __init__(self, options):
            captured.update(options)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def add_post_processor(self, post_processor):
            captured["post_processor"] = post_processor

        def download(self, urls):
            captured["urls"] = urls
            Path(captured["outtmpl"]).parent.joinpath("video_download.mp3").write_bytes(
                b"mp3"
            )
            Path(captured["outtmpl"]).parent.joinpath("video_download.webm").write_bytes(
                b"webm"
            )

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))
    monkeypatch.setattr(main_web, "emit", lambda message, **_: messages.append(message))
    monkeypatch.setattr(
        main_web,
        "_make_progress_extract_audio_postprocessor",
        lambda _downloader, bitrate: SimpleNamespace(preferredquality=bitrate),
    )
    result = download_youtube_media(
        YouTubeDownloadOptions(
            url="https://www.youtube.com/watch?v=abc123",
            output_dir=tmp_path,
            media_format="MP3",
            mp3_bitrate="256",
        )
    )

    assert [path.name for path in result] == ["video_download.mp3"]
    assert captured["urls"] == ["https://www.youtube.com/watch?v=abc123"]
    assert captured["noplaylist"] is True
    assert captured["noprogress"] is False
    assert captured["progress_with_newline"] is True
    assert captured["keepvideo"] is False
    assert captured["post_processor"].preferredquality == "256"
    assert not (tmp_path / "video_download.webm").exists()
    assert any("Fichier MP3 terminé" in message for message in messages)


def test_youtube_download_retries_a_temporary_windows_file_lock(monkeypatch, tmp_path):
    attempts = []
    delays = []

    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def add_post_processor(self, _post_processor):
            return None

        def download(self, _urls):
            attempts.append(1)
            if len(attempts) == 1:
                raise PermissionError(32, "Le processus ne peut pas accéder au fichier")
            Path(self.options["outtmpl"]).parent.joinpath(
                "video_download.mp3"
            ).write_bytes(b"mp3")

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))
    monkeypatch.setattr(main_web, "sleep", lambda seconds: delays.append(seconds))
    monkeypatch.setattr(
        main_web,
        "_make_progress_extract_audio_postprocessor",
        lambda _downloader, _bitrate: SimpleNamespace(),
    )

    result = download_youtube_media(
        YouTubeDownloadOptions(
            url="https://youtu.be/abc123", output_dir=tmp_path, media_format="MP3"
        )
    )

    assert [path.name for path in result] == ["video_download.mp3"]
    assert len(attempts) == 2
    assert delays == [1.0]


def test_windows_file_lock_recognition_supports_wrapped_yt_dlp_errors():
    assert main_web._is_transient_windows_file_lock(
        RuntimeError("ERROR: [WinError 32] Le processus ne peut pas accéder au fichier")
    )
    assert not main_web._is_transient_windows_file_lock(RuntimeError("réseau indisponible"))


def test_mp3_conversion_uses_a_custom_progress_postprocessor():
    post_processor = main_web._make_progress_extract_audio_postprocessor(
        SimpleNamespace(params={}), "160"
    )

    assert post_processor.mapping == "mp3"
    assert post_processor._preferredquality == 160.0


def test_mp3_conversion_postprocessor_forwards_real_ffmpeg_progress(monkeypatch):
    post_processor = main_web._make_progress_extract_audio_postprocessor(
        SimpleNamespace(params={}), "160"
    )
    post_processor._toolbox_duration = 42.0
    process = SimpleNamespace(returncode=0, wait=lambda: None)
    progress_reader = []
    popen_calls = []

    def fake_popen(command, **kwargs):
        popen_calls.append((command, kwargs))
        return process

    monkeypatch.setattr(main_web.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        main_web,
        "consume_ffmpeg_progress",
        lambda *args, **kwargs: progress_reader.append((args, kwargs)) or [],
    )

    post_processor.run_ffmpeg(
        "source.webm", "target.mp3", "libmp3lame", ["-q:a", "4"]
    )

    command = popen_calls[0][0]
    assert ["-progress", "pipe:1"] == command[-3:-1]
    assert progress_reader[0][1] == {
        "duration": 42.0,
        "desc": "Conversion audio vers MP3",
        "position": 1,
    }


def test_mp4_download_limits_the_selected_video_quality(monkeypatch, tmp_path):
    captured = {}

    class FakeYoutubeDL:
        def __init__(self, options):
            captured.update(options)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def download(self, _urls):
            Path(captured["outtmpl"]).parent.joinpath("video_download.mp4").write_bytes(
                b"mp4"
            )
            return 0

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))
    download_youtube_media(
        YouTubeDownloadOptions(
            url="https://youtube.com/watch?v=abc123",
            output_dir=tmp_path,
            media_format="MP4",
            video_quality="720",
        )
    )

    assert "height<=720" in captured["format"]
    assert captured["merge_output_format"] == "mp4"


@pytest.mark.parametrize(
    ("subtitles", "automatic", "expected"),
    [
        ({"fr": [{}], "en": [{}]}, {"fr": [{}]}, [("fr", False)]),
        ({"en-US": [{}]}, {"fr": [{}]}, [("en-US", False), ("fr", True)]),
        ({}, {"fr": [{}]}, [("fr", True)]),
        ({}, {}, []),
    ],
)
def test_subtitle_selection_honors_manual_french_then_english_and_auto_french(
    subtitles, automatic, expected
):
    class FakeYoutubeDL:
        def __init__(self, _options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _url, *, download):
            assert download is False
            return {
                "subtitles": subtitles,
                "automatic_captions": automatic,
            }

    assert main_web._select_youtube_subtitle_tracks(
        SimpleNamespace(YoutubeDL=FakeYoutubeDL), "https://youtu.be/example"
    ) == expected


def test_mp4_download_keeps_one_normalized_srt_subtitle(monkeypatch, tmp_path):
    captured = {}
    messages = []

    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options
            captured.update(options)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _url, *, download):
            assert download is False
            return {"subtitles": {"fr": [{}]}, "automatic_captions": {}}

        def download(self, _urls):
            output_dir = Path(self.options["outtmpl"]).parent
            if self.options.get("skip_download"):
                output_dir.joinpath("video_download.fr.srt").write_text(
                    "1\n00:00:00,000 --> 00:00:01,000\nBonjour\n",
                    encoding="utf-8",
                )
            else:
                output_dir.joinpath("video_download.mp4").write_bytes(b"mp4")

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))
    monkeypatch.setattr(main_web, "emit", lambda message, **_kwargs: messages.append(message))

    result = download_youtube_media(
        YouTubeDownloadOptions(
            url="https://youtu.be/abc123",
            output_dir=tmp_path,
            media_format="MP4",
            download_subtitles=True,
        )
    )

    assert [path.name for path in result] == ["video_download.mp4"]
    assert captured["writesubtitles"] is True
    assert captured["writeautomaticsub"] is False
    assert captured["subtitleslangs"] == ["fr"]
    assert (tmp_path / "video_download.srt").is_file()
    assert not (tmp_path / "video_download.fr.srt").exists()
    assert len(list(tmp_path.glob("*.srt"))) == 1
    assert any("Sous-titres SRT fourni" in message for message in messages)


def test_mp4_download_keeps_english_manual_and_french_auto_subtitles(
    monkeypatch, tmp_path
):
    options_seen = []

    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options
            options_seen.append(options)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _url, *, download):
            assert download is False
            return {
                "subtitles": {"en": [{}]},
                "automatic_captions": {"fr": [{}]},
            }

        def download(self, _urls):
            output_dir = Path(self.options["outtmpl"]).parent
            if self.options.get("skip_download") and self.options.get("writeautomaticsub"):
                output_dir.joinpath("video_download.fr.srt").write_text(
                    "Français automatique", encoding="utf-8"
                )
            elif self.options.get("skip_download"):
                output_dir.joinpath("video_download.en.srt").write_text(
                    "English manual", encoding="utf-8"
                )
            else:
                output_dir.joinpath("video_download.mp4").write_bytes(b"mp4")

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))
    monkeypatch.setattr(main_web, "emit", lambda *_args, **_kwargs: None)

    download_youtube_media(
        YouTubeDownloadOptions(
            url="https://youtu.be/abc123",
            output_dir=tmp_path,
            media_format="MP4",
            download_subtitles=True,
        )
    )

    assert (tmp_path / "video_download.en.srt").read_text(encoding="utf-8") == "English manual"
    assert (tmp_path / "video_download.fr-auto.srt").read_text(encoding="utf-8") == "Français automatique"
    assert len(list(tmp_path.glob("*.srt"))) == 2
    assert options_seen[-1]["skip_download"] is True
    assert options_seen[-1]["subtitleslangs"] == ["fr"]


def test_subtitle_rate_limit_keeps_the_downloaded_media_successful(
    monkeypatch, tmp_path
):
    messages = []

    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _url, *, download):
            assert download is False
            return {"subtitles": {"fr": [{}]}, "automatic_captions": {}}

        def download(self, _urls):
            if self.options.get("skip_download"):
                raise RuntimeError("HTTP Error 429: Too Many Requests")
            Path(self.options["outtmpl"]).parent.joinpath(
                "video_download.mp4"
            ).write_bytes(b"mp4")

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))
    monkeypatch.setattr(main_web, "emit", lambda message, **_kwargs: messages.append(message))

    result = download_youtube_media(
        YouTubeDownloadOptions(
            url="https://youtu.be/abc123",
            output_dir=tmp_path,
            media_format="MP4",
            download_subtitles=True,
        )
    )

    assert [path.name for path in result] == ["video_download.mp4"]
    assert not list(tmp_path.glob("*.srt"))
    assert any("HTTP Error 429" in message for message in messages)
    assert any("vidéo a bien été téléchargée" in message for message in messages)


def test_youtube_progress_combines_hls_fragments():
    status = {
        "downloaded_bytes": 50,
        "total_bytes": 100,
        "fragment_index": 2,
        "fragment_count": 4,
    }

    assert _YouTubeProgressReporter._percentage(status) == 37.5


def test_youtube_progress_uses_the_native_percentage_when_size_is_unknown():
    status = {"_percent_str": " 47.7%"}

    assert _YouTubeProgressReporter._percentage(status) == 47.7


def test_youtube_progress_reporter_creates_updates_and_completes_a_bar(
    monkeypatch,
):
    """Hook updates stay proportional and report the final downloaded file."""
    updates = []
    messages = []

    class FakeBar:
        def update(self, amount):
            updates.append(amount)

    monkeypatch.setattr(main_web, "progress", lambda **_kwargs: FakeBar())
    monkeypatch.setattr(main_web, "emit", lambda message, **_kwargs: messages.append(message))
    reporter = _YouTubeProgressReporter("MP3")
    status = {
        "status": "downloading",
        "tmpfilename": "download.webm.part",
        "downloaded_bytes": 25,
        "total_bytes": 100,
    }

    reporter.report(status)
    reporter.report({**status, "downloaded_bytes": 75})
    reporter.report({"status": "finished", "filename": "download.webm.part"})
    reporter.report({"status": "error"})

    assert updates == [25.0, 50.0, 25.0]
    assert any("Flux audio source téléchargé" in message for message in messages)

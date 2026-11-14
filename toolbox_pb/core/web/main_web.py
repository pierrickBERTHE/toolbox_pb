"""YouTube downloads powered by the local ``yt-dlp`` package."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
from time import sleep
from typing import Any
from urllib.parse import urlparse

from toolbox_pb.core.events import emit
from toolbox_pb.core.func_global import consume_ffmpeg_progress
from toolbox_pb.core.progress import progress

# yt-dlp supports many YouTube domains, but we only allow the most common ones.
YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}

# Video qualities and audio bitrates supported by the application.
VIDEO_QUALITIES = ("2160", "1440", "1080", "720", "480", "360")
MP3_BITRATES = ("320", "256", "192", "160", "128")
WINDOWS_FILE_LOCK_RETRIES = 3


@dataclass(frozen=True)
class YouTubeDownloadOptions:
    """User-selected settings for one YouTube download."""
    url: str
    output_dir: Path
    media_format: str
    video_quality: str = "1080"
    mp3_bitrate: str = "160"
    download_subtitles: bool = False


def _validate_youtube_url(url: str) -> str:
    """Return a safe YouTube URL or raise a readable validation error."""
    value = url.strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in YOUTUBE_HOSTS:
        raise ValueError(
            "Saisissez une URL YouTube valide (youtube.com ou youtu.be)."
        )
    return value


def download_youtube_media(options: YouTubeDownloadOptions) -> list[Path]:
    """Download one authorized YouTube video as MP3 or MP4.

    The output template includes the video ID so two videos with identical
    titles cannot overwrite each other. ``yt-dlp`` invokes FFmpeg when a
    conversion or a video/audio merge is required.
    """
    url = _validate_youtube_url(options.url)
    if options.media_format not in {"MP3", "MP4"}:
        raise ValueError("Le format de sortie doit être MP3 ou MP4.")
    if options.video_quality not in VIDEO_QUALITIES:
        raise ValueError(
            "La qualité vidéo sélectionnée n’est pas prise en charge."
        )
    if options.mp3_bitrate not in MP3_BITRATES:
        raise ValueError("Le débit MP3 sélectionné n’est pas pris en charge.")

    options.output_dir.mkdir(parents=True, exist_ok=True)
    existing_files = set(options.output_dir.iterdir())
    progress_reporter = _YouTubeProgressReporter(options.media_format)
    ydl_options: dict[str, object] = {
        "outtmpl": str(
            options.output_dir / "%(title)s [%(id)s]_download.%(ext)s"
        ),
        "noplaylist": True,
        "restrictfilenames": True,
        "windowsfilenames": True,
        "keepvideo": False,
        "quiet": True,
        "noprogress": False,
        "progress_with_newline": True,
        "no_warnings": False,
        "progress_hooks": [progress_reporter.report],
    }
    if options.media_format == "MP3":
        ydl_options.update(
            {
                "format": "bestaudio/best",
            }
        )
    else:
        maximum_height = options.video_quality
        ydl_options.update(
            {
                "format": (
                    f"bestvideo[ext=mp4][height<={maximum_height}]"
                    "+bestaudio[ext=m4a]/"
                    f"best[ext=mp4][height<={maximum_height}]/"
                    f"best[height<={maximum_height}]"
                ),
                "merge_output_format": "mp4",
            }
        )

    subtitle_selection: list[tuple[str, bool]] = []
    try:
        import yt_dlp

        if options.download_subtitles:
            subtitle_selection = _select_youtube_subtitle_tracks(yt_dlp, url)
            if not subtitle_selection:
                emit(
                    "Aucun sous-titre français ou anglais n’est disponible ; "
                    "aucun fichier SRT ne sera créé."
                )
        # Media must succeed independently from optional subtitle downloads.
        _download_with_file_lock_retry(
            yt_dlp,
            ydl_options,
            url,
            mp3_bitrate=(options.mp3_bitrate if options.media_format == "MP3" else None),
        )
    except ImportError as exc:
        raise ValueError(
            "\nyt-dlp n’est pas installé dans l’environnement Poetry."
        ) from exc
    except Exception as exc:
        # yt-dlp exposes several error classes whose public shape changes over
        # time. Convert them into an input error while retaining a useful text.
        raise ValueError(f"\nTéléchargement YouTube impossible : {exc}") from exc

    if options.media_format == "MP3":
        _remove_new_audio_intermediates(options.output_dir, existing_files)

    extension = ".mp3" if options.media_format == "MP3" else ".mp4"
    downloaded_files = sorted(
        (
            path
            for path in options.output_dir.iterdir()
            if path not in existing_files and path.suffix.lower() == extension
        ),
        key=lambda path: path.name.casefold(),
    )
    if not downloaded_files:
        raise ValueError("\nLe téléchargement YouTube n’a produit aucun fichier final.")
    if subtitle_selection:
        media_file = downloaded_files[0]
        for language, is_automatic in subtitle_selection:
            subtitle_files = _download_optional_subtitles(
                yt_dlp,
                ydl_options,
                url,
                options.output_dir,
                language=language,
                automatic=is_automatic,
            )
            _place_subtitle_file(
                subtitle_files,
                media_file,
                language=language,
                automatic=is_automatic,
            )
    if options.media_format == "MP3":
        for downloaded_file in downloaded_files:
            emit(f"\nFichier MP3 terminé : {downloaded_file}")
    emit(f"\nTéléchargement terminé dans : {options.output_dir}")
    return downloaded_files


def _select_youtube_subtitle_tracks(
    yt_dlp: Any, url: str
) -> list[tuple[str, bool]]:
    """Select the requested manual/automatic tracks in priority order.

    A provided French caption is exclusive. Without it, a provided English
    caption and a French automatic YouTube translation are both retained when
    available, producing one or two SRT files.
    """
    probe_options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
    }
    try:
        with yt_dlp.YoutubeDL(probe_options) as extractor:
            info = extractor.extract_info(url, download=False)
    except Exception as exc:
        emit(f"Analyse des sous-titres impossible : {exc}")
        return []

    if not isinstance(info, dict):
        return []
    manual_subtitles = info.get("subtitles")
    if isinstance(manual_subtitles, dict):
        french_language = _preferred_subtitle_language(manual_subtitles, "fr")
        if french_language is not None:
            return [(french_language, False)]
        english_language = _preferred_subtitle_language(manual_subtitles, "en")
    else:
        english_language = None

    automatic_captions = info.get("automatic_captions")
    tracks: list[tuple[str, bool]] = []
    if english_language is not None:
        tracks.append((english_language, False))
    if isinstance(automatic_captions, dict):
        language = _preferred_subtitle_language(automatic_captions, "fr")
        if language is not None:
            tracks.append((language, True))
    return tracks


def _preferred_subtitle_language(
    tracks: dict[object, object], language_prefix: str
) -> str | None:
    """Choose an exact language tag before a regional variant."""
    available = sorted(str(language) for language, values in tracks.items() if values)
    if language_prefix in available:
        return language_prefix
    prefix = f"{language_prefix}-"
    return next(
        (language for language in available if language.casefold().startswith(prefix)),
        None
    )


def _download_optional_subtitles(
    yt_dlp: Any,
    ydl_options: dict[str, object],
    url: str,
    output_dir: Path,
    *,
    language: str,
    automatic: bool,
) -> list[Path]:
    """Fetch one optional subtitle track without invalidating media success."""
    subtitle_files_before = set(output_dir.glob("*.srt"))
    subtitle_options = dict(ydl_options)
    subtitle_options.update(
        {
            "skip_download": True,
            "writesubtitles": not automatic,
            "writeautomaticsub": automatic,
            "subtitleslangs": [language],
            "subtitlesformat": "srt",
        }
    )
    try:
        with yt_dlp.YoutubeDL(subtitle_options) as downloader:
            downloader.download([url])
    except Exception as exc:
        kind = "automatique français" if automatic else f"fourni ({language})"
        emit(
            f"Sous-titre {kind} indisponible ({exc}). "
            "La vidéo a bien été téléchargée."
        )
        return []
    return sorted(set(output_dir.glob("*.srt")) - subtitle_files_before)


def _place_subtitle_file(
    subtitle_files: list[Path],
    media_file: Path,
    *,
    language: str,
    automatic: bool,
) -> None:
    """Place one selected subtitle next to media under a readable name."""
    if not subtitle_files:
        kind = "automatique français" if automatic else "fourni"
        emit(f"Le sous-titre {kind} sélectionné n’a pas pu être téléchargé.")
        return

    if automatic:
        target = media_file.with_suffix(".fr-auto.srt")
    elif language.casefold().startswith("fr"):
        target = media_file.with_suffix(".srt")
    else:
        target = media_file.with_suffix(".en.srt")
    source = subtitle_files[0]
    if source != target:
        source.replace(target)
    for subtitle_path in subtitle_files[1:]:
        if subtitle_path != target:
            subtitle_path.unlink()
    label = "automatique français" if automatic else f"fourni ({language})"
    emit(f"Sous-titres SRT {label} téléchargés : \n{target}")


def _download_with_file_lock_retry(
    yt_dlp: Any,
    ydl_options: dict[str, object],
    url: str,
    *,
    mp3_bitrate: str | None = None,
) -> None:
    """Retry briefly when Windows has not released a yt-dlp media file yet."""
    for attempt in range(1, WINDOWS_FILE_LOCK_RETRIES + 1):
        try:
            with yt_dlp.YoutubeDL(ydl_options) as downloader:
                if mp3_bitrate is not None:
                    downloader.add_post_processor(
                        _make_progress_extract_audio_postprocessor(
                            downloader,
                            mp3_bitrate,
                        )
                    )
                downloader.download([url])
            return
        except Exception as exc:
            if (
                not _is_transient_windows_file_lock(exc)
                or attempt == WINDOWS_FILE_LOCK_RETRIES
            ):
                raise
            delay_seconds = float(attempt)
            emit(
                "Fichier encore utilisé par Windows ; nouvelle tentative "
                f"dans {delay_seconds:.0f} seconde(s) "
                f"({attempt}/{WINDOWS_FILE_LOCK_RETRIES - 1})."
            )
            sleep(delay_seconds)


def _is_transient_windows_file_lock(exc: BaseException) -> bool:
    """Recognize the Windows sharing violation reported by yt-dlp/FFmpeg."""
    if getattr(exc, "winerror", None) == 32 or getattr(exc, "errno", None) == 32:
        return True
    message = str(exc).casefold()
    return "[winerror 32]" in message or "utilisé par un autre processus" in message


def _remove_new_audio_intermediates(
    output_dir: Path, existing_files: set[Path]
) -> None:
    """Delete only temporary media created while extracting an MP3."""
    temporary_extensions = {".webm", ".m4a", ".opus", ".part", ".ytdl"}
    for path in output_dir.iterdir():
        if path in existing_files or not path.is_file():
            continue
        if path.suffix.lower() in temporary_extensions:
            path.unlink()
            emit(f"Fichier intermédiaire supprimé : {path.name}")


class _YouTubeProgressReporter:
    """Translate yt-dlp hook data into quiet, accurate toolbox progress bars."""

    def __init__(self, media_format: str = "MP4") -> None:
        self._bars: dict[str, Any] = {}
        self._percentages: dict[str, float] = {}
        self._media_format = media_format

    def report(self, status: dict[str, object]) -> None:
        """Update one bar per downloaded media stream, without raw CLI noise."""
        state = status.get("status")
        filename = str(status.get("tmpfilename") or status.get("filename") or "")
        info = status.get("info_dict")
        if not filename and isinstance(info, dict):
            filename = str(info.get("format_id") or info.get("id") or "")
        if state == "finished":
            bar = self._bars.get(filename)
            if bar is not None:
                previous = self._percentages.get(filename, 0.0)
                if previous < 100:
                    bar.update(100 - previous)
                    self._percentages[filename] = 100
            label = (
                "Flux audio source téléchargé (temporaire)"
                if self._media_format == "MP3"
                else "Fichier téléchargé"
            )
            emit(f"\n{label} : {status.get('filename', '')}")
            return
        if state != "downloading" or not filename:
            return

        percentage = self._percentage(status)
        if percentage is None:
            return
        bar = self._bars.get(filename)
        if bar is None:
            title = Path(filename).name
            bar = progress(
                total=100,
                desc=f"Téléchargement : {title}",
                unit="%",
                position=len(self._bars),
            )
            self._bars[filename] = bar

        previous = self._percentages.get(filename, 0.0)
        increment = max(0.0, percentage - previous)
        if increment:
            bar.update(increment)
            self._percentages[filename] = percentage

    @staticmethod
    def _percentage(status: dict[str, object]) -> float | None:
        """Return one stream's percentage, including HLS fragment progress."""
        downloaded = status.get("downloaded_bytes")
        total = status.get("total_bytes") or status.get("total_bytes_estimate")
        if isinstance(downloaded, (int, float)) and isinstance(total, (int, float)) and total > 0:
            local_percentage = min(downloaded / total * 100, 100)
        else:
            percent_text = str(status.get("_percent_str", ""))
            match = re.search(r"(\d+(?:\.\d+)?)%", percent_text)
            if match is None:
                return None
            local_percentage = min(float(match.group(1)), 100)
        fragment_count = status.get("fragment_count")
        fragment_index = status.get("fragment_index")
        if (
            isinstance(fragment_count, int)
            and fragment_count > 0
            and isinstance(fragment_index, int)
            and fragment_index > 0
        ):
            return min(
                ((fragment_index - 1) + local_percentage / 100) / fragment_count * 100,
                100,
            )
        return local_percentage


def _make_progress_extract_audio_postprocessor(
    downloader: Any,
    mp3_bitrate: str,
) -> Any:
    """Create yt-dlp's MP3 post-processor with real FFmpeg progress output."""
    from yt_dlp.postprocessor.ffmpeg import (
        FFmpegExtractAudioPP,
        FFmpegPostProcessorError,
    )

    class ProgressExtractAudioPP(FFmpegExtractAudioPP):
        """FFmpegExtractAudioPP that reports ``out_time_ms`` to Streamlit."""

        def run(self, information: dict[str, object]):
            duration = information.get("duration")
            try:
                self._toolbox_duration = max(float(duration), 0.0)
            except (TypeError, ValueError):
                self._toolbox_duration = 0.0
            # yt-dlp can invoke the same post-processor more than once while
            # preparing the target file.  Keep the Streamlit console concise.
            if not getattr(self, "_toolbox_conversion_announced", False):
                emit("\nConversion du flux audio en MP3…", log=False)
                self._toolbox_conversion_announced = True
            return super().run(information)

        def run_ffmpeg(
            self,
            path: str,
            out_path: str,
            codec: str | None,
            more_opts: list[str],
        ) -> None:
            audio_codec_options = ["-acodec", codec] if codec else []
            command = [
                self.executable,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                path,
                "-vn",
                *audio_codec_options,
                *more_opts,
                "-progress",
                "pipe:1",
                out_path,
            ]
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            errors = consume_ffmpeg_progress(
                process,
                duration=self._toolbox_duration,
                desc="Conversion audio vers MP3",
                position=1,
            )
            process.wait()
            if process.returncode != 0:
                details = "\n".join(errors) or "Erreur FFmpeg inconnue"
                raise FFmpegPostProcessorError(details)

    return ProgressExtractAudioPP(
        downloader=downloader,
        preferredcodec="mp3",
        preferredquality=mp3_bitrate,
    )

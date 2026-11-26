"""Shared post-download workflow for the two web interfaces.

The downloader lives in :mod:`toolbox_pb.core.web`; this module only adds the
UI-independent validation, reporting and optional MP4 re-encoding workflow.
"""

from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import toolbox_pb.core.func_global as func_global_module
from toolbox_pb.core.audio.func_audio import probe_audio_bitrate_kbps
from toolbox_pb.core.config_global import AppConfig
from toolbox_pb.core.events import emit
from toolbox_pb.core.video.func_video import (
    format_duration_hms,
    get_all_metadata,
)
from toolbox_pb.core.video.main_video import video_encodor
from toolbox_pb.core.web.main_web import (
    YouTubeDownloadOptions,
    download_youtube_media,
)


def run_youtube_download(
    options: YouTubeDownloadOptions, cfg: AppConfig
) -> bool:
    """Download media, tolerate optional subtitle failures and encode MP4s."""
    # Keep a snapshot because yt-dlp can return different result shapes across
    # versions; comparing the directory contents is the stable fallback.
    existing_output_files = set(options.output_dir.iterdir())
    downloaded_files: list[Path] = []
    try:
        download_result = download_youtube_media(options)
    except ValueError as exc:
        # Subtitle retrieval is optional: retain a completed media download
        # when only the follow-up subtitle request has failed.
        if not _is_youtube_subtitle_download_error(exc):
            raise
        recovered_files = _find_new_youtube_files(
            options.output_dir, existing_output_files, options.media_format
        )
        if not recovered_files:
            raise
        downloaded_files.extend(recovered_files)
        emit(
            "Sous-titres indisponibles ; le fichier média a bien été téléchargé.",
            log=False,
        )
        download_result = recovered_files

    if isinstance(download_result, list):
        # Prefer the downloader's explicit result when it is available.
        downloaded_files.extend(
            path for path in download_result if path not in downloaded_files
        )
    else:
        # Use the directory snapshot for older or custom downloader results.
        downloaded_files.extend(
            _find_new_youtube_files(
                options.output_dir, existing_output_files, options.media_format
            )
        )
    if not downloaded_files:
        raise ValueError(
            "Le téléchargement YouTube n’a produit aucun fichier final."
        )

    if options.media_format == "MP4":
        for downloaded_file in downloaded_files:
            _, specs, actual_height = _youtube_video_specs(downloaded_file)
            emit(f"\n{specs}", log=False)
            notice = _youtube_requested_level_notice(
                options.media_format,
                options.video_quality,
                options.mp3_bitrate,
                actual_video_height=actual_height,
            )
            if notice:
                emit(notice)
        return encode_downloaded_youtube_videos(downloaded_files, cfg)

    for downloaded_file in downloaded_files:
        notice = _youtube_requested_level_notice(
            options.media_format,
            options.video_quality,
            options.mp3_bitrate,
            actual_audio_bitrate=probe_audio_bitrate_kbps(downloaded_file),
        )
        if notice:
            emit(notice)
    return False


def encode_downloaded_youtube_videos(
    downloaded_files: list[Path],
    cfg: AppConfig,
) -> bool:
    """Encode newly downloaded MP4 files only when a gain is expected."""
    if not downloaded_files:
        raise ValueError("Aucun fichier YouTube téléchargé n’est disponible.")
    for downloaded_file in downloaded_files:
        if not downloaded_file.is_file():
            raise FileNotFoundError(
                f"Fichier téléchargé introuvable : {downloaded_file}"
            )
        stem = downloaded_file.stem.removesuffix("_download")
        processed_path = cfg.OUTPUT_DIR / f"{stem}_processed.mp4"
        if processed_path.exists():
            emit(f"Fichier déjà traité : {processed_path.name}")
            continue
        should_encode, preflight_message = youtube_video_encodor_preflight(
            downloaded_file, cfg
        )
        emit(f"\n{preflight_message}", log=False)
        if not should_encode:
            continue

        before_size = downloaded_file.stat().st_size
        emit("\nLancement de Video_encodor…")
        with TemporaryDirectory(prefix="toolbox_pb_youtube_") as temp_name:
            # The encoder scans its complete INPUT directory. Stage one file in
            # isolated folders so unrelated user files are never processed.
            temp_root = Path(temp_name)
            input_dir, output_dir = temp_root / "input", temp_root / "output"
            input_dir.mkdir()
            staged_input = input_dir / f"{stem}{downloaded_file.suffix}"
            shutil.copy2(downloaded_file, staged_input)
            video_encodor(
                replace(cfg, INPUT_DIR=input_dir, OUTPUT_DIR=output_dir)
            )
            generated_files = sorted(output_dir.rglob("*.mp4"))
            if not generated_files:
                raise ValueError(
                    "Le traitement n’a produit aucun fichier .mp4."
                )
            processed_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(generated_files[0]), processed_path)
            after_size = processed_path.stat().st_size
            difference = before_size - after_size
            direction = (
                "réduction de" if difference >= 0 else "augmentation de"
            )
            absolute_difference = abs(difference)
            emit(
                f"Fichier traité : {processed_path.name}\n"
                "Taille Video_encodor : "
                f"{func_global_module.format_bytes(before_size)} → "
                f"{func_global_module.format_bytes(after_size)} "
                f"({direction} {func_global_module.format_bytes(absolute_difference)} "
                f"({absolute_difference / before_size * 100:.1f} %))"
            )
    return False


def youtube_video_encodor_preflight(
    video_path: Path, cfg: AppConfig
) -> tuple[bool, str]:
    """Avoid an MP4 encode when it is unlikely to reduce the source."""
    try:
        metadata = get_all_metadata(video_path)
    except (OSError, RuntimeError, ValueError) as exc:
        return (
            False,
            f"Analyse avant Video_encodor impossible ; encodage ignoré par précaution ({exc}).",
        )
    streams = metadata.get("streams")
    format_info = metadata.get("format")
    if not isinstance(streams, list):
        return (
            False,
            "Analyse avant Video_encodor indisponible ; encodage ignoré.",
        )
    video_stream = next(
        (
            stream
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "video"
        ),
        None,
    )
    if not isinstance(video_stream, dict):
        return False, "Aucun flux vidéo détecté ; Video_encodor ignoré."
    codec = str(video_stream.get("codec_name") or "inconnu").casefold()
    height = video_stream.get("height")
    height = height if isinstance(height, int) else None
    source_bitrate = _total_bitrate_kbps(format_info, streams)
    target_bitrate = _target_bitrate_kbps(height, cfg)
    source_label = (
        f"{source_bitrate:.0f} kb/s"
        if source_bitrate is not None
        else "indisponible"
    )
    resolution_label = f"{height}p" if height is not None else "inconnue"
    analysis = (
        "Analyse avant Video_encodor :\n"
        f"- Codec source : {codec.upper()}\n- Résolution : {resolution_label}\n"
        f"- Débit actuel : {source_label}\n- Débit H.265 estimé : {target_bitrate:.0f} kb/s\n"
    )
    if codec in {"av1", "hevc", "h265"}:
        return (
            False,
            f"{analysis}\nVideo_encodor ignoré : source déjà encodée avec {codec.upper()}.",
        )
    if source_bitrate is None:
        return (
            False,
            f"{analysis}\nVideo_encodor ignoré : débit source indisponible.",
        )
    minimum_source_bitrate = target_bitrate * (
        1 + cfg.YOUTUBE_VIDEO_ENCODOR_MIN_EXPECTED_SAVINGS_PERCENT / 100
    )
    if source_bitrate < minimum_source_bitrate:
        return (
            False,
            f"{analysis}\nVideo_encodor ignoré : gain estimé insuffisant.",
        )
    expected_savings = (1 - target_bitrate / source_bitrate) * 100
    return (
        True,
        f"{analysis}\nEncodage recommandé : réduction estimée d’environ {expected_savings:.1f} %.",
    )


def _total_bitrate_kbps(
    format_info: object, streams: list[object]
) -> float | None:
    if isinstance(format_info, dict):
        # Container bitrate is the most representative estimate when FFprobe
        # provides it; individual stream bitrates are only a fallback.
        bitrate = _bitrate_kbps(format_info.get("bit_rate"))
        if bitrate is not None:
            return bitrate
    values = [
        bitrate
        for stream in streams
        if isinstance(stream, dict)
        for bitrate in [_bitrate_kbps(stream.get("bit_rate"))]
        if bitrate is not None
    ]
    return sum(values) if values else None


def _bitrate_kbps(value: object) -> float | None:
    try:
        bitrate = float(value)
    except (TypeError, ValueError):
        return None
    return bitrate / 1_000 if bitrate > 0 else None


def _target_bitrate_kbps(height: int | None, cfg: AppConfig) -> float:
    for (
        maximum_height,
        bitrate,
    ) in cfg.YOUTUBE_VIDEO_ENCODOR_TARGET_TOTAL_BITRATE_KBPS_BY_HEIGHT:
        if height is not None and height <= maximum_height:
            return float(bitrate)
    # Unknown or larger resolutions use the highest configured target rather
    # than guessing a lower bitrate that could visibly degrade the video.
    return float(
        cfg.YOUTUBE_VIDEO_ENCODOR_TARGET_TOTAL_BITRATE_KBPS_BY_HEIGHT[-1][1]
    )


def _youtube_video_specs(video_path: Path) -> tuple[str, str, int | None]:
    metadata = get_all_metadata(video_path)
    streams = metadata.get("streams")
    if not isinstance(streams, list):
        raise ValueError(f"Aucun flux vidéo détecté dans : {video_path.name}")
    video_stream = next(
        (
            stream
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "video"
        ),
        None,
    )
    if not isinstance(video_stream, dict):
        raise ValueError(f"Aucun flux vidéo détecté dans : {video_path.name}")
    codec = str(video_stream.get("codec_name") or "inconnu").casefold()
    try:
        file_size = func_global_module.format_bytes(video_path.stat().st_size)
    except OSError:
        file_size = "indisponible"
    details = [
        "\nSpécifications de la vidéo téléchargée :",
        f"- Fichier : {video_path.name}",
        f"- Taille : {file_size}",
        f"- Codec vidéo : {codec.upper()}",
    ]
    format_info = metadata.get("format")
    if (
        isinstance(format_info, dict)
        and format_info.get("duration") is not None
    ):
        duration = format_duration_hms(format_info["duration"])
        if duration != "N/A":
            details.append(f"- Durée : {duration}")
    height = video_stream.get("height")
    width = video_stream.get("width")
    actual_height = height if isinstance(height, int) else None
    if isinstance(width, int) and actual_height is not None:
        details.append(f"- Résolution : {width}×{actual_height}")
    return codec, "\n".join(details), actual_height


def _youtube_requested_level_notice(
    media_format: str,
    requested_video_height: str,
    requested_audio_bitrate: str,
    *,
    actual_video_height: int | None = None,
    actual_audio_bitrate: float | None = None,
) -> str | None:
    if media_format == "MP4":
        expected_height = int(requested_video_height)
        if (
            actual_video_height is not None
            and actual_video_height < expected_height
        ):
            return f"Définition demandée : {expected_height}p indisponible ; définition utilisée : {actual_video_height}p."
        return None
    expected_bitrate = int(requested_audio_bitrate)
    if (
        actual_audio_bitrate is not None
        and round(actual_audio_bitrate) != expected_bitrate
    ):
        return f"Débit audio demandé : {expected_bitrate} kb/s indisponible ; débit utilisé : {round(actual_audio_bitrate)} kb/s."
    return None


def _find_new_youtube_files(
    output_dir: Path, existing_files: set[Path], media_format: str
) -> list[Path]:
    suffix = ".mp3" if media_format == "MP3" else ".mp4"
    return sorted(
        (
            path
            for path in output_dir.iterdir()
            if path not in existing_files and path.suffix.lower() == suffix
        ),
        key=lambda path: path.name.casefold(),
    )


def _is_youtube_subtitle_download_error(exc: ValueError) -> bool:
    message = str(exc).casefold()
    return "subtitle" in message and (
        "unable to download video subtitles" in message
        or "http error 429" in message
    )

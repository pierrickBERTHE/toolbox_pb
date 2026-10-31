"""
Ce fichier contient les fonctions pour la compression audio MP3.

Auteurs :
Pierrick BERTHE
mail : pierrick.berthe@gmx.fr
Octobre 2026
"""

import json
from pathlib import Path
import subprocess
from mutagen import File as open_audio_file
from mutagen.id3 import COMM, POPM
from mutagen.mp3 import MP3

from func_global import (
    build_video_processing_comment,
    is_processable_file,
    preserve_file_modification_time,
)


def find_audio_files(input_dir: Path, extensions: list[str]) -> list[Path]:
    """Return supported audio files in deterministic relative-path order."""
    accepted_extensions = {extension.lower() for extension in extensions}
    return sorted(
        (
            path for path in input_dir.rglob("*")
            if is_processable_file(path)
            and path.suffix.lower() in accepted_extensions
        ),
        key=lambda path: str(path.relative_to(input_dir)).lower(),
    )


def read_audio_comment(audio_path: Path) -> str | None:
    """Return the existing media comment, without failing the batch on probe errors."""
    command = [
        "ffprobe", "-v", "error",
        "-show_entries", "format_tags=comment:stream_tags=comment",
        "-of", "json", str(audio_path),
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, check=True
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    metadata = json.loads(result.stdout)
    format_comment = metadata.get("format", {}).get("tags", {}).get("comment")
    if format_comment:
        return format_comment
    for stream in metadata.get("streams", []):
        comment = stream.get("tags", {}).get("comment")
        if comment:
            return comment
    return None


def build_audio_processing_comment(input_path: Path, bitrate_kbps: int) -> str:
    """Build history with the shared toolbox processing-comment helper."""
    return build_video_processing_comment(
        input_path,
        f"audio_compressor | MP3 : {bitrate_kbps} kb/s",
        audio_codec="libmp3lame",
    )


def probe_audio_bitrate_kbps(input_path: Path) -> float | None:
    """Return the source average bitrate in kb/s, or None when unavailable."""
    command = [
        "ffprobe", "-v", "error", "-show_entries", "format=bit_rate",
        "-of", "json", str(input_path),
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, check=True
        )
        bitrate_bps = json.loads(result.stdout).get("format", {}).get("bit_rate")
        return float(bitrate_bps) / 1_000 if bitrate_bps else None
    except (
        FileNotFoundError, subprocess.CalledProcessError, TypeError, ValueError,
        json.JSONDecodeError,
    ):
        return None


def copy_star_rating(input_path: Path, output_path: Path) -> None:
    """Copy Windows star ratings (ID3 POPM frames) to an output MP3.

    FFmpeg preserves common text tags but does not reliably carry the ID3
    POPM frame that Windows uses for its five-star rating property.
    """
    # try to read the input and output audio files with mutagen.
    # If either fails, return early.
    try:
        input_audio = open_audio_file(input_path)
        output_audio = MP3(output_path)
    except Exception:
        return
    if input_audio is None or input_audio.tags is None or output_audio.tags is None:
        return

    # Copy all POPM frames from the input to the output, preserving the email, rating and count.
    ratings = [
        frame for key, frame in input_audio.tags.items()
        if key.startswith("POPM")
    ]
    if not ratings:
        return
    output_audio.tags.delall("POPM")
    for rating in ratings:
        output_audio.tags.add(
            POPM(
                email=rating.email,
                rating=rating.rating,
                count=getattr(rating, "count", 0),
            )
        )
    try:
        output_audio.save(v2_version=3)
    except Exception:
        # Rating metadata must never prevent audio compression from finishing.
        return


def write_id3_processing_comment(
    output_path: Path, processing_comment: str
) -> None:
    """Write a Windows-visible ID3 COMM frame to an MP3 output."""
    try:
        output_audio = MP3(output_path)
        if output_audio.tags is None:
            output_audio.add_tags()
        output_audio.tags.delall("COMM")
        output_audio.tags.add(
            # Windows Explorer can filter COMM frames by UI language. Use the
            # French ISO-639-2 code used by this French-language toolbox.
            COMM(encoding=1, lang="fra", desc="", text=processing_comment)
        )
        output_audio.save(v1=1, v2_version=3)
    except Exception as exc:
        print(f"Commentaire ID3 non écrit : {output_path.name} ({exc})")


def _build_mp3_command(
    input_path: Path,
    output_path: Path,
    processing_comment: str,
    audio_options: list[str],
) -> list[str]:
    """Build an MP3 command that copies tags, artwork and the new comment."""
    return [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(input_path),
        "-map", "0:a:0", "-map", "0:v?", "-map_metadata", "0",
        *audio_options,
        "-c:v", "copy", "-disposition:v:0", "attached_pic",
        "-id3v2_version", "3", "-write_id3v1", "1",
        "-metadata", f"comment={processing_comment}",
        str(output_path),
    ]


def compress_audio_to_mp3(
    input_path: Path,
    output_path: Path,
    bitrate_kbps: int,
    processing_comment: str,
) -> None:
    """Encode one source directly to MP3 at the requested bitrate."""
    if bitrate_kbps <= 0:
        raise ValueError("AUDIO_COMPRESSOR_MP3_BITRATE_KBPS doit être positif.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        _build_mp3_command(
            input_path, output_path, processing_comment,
            ["-c:a", "libmp3lame", "-b:a", f"{bitrate_kbps}k"],
        ),
        check=True,
    )
    copy_star_rating(input_path, output_path)
    write_id3_processing_comment(output_path, processing_comment)
    if output_path.exists():
        preserve_file_modification_time(input_path, output_path)

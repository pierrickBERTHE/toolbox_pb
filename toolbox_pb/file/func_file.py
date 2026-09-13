"""Low-level helpers for file-management features."""

from datetime import datetime
from pathlib import Path
import re
import shutil


# Regex to match the timeline-sort prefix of a filename.
_TIMELINE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}__")


def get_file_modification_time(input_path: Path) -> datetime:
    """Return the timestamp of the last file-content modification."""

    stat_result = input_path.stat()
    return datetime.fromtimestamp(stat_result.st_mtime)


def is_timeline_filename(filename: str) -> bool:
    """Return whether a filename already has the timeline-sort prefix."""

    return bool(_TIMELINE_PREFIX.match(filename))


def build_timeline_filename(input_path: Path, modification_time: datetime) -> str:
    """Build a sortable filename that retains the original filename and suffix."""

    return f"{modification_time:%Y-%m-%d_%H-%M-%S}__{input_path.name}"


def copy_file_for_timeline(input_path: Path, output_path: Path) -> bool:
    """Copy one file with metadata unless its timeline output already exists."""

    if output_path.exists():
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(input_path, output_path)
    return True

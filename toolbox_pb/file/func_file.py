"""Low-level helpers for file-management features."""

from datetime import date, datetime
from pathlib import Path
import re
import shutil
import unicodedata


# Regex to match the timeline-sort prefix of a filename.
_TIMELINE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}__")

# Regex to match a French date anywhere in a folder name, e.g. "Title - 1er janvier 2023".
_FRENCH_DATE = re.compile(
    r"(?<!\w)(?P<day>1er|\d{1,2})\s+(?P<month>[^\W\d_]+)\s+"
    r"(?P<year>\d{4})(?!\w)",
    re.IGNORECASE | re.UNICODE,
)

# Mapping of French month names to their corresponding month numbers.
_FRENCH_MONTHS = {
    "janvier": 1,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "decembre": 12,
}


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


def remove_string_from_filename(filename: str, string_to_remove: str) -> str:
    """Return a filename with every occurrence of a string removed."""

    return filename.replace(string_to_remove, "")


def copy_file_for_string_removal(input_path: Path, output_path: Path) -> bool:
    """Copy one renamed file unless its destination already exists."""

    if output_path.exists():
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(input_path, output_path)
    return True


def _normalize_french_month(month: str) -> str:
    """Return a lowercase, accent-free representation of a French month."""
    return "".join(
        character
        for character in unicodedata.normalize("NFD", month.casefold())
        if unicodedata.category(character) != "Mn"
    )


def _levenshtein_distance(left: str, right: str) -> int:
    """Return the Levenshtein distance between two strings. 
    it is the number of single-character edits (insertions, deletions, or 
    substitutions) required to change one string into the other.
    
    for exemple, the Levenshtein distance between "octobre" and "octobr" is 1, 
    because only one character needs to be removed to make the two strings identical.
    but the Levenshtein distance between "octobre" and "novembre" is 6, 
    because six characters need to be changed to make the two strings identical.
    """
    previous_row = list(range(len(right) + 1))
    for left_index, left_character in enumerate(left, start=1):
        current_row = [left_index]
        for right_index, right_character in enumerate(right, start=1):
            current_row.append(
                min(
                    current_row[-1] + 1,
                    previous_row[right_index] + 1,
                    previous_row[right_index - 1]
                    + (left_character != right_character),
                )
            )
        previous_row = current_row
    return previous_row[-1]


def get_french_month_number(month: str) -> int | None:
    """Return a French month number, accepting accents and one typo at most.

    A fuzzy result is used only when it identifies exactly one month. This keeps
    names with an ambiguous or unrecognised month unchanged.
    """

    # Normalize the month name and check for an exact match in the dictionary.
    normalized_month = _normalize_french_month(month)
    if normalized_month in _FRENCH_MONTHS:
        return _FRENCH_MONTHS[normalized_month]

    # If no exact match was found, check for a fuzzy match with at most one typo.
    candidates = [
        month_number
        for french_month, month_number in _FRENCH_MONTHS.items()
        if _levenshtein_distance(normalized_month, french_month) <= 1
    ]
    return candidates[0] if len(candidates) == 1 else None


def build_dated_folder_name(folder_name: str) -> str | None:
    """Build a ``YYMMDD-title`` folder name from a French date anywhere in it.

    The matched date is removed from the title and inserted as the prefix.
    ``None`` is returned for names without a valid date or whose month cannot
    be safely recognised.
    """

    # Match the first French date in the folder name.
    match = _FRENCH_DATE.search(folder_name)
    if match is None:
        return None

    # Convert the French month name to a month number, returning None if not recognised.
    month_number = get_french_month_number(match.group("month"))
    if month_number is None:
        return None

    # Parse the day and year, returning None if they are invalid.
    try:
        day_text = match.group("day")
        parsed_date = date(
            int(match.group("year")),
            month_number,
            int(day_text[:-2] if day_text.casefold().endswith("er") else day_text),
        )
    except ValueError:
        return None

    # Remove a date wherever it occurs. Separators left at either edge are
    # dropped, while repeated separators in a middle position collapse to one.
    title = folder_name[:match.start()] + folder_name[match.end():]
    title = re.sub(r"\s{2,}", " ", title)
    title = re.sub(r"(?:\s*[-–—]\s*){2,}", " - ", title)
    title = title.strip(" \t-–—")

    return f"{parsed_date:%y%m%d}-{title}"


def copy_folder(input_path: Path, output_path: Path) -> bool:
    """Copy a complete folder tree unless its destination already exists."""

    if output_path.exists():
        return False

    shutil.copytree(input_path, output_path, copy_function=shutil.copy2)
    return True

"""Unit tests for low-level file timeline helpers."""

from datetime import datetime
import os
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2] / "toolbox_pb"))

from file import func_file


def test_get_file_modification_time_uses_the_last_modification_timestamp(tmp_path):
    """The timeline source date must come from the file modification time."""
    input_path = tmp_path / "archive.txt"
    input_path.touch()
    timestamp = datetime(2020, 6, 15, 12, 30, 45).timestamp()
    os.utime(input_path, (timestamp, timestamp))

    modification_time = func_file.get_file_modification_time(input_path)

    assert modification_time == datetime(2020, 6, 15, 12, 30, 45)


def test_build_timeline_filename_keeps_original_name_and_adds_sortable_date(tmp_path):
    """The date prefix must sort chronologically and preserve the file extension."""
    input_path = tmp_path / "vacances.jpg"

    filename = func_file.build_timeline_filename(
        input_path, datetime(2026, 9, 12, 8, 30, 5)
    )

    assert filename == "2026-09-12_08-30-05__vacances.jpg"


def test_copy_file_for_timeline_copies_without_changing_the_source(tmp_path):
    """The timeline copy must leave its input file intact."""
    input_path = tmp_path / "facture.pdf"
    input_path.write_text("source", encoding="utf-8")
    output_path = tmp_path / "output" / "2026-01-02_03-04-05__facture.pdf"

    copied = func_file.copy_file_for_timeline(input_path, output_path)

    assert copied is True
    assert input_path.read_text(encoding="utf-8") == "source"
    assert output_path.read_text(encoding="utf-8") == "source"


def test_copy_file_for_timeline_skips_an_existing_output(tmp_path):
    """An existing output must not be overwritten on a repeated run."""
    input_path = tmp_path / "facture.pdf"
    output_path = tmp_path / "output" / "2026-01-02_03-04-05__facture.pdf"
    input_path.write_text("source", encoding="utf-8")
    output_path.parent.mkdir()
    output_path.write_text("existing", encoding="utf-8")

    copied = func_file.copy_file_for_timeline(input_path, output_path)

    assert copied is False
    assert output_path.read_text(encoding="utf-8") == "existing"


def test_is_timeline_filename_recognizes_only_valid_prefixes():
    """Already redated files must be distinguishable from ordinary filenames."""
    assert func_file.is_timeline_filename("2026-09-12_08-30-05__photo.jpg")
    assert not func_file.is_timeline_filename("photo_2026-09-12.jpg")

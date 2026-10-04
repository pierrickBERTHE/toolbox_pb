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


def test_remove_string_from_filename_removes_every_occurrence():
    """The requested string is removed everywhere in the filename."""
    assert (
        func_file.remove_string_from_filename(
            "photo_compressed_90_compressed_90.jpg", "_compressed_90"
        )
        == "photo.jpg"
    )


def test_copy_file_for_string_removal_skips_an_existing_destination(tmp_path):
    """A renamed destination must not be overwritten."""
    input_path = tmp_path / "photo_compressed_90.jpg"
    output_path = tmp_path / "output" / "photo.jpg"
    input_path.write_text("source", encoding="utf-8")
    output_path.parent.mkdir()
    output_path.write_text("existing", encoding="utf-8")

    copied = func_file.copy_file_for_string_removal(input_path, output_path)

    assert copied is False
    assert output_path.read_text(encoding="utf-8") == "existing"


def test_build_dated_folder_name_converts_a_french_date_prefix():
    assert (
        func_file.build_dated_folder_name(
            "17 octobre 2010 - Triathlon du Cap sicié CD (1500m, 43kms, 10kms)"
        )
        == "101017-Triathlon du Cap sicié CD (1500m, 43kms, 10kms)"
    )


def test_build_dated_folder_name_accepts_first_day_written_as_1er():
    assert (
        func_file.build_dated_folder_name("1er mai 2011 - Course")
        == "110501-Course"
    )


def test_build_dated_folder_name_accepts_missing_accents_and_one_typo():
    assert (
        func_file.build_dated_folder_name("25 fevrer 2010 - Triathlon")
        == "100225-Triathlon"
    )
    assert (
        func_file.build_dated_folder_name("9 aoutt 2013 - Meeting")
        == "130809-Meeting"
    )


def test_build_dated_folder_name_rejects_invalid_or_unknown_dates():
    assert func_file.build_dated_folder_name("31 avril 2013 - Impossible") is None
    assert func_file.build_dated_folder_name("9 inconnu 2013 - Meeting") is None


def test_copy_folder_does_not_overwrite_an_existing_destination(tmp_path):
    source = tmp_path / "9 mai 2013 - Meeting"
    destination = tmp_path / "130509-Meeting"
    source.mkdir()
    destination.mkdir()

    assert func_file.copy_folder(source, destination) is False
    assert source.is_dir()


def test_copy_folder_preserves_the_source_tree(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "output" / "destination"
    nested_file = source / "nested" / "result.txt"
    nested_file.parent.mkdir(parents=True)
    nested_file.write_text("content", encoding="utf-8")

    assert func_file.copy_folder(source, destination) is True
    assert nested_file.read_text(encoding="utf-8") == "content"
    assert (destination / "nested" / "result.txt").read_text(encoding="utf-8") == "content"

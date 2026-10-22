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
    """Convert a French date at the start of a folder name."""
    assert (
        func_file.build_dated_folder_name(
            "17 octobre 2010 - Triathlon du Cap sicié CD (1500m, 43kms, 10kms)"
        )
        == "101017-Triathlon du Cap sicié CD (1500m, 43kms, 10kms)"
    )


def test_build_dated_folder_name_moves_a_date_at_the_end_to_the_prefix():
    """Move a trailing French date to the start of the folder name."""
    assert (
        func_file.build_dated_folder_name(
            "Match Fruit des Fondus Vs. Les clichés d'Eyguières - 8 avril 2017"
        )
        == "170408-Match Fruit des Fondus Vs. Les clichés d'Eyguières"
    )


def test_build_dated_folder_name_accepts_first_day_written_as_1er():
    """Recognize the French ordinal spelling of the first day."""
    assert (
        func_file.build_dated_folder_name("1er mai 2011 - Course")
        == "110501-Course"
    )


def test_build_dated_folder_name_accepts_missing_accents_and_one_typo():
    """Accept unaccented month names and a single spelling error."""
    assert (
        func_file.build_dated_folder_name("25 fevrer 2010 - Triathlon")
        == "100225-Triathlon"
    )
    assert (
        func_file.build_dated_folder_name("9 aoutt 2013 - Meeting")
        == "130809-Meeting"
    )


def test_build_dated_folder_name_rejects_invalid_or_unknown_dates():
    """Reject invalid calendar dates and unknown month names."""
    assert func_file.build_dated_folder_name("31 avril 2013 - Impossible") is None
    assert func_file.build_dated_folder_name("9 inconnu 2013 - Meeting") is None


def test_copy_folder_does_not_overwrite_an_existing_destination(tmp_path):
    """Keep both folders unchanged when the destination already exists."""
    source = tmp_path / "9 mai 2013 - Meeting"
    destination = tmp_path / "130509-Meeting"
    source.mkdir()
    destination.mkdir()

    assert func_file.copy_folder(source, destination) is False
    assert source.is_dir()


def test_copy_folder_preserves_the_source_tree(tmp_path):
    """Copy nested files while leaving the original tree intact."""
    source = tmp_path / "source"
    destination = tmp_path / "output" / "destination"
    nested_file = source / "nested" / "result.txt"
    nested_file.parent.mkdir(parents=True)
    nested_file.write_text("content", encoding="utf-8")

    assert func_file.copy_folder(source, destination) is True
    assert nested_file.read_text(encoding="utf-8") == "content"
    assert (destination / "nested" / "result.txt").read_text(encoding="utf-8") == "content"


def test_cache_size_and_clean_contents_preserve_root(tmp_path):
    """Measure and remove cache contents while retaining the root folder."""
    cache = tmp_path / "cache"
    (cache / "nested").mkdir(parents=True)
    (cache / "nested" / "file").write_bytes(b"12345")
    (cache / "file").write_bytes(b"123")

    assert func_file.get_size(cache) == 8
    assert func_file.clean_contents(cache) == 8
    assert cache.is_dir() and not list(cache.iterdir())
    assert func_file.clean_contents(tmp_path / "missing") == 0


def test_cache_size_format_uses_decimal_units():
    """Display cache sizes in decimal megabytes or gigabytes."""
    assert func_file.format_size(125_000_000) == "125.0 Mo"
    assert func_file.format_size(1_000_000_000) == "1.0 Go"


def test_get_cli_caches_handles_missing_and_empty_commands(
    tmp_path, monkeypatch, capsys
):
    """Report unavailable tools and empty cache paths without failing."""
    from types import SimpleNamespace

    commands = [
        ("ok", ["ok", "dir"], ["ok", "clean"]),
        ("empty", ["empty", "dir"], ["empty", "clean"]),
        ("missing", ["missing", "dir"], ["missing", "clean"]),
    ]
    monkeypatch.setattr(func_file.config_global, "CLI_CLEAN_COMMANDS", commands)

    def run(command, **kwargs):
        if command[0] == "missing":
            raise FileNotFoundError("missing tool")
        return SimpleNamespace(stdout=str(tmp_path) if command[0] == "ok" else " ")

    monkeypatch.setattr(func_file.subprocess, "run", run)
    assert func_file.get_cli_caches() == [("ok", tmp_path, ["ok", "clean"])]
    output = capsys.readouterr().out
    assert "empty : unable to find cache" in output
    assert "missing : unable to find cache" in output


def test_cli_cleaner_measures_partial_cleanup_on_failure(
    tmp_path, monkeypatch, capsys
):
    """Count files removed before a cleaner reports an incomplete operation."""
    from types import SimpleNamespace

    (tmp_path / "removed").write_bytes(b"12345")
    (tmp_path / "remaining").write_bytes(b"123")

    def run(command, **kwargs):
        (tmp_path / "removed").unlink()
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(func_file.subprocess, "run", run)
    assert func_file.run_cli_cleaners([("test", tmp_path, ["test", "clean"])]) == 5
    assert "cleaning failed or incomplete" in capsys.readouterr().out
    assert (tmp_path / "remaining").is_file()

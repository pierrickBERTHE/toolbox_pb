"""Unit tests for the file timeline sorter workflow."""

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import sys

sys.path.append(str(Path(__file__).resolve().parents[2] / "toolbox_pb"))

from file.main_file import folder_date_renammer, file_str_remover, file_timeline_sorter


def test_file_timeline_sorter_copies_files_from_their_modification_dates(tmp_path):
    """The generated output prefixes make alphabetical sorting chronological."""
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    later_file = input_dir / "zebra.jpg"
    earlier_file = input_dir / "alpha.pdf"
    later_file.touch()
    earlier_file.touch()
    cfg = SimpleNamespace(INPUT_DIR=input_dir, OUTPUT_DIR=output_dir)
    modification_times = {
        later_file: datetime(2026, 5, 2, 10, 0, 0),
        earlier_file: datetime(2026, 5, 1, 10, 0, 0),
    }

    with mock.patch(
        "file.main_file.func_file.get_file_modification_time",
        side_effect=lambda path: modification_times[path],
    ):
        is_empty = file_timeline_sorter(cfg)

    assert is_empty is False
    assert sorted(path.name for path in input_dir.iterdir()) == ["alpha.pdf", "zebra.jpg"]
    assert sorted(path.name for path in output_dir.iterdir()) == [
        "2026-05-01_10-00-00__alpha.pdf",
        "2026-05-02_10-00-00__zebra.jpg",
    ]


def test_file_timeline_sorter_copies_already_redated_files_without_new_prefix(tmp_path):
    """Existing prefixes are retained when files are copied to the output."""
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    (input_dir / "2026-05-01_10-00-00__photo.jpg").touch()
    cfg = SimpleNamespace(INPUT_DIR=input_dir, OUTPUT_DIR=output_dir)

    is_empty = file_timeline_sorter(cfg)

    assert is_empty is False
    assert (output_dir / "2026-05-01_10-00-00__photo.jpg").is_file()


def test_file_timeline_sorter_ignores_gitkeep_in_input(tmp_path):
    """Git placeholders must never be copied or considered input files."""
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    (input_dir / ".gitkeep").touch()
    cfg = SimpleNamespace(INPUT_DIR=input_dir, OUTPUT_DIR=output_dir)

    is_empty = file_timeline_sorter(cfg)

    assert is_empty is True
    assert not output_dir.exists()


def test_file_str_remover_copies_renamed_files_and_preserves_subdirectories(tmp_path):
    """String removal must copy files without changing the source tree."""
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    nested_dir = input_dir / "nested"
    nested_dir.mkdir(parents=True)
    source_path = nested_dir / "photo_compressed_90.jpg"
    source_path.write_text("source", encoding="utf-8")
    cfg = SimpleNamespace(INPUT_DIR=input_dir, OUTPUT_DIR=output_dir)

    is_empty = file_str_remover(cfg, "_compressed_90")

    assert is_empty is False
    assert source_path.is_file()
    assert source_path.read_text(encoding="utf-8") == "source"
    assert (output_dir / "nested" / "photo.jpg").read_text(encoding="utf-8") == "source"


def test_file_str_remover_ignores_gitkeep_in_input(tmp_path):
    """Git placeholders must not trigger the string-removal workflow."""
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    (input_dir / ".gitkeep").touch()
    cfg = SimpleNamespace(INPUT_DIR=input_dir, OUTPUT_DIR=output_dir)

    is_empty = file_str_remover(cfg, "_compressed_90")

    assert is_empty is True
    assert not output_dir.exists()


def test_folder_date_renammer_copies_direct_input_folders_with_renamed_dates(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    source_folder = input_dir / "9 mai 2013 - Meeting d'Aubagne (800m+1500m)"
    nested_folder = source_folder / "17 octobre 2010 - Ne pas renommer"
    nested_folder.mkdir(parents=True)
    (input_dir / "unrelated folder").mkdir()
    output_dir = tmp_path / "output"
    cfg = SimpleNamespace(INPUT_DIR=input_dir, OUTPUT_DIR=output_dir)

    is_empty = folder_date_renammer(cfg)

    renamed_folder = input_dir / "130509-Meeting d'Aubagne (800m+1500m)"
    assert is_empty is False
    assert source_folder.is_dir()
    assert nested_folder.is_dir()
    assert not renamed_folder.exists()
    copied_folder = output_dir / renamed_folder.name
    assert (copied_folder / nested_folder.name).is_dir()
    assert (input_dir / "unrelated folder").is_dir()
    assert (output_dir / "unrelated folder").is_dir()


def test_folder_date_renammer_returns_true_without_direct_folders(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    cfg = SimpleNamespace(INPUT_DIR=input_dir, OUTPUT_DIR=tmp_path / "output")

    assert folder_date_renammer(cfg) is True

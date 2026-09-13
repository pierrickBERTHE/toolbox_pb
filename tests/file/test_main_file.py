"""Unit tests for the file timeline sorter workflow."""

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import sys

sys.path.append(str(Path(__file__).resolve().parents[2] / "toolbox_pb"))

from file.main_file import file_timeline_sorter


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

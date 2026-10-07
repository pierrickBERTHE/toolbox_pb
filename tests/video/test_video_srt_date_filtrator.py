"""Unit tests for video_srt_date_filtrator."""

import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2] / "toolbox_pb"))

from config_global import AppConfig
from video.main_video import video_srt_date_filtrator


@pytest.fixture
def fake_config(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    segment_dir = tmp_path / "segment"
    input_dir.mkdir()
    output_dir.mkdir()
    segment_dir.mkdir()
    return AppConfig(
        INPUT_ACCEPTED_VIDEO_FILES=[".mp4"],
        INPUT_ACCEPTED_IMAGE_FILES=[".jpg"],
        INPUT_ACCEPTED_PDF_FILES=[".pdf"],
        CODEC_VIDEO_LIST=["libx265"],
        CODEC_VIDEO="libx265",
        CODEC_AUDIO="aac",
        SUFFIX_OUTPUT=[".mp4", ".jpg", ".pdf"],
        SUFFIX_OUTPUT_VIDEO=".mp4",
        SUFFIX_OUTPUT_IMAGE=".jpg",
        SUFFIX_OUTPUT_PDF=".pdf",
        ROOT=tmp_path,
        LOG_DIR=tmp_path / "log",
        INPUT_DIR=input_dir,
        OUTPUT_DIR=output_dir,
        SEGMENT_DIR=segment_dir,
        LOG_TO_FILE=False,
    )


def test_filters_later_duplicate_dates_and_prints_statistics(fake_config, capsys):
    source = fake_config.INPUT_DIR / "subtitles.txt"
    source.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\n01/02/2020\n\n"
        "2\n00:00:02,000 --> 00:00:03,000\nTexte sans date\n\n"
        "3\n00:00:04,000 --> 00:00:05,000\n2020-02-01\n\n"
        "4\n00:00:06,000 --> 00:00:07,000\n03.02.2020\n",
        encoding="utf-8",
    )

    assert video_srt_date_filtrator(fake_config) is False

    output = (fake_config.OUTPUT_DIR / "subtitles.txt").read_text(encoding="utf-8")
    assert "01/02/2020" in output
    assert "Texte sans date" in output
    assert "2020-02-01" not in output
    assert "03.02.2020" in output
    assert output.startswith("1\n")
    assert "3\n00:00:06,000" in output

    captured = capsys.readouterr().out
    assert "Avant filtrage : 2 date(s) différente(s), 3 occurrence(s) de date, 4 sous-titre(s) détecté(s)." in captured
    assert "Dates en doublon détectées :" in captured
    assert "- 01/02/2020 : 2 occurrence(s)" in captured
    assert "\nAprès filtrage : 2 date(s) différente(s), 2 occurrence(s) de date, 3 sous-titre(s) détecté(s)." in captured
    assert "Aucune date en doublon détectée." in captured


def test_returns_true_when_no_txt_file_exists(fake_config):
    assert video_srt_date_filtrator(fake_config) is True


def test_filters_standard_srt_files(fake_config):
    source = fake_config.INPUT_DIR / "subtitles.srt"
    source.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\n01/02/2020\n\n"
        "2\n00:00:02,000 --> 00:00:03,000\n01/02/2020\n",
        encoding="utf-8",
    )

    assert video_srt_date_filtrator(fake_config) is False
    output = (fake_config.OUTPUT_DIR / "subtitles.srt").read_text(encoding="utf-8")
    assert output.count("01/02/2020") == 1


def test_filters_extracted_srt_in_place(fake_config):
    """The extractor follow-up can overwrite the freshly generated SRT."""
    extracted_srt = fake_config.OUTPUT_DIR / "subtitles.srt"
    extracted_srt.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\n01/02/2020\n\n"
        "2\n00:00:02,000 --> 00:00:03,000\n01/02/2020\n",
        encoding="utf-8",
    )

    assert video_srt_date_filtrator(
        fake_config,
        source_files=[extracted_srt],
        output_dir=fake_config.OUTPUT_DIR,
        overwrite=True,
    ) is False

    assert extracted_srt.read_text(encoding="utf-8").count("01/02/2020") == 1

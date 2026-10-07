"""Unit tests for video_convert_srt_to_ass."""

import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2] / "toolbox_pb"))

from config_global import AppConfig
from video.main_video import video_convert_srt_to_ass


@pytest.fixture
def fake_config(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    segment_dir = tmp_path / "segment"
    template_dir = tmp_path / "data" / "template"
    input_dir.mkdir()
    output_dir.mkdir()
    segment_dir.mkdir()
    template_dir.mkdir(parents=True)
    (template_dir / "template_sous_titre.ass").write_text(
        "[Script Info]\nTitle: Test\n\n[V4+ Styles]\n"
        "Format: Name, Fontname\nStyle: sous-titre,Arial\n\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:01.00,sous-titre,,0,0,0,,Template text\n",
        encoding="utf-8",
    )
    return AppConfig(
        INPUT_ACCEPTED_VIDEO_FILES=[".mp4"],
        INPUT_ACCEPTED_IMAGE_FILES=[".jpg"],
        INPUT_ACCEPTED_PDF_FILES=[".pdf"],
        CODEC_VIDEO_LIST=["libx265"], CODEC_VIDEO="libx265", CODEC_AUDIO="aac",
        SUFFIX_OUTPUT=[".mp4", ".jpg", ".pdf"], SUFFIX_OUTPUT_VIDEO=".mp4",
        SUFFIX_OUTPUT_IMAGE=".jpg", SUFFIX_OUTPUT_PDF=".pdf", ROOT=tmp_path,
        LOG_DIR=tmp_path / "log", INPUT_DIR=input_dir, OUTPUT_DIR=output_dir,
        SEGMENT_DIR=segment_dir, LOG_TO_FILE=False,
    )


@pytest.mark.parametrize(
    "subtitle_text",
    [
        "26/12/2024 - 1er bain de Lino",
        "26/12/2024- 1er bain de Lino",
        "26/12/2024 -1er bain de Lino",
        "26/12/2024-1er bain de Lino",
    ],
)
def test_converts_dated_title_with_any_spacing_around_dash(fake_config, subtitle_text):
    (fake_config.INPUT_DIR / "captions.srt").write_text(
        "1\n00:00:23,200 --> 00:00:33,200\n"
        f"{subtitle_text}\n",
        encoding="utf-8",
    )

    assert video_convert_srt_to_ass(fake_config) is False

    output = (fake_config.OUTPUT_DIR / "captions.ass").read_text(encoding="utf-8")
    assert "Title: Test" in output
    assert "Template text" not in output
    assert "Dialogue: 0,0:00:24.00,0:00:29.00,TITRE,,0,0,0,,{\\fad(1000,1000)}1er bain de Lino" in output
    assert "Dialogue: 0,0:00:24.00,0:00:34.00,sous-titre,,0,0,0,,{\\fad(500,500)}26/12/2024" in output


def test_returns_true_when_no_srt_file_exists(fake_config):
    assert video_convert_srt_to_ass(fake_config) is True


def test_uses_configured_ass_durations_and_fades(fake_config):
    config = replace(
        fake_config,
        ASS_TITLE_DURATION_SECONDS=3.0,
        ASS_SUBTITLE_DURATION_SECONDS=7.0,
        ASS_TITLE_FADE_DURATION_MS=250,
        ASS_SUBTITLE_FADE_DURATION_MS=750,
    )
    (config.INPUT_DIR / "captions.srt").write_text(
        "1\n00:00:23,200 --> 00:00:24,000\n"
        "26/12/2024-1er bain de Lino\n",
        encoding="utf-8",
    )

    assert video_convert_srt_to_ass(config) is False

    output = (config.OUTPUT_DIR / "captions.ass").read_text(encoding="utf-8")
    assert "0:00:24.00,0:00:27.00,TITRE,,0,0,0,,{\\fad(250,250)}" in output
    assert "0:00:24.00,0:00:31.00,sous-titre,,0,0,0,,{\\fad(750,750)}" in output

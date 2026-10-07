"""Tests for automatic SRT post-processing after video assembly."""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2] / "toolbox_pb"))

from video.main_video import _extract_and_filter_assembled_srt
import video.main_video as main_video


def test_extracts_filters_and_replaces_assembled_video(tmp_path, monkeypatch, capsys):
    assembled_video = tmp_path / "assembled.mp4"
    assembled_video.write_bytes(b"with-subtitles")

    def fake_extractor(input_video, output_video, srt_output_path, processing_comment):
        assert input_video == assembled_video
        assert "video_srt_extractor | video_srt_date_filtrator" in processing_comment
        output_video.write_bytes(b"without-subtitles")
        srt_output_path.write_text(
            "1\n00:00:00,000 --> 00:00:10,000\n01/01/2025\n\n"
            "2\n00:00:11,000 --> 00:00:21,000\n01/01/2025\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(main_video.func_vid, "extract_video_srt_ffmpeg", fake_extractor)
    monkeypatch.setattr(
        main_video.func_glob,
        "build_video_processing_comment",
        lambda *_: "video_srt_extractor | video_srt_date_filtrator",
    )

    _extract_and_filter_assembled_srt(assembled_video)

    assert assembled_video.read_bytes() == b"without-subtitles"
    output_srt = assembled_video.with_suffix(".srt").read_text(encoding="utf-8")
    assert output_srt.count("01/01/2025") == 1
    output = capsys.readouterr().out
    assert "VIDEO_ASSEMBLOR_EXTRACT_AND_FILTER_DATES activé" in output
    assert "Vidéo_srt_extractor après l'assemblage" in output
    assert "Vidéo_srt_date_filtrator après l'extraction" in output
    assert "Extraction et filtrage des sous-titres terminés" in output

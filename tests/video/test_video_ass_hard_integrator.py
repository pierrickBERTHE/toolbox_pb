"""Unit tests for video_ass_hard_integrator."""

import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2] / "toolbox_pb"))

from config_global import AppConfig
from video.main_video import video_ass_hard_integrator
from video.func_video import integrate_ass_hard_ffmpeg


@pytest.fixture
def fake_config(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    segment_dir = tmp_path / "segment"
    input_dir.mkdir()
    output_dir.mkdir()
    segment_dir.mkdir()
    return AppConfig(
        INPUT_ACCEPTED_FILES=[".mp4"], INPUT_ACCEPTED_VIDEO_FILES=[".mp4"],
        INPUT_ACCEPTED_IMAGE_FILES=[".jpg"], INPUT_ACCEPTED_PDF_FILES=[".pdf"],
        CODEC_VIDEO_LIST=["libx265"], CODEC_VIDEO="libx265", CODEC_AUDIO="aac",
        SUFFIX_OUTPUT=[".mp4", ".jpg", ".pdf"], SUFFIX_OUTPUT_VIDEO=".mp4",
        SUFFIX_OUTPUT_IMAGE=".jpg", SUFFIX_OUTPUT_PDF=".pdf", ROOT=tmp_path,
        LOG_DIR=tmp_path / "log", INPUT_DIR=input_dir, OUTPUT_DIR=output_dir,
        SEGMENT_DIR=segment_dir, LOG_TO_FILE=False, ADD_CODEC_NAME_IN_OUTPUT=True,
    )


def test_burns_matching_ass_with_global_codecs_and_output_name(fake_config):
    video = fake_config.INPUT_DIR / "clip.mp4"
    ass = fake_config.INPUT_DIR / "clip.ass"
    video.touch()
    ass.touch()

    with mock.patch("video.main_video.func_vid.integrate_ass_hard_ffmpeg") as burner:
        assert video_ass_hard_integrator(fake_config) is False

    burner.assert_called_once_with(
        input_video=video,
        ass_path=ass,
        output_video=fake_config.OUTPUT_DIR / "clip_libx265.mp4",
        codec_video="libx265",
        codec_audio="aac",
        processing_comment="toolbox_pb :\nn_1 : video_ass_hard_integrator | V : libx265 | A : aac",
    )


def test_uses_a_single_ass_for_all_videos(fake_config):
    (fake_config.INPUT_DIR / "one.mp4").touch()
    (fake_config.INPUT_DIR / "two.mp4").touch()
    shared_ass = fake_config.INPUT_DIR / "captions.ass"
    shared_ass.touch()

    with mock.patch("video.main_video.func_vid.integrate_ass_hard_ffmpeg") as burner:
        assert video_ass_hard_integrator(fake_config) is False

    assert burner.call_count == 2
    assert all(call.kwargs["ass_path"] == shared_ass for call in burner.call_args_list)


def test_requires_a_subtitle_file(fake_config, capsys):
    (fake_config.INPUT_DIR / "clip.mp4").touch()

    assert video_ass_hard_integrator(fake_config) is True
    assert "Aucun fichier SRT ou ASS" in capsys.readouterr().out


def test_converts_srt_before_hard_integration(fake_config):
    video = fake_config.INPUT_DIR / "clip.mp4"
    srt = fake_config.INPUT_DIR / "clip.srt"
    template = fake_config.ROOT / "data" / "template" / "template_sous_titre.ass"
    video.touch()
    srt.touch()
    template.parent.mkdir(parents=True)
    template.touch()

    with mock.patch("video.main_video.func_vid.convert_srt_to_ass") as converter, \
        mock.patch("video.main_video.func_vid.integrate_ass_hard_ffmpeg") as burner:
        assert video_ass_hard_integrator(fake_config) is False

    converter.assert_called_once()
    assert converter.call_args.args[0] == srt
    assert converter.call_args.kwargs["title_duration_seconds"] == 5.0
    assert converter.call_args.kwargs["subtitle_duration_seconds"] == 10.0
    assert burner.call_args.kwargs["ass_path"].suffix == ".ass"
    assert burner.call_args.kwargs["ass_path"].parent != fake_config.INPUT_DIR
    assert "video_ass_hard_integrator" in burner.call_args.kwargs["processing_comment"]
    assert "video_convert_srt_to_ass" not in burner.call_args.kwargs["processing_comment"]


def test_hard_ass_command_emits_ffmpeg_progress(tmp_path):
    input_video = tmp_path / "clip.mp4"
    ass_file = tmp_path / "clip.ass"
    output_video = tmp_path / "output.mp4"
    with mock.patch("video.func_video.probe_video_duration", return_value=12.0), \
        mock.patch("video.func_video._run_ffmpeg_with_progress") as runner:
        integrate_ass_hard_ffmpeg(
            input_video, ass_file, output_video, "libx265", "aac", "comment"
        )

    command = runner.call_args.args[0]
    assert ["-progress", "pipe:1"] == command[-3:-1]
    assert runner.call_args.kwargs["duration"] == 12.0

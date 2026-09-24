"""
Tests unitaires et fonctionnels de video_assemblor().

Les tests sont volontairement isolés de FFmpeg :
les fichiers vidéo utilisés sont de simples fichiers vides créés
par pytest dans tmp_path.

L'implémentation actuelle de video_assemblor() utilise :
    prepare_video_for_assembly()
    get_video_frame_size_from_paths()
    get_video_output_fps_from_paths()
    render_normalized_source_clip()
    write_video_assemblor_input_subtitles_srt()
    write_video_assemblor_date_srt()
    concat_normalized_clips_ffmpeg()

Auteur :
    Pierrick BERTHE
"""

import sys
from pathlib import Path
from dataclasses import replace
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# IMPORTS
# ---------------------------------------------------------------------------

sys.path.append(
    str(Path(__file__).resolve().parents[2] / "toolbox_pb")
)

from config_global import AppConfig
from video.main_video import video_assemblor


# ---------------------------------------------------------------------------
# FIXTURES
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_config(tmp_path):
    """
    Configuration minimale et isolée pour les tests.

    Aucun vrai traitement FFmpeg n'est exécuté.
    """

    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    segment_dir = tmp_path / "segment"

    input_dir.mkdir()
    output_dir.mkdir()
    segment_dir.mkdir()

    # Faux fichiers vidéo.
    (input_dir / "video1.mp4").touch()
    (input_dir / "video2.mp4").touch()

    return AppConfig(
        INPUT_ACCEPTED_FILES=[".mp4"],
        INPUT_ACCEPTED_VIDEO_FILES=[".mp4"],
        INPUT_ACCEPTED_IMAGE_FILES=[".jpg", ".png"],
        INPUT_ACCEPTED_PDF_FILES=[".pdf"],
        CODEC_VIDEO_LIST=["libx264", "libx265"],
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
        ADD_CODEC_NAME_IN_OUTPUT=False,
        PRINT_ALL_KEYS_IN_METADATA_SUMMARY=False,
        VIDEO_ASSEMBLOR_ADD_DATE_SUBTITLES=False,
        IMAGE_DIAPO_MAX_HEIGHT=1080,
    )


@pytest.fixture(autouse=True)
def mock_assembly_probing():
    """
    Neutralise toutes les opérations FFprobe/FFmpeg liées à la préparation.

    Les fichiers .mp4 sont volontairement vides : aucun appel réel à FFmpeg
    ne doit donc être effectué pendant les tests unitaires.
    """

    with (
        mock.patch(
            "video.main_video.func_vid.prepare_video_for_assembly",
            side_effect=lambda path, *args, **kwargs: path,
        ) as mock_prepare,

        mock.patch(
            "video.main_video.func_vid.get_video_frame_size_from_paths",
            return_value=(1920, 1080),
        ) as mock_frame_size,

        mock.patch(
            "video.main_video.func_vid.get_video_output_fps_from_paths",
            return_value=30.0,
        ) as mock_output_fps,
    ):
        yield {
            "prepare": mock_prepare,
            "frame_size": mock_frame_size,
            "output_fps": mock_output_fps,
        }


@pytest.fixture(autouse=True)
def mock_input_subtitles():
    """
    Les vidéos fictives ne contiennent pas de vrais sous-titres.
    """

    with mock.patch(
        "video.main_video.func_vid.write_video_assemblor_input_subtitles_srt",
        return_value=False,
    ) as mock_subtitles:
        yield mock_subtitles


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def mock_metadata_dependencies():
    """
    Retourne les mocks communs utilisés pour les métadonnées.
    """

    return {
        "get_metadata": mock.patch(
            "video.main_video.func_vid.get_all_metadata",
            return_value={
                "format": {
                    "size": "1000000",
                    "duration": "20",
                }
            },
        ),
        "print_diff": mock.patch(
            "video.main_video.func_vid.print_metadata_diff_summary"
        ),
        "get_inputs_metadata": mock.patch(
            "video.main_video.func_vid.get_inputs_metadata",
            return_value=[
                {
                    "format": {
                        "size": "1000000",
                        "duration": "10",
                    }
                }
            ],
        ),
        "compute": mock.patch(
            "video.main_video.func_vid.compute_size_reduction_from_inputs",
            return_value={
                "size_before": 2_000_000,
                "size_after": 1_000_000,
                "reduction_percent": 50.0,
                "compression_factor": 2.0,
            },
        ),
        "print_reduction": mock.patch(
            "video.main_video.func_vid.print_size_reduction"
        ),
    }


# ---------------------------------------------------------------------------
# TEST 1 - VÉRIFICATION DES PARAMÈTRES DE RENDU
# ---------------------------------------------------------------------------

def test_video_assemblor_render_parameters(
    fake_config,
):
    """
    Vérifie que render_normalized_source_clip reçoit bien :
        - frame_size
        - FPS
        - codec vidéo
        - codec audio
        - chemin de sortie temporaire
    """

    with (
        mock.patch(
            "video.main_video.func_vid.resolve_video_sequence",
            return_value=[
                {
                    "path": fake_config.INPUT_DIR / "video1.mp4",
                    "start": 2,
                    "end": 8,
                }
            ],
        ),

        mock.patch(
            "video.main_video.func_vid.prepare_video_for_assembly",
            side_effect=lambda path, *args, **kwargs: path,
        ),

        mock.patch(
            "video.main_video.func_vid.get_video_frame_size_from_paths",
            return_value=(1280, 720),
        ),

        mock.patch(
            "video.main_video.func_vid.get_video_output_fps_from_paths",
            return_value=25.0,
        ),

        mock.patch(
            "video.main_video.func_vid.render_normalized_source_clip",
            return_value=6.0,
        ) as mock_render,

        mock.patch(
            "video.main_video.func_vid.concat_normalized_clips_ffmpeg"
        ),

        mock.patch(
            "video.main_video.func_vid.get_all_metadata",
            return_value={"format": {"size": "1000"}},
        ),

        mock.patch(
            "video.main_video.func_vid.print_metadata_diff_summary"
        ),

        mock.patch(
            "video.main_video.func_vid.get_inputs_metadata",
            return_value=[],
        ),

        mock.patch(
            "video.main_video.func_vid.compute_size_reduction_from_inputs",
            return_value={},
        ),

        mock.patch(
            "video.main_video.func_vid.print_size_reduction"
        ),
    ):

        video_assemblor(fake_config)

    mock_render.assert_called_once()

    args = mock_render.call_args.args

    assert args[1] == 2
    assert args[2] == 8
    assert args[3] == (1280, 720)
    assert args[4] == 25.0
    assert args[5] == fake_config.CODEC_VIDEO
    assert args[6] == fake_config.CODEC_AUDIO

    # Le dernier argument est le fichier temporaire de sortie.
    assert isinstance(args[7], Path)
    assert args[7].name == "assembled_source_000.mp4"


# ---------------------------------------------------------------------------
# TEST 2 - SOUS-TITRES DE DATE
# ---------------------------------------------------------------------------

def test_video_assemblor_date_subtitles(fake_config):
    """
    Vérifie que les sous-titres de date sont créés uniquement
    lorsque VIDEO_ASSEMBLOR_ADD_DATE_SUBTITLES=True.
    """

    fake_config = replace(
        fake_config,
        VIDEO_ASSEMBLOR_ADD_DATE_SUBTITLES=True,
        SRT_DURATION_SECONDS=3.0,
    )

    with (
        mock.patch(
            "video.main_video.func_vid.resolve_video_sequence",
            return_value=[
                {
                    "path": fake_config.INPUT_DIR / "video1_2024-01-15.mp4",
                    "start": None,
                    "end": None,
                }
            ],
        ),

        mock.patch(
            "video.main_video.func_vid.prepare_video_for_assembly",
            side_effect=lambda path, *args, **kwargs: path,
        ),

        mock.patch(
            "video.main_video.func_vid.get_video_frame_size_from_paths",
            return_value=(1920, 1080),
        ),

        mock.patch(
            "video.main_video.func_vid.get_video_output_fps_from_paths",
            return_value=30.0,
        ),

        mock.patch(
            "video.main_video.func_vid.render_normalized_source_clip",
            return_value=10.0,
        ),

        mock.patch(
            "video.main_video.func_vid.write_video_assemblor_date_srt",
            return_value=True,
        ) as mock_dates,

        mock.patch(
            "video.main_video.func_vid.concat_normalized_clips_ffmpeg"
        ),

        mock.patch(
            "video.main_video.func_vid.get_all_metadata",
            return_value={"format": {"size": "1000"}},
        ),

        mock.patch(
            "video.main_video.func_vid.print_metadata_diff_summary"
        ),

        mock.patch(
            "video.main_video.func_vid.get_inputs_metadata",
            return_value=[],
        ),

        mock.patch(
            "video.main_video.func_vid.compute_size_reduction_from_inputs",
            return_value={},
        ),

        mock.patch(
            "video.main_video.func_vid.print_size_reduction"
        ),
    ):

        # Le fichier n'existe pas réellement mais resolve_video_sequence
        # est mocké, donc ce n'est pas un problème.
        video_assemblor(fake_config)

    mock_dates.assert_called_once()

    args = mock_dates.call_args.args

    assert len(args) == 3
    assert args[0][0]["start"] is None
    assert args[0][0]["end"] is None


# ---------------------------------------------------------------------------
# TEST 3 - MÉTADONNÉES ET COMPRESSION
# ---------------------------------------------------------------------------

def test_video_assemblor_metadata_and_compression(fake_config):
    """
    Vérifie le traitement des métadonnées après assemblage.
    """

    metadata_before = {
        "format": {
            "size": "9000000",
            "duration": "105",
        }
    }

    metadata_after = {
        "format": {
            "size": "7000000",
            "duration": "105",
        }
    }

    inputs_metadata = [
        {
            "format": {
                "filename": "video1.mp4",
                "size": "5000000",
            }
        },
        {
            "format": {
                "filename": "video2.mp4",
                "size": "4000000",
            }
        },
    ]

    compression_stats = {
        "size_before": 9000000,
        "size_after": 7000000,
        "reduction_percent": 22.22,
        "compression_factor": 1.285,
    }

    with (
        mock.patch(
            "video.main_video.func_vid.resolve_video_sequence",
            return_value=[
                {
                    "path": fake_config.INPUT_DIR / "video1.mp4",
                    "start": None,
                    "end": None,
                },
                {
                    "path": fake_config.INPUT_DIR / "video2.mp4",
                    "start": None,
                    "end": None,
                },
            ],
        ),

        mock.patch(
            "video.main_video.func_vid.prepare_video_for_assembly",
            side_effect=lambda path, *args, **kwargs: path,
        ),

        mock.patch(
            "video.main_video.func_vid.get_video_frame_size_from_paths",
            return_value=(1920, 1080),
        ),

        mock.patch(
            "video.main_video.func_vid.get_video_output_fps_from_paths",
            return_value=30.0,
        ),

        mock.patch(
            "video.main_video.func_vid.render_normalized_source_clip",
            side_effect=[50.0, 55.0],
        ),

        mock.patch(
            "video.main_video.func_vid.concat_normalized_clips_ffmpeg"
        ),

        mock.patch(
            "video.main_video.func_vid.get_all_metadata",
            side_effect=[
                metadata_before,
                metadata_after,
                metadata_after,
            ],
        ) as mock_get_metadata,

        mock.patch(
            "video.main_video.func_vid.print_metadata_diff_summary"
        ) as mock_print_diff,

        mock.patch(
            "video.main_video.func_vid.get_inputs_metadata",
            return_value=inputs_metadata,
        ) as mock_get_inputs,

        mock.patch(
            "video.main_video.func_vid.compute_size_reduction_from_inputs",
            return_value=compression_stats,
        ) as mock_compute,

        mock.patch(
            "video.main_video.func_vid.print_size_reduction"
        ) as mock_print_reduction,
    ):

        result = video_assemblor(fake_config)

    assert result is False

    # get_all_metadata :
    #   1. premier fichier d'entrée
    #   2. fichier final
    #   3. fichier final une seconde fois pour les statistiques
    assert mock_get_metadata.call_count == 3

    mock_print_diff.assert_called_once()

    mock_get_inputs.assert_called_once_with(
        sequence=mock_get_inputs.call_args.kwargs["sequence"],
        get_metadata_fn=mock_get_inputs.call_args.kwargs["get_metadata_fn"],
    )

    mock_compute.assert_called_once_with(
        metas_before=inputs_metadata,
        meta_after=metadata_after,
    )

    mock_print_reduction.assert_called_once_with(
        compression_stats
    )


# ---------------------------------------------------------------------------
# TEST 4 - PAS DE VIDÉOS
# ---------------------------------------------------------------------------

def test_video_assemblor_empty_input(fake_config):
    """
    Vérifie que video_assemblor() retourne True lorsqu'aucune
    vidéo n'est présente dans le dossier d'entrée.
    """

    # Supprime les faux fichiers vidéo créés par la fixture.
    for path in fake_config.INPUT_DIR.glob("*.mp4"):
        path.unlink()

    result = video_assemblor(fake_config)

    assert result is True

"""Tests for the terminal-only option prompts."""

from unittest import mock

import toolbox_pb.ui.cli_helpers as cli_helpers


def test_image_defilor_reprompts_then_uses_the_entered_options(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", mock.Mock(side_effect=["maybe", "oui", "--height 720"]))
    runner = mock.Mock(return_value=False)
    monkeypatch.setattr(cli_helpers, "image_defilor", runner)

    assert cli_helpers.run_image_defilor_interactive(mock.sentinel.config) is False
    runner.assert_called_once_with(mock.sentinel.config, extra_args="--height 720")
    assert "Réponse invalide" in capsys.readouterr().out


def test_image_defilor_uses_no_extra_options_and_handles_invalid_arguments(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", mock.Mock(return_value="n"))
    runner = mock.Mock(side_effect=ValueError("option inconnue"))
    monkeypatch.setattr(cli_helpers, "image_defilor", runner)

    assert cli_helpers.run_image_defilor_interactive(mock.sentinel.config) is True
    runner.assert_called_once_with(mock.sentinel.config, extra_args=None)
    assert "option inconnue" in capsys.readouterr().out


def test_audio_decalator_reprompts_after_invalid_number(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", mock.Mock(side_effect=["invalid", "-0.5"]))
    runner = mock.Mock(return_value=True)
    monkeypatch.setattr(cli_helpers, "video_audio_decalator", runner)

    assert cli_helpers.run_video_audio_decalator_interactive(mock.sentinel.config) is True
    runner.assert_called_once_with(mock.sentinel.config, -0.5)
    assert "Format invalide" in capsys.readouterr().out

"""
Unit tests for the main module menu system and command routing.

This module contains tests that verify the main application menu correctly
routes user choices to the appropriate handler functions and validates input,
including video encoding, video assembly, image reduction, PDF operations,
directory flattening, and sports data collection.

Test Coverage:
    - Video Encoder: Tests that menu choice '1' correctly invokes the video encoder
    - Video Assembler: Tests that menu choice '2' correctly invokes the video assembler
    - Audio Decalator: Tests that menu choice '3' correctly invokes the audio decalator
    - Volume Adjust: Tests that menu choice '4' correctly invokes volume adjustment
    - Other Tools: Tests that menu choices '5-10' display correct launch messages
    - Invalid Input: Tests that invalid menu choices trigger an error message
    - Exit Handler: Tests that menu choice '11' properly exits the application
    - Main Flow: Tests that the application runs without errors through the menu system
"""
# general imports
from pathlib import Path
import pytest
from unittest import mock
import sys

# Add the toolbox_pb directory to sys.path for imports
sys.path.append(str(Path(__file__).resolve().parents[1] / 'toolbox_pb'))

# local imports
import main
from config_global import APP_CONFIG


def test_main_video_encodor_called(monkeypatch):
    """Test that choosing option '1' calls video_encodor."""
    # Mock input for choice '1'
    monkeypatch.setattr('builtins.input', lambda _: '1')

    # Mock others functions to avoid side effects except video_encodor
    with mock.patch('main.video_encodor', autospec=True) as mock_video, \
        mock.patch('func_global.get_git_version', return_value="git123"), \
        mock.patch('func_global.format_git_version', return_value="git123"), \
        mock.patch('func_global.print_system_info'), \
        mock.patch('func_global.print_config_flags'), \
        mock.patch('func_global.summarize_files'):

        # Call main
        main.main(APP_CONFIG)
        
        # Check that video_encodor was called once with APP_CONFIG
        mock_video.assert_called_once_with(APP_CONFIG)


def test_main_video_assemblor_called(monkeypatch):
    """Test that choosing option '2' calls video_assemblor."""
    # Mock input for choice '2'
    monkeypatch.setattr('builtins.input', lambda _: '2')

    # Mock others functions to avoid side effects except video_assemblor
    with mock.patch('main.video_assemblor', autospec=True) as mock_video, \
        mock.patch('func_global.get_git_version', return_value="git123"), \
        mock.patch('func_global.format_git_version', return_value="git123"), \
        mock.patch('func_global.print_system_info'), \
        mock.patch('func_global.print_config_flags'), \
        mock.patch('func_global.summarize_files'):

        # Call main
        main.main(APP_CONFIG)
        
        # Check that video_encodor was called once with APP_CONFIG
        mock_video.assert_called_once_with(APP_CONFIG)


def test_main_video_audio_decalator_called(monkeypatch):
    """Test that choosing option '3' calls video_audio_decalator."""
    monkeypatch.setattr('builtins.input', lambda _: '3')

    with mock.patch('main.video_audio_decalator', autospec=True) as mock_audio, \
        mock.patch('func_global.get_git_version', return_value="git123"), \
        mock.patch('func_global.format_git_version', return_value="git123"), \
        mock.patch('func_global.print_system_info'), \
        mock.patch('func_global.print_config_flags'), \
        mock.patch('func_global.summarize_files'):

        main.main(APP_CONFIG)
        mock_audio.assert_called_once_with(APP_CONFIG)


def test_main_video_volume_adjust_called(monkeypatch):
    """Test that choosing option '4' calls video_volume_adjust."""
    monkeypatch.setattr('builtins.input', lambda _: '4')

    with mock.patch('main.video_volume_adjust', autospec=True) as mock_volume, \
        mock.patch('func_global.get_git_version', return_value="git123"), \
        mock.patch('func_global.format_git_version', return_value="git123"), \
        mock.patch('func_global.print_system_info'), \
        mock.patch('func_global.print_config_flags'), \
        mock.patch('func_global.summarize_files'):

        main.main(APP_CONFIG)
        mock_volume.assert_called_once_with(APP_CONFIG)


# Decorator to parametrize other valid choices
@pytest.mark.parametrize("choice,msg", [
    ("5", "Image_defilor"),
    ("6", "Image_reductor"),
    ("7", "PDF_filigranor"),
    ("8", "PDF_assemblor"),
    ("9", "Flatten_directory_tree"),
    ("10", "Sport_garmin_recoltor"),
])
def test_other_menu_choices(monkeypatch, capsys, choice, msg):
    """Test that other menu choices print the correct launch message."""
    # Mock input for the given choice
    monkeypatch.setattr('builtins.input', lambda _: choice)

    # Mock others functions to avoid side effects
    with mock.patch('main.video_encodor'), \
        mock.patch('main.run_image_defilor_interactive'), \
        mock.patch('func_global.print_system_info'), \
        mock.patch('func_global.get_git_version', return_value="git123"), \
        mock.patch('func_global.format_git_version', return_value="git123"), \
        mock.patch('func_global.print_config_flags'), \
        mock.patch('func_global.summarize_files'):

        # Call main
        main.main(APP_CONFIG)
        
        # Check correct launch message is printed
        captured = capsys.readouterr()
        assert msg in captured.out


# Decorator to parametrize invalid choices (not in 1-7)
@pytest.mark.parametrize("choice", ["invalid", "", "0", "19", "-1", "abc"])
def test_main_invalid_choice(monkeypatch, capsys, choice):
    """Test that invalid choices are handled properly.
    Args:
        monkeypatch: fixture to mock input
        capsys: fixture to capture stdout/stderr
        choice: the invalid choice to test
    """
    # Mock input for invalid choice
    monkeypatch.setattr('builtins.input', lambda _: choice)

    # Mock others functions to avoid side effects
    with mock.patch('main.video_encodor'), \
        mock.patch('func_global.print_system_info'), \
        mock.patch('func_global.get_git_version', return_value="git123"), \
        mock.patch('func_global.format_git_version', return_value="git123"), \
        mock.patch('func_global.print_config_flags'):

        # Call main
        main.main(APP_CONFIG)
        
        # Check output for invalid choice message
        captured = capsys.readouterr()
        
        # Verify that the invalid choice message is in output
        assert "Choix invalide" in captured.out


def test_main_quit(monkeypatch):
    """Test that choosing option '11' exits the program."""
    # Mock input for choice '11'
    monkeypatch.setattr('builtins.input', lambda _: '11')

    # Mock python sys.exit to raise SystemExit
    with pytest.raises(SystemExit):
        main.main(APP_CONFIG)


def test_main_called(monkeypatch):
    """Test that main runs without errors for choice '11' (quit)."""
    # Mock input for choice '11'
    monkeypatch.setattr("builtins.input", lambda _: "11")

    # Mock others functions to avoid side effects
    with (
        mock.patch("main.video_encodor"), \
        mock.patch("func_global.get_git_version", return_value="git123"), \
        mock.patch("func_global.format_git_version", return_value="git123"), \
        mock.patch("func_global.print_system_info"), \
        mock.patch("func_global.print_config_flags"),
        pytest.raises(SystemExit)
    ):

        # Call main
        main.main(APP_CONFIG)

    # If no exception is raised, the test passes    
    assert True

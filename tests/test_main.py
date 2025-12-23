"""
Tests unitaires du point d’entrée principal `main.py` du projet toolbox_pb.

Liste des fonctions testées :
- Le fonctionnement du menu utilisateur pour le choix 1,
- la logique de routage du menu utilisateur (choix 2 à 6),
- la gestion des choix invalides.
- La sortie propre du programme.

Les traitements lourds (encodage vidéo, accès système, appels FFmpeg,
etc.) sont systématiquement mockés afin de :
- garantir des tests rapides et déterministes,
- éviter tout effet de bord (I/O, calculs, dépendances externes),
- isoler la logique de contrôle et d’orchestration de `main()`.
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
    with mock.patch('main.video_encodor') as mock_video, \
        mock.patch('func_global.get_git_version', return_value="git123"), \
        mock.patch('func_global.format_git_version', return_value="git123"), \
        mock.patch('func_global.print_system_info'), \
        mock.patch('func_global.print_config_flags'):

        # Call main
        main.main(APP_CONFIG)
        
        # Check that video_encodor was called once with APP_CONFIG
        mock_video.assert_called_once_with(APP_CONFIG)


# Decorator to parametrize other valid choices (2-6)
@pytest.mark.parametrize("choice,msg", [
    ("2", "Vidéo_assemblor"),
    ("3", "Image_reductor"),
    ("4", "PDF_filigranor"),
    ("5", "Flatten_directory_tree"),
    ("6", "Sport_garmin_recoltor"),
])
def test_other_menu_choices(monkeypatch, capsys, choice, msg):
    """Test that other menu choices print the correct launch message.
    
    Args:
        monkeypatch: fixture to mock input
        capsys: fixture to capture stdout/stderr
        choice: the menu choice to test
        msg: the expected message in output
    """
    # Mock input for the given choice
    monkeypatch.setattr('builtins.input', lambda _: choice)

    # Mock others functions to avoid side effects
    with mock.patch('main.video_encodor'), \
        mock.patch('func_global.print_system_info'), \
        mock.patch('func_global.get_git_version', return_value="git123"), \
        mock.patch('func_global.format_git_version', return_value="git123"), \
        mock.patch('func_global.print_config_flags'):

        # Call main
        main.main(APP_CONFIG)
        
        # Check correct launch message is printed
        captured = capsys.readouterr()
        assert msg in captured.out


# Decorator to parametrize invalid choices (not in 1-7)
@pytest.mark.parametrize("choice", ["invalid", "", "0", "8"])
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
    """Test that choosing option '7' exits the program."""
    # Mock input for choice '7'
    monkeypatch.setattr('builtins.input', lambda _: '7')

    # Mock python sys.exit to raise SystemExit
    with pytest.raises(SystemExit):
        main.main(APP_CONFIG)

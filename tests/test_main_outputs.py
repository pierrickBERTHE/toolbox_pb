""" Tests unitaires du point d’entrée principal `main.py` du projet toolbox_pb.

Ce module teste exclusivement les outputs de la fonction `main()` :
- Le message de version git affiché au démarrage,
- les informations système affichées au démarrage,
- les flags de configuration affichés au démarrage.

Ces tests sont des tests unitaires d’interface CLI,
et ne couvrent pas les implémentations internes des modules appelés.

Liste des fonctions testées :
- print git version au démarrage OK
- print system info au démarrage OK
- print config flags au démarrage OK
"""
# general imports
import sys
from pathlib import Path
from unittest import mock
import pytest

# Add the toolbox_pb directory to sys.path for imports
sys.path.append(str(Path(__file__).resolve().parents[1] / 'toolbox_pb'))

# local imports
import main
from config_global import APP_CONFIG


def test_main_prints_git_version(monkeypatch, capsys):
    """ Test that the git version is printed on startup."""
    
    # Mock input for choice '7'
    monkeypatch.setattr('builtins.input', lambda _: '7')

    # Mock get_git_version and format_git_version
    with mock.patch('func_global.get_git_version', return_value="abc123"), \
        mock.patch('func_global.format_git_version', return_value="Version : abc123"):

        # Call main and expect SystemExit
        with pytest.raises(SystemExit):
            main.main(APP_CONFIG)

        # Capture stdout and check for git version
        captured = capsys.readouterr()
        assert "Version : abc123" in captured.out


def test_main_prints_system_info(monkeypatch, capsys):
    """Test that system info is printed on startup."""
    
    # Mock input for choice '7'
    monkeypatch.setattr('builtins.input', lambda _: '7')

    # Mock print_system_info
    with mock.patch('func_global.print_system_info') as m_sys:

        # Call main and expect SystemExit
        with pytest.raises(SystemExit):
            main.main(APP_CONFIG)

        # Check that print_system_info was called once
        m_sys.assert_called_once()


def test_main_prints_config_flags(monkeypatch):
    """Test that config flags are printed on startup."""

    # Mock input for choice '7'
    monkeypatch.setattr('builtins.input', lambda _: '7')

    # Mock print_config_flags
    with mock.patch('func_global.print_config_flags') as m_flags:

        # Call main and expect SystemExit
        with pytest.raises(SystemExit):
            main.main(APP_CONFIG)

        # Check that print_config_flags was called once with correct args
        m_flags.assert_called_once_with(
            APP_CONFIG,
            flag_names=[
                "LOG_TO_FILE",
                "ADD_CODEC_NAME_IN_OUTPUT",
                "PRINT_ALL_KEYS_IN_METADATA_SUMMARY"
            ]
        )

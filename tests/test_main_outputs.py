"""
Unit tests for the main module startup behavior.

This module contains tests that verify the main application displays
correct system information and configuration on startup, including
git version, system dependencies, and active configuration flags.

Test Coverage:
    - Git Version: Tests that git version is retrieved and formatted correctly on startup
    - System Info: Tests that system dependency information is displayed during initialization
    - Config Flags: Tests that active configuration flags are displayed with their values
"""
# general imports
import sys
from pathlib import Path
from unittest import mock
import pytest
from dataclasses import replace

# Add the toolbox_pb directory to sys.path for imports
sys.path.append(str(Path(__file__).resolve().parents[1] / 'toolbox_pb'))

# local imports
import main
from config_global import APP_CONFIG


def test_main_prints_git_version(monkeypatch, capsys):
    """Test that the git version is printed on startup."""

    # Mock input for "Quitter"
    monkeypatch.setattr('builtins.input', lambda _: '12')
    cfg = replace(APP_CONFIG, LOG_TO_FILE=False)

    # Mock get_git_version and format_git_version
    with mock.patch('func_global.get_git_version', return_value="abc123"), \
        mock.patch('func_global.format_git_version', return_value="Version : abc123"):

        # Call main and expect SystemExit
        with pytest.raises(SystemExit):
            main.main(cfg)

        # Capture stdout and check for git version
        captured = capsys.readouterr()
        assert "Version : abc123" in captured.out


def test_main_prints_system_info(monkeypatch, capsys):
    """Test that system info is printed on startup."""
    
    # Mock input for "Quitter"
    monkeypatch.setattr('builtins.input', lambda _: '12')
    cfg = replace(APP_CONFIG, LOG_TO_FILE=False)

    # Mock print_system_info
    with mock.patch('func_global.print_system_info') as m_sys:

        # Call main and expect SystemExit
        with pytest.raises(SystemExit):
            main.main(cfg)

        # Check that print_system_info was called once
        m_sys.assert_called_once()


def test_main_prints_config_flags(monkeypatch):
    """Test that config flags are printed on startup."""

    # Mock input for "Quitter"
    monkeypatch.setattr('builtins.input', lambda _: '12')
    cfg = replace(APP_CONFIG, LOG_TO_FILE=False)

    # Mock print_config_flags
    with mock.patch('func_global.print_config_flags') as m_flags:

        # Call main and expect SystemExit
        with pytest.raises(SystemExit):
            main.main(cfg)

        # Check that print_config_flags was called once with correct args
        m_flags.assert_called_once_with(
            cfg,
            flag_names=[
                "LOG_TO_FILE",
                "ADD_CODEC_NAME_IN_OUTPUT",
                "PRINT_ALL_KEYS_IN_METADATA_SUMMARY"
            ]
        )

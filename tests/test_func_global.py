"""
Tests unitaires pour les fonctions utilitaires de func_global.py.

Objectifs :
- Vérifier les comportements unitaires
- Éviter tout effet de bord (git, ffmpeg, fichiers, stdout réel)
- Ne tester que la logique locale

Liste des fonctions testées :
- Logger.write
- get_git_version : 
    - version ok
    exception
- format_git_version :
    - format simple
    - format étendu
    - format inattendu
- print_system_info :
    - ffmpeg ok
    - ffmpeg absent
- print_config_flags avec flags existants et non existants
- transform_sec_duration_in_min_sec OK
- measure_time décorateur OK
- print_step OK
- print_json OK
- exit_toolbox OK
"""
# Imports standard
import sys
from pathlib import Path
import json
import pytest
from unittest import mock

# Add the toolbox_pb directory to sys.path for imports
sys.path.append(str(Path(__file__).resolve().parents[1] / 'toolbox_pb'))

# Import the module to test
import func_global


# ==========================================================
# Tests Logger
# ==========================================================

def test_logger_write(tmp_path, capsys):
    """Test the Logger class to ensure it writes to both stdout and a file."""
    
    # Create a temporary log file
    log_file = tmp_path / "test.log"
    logger = func_global.Logger(log_file)

    # Write a message
    message = "Hello Logger\n"
    logger.write(message)
    logger.flush()

    # Verify stdout
    captured = capsys.readouterr()
    assert message in captured.out

    # Verify log file
    content = log_file.read_text(encoding="utf-8")
    assert message in content


# ==========================================================
# Tests Git version
# ==========================================================

def test_get_git_version_ok():
    """ Test get_git_version when git command works correctly."""
    # Mock subprocess.check_output to return a known git version
    with mock.patch(
        "subprocess.check_output",
        return_value=b"v1.2.3"
    ):
        # Call the function and verify the result
        version = func_global.get_git_version()
        assert version == "v1.2.3"


def test_get_git_version_exception():
    """Test get_git_version when git command fails."""
    # Mock subprocess.check_output to raise an exception
    with mock.patch(
        "subprocess.check_output",
        side_effect=Exception("git error")
    ):
        # Call the function and verify the result
        version = func_global.get_git_version()
        assert version == "version inconnue"


def test_format_git_version_simple():
    """Test format_git_version with simple tag format."""
    assert func_global.format_git_version("v1.0.0") == "Version : v1.0.0"


def test_format_git_version_extended():
    """ Test format_git_version with extended format."""
    result = func_global.format_git_version("v1.0.0-3-gabc123")
    assert "v1.0.0" in result
    assert "3 commits" in result
    assert "gabc123" in result


def test_format_git_version_fallback():
    """Test format_git_version with unexpected format."""
    version = "strange-format-here"
    assert func_global.format_git_version(version) == f"Version : {version}"


# ==========================================================
# Tests print_system_info
# ==========================================================

def test_print_system_info(monkeypatch, capsys):
    """Test print_system_info with ffmpeg available."""

    # Mock subprocess.check_output to return a known ffmpeg version
    monkeypatch.setattr(
        "subprocess.check_output", lambda *a, **k: b"ffmpeg version test"
    )

    # Call the function and capture output
    func_global.print_system_info()
    captured = capsys.readouterr()

    # Verify output contains expected information
    assert "Python" in captured.out
    assert "MoviePy" in captured.out
    assert "Numpy" in captured.out
    assert "Pillow" in captured.out
    assert "ffmpeg version test" in captured.out


def test_print_system_info_ffmpeg_missing(monkeypatch, capsys):
    """Test print_system_info when ffmpeg is not available."""
    
    # Mock subprocess.check_output to raise an exception
    monkeypatch.setattr(
        "subprocess.check_output",
        lambda *a, **k: (_ for _ in ()).throw(Exception())
    )

    # Call the function and capture output
    func_global.print_system_info()
    captured = capsys.readouterr()

    # Verify output indicates ffmpeg is not available
    assert "FFmpeg version    : non disponible" in captured.out


# ==========================================================
# Tests print_config_flags
# ==========================================================

class DummyConfig:
    """Dummy configuration class for testing."""
    FLAG_A = True
    FLAG_B = False


def test_print_config_flags(capsys):
    """Test print_config_flags with dummy config."""
    
    # Create a dummy config object
    cfg = DummyConfig()
    func_global.print_config_flags(cfg, ["FLAG_A", "FLAG_B", "FLAG_C"])

    # Capture output and verify
    captured = capsys.readouterr()
    assert "FLAG_A = True" in captured.out
    assert "FLAG_B = False" in captured.out
    assert "FLAG_C = None" in captured.out


# ==========================================================
# Tests durée / timing
# ==========================================================

def test_transform_sec_duration_in_min_sec():
    """Test transform_sec_duration_in_min_sec function."""
    minutes, seconds = func_global.transform_sec_duration_in_min_sec(0, 125)
    assert minutes == 2
    assert seconds == 5


def test_measure_time_decorator(capsys):
    """Test measure_time decorator."""
    
    # Define a dummy function to decorate
    @func_global.measure_time
    def dummy():
        return 42

    # Call the decorated function
    result = dummy()
    captured = capsys.readouterr()

    # Verify results and output
    assert result == 42
    assert "Temps d'exécution de dummy" in captured.out


# ==========================================================
# Tests affichage étapes
# ==========================================================

def test_print_step(capsys):
    """Test print_step function."""
    
    # Call the function to print a step
    func_global.print_step(1, "Test step")
    captured = capsys.readouterr()

    # Verify output format and content
    assert "STEP 1" in captured.out
    assert "Test step" in captured.out


# ==========================================================
# Tests print_json
# ==========================================================

def test_print_json(capsys):
    """Test print_json function."""
    
    # Create a sample object to print as JSON
    data = {"a": 1, "b": "test"}
    func_global.print_json(data, title="DATA")

    # Capture output and verify content
    captured = capsys.readouterr()
    assert "DATA" in captured.out
    assert json.dumps(data, indent=4, ensure_ascii=False) in captured.out


# ==========================================================
# Tests exit_toolbox
# ==========================================================

def test_exit_toolbox():
    """Test exit_toolbox function."""
    with pytest.raises(SystemExit):
        func_global.exit_toolbox()

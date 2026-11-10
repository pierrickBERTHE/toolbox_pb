"""Tests for the shared interface and file logging bridge."""

import logging

from toolbox_pb.core.events import configure_file_logging, emit, ui_only, use_message_sink


def test_emit_writes_to_the_active_ui_and_process_log(tmp_path):
    """One emitted message is both displayed and durably recorded."""
    displayed: list[str] = []
    configure_file_logging(tmp_path)
    try:
        with use_message_sink(displayed.append):
            emit("Traitement démarré", level=logging.WARNING)
    finally:
        configure_file_logging(tmp_path, enabled=False)

    assert displayed == ["Traitement démarré\n"]
    log_text = (tmp_path / "process_log.txt").read_text(encoding="utf-8")
    assert "| WARNING | Traitement démarré" in log_text


def test_ui_only_keeps_verbose_text_out_of_the_process_log(tmp_path):
    """Formatting details stay visible without making the persistent log noisy."""
    displayed: list[str] = []

    @ui_only
    def show_metadata_details() -> None:
        emit("======= DIFFÉRENCES MÉTADONNÉES =======")

    configure_file_logging(tmp_path)
    try:
        with use_message_sink(displayed.append):
            show_metadata_details()
    finally:
        configure_file_logging(tmp_path, enabled=False)

    assert displayed == ["======= DIFFÉRENCES MÉTADONNÉES =======\n"]
    assert not (tmp_path / "process_log.txt").read_text(encoding="utf-8")


def test_debug_and_error_levels_are_recorded_when_debug_is_enabled(tmp_path):
    """The DEBUG setting preserves diagnostics as well as failures."""
    configure_file_logging(tmp_path, level="DEBUG")
    try:
        emit("Diagnostic détaillé", level=logging.DEBUG)
        emit("Échec de traitement", level=logging.ERROR)
    finally:
        configure_file_logging(tmp_path, enabled=False)

    log_text = (tmp_path / "process_log.txt").read_text(encoding="utf-8")
    assert "| DEBUG | Diagnostic détaillé" in log_text
    assert "| ERROR | Échec de traitement" in log_text


def test_info_level_filters_debug_messages(tmp_path):
    """The default level keeps production logs focused on useful events."""
    configure_file_logging(tmp_path, level="INFO")
    try:
        emit("Diagnostic masqué", level=logging.DEBUG)
        emit("Message normal", level=logging.INFO)
    finally:
        configure_file_logging(tmp_path, enabled=False)

    log_text = (tmp_path / "process_log.txt").read_text(encoding="utf-8")
    assert "Diagnostic masqué" not in log_text
    assert "| INFO | Message normal" in log_text


def test_exception_logging_records_an_error_and_its_traceback(tmp_path):
    """Unexpected failures retain their traceback in the persistent log."""
    configure_file_logging(tmp_path)
    try:
        try:
            raise RuntimeError("panne simulée")
        except RuntimeError:
            logging.getLogger("toolbox_pb").exception("Traitement en échec")
    finally:
        configure_file_logging(tmp_path, enabled=False)

    log_text = (tmp_path / "process_log.txt").read_text(encoding="utf-8")
    assert "| ERROR | Traitement en échec" in log_text
    assert "RuntimeError: panne simulée" in log_text

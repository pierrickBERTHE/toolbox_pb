"""Interface Streamlit de la toolbox_pb.

L'application pilote les traitements existants sans dupliquer leur logique :
les fichiers restent lus depuis ``data/input`` et les résultats sont écrits
dans ``data/output``.
"""

from __future__ import annotations

import base64
import io
import logging
from math import ceil
from queue import Empty, Queue
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory
from threading import Event, Thread
import traceback
from datetime import datetime
from contextlib import redirect_stdout
from dataclasses import dataclass, field, replace
from html import escape
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

import streamlit as st

from toolbox_pb.core.audio.main_audio import audio_compressor
from toolbox_pb.core.audio.func_audio import probe_audio_bitrate_kbps
import toolbox_pb.core.func_global as func_global_module
from toolbox_pb.core.config_global import (
    APP_CONFIG,
    AppConfig,
    IMAGE_EXAMPLE_DIR,
    LOG_LEVELS,
    PROJECT_DIR,
)
from toolbox_pb.core.cancellation import (
    ProcessingCancelled,
    raise_if_cancelled,
    use_cancellation_event,
)
from toolbox_pb.core.events import (
    configure_file_logging,
    emit,
    use_message_sink,
)
from toolbox_pb.core.progress import use_progress_factory
from toolbox_pb.core.video.func_video import (
    find_files_by_extensions,
    format_duration_hms,
    get_all_metadata,
)
from toolbox_pb.core.file.main_file import (
    cache_nettoyor,
    file_str_remover,
    file_timeline_sorter,
    folder_date_renammer,
)
from toolbox_pb.core.image.main_image import (
    image_defilor,
    image_reductor,
    image_withoutbg,
)
from toolbox_pb.core.pdf.main_pdf import (
    pdf_assemblor,
    pdf_filigranor,
    pdf_page_alternator,
)
from toolbox_pb.core.video.main_video import (
    video_ass_hard_integrator,
    video_assemblor,
    video_audio_decalator,
    video_encodor,
    image_diapo_video_creator,
    video_srt_date_filtrator,
    video_srt_extractor,
    video_srt_integrator,
    video_volume_adjust,
    video_rotator,
)
from toolbox_pb.core.web.main_web import (
    MP3_BITRATES,
    VIDEO_QUALITIES,
    YouTubeDownloadOptions,
    download_youtube_media,
)
from toolbox_pb.ui.reductor_workflow import _run_complementary_reductor


# This helper belongs to the Streamlit UI package, not to the shared core
# package directory configured globally.
FOCUS_EXPLORER_SCRIPT = Path(__file__).resolve().parent / "focus_explorer.ps1"


ToolRunner = Callable[[], bool | None]
FollowUpRequirement = Callable[[], bool]
CATEGORY_ICON_DIR = PROJECT_DIR / "image" / "icons" / "categories"
TOOL_ICON_DIR = PROJECT_DIR / "image" / "icons" / "tools"
FOLDER_ICON_DIR = PROJECT_DIR / "image" / "icons" / "folders"
# Artwork displayed next to the shortcut that opens the historical CLI.
LEGACY_CLI_LOGO = PROJECT_DIR / "image" / "legacy" / "logo_a_l'ancienne.png"
# Boolean settings exposed as per-browser-session controls in the sidebar.
SESSION_FLAGS = (
    "LOG_TO_FILE",
    "OPEN_OUTPUT_DIR_AFTER_TREATMENT",
    "ADD_CODEC_NAME_IN_OUTPUT",
    "VIDEO_ENCODOR_PRINT_ALL_KEYS_IN_METADATA_SUMMARY",
    "IMAGE_WITHOUTBG_ADD_WITHOUTBG_IN_NAME_IN_OUTPUT",
    "IMAGE_REDUCTOR_ADD_COMPRESS_TO_IMAGE_NAME_IN_OUTPUT",
    "VIDEO_ASSEMBLOR_ADD_DATE_SUBTITLES",
    "VIDEO_ASSEMBLOR_EXTRACT_AND_FILTER_DATES",
    "AUDIO_COMPRESSOR_COPY_JPEG_FILES",
)
# Numeric settings exposed alongside the boolean session controls.
SESSION_VALUES = (
    "AUDIO_COMPRESSOR_MP3_BITRATE_KBPS",
)
CATEGORY_ICONS = {
    "Vidéo": CATEGORY_ICON_DIR / "video.png",
    "Image": CATEGORY_ICON_DIR / "image.png",
    "Audio": CATEGORY_ICON_DIR / "audio.png",
    "PDF": CATEGORY_ICON_DIR / "pdf.png",
    "Fichier": CATEGORY_ICON_DIR / "file.png",
    "Web": CATEGORY_ICON_DIR / "web.png",
}
TOOL_NUMBERS = {
    "video_encodor": 1,
    "video_assemblor": 2,
    "video_audio_decalator": 3,
    "video_volume_adjust": 4,
    "video_srt_extractor": 5,
    "video_srt_integrator": 6,
    "video_srt_date_filtrator": 7,
    "video_ass_hard_integrator": 8,
    "video_rotator": 9,
    "image_defilor": 1,
    "image_reductor": 2,
    "image_diapo_video_creator": 3,
    "image_withoutbg": 4,
    "audio_compressor": 1,
    "pdf_filigranor": 1,
    "pdf_assemblor": 2,
    "pdf_page_alternator": 3,
    "file_timeline_sorter": 1,
    "file_str_remover": 2,
    "folder_date_renammer": 3,
    "cache_nettoyor": 4,
}


def _folder_open_icon(kind: str, folder: Path, label: str) -> None:
    """Render the existing SVG as a native, reliable Streamlit button."""
    icon_path = FOLDER_ICON_DIR / f"{kind}_box.svg"
    image_data = base64.b64encode(icon_path.read_bytes()).decode("ascii")
    image_label = (
        f"![Ouvrir le dossier {label}]"
        f"(data:image/svg+xml;base64,{image_data})"
    )
    st.html(
        f"""
        <style>
        .st-key-open_{kind}_folder_icon button {{
          background: transparent;
          border: 0;
          cursor: pointer;
          min-height: 96px;
          padding: 0;
        }}
        .st-key-open_{kind}_folder_icon button img {{
          display: block;
          height: 96px !important;
          width: 96px !important;
          max-height: 96px !important;
          object-fit: contain;
        }}
        </style>
        """
    )
    if st.button(
        image_label,
        key=f"open_{kind}_folder_icon",
        help=f"Ouvrir le dossier {label} dans Windows Explorer.",
        type="secondary",
        width="content",
    ):
        _open_in_file_explorer(folder, label)


class StreamlitProgressBar:
    """Render a Streamlit progress bar whose percentage is overlaid on it."""

    def __init__(self, target: object) -> None:
        self._target = target

    def progress(self, value: int, *, text: str) -> "StreamlitProgressBar":
        """Update the bar while keeping its percentage visible in the bar."""
        percent = max(0, min(int(value), 100))
        safe_text = escape(text)
        self._target.html(
            f"""
            <div style="margin: 0.25rem 0 0.75rem;">
              <div
                role="progressbar"
                aria-label="{safe_text}"
                aria-valuemin="0"
                aria-valuemax="100"
                aria-valuenow="{percent}"
                style="position: relative; height: 2.75rem; overflow: hidden;
                       border-radius: 1.375rem;
                       background: rgba(128, 128, 128, 0.25);"
              >
                <div style="width: {percent}%; height: 100%;
                            background: var(--primary-color, #ff4b4b);"></div>
                <span style="position: absolute; inset: 0; display: flex;
                             align-items: center; justify-content: center;
                             color: #111; font-size: 2.25rem;
                             font-weight: 700; text-shadow: 0 0 2px #fff;">
                  {percent} %
                </span>
              </div>
              <div style="margin-top: 0.25rem; font-size: 0.875rem;">
                {safe_text}
              </div>
            </div>
            """,
        )
        return self


@dataclass
class TreatmentJob:
    """State shared between a background treatment and the Streamlit view."""

    tool_name: str
    events: Queue[tuple[str, Any]] = field(default_factory=Queue)
    cancel_event: Event = field(default_factory=Event)
    output: str = ""
    progress: dict[int, tuple[int, str]] = field(default_factory=dict)
    status: str = "running"
    is_empty_folder: bool | None = None
    error: str | None = None
    worker: Thread | None = None
    origin_tool_name: str | None = None
    output_dir: Path | None = None
    output_folder_opened: bool = False
    open_output_on_success: bool = True
    follow_up_label: str | None = None
    follow_up_runner: ToolRunner | None = None
    follow_up_required: FollowUpRequirement | None = None
    follow_up_output_dir: Path | None = None
    follow_up_deadline: float | None = None
    follow_up_open_output_on_success: bool | None = None


class QueuedProgress:
    """Progress reporter rendered separately by the Streamlit worker."""

    def __init__(
        self,
        job: TreatmentJob,
        iterable=None,
        total: float | None = None,
        desc: str | None = None,
        unit: str = "élément",
        position: int | None = None,
        **_: object,
    ) -> None:
        self.job = job
        self.iterable = iterable
        self.total = total if total is not None else self._get_length(iterable)
        self.n = 0.0
        self.desc = desc or "Traitement"
        self.unit = unit
        self.position = position or 0
        self.started_at = perf_counter()
        self._publish()

    @staticmethod
    def _get_length(iterable) -> int | None:
        try:
            return len(iterable)
        except TypeError:
            return None

    @staticmethod
    def _format_duration(seconds: float) -> str:
        seconds = max(0, int(seconds))
        hours, remainder = divmod(seconds, 3_600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def _label(self) -> str:
        elapsed = perf_counter() - self.started_at
        if self.total:
            completed = min(self.n, self.total)
            remaining = (
                elapsed * (self.total - completed) / completed
                if completed
                else None
            )
            remaining_text = (
                self._format_duration(remaining)
                if remaining is not None
                else "calcul…"
            )
            if self.unit == "%":
                return (
                    f"{self.desc} — {completed:.0f} % — écoulé : "
                    f"{self._format_duration(elapsed)} — restant : "
                    f"{remaining_text}"
                )
            return (
                f"{self.desc} — fichier {completed:.0f}/{self.total:.0f} "
                f"— écoulé : {self._format_duration(elapsed)} "
                f"— restant : {remaining_text}"
            )
        return (
            f"{self.desc} : {self.n:.0f} {self.unit} — écoulé : "
            f"{self._format_duration(elapsed)}"
        )

    def _publish(self) -> None:
        percent = min(int(self.n / self.total * 100), 100) if self.total else 0
        self.job.events.put(
            ("progress", (self.position, percent, self._label()))
        )

    def update(self, increment: float = 1) -> None:
        raise_if_cancelled()
        self.n += increment
        self._publish()

    def __iter__(self):
        if self.iterable is None:
            return iter(())
        for item in self.iterable:
            raise_if_cancelled()
            yield item
            self.update()

    def __enter__(self) -> "QueuedProgress":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self.total and self.n >= self.total:
            self._publish()


class QueuedLog(io.StringIO):
    """Forward legacy print output from the worker to the active page."""

    def __init__(self, job: TreatmentJob) -> None:
        super().__init__()
        self.job = job
        self._youtube_has_visible_content = False
        self._youtube_last_line_is_blank = False
        self._youtube_audio_conversion_announced = False

    def write(self, text: str) -> int:
        # Console tools such as yt-dlp redraw their progress using ``\r``.
        # Streamlit's log viewer does not emulate a terminal, so turn each
        # redraw into a readable vertical line instead.
        visible_text = text.replace("\r\n", "\n").replace("\r", "\n")
        visible_text = visible_text.replace(
            "Fichier téléchargé :", "\nFichier téléchargé :"
        )
        self._publish_youtube_progress(visible_text)
        log_text = self._without_youtube_download_lines(visible_text)
        written = super().write(log_text)
        if log_text:
            self.job.events.put(("log", log_text))
        return len(text)

    def _without_youtube_download_lines(self, text: str) -> str:
        """Keep yt-dlp's progress in the bar and collapse terminal blanks."""
        if self.job.tool_name != "youtube_downloader":
            return text
        visible_lines: list[str] = []
        for line in text.splitlines(keepends=True):
            if line.lstrip().startswith("[download]"):
                continue
            if line.strip() == "Conversion du flux audio en MP3…":
                if self._youtube_audio_conversion_announced:
                    continue
                self._youtube_audio_conversion_announced = True
            if not line.strip():
                if (
                    self._youtube_has_visible_content
                    and not self._youtube_last_line_is_blank
                ):
                    visible_lines.append("\n")
                    self._youtube_last_line_is_blank = True
                continue
            visible_lines.append(line)
            self._youtube_has_visible_content = True
            self._youtube_last_line_is_blank = False
        return "".join(visible_lines)

    def _publish_youtube_progress(self, text: str) -> None:
        """Use yt-dlp's rendered percentage as a robust Streamlit fallback."""
        if self.job.tool_name != "youtube_downloader":
            return
        for match in re.finditer(
            r"\[download\]\s+(\d+(?:\.\d+)?)%\s+of\s+([^\n]+)",
            text,
        ):
            percentage = float(match.group(1))
            details = match.group(2).strip()
            self.job.events.put(
                (
                    "progress",
                    (
                        0,
                        round(percentage),
                        f"Téléchargement YouTube — {percentage:.1f} % — {details}",
                    ),
                )
            )


def _run_treatment_worker(job: TreatmentJob, runner: ToolRunner) -> None:
    """Run a treatment away from Streamlit's UI thread."""
    log = QueuedLog(job)
    try:
        with (
            use_cancellation_event(job.cancel_event),
            redirect_stdout(log),
            use_message_sink(log.write),
            use_progress_factory(
                lambda *args, **kwargs: QueuedProgress(job, *args, **kwargs)
            ),
        ):
            raise_if_cancelled()
            emit(f"Démarrage du traitement : {job.tool_name}")
            is_empty_folder = runner()
    except ProcessingCancelled:
        job.events.put(("cancelled", None))
    except (FileNotFoundError, ValueError) as exc:
        # These exceptions describe invalid input, not an application failure.
        message = str(exc).strip()
        logging.getLogger("toolbox_pb").warning(
            "Traitement %s non effectué : %s", job.tool_name, message
        )
        job.events.put(("validation_error", message))
    except Exception as exc:  # The main thread renders the full diagnostic.
        error_text = str(exc).strip() or type(exc).__name__
        logging.getLogger("toolbox_pb").error(
            "Le traitement %s a échoué : %s", job.tool_name, error_text
        )
        job.events.put(("error", f"{exc}\n{traceback.format_exc()}"))
    else:
        job.events.put(("done", is_empty_folder))


def _drain_treatment_events(job: TreatmentJob) -> None:
    """Apply worker updates to the state displayed by Streamlit."""
    while True:
        try:
            event, payload = job.events.get_nowait()
        except Empty:
            return
        if event == "log":
            job.output += str(payload)
        elif event == "progress":
            position, percent, label = payload
            job.progress[position] = (percent, label)
        elif event == "done":
            job.is_empty_folder = bool(payload)
            job.output += f"\nTraitement terminé : {job.tool_name}\n"
            follow_up_is_required = (
                job.follow_up_required is None or job.follow_up_required()
            )
            if (
                job.follow_up_runner is not None
                and job.follow_up_label
                and follow_up_is_required
            ):
                job.status = "awaiting_follow_up"
                job.follow_up_deadline = perf_counter() + 10
                job.output += (
                    f"\nLancement de {job.follow_up_label} dans 10 secondes "
                    "sans réponse.\n"
                )
                continue
            job.status = "done"
            if (
                job.open_output_on_success
                and job.output_dir is not None
                and not job.output_folder_opened
            ):
                _open_in_file_explorer(job.output_dir, "de sortie")
                job.output_folder_opened = True
        elif event == "cancelled":
            job.status = "cancelled"
            job.output += (
                "\nTraitement arrêté à la demande de l’utilisateur.\n"
            )
        elif event == "validation_error":
            job.status = "validation_error"
            job.error = str(payload)
            job.output += f"\n⚠️ {job.error}\n"
        elif event == "error":
            job.status = "error"
            job.error = str(payload)


def _launch_follow_up(job: TreatmentJob) -> None:
    """Launch a queued post-download treatment in a fresh worker."""
    if job.follow_up_runner is None or job.follow_up_label is None:
        return
    _run_tool(
        job.follow_up_label,
        job.follow_up_runner,
        origin_tool_name=job.origin_tool_name or job.tool_name,
        output_dir=job.follow_up_output_dir,
        open_output_on_success=job.follow_up_open_output_on_success,
    )


@st.fragment(run_every="0.5s")
def _render_active_treatment() -> None:
    """Refresh the active treatment without blocking the other controls."""
    job = st.session_state.get("active_treatment")
    if not isinstance(job, TreatmentJob):
        return
    _drain_treatment_events(job)

    if job.status == "awaiting_follow_up":
        deadline = job.follow_up_deadline or perf_counter()
        remaining = max(0, ceil(deadline - perf_counter()))
        if remaining == 0:
            _launch_follow_up(job)
            st.rerun()
        st.warning(
            f"Lancer {job.follow_up_label} ? Démarrage automatique dans "
            f"{remaining} seconde(s)."
        )
        launch_column, skip_column = st.columns(2)
        with launch_column:
            if st.button(
                "Lancer maintenant",
                key="launch_download_follow_up",
                type="primary",
                width="stretch",
            ):
                _launch_follow_up(job)
                st.rerun()
        with skip_column:
            if st.button(
                "Ne pas lancer",
                key="skip_download_follow_up",
                width="stretch",
            ):
                job.follow_up_runner = None
                job.status = "done"
                job.output += f"{job.follow_up_label} ignoré.\n"
                if (
                    job.open_output_on_success
                    and job.output_dir is not None
                    and not job.output_folder_opened
                ):
                    _open_in_file_explorer(job.output_dir, "de sortie")
                    job.output_folder_opened = True
                st.rerun()
        return

    st.caption(f"Sortie du traitement : {job.tool_name}")
    progress_items = sorted(job.progress.items()) or [
        (0, (0, "Préparation du traitement…"))
    ]
    for index, (_, (percent, label)) in enumerate(progress_items):
        progress_column, stop_column = st.columns(
            [8, 2], vertical_alignment="center"
        )
        with progress_column:
            StreamlitProgressBar(progress_column).progress(percent, text=label)
        with stop_column:
            if index == 0 and job.status in {"running", "stopping"}:
                if st.button(
                    "Arrêter",
                    key="stop_active_treatment",
                    type="secondary",
                    width="stretch",
                    disabled=job.status == "stopping",
                ):
                    job.cancel_event.set()
                    job.status = "stopping"
                    st.rerun()

    st.code(job.output or "Préparation du traitement…", language="text")
    if job.status == "done":
        if job.is_empty_folder:
            st.warning(
                "Aucun fichier compatible n'a été trouvé dans le dossier "
                "d'entrée."
            )
        else:
            st.success(f"{job.tool_name} terminé.")
    elif job.status == "cancelled":
        st.warning("Traitement arrêté.")
    elif job.status == "validation_error":
        st.warning(f"Traitement non effectué : {job.error}")
    elif job.status == "error":
        first_error_line = job.error.splitlines()[0] if job.error else ""
        st.error(
            f"Le traitement « {job.tool_name} » a échoué : {first_error_line}"
        )
        if job.error:
            st.code(job.output + "\n" + job.error, language="text")


@st.cache_data(show_spinner=False)
def _environment_report() -> str:
    """Return the legacy environment report without printing to the console."""
    report = io.StringIO()
    with redirect_stdout(report):
        func_global_module.print_system_info()
    return report.getvalue().strip()


def _runtime_config() -> AppConfig:
    """Build a per-session configuration from the sidebar flag toggles."""
    overrides = {
        flag: st.session_state.get(f"flag_{flag}", getattr(APP_CONFIG, flag))
        for flag in SESSION_FLAGS
    }
    overrides.update({
        value: st.session_state.get(
            f"value_{value}", getattr(APP_CONFIG, value)
        )
        for value in SESSION_VALUES
    })
    overrides["LOG_LEVEL"] = st.session_state.get(
        "value_LOG_LEVEL", APP_CONFIG.LOG_LEVEL
    )
    return replace(APP_CONFIG, **overrides)


def _startup_report() -> str:
    """Return the CLI-equivalent code version and session launch time."""
    if "code_launch_time" not in st.session_state:
        st.session_state.code_launch_time = datetime.now().isoformat()
    version = func_global_module.format_git_version(
        func_global_module.get_git_version()
    )
    return f"{version}\n\nCode lancé le : {st.session_state.code_launch_time}"


def _run_tool(
    tool_name: str,
    runner: ToolRunner,
    *,
    origin_tool_name: str | None = None,
    output_dir: Path | None = None,
    follow_up_label: str | None = None,
    follow_up_runner: ToolRunner | None = None,
    follow_up_required: FollowUpRequirement | None = None,
    follow_up_output_dir: Path | None = None,
    open_output_on_success: bool | None = None,
    follow_up_open_output_on_success: bool | None = None,
) -> None:
    """Start one treatment without blocking the Streamlit interaction loop."""
    active_job = st.session_state.get("active_treatment")
    if (
        isinstance(active_job, TreatmentJob)
        and active_job.status in {"running", "stopping"}
    ):
        st.warning(
            "Un traitement est déjà en cours. Arrêtez-le avant d’en lancer "
            "un autre."
        )
        return

    configure_file_logging(
        APP_CONFIG.LOG_DIR,
        enabled=st.session_state.get(
            "flag_LOG_TO_FILE", APP_CONFIG.LOG_TO_FILE
        ),
        level=st.session_state.get("value_LOG_LEVEL", APP_CONFIG.LOG_LEVEL),
    )
    job = TreatmentJob(
        tool_name=tool_name,
        origin_tool_name=origin_tool_name,
        output_dir=output_dir or APP_CONFIG.OUTPUT_DIR,
        open_output_on_success=(
            st.session_state.get(
                "flag_OPEN_OUTPUT_DIR_AFTER_TREATMENT",
                APP_CONFIG.OPEN_OUTPUT_DIR_AFTER_TREATMENT,
            )
            if open_output_on_success is None
            else open_output_on_success
        ),
        follow_up_label=follow_up_label,
        follow_up_runner=follow_up_runner,
        follow_up_required=follow_up_required,
        follow_up_output_dir=follow_up_output_dir,
        follow_up_open_output_on_success=follow_up_open_output_on_success,
    )
    worker = Thread(
        target=_run_treatment_worker,
        args=(job, runner),
        name=f"toolbox_pb_{tool_name}",
        daemon=True,
    )
    job.worker = worker
    st.session_state.active_treatment = job
    worker.start()


def _run_video_encodor_with_image_reductor(cfg: AppConfig) -> bool:
    """Encode videos, then offer the CLI's complementary image reduction."""
    video_folder_is_empty = video_encodor(cfg)
    image_folder_is_empty = _run_complementary_reductor(
        cfg,
        "video",
        find_files_by_extensions,
        video_encodor,
        image_reductor,
    )
    if image_folder_is_empty is None:
        return video_folder_is_empty
    return video_folder_is_empty and image_folder_is_empty


def _encode_downloaded_youtube_videos(
    downloaded_files: list[Path],
    cfg: AppConfig,
) -> bool:
    """Encode newly downloaded videos only, keeping output files flat."""
    if not downloaded_files:
        raise ValueError("Aucun fichier YouTube téléchargé n’est disponible.")

    target_suffix = ".mp4"
    for downloaded_file in downloaded_files:
        if not downloaded_file.is_file():
            raise FileNotFoundError(
                f"Fichier téléchargé introuvable : {downloaded_file}"
            )
        stem = downloaded_file.stem.removesuffix("_download")
        processed_path = cfg.OUTPUT_DIR / f"{stem}_processed{target_suffix}"
        if processed_path.exists():
            emit(f"Fichier déjà traité : {processed_path.name}")
            continue

        should_encode, preflight_message = _youtube_video_encodor_preflight(
            downloaded_file, cfg
        )
        # This diagnostic is useful in the Streamlit console but does not
        # need to clutter the persistent application log.
        emit(f"\n{preflight_message}", log=False)
        if not should_encode:
            continue

        before_size = downloaded_file.stat().st_size
        emit("\nLancement de Video_encodor…")

        with TemporaryDirectory(prefix="toolbox_pb_youtube_") as temp_name:
            temp_root = Path(temp_name)
            input_dir = temp_root / "input"
            output_dir = temp_root / "output"
            input_dir.mkdir()
            staged_input = input_dir / f"{stem}{downloaded_file.suffix}"
            shutil.copy2(downloaded_file, staged_input)
            staging_cfg = replace(
                cfg,
                INPUT_DIR=input_dir,
                OUTPUT_DIR=output_dir,
            )
            video_encodor(staging_cfg)

            generated_files = sorted(output_dir.rglob(f"*{target_suffix}"))
            if not generated_files:
                raise ValueError(
                    f"Le traitement n’a produit aucun fichier {target_suffix}."
                )
            processed_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(generated_files[0]), processed_path)
            emit(f"Fichier traité : {processed_path.name}")
            after_size = processed_path.stat().st_size
            size_delta = before_size - after_size
            if size_delta >= 0:
                difference = (
                    f"réduction de {func_global_module.format_bytes(size_delta)} "
                    f"({size_delta / before_size * 100:.1f} %)"
                )
            else:
                difference = (
                    f"augmentation de {func_global_module.format_bytes(-size_delta)} "
                    f"({-size_delta / before_size * 100:.1f} %)"
                )
            emit(
                "Taille Video_encodor : "
                f"{func_global_module.format_bytes(before_size)} → "
                f"{func_global_module.format_bytes(after_size)} "
                f"({difference})"
            )
    return False


def _youtube_video_encodor_preflight(
    video_path: Path,
    cfg: AppConfig,
) -> tuple[bool, str]:
    """Decide conservatively whether H.265 encoding should reduce a download."""
    try:
        metadata = get_all_metadata(video_path)
    except (OSError, RuntimeError, ValueError) as exc:
        return (
            False,
            "Analyse avant Video_encodor impossible ; encodage ignoré par "
            f"précaution ({exc}).",
        )
    return _youtube_video_encodor_preflight_from_metadata(metadata, cfg)


def _youtube_video_encodor_preflight_from_metadata(
    metadata: dict[str, object],
    cfg: AppConfig,
) -> tuple[bool, str]:
    """Estimate a size reduction from FFprobe metadata without re-encoding."""
    streams = metadata.get("streams")
    format_info = metadata.get("format")
    if not isinstance(streams, list):
        return False, "Analyse avant Video_encodor indisponible ; encodage ignoré."

    video_stream = next(
        (
            stream
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "video"
        ),
        None,
    )
    if not isinstance(video_stream, dict):
        return False, "Aucun flux vidéo détecté ; Video_encodor ignoré.\n"

    codec = str(video_stream.get("codec_name") or "inconnu").casefold()
    height_value = video_stream.get("height")
    height = height_value if isinstance(height_value, int) else None
    source_bitrate = _youtube_total_bitrate_kbps(format_info, streams)
    target_bitrate = _youtube_target_bitrate_kbps(height, cfg)
    source_label = (
        f"{source_bitrate:.0f} kb/s"
        if source_bitrate is not None
        else "indisponible"
    )
    resolution_label = f"{height}p" if height is not None else "inconnue"
    analysis = (
        "Analyse avant Video_encodor :\n"
        f"- Codec source : {codec.upper()}\n"
        f"- Résolution : {resolution_label}\n"
        f"- Débit actuel : {source_label}\n"
        f"- Débit H.265 estimé : {target_bitrate:.0f} kb/s\n"
    )

    if codec in {"av1", "hevc", "h265"}:
        return (
            False,
            f"{analysis}\nVideo_encodor ignoré : la source est déjà encodée "
            f"avec {codec.upper()}, un gain de taille n’est pas attendu.\n",
        )
    if source_bitrate is None:
        return (
            False,
            f"{analysis}\nVideo_encodor ignoré : le débit source est "
            "indisponible, donc une réduction ne peut pas être estimée.\n",
        )

    minimum_source_bitrate = target_bitrate * (
        1 + cfg.YOUTUBE_VIDEO_ENCODOR_MIN_EXPECTED_SAVINGS_PERCENT / 100
    )
    if source_bitrate < minimum_source_bitrate:
        return (
            False,
            f"{analysis}\nVideo_encodor ignoré : la taille augmenterait "
            "probablement ou le gain estimé serait inférieur à "
            f"{cfg.YOUTUBE_VIDEO_ENCODOR_MIN_EXPECTED_SAVINGS_PERCENT:.0f} %.\n",
        )

    expected_savings = (1 - target_bitrate / source_bitrate) * 100
    return (
        True,
        f"{analysis}\nEncodage recommandé : réduction estimée d’environ "
        f"{expected_savings:.1f} %.",
    )


def _youtube_total_bitrate_kbps(
    format_info: object,
    streams: list[object],
) -> float | None:
    """Read the total source bitrate, falling back to individual streams."""
    if isinstance(format_info, dict):
        bitrate = _youtube_bitrate_kbps(format_info.get("bit_rate"))
        if bitrate is not None:
            return bitrate

    stream_bitrates = [
        bitrate
        for stream in streams
        if isinstance(stream, dict)
        for bitrate in [_youtube_bitrate_kbps(stream.get("bit_rate"))]
        if bitrate is not None
    ]
    return sum(stream_bitrates) if stream_bitrates else None


def _youtube_bitrate_kbps(value: object) -> float | None:
    """Convert one FFprobe bitrate value from bit/s to kb/s."""
    try:
        bitrate = float(value)
    except (TypeError, ValueError):
        return None
    return bitrate / 1_000 if bitrate > 0 else None


def _youtube_target_bitrate_kbps(height: int | None, cfg: AppConfig) -> float:
    """Return the first configured H.265 bitrate tier covering ``height``."""
    tiers = cfg.YOUTUBE_VIDEO_ENCODOR_TARGET_TOTAL_BITRATE_KBPS_BY_HEIGHT
    if height is not None:
        for maximum_height, bitrate in tiers:
            if height <= maximum_height:
                return float(bitrate)
    return float(tiers[-1][1])


def _youtube_video_codec(video_path: Path) -> str:
    """Return the first video codec reported by FFprobe for a download."""
    metadata = get_all_metadata(video_path)
    return _youtube_video_codec_from_metadata(metadata, video_path)


def _youtube_video_codec_from_metadata(metadata: dict[str, object], video_path: Path) -> str:
    """Extract the first video codec from FFprobe metadata."""
    streams = metadata.get("streams")
    if not isinstance(streams, list):
        raise ValueError(f"Aucun flux vidéo détecté dans : {video_path.name}")
    for stream in streams:
        if not isinstance(stream, dict) or stream.get("codec_type") != "video":
            continue
        codec = str(stream.get("codec_name") or "").casefold()
        if codec:
            return codec
    raise ValueError(f"Aucun codec vidéo détecté dans : {video_path.name}")


def _youtube_video_specs(video_path: Path) -> tuple[str, str, int | None]:
    """Return the detected codec and a readable technical summary."""
    metadata = get_all_metadata(video_path)
    codec = _youtube_video_codec_from_metadata(metadata, video_path)
    try:
        file_size = func_global_module.format_bytes(video_path.stat().st_size)
    except OSError:
        file_size = "indisponible"

    format_info = metadata.get("format")
    streams = metadata.get("streams")
    video_stream = next(
        (
            stream
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "video"
        ),
        {},
    ) if isinstance(streams, list) else {}
    details = [
        "\nSpécifications de la vidéo téléchargée :",
        f"- Fichier : {video_path.name}",
        f"- Taille : {file_size}",
        f"- Codec vidéo : {codec.upper()}",
    ]
    if isinstance(format_info, dict):
        duration = format_info.get("duration")
        if duration is not None:
            formatted_duration = format_duration_hms(duration)
            if formatted_duration != "N/A":
                details.append(f"- Durée : {formatted_duration}")
    video_height: int | None = None
    if isinstance(video_stream, dict):
        width, height = video_stream.get("width"), video_stream.get("height")
        if isinstance(width, int) and isinstance(height, int):
            video_height = height
            details.append(f"- Résolution : {width}×{height}")
        bitrate = video_stream.get("bit_rate")
        if bitrate is None and isinstance(format_info, dict):
            bitrate = format_info.get("bit_rate")
        try:
            details.append(f"- Débit : {round(float(bitrate) / 1_000):.0f} kb/s")
        except (TypeError, ValueError):
            pass
    return codec, "\n".join(details), video_height


def _youtube_requested_level_notice(
    media_format: str,
    requested_video_height: str,
    requested_audio_bitrate: str,
    *,
    actual_video_height: int | None = None,
    actual_audio_bitrate: float | None = None,
) -> str | None:
    """Explain when YouTube supplied a lower level than the requested one."""
    if media_format == "MP4":
        expected_height = int(requested_video_height)
        if actual_video_height is not None and actual_video_height < expected_height:
            return (
                f"Définition demandée : {expected_height}p indisponible ; "
                f"définition utilisée : {actual_video_height}p."
            )
        return None

    expected_bitrate = int(requested_audio_bitrate)
    if (
        actual_audio_bitrate is not None
        and round(actual_audio_bitrate) != expected_bitrate
    ):
        return (
            f"Débit audio demandé : {expected_bitrate} kb/s indisponible ; "
            f"débit utilisé : {round(actual_audio_bitrate)} kb/s."
        )
    return None


def _find_new_youtube_files(
    output_dir: Path,
    existing_files: set[Path],
    media_format: str,
) -> list[Path]:
    """Find final media files created by a legacy downloader result."""
    suffix = ".mp3" if media_format == "MP3" else ".mp4"
    return sorted(
        (
            path
            for path in output_dir.iterdir()
            if path not in existing_files and path.suffix.lower() == suffix
        ),
        key=lambda path: path.name.casefold(),
    )


def _is_youtube_subtitle_download_error(exc: ValueError) -> bool:
    """Recognize yt-dlp failures limited to an optional subtitle request."""
    message = str(exc).casefold()
    return (
        "subtitle" in message
        and (
            "unable to download video subtitles" in message
            or "http error 429" in message
        )
    )


def _open_in_file_explorer(path: Path, label: str) -> None:
    """Open a configured folder and focus its Explorer window on Windows."""
    if not path.is_dir():
        st.error(f"Le dossier {label.lower()} n’existe pas : {path}")
        return
    status = st.empty()
    target_path = path.resolve()
    status.info(f"Ouverture de Windows Explorer sur : {target_path}")
    try:
        completed = subprocess.run(
            (
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-WindowStyle",
                "Hidden",
                "-File",
                str(FOCUS_EXPLORER_SCRIPT),
                str(target_path),
            ),
            creationflags=subprocess.CREATE_NO_WINDOW,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except subprocess.TimeoutExpired:
        status.warning(
            "Windows Explorer a été demandé, mais Focus Explorer n’a pas "
            "répondu dans les 8 secondes."
        )
        return
    except OSError as exc:
        st.error(f"Impossible d’ouvrir le dossier {label.lower()} : {exc}")
        return

    if completed.returncode == 0:
        status.success(
            completed.stdout.strip()
            or f"Windows Explorer ouvert sur : {target_path}"
        )
        return

    details = completed.stderr.strip() or completed.stdout.strip()
    status.error(
        f"Impossible d’ouvrir Windows Explorer sur {target_path}. "
        f"Détail : {details or f'code PowerShell {completed.returncode}'}"
    )


def _launch_cli() -> None:
    """Launch the historical interactive menu in its own Windows terminal."""
    try:
        subprocess.Popen(
            ("cmd.exe", "/k", "poetry run python -m toolbox_pb.ui.cli"),
            cwd=PROJECT_DIR,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
    except OSError as exc:
        st.error(f"Impossible d’ouvrir le mode CLI : {exc}")
        return
    st.success("Le mode CLI est ouvert dans une nouvelle fenêtre de commande.")


def _tool_icon(key: str) -> Path:
    """Return the generated action-specific icon."""
    return TOOL_ICON_DIR / f"{key}.png"


def _tool_card(
    title: str,
    description: str,
    before_example: str,
    after_example: str,
    runner: ToolRunner,
    *,
    key: str,
    before_image: Path | None = None,
    after_image: Path | None = None,
    input_label: str | None = None,
    input_help: str | None = None,
    input_caption: str | None = None,
    input_type: str = "text",
    input_options: tuple[int, ...] | None = None,
    input_required: bool = False,
    icon_key: str | None = None,
) -> None:
    """Render one expandable sub-category and its action button."""
    expanded_key = f"{key}_expanded"
    is_expanded = st.session_state.get(expanded_key, False)
    header_icon_column, header_button_column = st.columns(
        [2.1, 7.9], gap=None, vertical_alignment="center"
    )
    with header_icon_column:
        st.image(_tool_icon(icon_key or key), width=208)
    with header_button_column:
        marker = "▾" if is_expanded else "▸"
        label = f"{marker} {TOOL_NUMBERS[title]}. {title}"
        if st.button(label, key=f"{key}_toggle", width="stretch"):
            st.session_state[expanded_key] = not is_expanded

    if not st.session_state.get(expanded_key, False):
        return

    with st.container(border=True):
        st.write(description)
        before_column, after_column = st.columns(2)
        with before_column:
            with st.container(border=True):
                st.markdown(
                    "### :material/cloud: :material/movie:",
                    text_alignment="center",
                )
                st.markdown("#### Avant")
                if before_image:
                    st.image(
                        before_image,
                        width="stretch",
                        alt=f"Exemple avant — {title}",
                    )
                st.write(before_example)
        with after_column:
            with st.container(border=True):
                st.markdown(
                    "### :material/computer: :material/video_file:",
                    text_alignment="center",
                )
                st.markdown("#### Après")
                if after_image:
                    st.image(
                        after_image,
                        width="stretch",
                        alt=f"Exemple après — {title}",
                    )
                st.write(after_example)
        value = None
        if input_label:
            if input_type == "number":
                value = st.number_input(
                    input_label,
                    value=0.0,
                    step=0.1,
                    format="%.2f",
                    key=f"{key}_value",
                    help=input_help,
                )
            elif input_type == "select":
                if input_options is None:
                    raise ValueError("Les options du sélecteur sont requises.")
                value = st.selectbox(
                    input_label,
                    options=input_options,
                    key=f"{key}_value",
                    help=input_help,
                )
            else:
                value = st.text_input(
                    input_label,
                    key=f"{key}_value",
                    help=input_help,
                )
            if input_caption:
                st.caption(input_caption)
        if st.button(f"Lancer {title}", key=f"{key}_run", type="primary"):
            if input_required and (value is None or not str(value).strip()):
                st.warning(
                    f"Renseignez « {input_label} » avant de lancer ce "
                    "traitement."
                )
            else:
                _run_tool(
                    title,
                    runner if value is None else lambda: runner(value),
                )
        active_job = st.session_state.get("active_treatment")
        if (
            isinstance(active_job, TreatmentJob)
            and active_job.tool_name == title
        ):
            _render_active_treatment()


def _category_video(cfg: AppConfig) -> None:
    _tool_card(
        "video_encodor",
        (
            "Réencode chaque vidéo du dossier d’entrée avec les codecs "
            "configurés, compare les tailles avant/après et conserve une "
            "trace "
            "du traitement dans le MP4 de sortie."
        ),
        """`vacances.mov` — 2 Go

- Codec vidéo : aucun
- Codec audio : AAC""",
        """`vacances.mov` — 700 Mo

- Codec vidéo : H.265
- Codec audio : AAC (inchangé)""",
        lambda: _run_video_encodor_with_image_reductor(cfg),
        key="video_encode",
    )
    _tool_card(
        "video_assemblor",
        (
            "Assemble plusieurs vidéos en un seul fichier. Si "
            "`data/segment/segments.csv` existe, il définit l’ordre des clips "
            "et leurs points de début et de fin ; sinon, les vidéos sont "
            "assemblées selon leurs noms."
        ),
        """3 fichiers :

- `clip-01.mp4` — 00:00:08
- `clip-02.mp4` — 00:00:12
- `clip-03.mp4` — 00:00:10""",
        """`assembled.mp4`

- Durée : 00:00:30
- Clips : assemblés dans l'ordre défini""",
        lambda: video_assemblor(cfg),
        key="video_assemble",
    )
    _tool_card(
        "video_audio_decalator",
        (
            "Avance ou retarde la piste audio d’une vidéo sans réencoder son "
            "flux vidéo."
        ),
        """`video.mp4`

- Décalage audio : +0,5 s
- État : voix en retard""",
        """`video.mp4`

- Correction : −0,5 s
- État : voix synchronisée""",
        lambda delay=0.0: video_audio_decalator(cfg, delay),
        key="video_audio_offset",
        input_label="Délai de décalage audio (secondes)",
        input_help=(
            "Exemple : -0,5 pour avancer de 0,5 s ; 0,5 pour retarder de "
            "0,5 s."
        ),
        input_type="number",
    )
    _tool_card(
        "video_volume_adjust",
        (
            "Applique des variations de volume audio sur les plages "
            "temporelles "
            "définies dans `data/segment/boosts.csv`, sans réencoder le flux "
            "vidéo."
        ),
        """`video.mp4`

- Plage : 00:01:00 → 00:01:30
- Volume : niveau initial""",
        """`video.mp4`

- Plage : 00:01:00 → 00:01:30
- Gain : règle de `boosts.csv` appliquée""",
        lambda: video_volume_adjust(cfg),
        key="video_volume",
    )
    _tool_card(
        "video_srt_extractor",
        (
            "Extrait la piste de sous-titres intégrée à chaque vidéo vers un "
            "fichier `.srt` et crée une copie de la vidéo sans cette piste, "
            "sans réencoder l’audio ni la vidéo."
        ),
        """`interview.mp4`

- Sous-titres : piste intégrée""",
        """2 fichiers créés :

- `interview.srt` — sous-titres extraits
- `interview.mp4` — copie sans piste de sous-titres""",
        lambda: video_srt_extractor(cfg),
        key="video_srt_extract",
    )
    _tool_card(
        "video_srt_integrator",
        (
            "Intègre `data/segment/sous_titre.srt` comme piste de sous-titres "
            "MP4 aux vidéos, sans réencoder l’audio ou la vidéo."
        ),
        """2 fichiers :

- `film.mp4` — vidéo source
- `sous_titre.srt` — sous-titres séparés""",
        """`film.mp4`

- Piste de sous-titres : intégrée
- Lecture : activable ou désactivable""",
        lambda: video_srt_integrator(cfg),
        key="video_srt_integrate",
    )
    _tool_card(
        "video_srt_date_filtrator",
        (
            "Filtre les fichiers SRT ou TXT afin de ne conserver que la "
            "première occurrence de chaque date, avec un bilan avant et après "
            "traitement."
        ),
        """`sous_titre.srt` — 3 occurrences de date :

- 00:00:02 — « 12/05/2024 »
- 00:00:18 — « 12/05/2024 »
- 00:00:35 — « 12/05/2024 »""",
        """`sous_titre.srt` — date conservée :

- 00:00:02 — « 12/05/2024 »
- 2 doublons supprimés""",
        lambda: video_srt_date_filtrator(cfg),
        key="video_srt_filter",
    )
    _tool_card(
        "video_ass_hard_integrator",
        (
            "Convertit automatiquement les fichiers SRT en ASS, puis incruste "
            "les sous-titres de façon permanente dans les vidéos."
        ),
        """2 fichiers :

- `film.mp4` — vidéo source
- `sous_titre.srt` — sous-titres séparés""",
        """`film.mp4`

- Sous-titres : inscrits dans l'image
- Lecture : toujours visibles, non désactivables""",
        lambda: video_ass_hard_integrator(cfg),
        key="video_ass",
    )
    _tool_card(
        "video_rotator",
        (
            "Fait pivoter l’image de chaque vidéo dans le sens horaire. "
            "Seuls les angles 90°, 180° et 270° sont acceptés."
        ),
        (
            "`portrait_mal_orienté.mp4`\n\n- Orientation : paysage\n"
            "- Image : couchée"
        ),
        "`portrait.mp4`\n\n- Rotation : 270°\n- Image : redressée",
        lambda angle="": video_rotator(cfg, angle),
        key="video_rotator",
        before_image=IMAGE_EXAMPLE_DIR / "video_rotator_before.png",
        after_image=IMAGE_EXAMPLE_DIR / "video_rotator_after.png",
        input_label="Angle de rotation (90°, 180° ou 270°)",
        input_help="La rotation est horaire.",
        input_type="select",
        input_options=(90, 180, 270),
    )


def _category_image(cfg: AppConfig) -> None:
    _tool_card(
        "image_defilor",
        (
            "Génère une vidéo verticale défilante pour chaque image source "
            "et, "
            "pour les PDF, une vidéo par image extraite de chaque page. La "
            "hauteur, la vitesse, le FPS et les temps d’arrêt sont "
            "paramétrables."
        ),
        """`panorama.jpg`

- Image fixe et horizontale
- Format : 4000 × 1200 px""",
        """`panorama.mp4`

- Format : vidéo verticale
- Mouvement : défilement de l'image""",
        lambda extra_args="": image_defilor(cfg, extra_args or None),
        key="image_defilor",
        input_label="Options ImageMagick (facultatif)",
        input_help="Exemple : --height 720 --speed 50",
        input_caption=(
            "Options possibles : `--height <px>` (1080), `--speed <px/s>` "
            "(35), `--fps <ips>` (60), `--hold-start <s>` (5), "
            "`--hold-end <s>` (5), "
            "`--codec <codec>` (`libx265`) et `--crf <0-51>` (18)."
        ),
    )
    _tool_card(
        "image_reductor",
        (
            "Réduit les photos JPEG et PNG sans changer leur format ni leurs "
            "dimensions. Les JPEG sont réencodés avec la qualité configurée "
            "et "
            "les PNG sont optimisés sans perte."
        ),
        """`photo.jpg`

- Taille : 8 Mo
- Dimensions : 4000 × 3000 px""",
        """`photo.jpg`

- Taille : 2 Mo
- Dimensions : 4000 × 3000 px (inchangées)
- Qualité JPEG : valeur configurée (75 par défaut)""",
        lambda: image_reductor(cfg),
        key="image_reduce",
    )
    _tool_card(
        "image_diapo_video_creator",
        (
            "Assemble toutes les photos du dossier d’entrée dans une vidéo. "
            "Une "
            "piste audio unique peut être ajoutée et les noms des photos sont "
            "intégrés comme sous-titres."
        ),
        """3 fichiers :

- `01-plage.jpg`
- `02-montagne.jpg`
- `musique.mp3`""",
        """`diaporama.mp4`

- Photos : affichées dans l'ordre
- Audio : `musique.mp3`
- Sous-titres : noms des photos""",
        lambda: image_diapo_video_creator(cfg),
        key="image_diapo",
    )
    _tool_card(
        "image_withoutbg",
        (
            "Supprime l’arrière-plan de chaque image source et génère un PNG "
            "transparent en conservant l’arborescence des sous-dossiers."
        ),
        """`produit.jpg`

- Arrière-plan : blanc
- Sujet : objet photographié""",
        """`produit.png`

- Arrière-plan : transparent
- Sujet : conservé""",
        lambda: image_withoutbg(cfg),
        key="image_withoutbg",
        before_image=IMAGE_EXAMPLE_DIR / "image_withoutbg_before.png",
        after_image=IMAGE_EXAMPLE_DIR / "image_withoutbg_after.png",
    )


def _category_audio(cfg: AppConfig) -> None:
    _tool_card(
        "audio_compressor",
        (
            "Convertit les fichiers audio acceptés en MP3 au débit configuré. "
            "Les MP3 déjà à un débit inférieur ou égal sont copiés intacts, "
            "sans réencodage."
        ),
        """`concert.flac`

- Taille : 120 Mo
- Format : audio sans perte""",
        """`concert.mp3`

- Débit : valeur configurée
- Taille : réduite
- MP3 déjà assez compressé : copié intact""",
        lambda: audio_compressor(cfg),
        key="audio_compress",
    )


def _category_pdf(cfg: AppConfig) -> None:
    _tool_card(
        "pdf_filigranor",
        (
            "Ajoute à chaque PDF un filigrane textuel diagonal répété. Le "
            "préfixe configuré est ajouté automatiquement au destinataire "
            "saisi."
        ),
        """`contrat.pdf`

- Pages : sans filigrane
- Destinataire : « Alice »""",
        """`contrat.pdf`

- Pages : filigrane diagonal répété
- Texte : « document exclusivement destiné à Alice »""",
        lambda recipient="": pdf_filigranor(cfg, recipient),
        key="pdf_watermark",
        before_image=IMAGE_EXAMPLE_DIR / "pdf_filigranor_before.png",
        after_image=IMAGE_EXAMPLE_DIR / "pdf_filigranor_after.png",
        input_label="Destinataire du filigrane",
        input_required=True,
    )
    _tool_card(
        "pdf_assemblor",
        (
            "Fusionne tous les PDF du dossier d’entrée et de ses "
            "sous-dossiers "
            "en un unique fichier, dans l’ordre alphabétique de leurs chemins "
            "relatifs."
        ),
        """3 fichiers :

- `01-couverture.pdf`
- `02-contrat.pdf`
- `03-annexe.pdf`""",
        """`assembled.pdf`

- Documents : fusionnés
- Ordre : couverture → contrat → annexe""",
        lambda: pdf_assemblor(cfg),
        key="pdf_assemble",
    )
    _tool_card(
        "pdf_page_alternator",
        (
            "Alterne les pages de `impaire.pdf` et `paire.pdf` placés dans le "
            "dossier d’entrée, en commençant par le fichier impair."
        ),
        """2 fichiers :

- `impaire.pdf` — pages 1, 3, 5
- `paire.pdf` — pages 2, 4, 6""",
        """`alternated.pdf`

- Pages : 1, 2, 3, 4, 5, 6
- Ordre : rétabli""",
        lambda: pdf_page_alternator(cfg),
        key="pdf_alternate",
    )


def _category_web(cfg: AppConfig) -> None:
    """Render the local YouTube-to-MP3/MP4 downloader."""
    expanded_key = "youtube_downloader_expanded"
    is_expanded = st.session_state.get(expanded_key, False)
    header_icon_column, header_button_column = st.columns(
        [2.1, 7.9], gap=None, vertical_alignment="center"
    )
    with header_icon_column:
        st.image(
            _tool_icon("youtube_downloader"),
            width=208,
            alt="Téléchargement YouTube audio ou vidéo",
        )
    with header_button_column:
        if st.button(
            f"{'▾' if is_expanded else '▸'} YouTube Downloader",
            key="youtube_downloader_toggle",
            width="stretch",
        ):
            st.session_state[expanded_key] = not is_expanded

    if not st.session_state.get(expanded_key, False):
        return

    with st.container(border=True):
        st.write(
            "Télécharge une vidéo YouTube que vous êtes autorisé à conserver, "
            "au format audio MP3 ou vidéo MP4. Les fichiers sont écrits dans "
            "le dossier de sortie de la toolbox."
        )
        st.info(
            "Utilisez cette fonction uniquement pour vos propres vidéos ou du "
            "contenu dont le téléchargement est autorisé.",
            icon=":material/copyright:",
        )
        before_column, after_column = st.columns(2)
        with before_column:
            with st.container(border=True):
                st.markdown("#### Avant")
                st.write(
                    """:material/language: **Vidéo présente sur le Web**

`https://www.youtube.com/watch?v=exemple`

- Hébergée sur YouTube"""
                )
        with after_column:
            with st.container(border=True):
                st.markdown("#### Après")
                st.write(
                    f""":material/computer: **Fichier multimédia présent sur le PC**

`{cfg.OUTPUT_DIR}\\video_download.mp4`

- Fichier local MP4 ou MP3"""
                )
        output_type_key = "youtube_downloader_output_type"
        legacy_output_type = st.session_state.get(output_type_key)
        if legacy_output_type == "Audio MP3":
            st.session_state[output_type_key] = "MP3"
        elif legacy_output_type == "Vidéo MP4":
            st.session_state[output_type_key] = "MP4"
        output_type = st.segmented_control(
            "Format de sortie",
            options=("MP3", "MP4"),
            default="MP3",
            format_func=lambda value: (
                "♫ Audio MP3" if value == "MP3" else "🎞️ Vidéo MP4"
            ),
            required=True,
            key=output_type_key,
        )
        with st.form("youtube_downloader_form", border=False):
            url = st.text_input(
                "URL YouTube",
                key="youtube_downloader_url",
                placeholder="https://www.youtube.com/watch?v=…",
                help="Les liens youtube.com et youtu.be sont acceptés.",
            )
            if output_type == "MP3":
                mp3_bitrate = st.selectbox(
                    "Débit audio MP3",
                    options=MP3_BITRATES,
                    index=MP3_BITRATES.index("160"),
                    format_func=lambda value: f"{value} kb/s",
                    key="youtube_downloader_bitrate",
                )
                media_format = "MP3"
                video_quality = "1080"
            else:
                video_quality = st.selectbox(
                    "Qualité vidéo maximale",
                    options=VIDEO_QUALITIES,
                    index=VIDEO_QUALITIES.index("1080"),
                    format_func=lambda value: f"{value}p",
                    key="youtube_downloader_quality",
                )
                media_format = "MP4"
                mp3_bitrate = "160"
                download_subtitles = st.checkbox(
                    "Télécharger les sous-titres SRT",
                    value=False,
                    key="youtube_downloader_subtitles",
                    help=(
                        "Priorité : sous-titre fourni français seul ; sinon, "
                        "sous-titre fourni anglais et sous-titre automatique "
                        "français de YouTube lorsqu’ils sont disponibles."
                    ),
                )
            if output_type == "MP3":
                download_subtitles = False
            submitted = st.form_submit_button(
                "Télécharger",
                type="primary",
                icon=":material/download:",
            )

        if submitted:
            if not url.strip():
                st.warning(
                    "Renseignez une URL YouTube avant de lancer le téléchargement."
                )
            elif media_format not in {"MP3", "MP4"}:
                st.warning("Choisissez un format de sortie.")
            else:
                download_options = YouTubeDownloadOptions(
                    url=url,
                    output_dir=cfg.OUTPUT_DIR,
                    media_format=media_format,
                    video_quality=video_quality,
                    mp3_bitrate=mp3_bitrate,
                    download_subtitles=download_subtitles,
                )
                downloaded_files: list[Path] = []
                existing_output_files = set(cfg.OUTPUT_DIR.iterdir())

                def download_runner() -> bool:
                    try:
                        download_result = download_youtube_media(download_options)
                    except ValueError as exc:
                        # A worker created before a hot reload can still hold
                        # the older downloader, where an optional subtitle
                        # failure also raised for an already-written video.
                        if not _is_youtube_subtitle_download_error(exc):
                            raise
                        recovered_files = _find_new_youtube_files(
                            cfg.OUTPUT_DIR,
                            existing_output_files,
                            media_format,
                        )
                        if not recovered_files:
                            raise
                        downloaded_files.extend(recovered_files)
                        emit(
                            "Sous-titres indisponibles ; le fichier média "
                            "a bien été téléchargé.",
                            log=False,
                        )
                        download_result = recovered_files
                    if isinstance(download_result, list):
                        for downloaded_file in download_result:
                            if downloaded_file not in downloaded_files:
                                downloaded_files.append(downloaded_file)
                    else:
                        # A worker started before hot reload can retain the
                        # previous boolean-returning downloader function.
                        downloaded_files.extend(
                            _find_new_youtube_files(
                                cfg.OUTPUT_DIR,
                                existing_output_files,
                                media_format,
                            )
                        )
                    if not downloaded_files:
                        raise ValueError(
                            "Le téléchargement YouTube n’a produit aucun "
                            "fichier final."
                        )
                    if media_format == "MP4":
                        for downloaded_file in downloaded_files:
                            _, specs, actual_height = _youtube_video_specs(
                                downloaded_file
                            )
                            # Useful in the Streamlit console, but too verbose
                            # for the persistent process log.
                            emit("\n", specs, log=False)
                            notice = _youtube_requested_level_notice(
                                media_format,
                                video_quality,
                                mp3_bitrate,
                                actual_video_height=actual_height,
                            )
                            if notice:
                                emit(notice)
                        return _encode_downloaded_youtube_videos(
                            downloaded_files, cfg
                        )
                    for downloaded_file in downloaded_files:
                        notice = _youtube_requested_level_notice(
                            media_format,
                            video_quality,
                            mp3_bitrate,
                            actual_audio_bitrate=probe_audio_bitrate_kbps(
                                downloaded_file
                            ),
                        )
                        if notice:
                            emit(notice)
                    return False

                _run_tool(
                    "youtube_downloader",
                    download_runner,
                    output_dir=download_options.output_dir,
                    open_output_on_success=True,
                )

        active_job = st.session_state.get("active_treatment")
        if (
            isinstance(active_job, TreatmentJob)
            and (
                active_job.tool_name == "youtube_downloader"
                or active_job.origin_tool_name == "youtube_downloader"
            )
        ):
            _render_active_treatment()


def _category_file(cfg: AppConfig) -> None:
    _tool_card(
        "file_timeline_sorter",
        (
            "Copie les fichiers vers le dossier de sortie en préfixant leur "
            "date de dernière modification afin que le tri alphabétique "
            "corresponde à "
            "l’ordre chronologique."
        ),
        """`photo.jpg`

- Modifiée : 6 mars 2026 à 14:30
- Nom : sans date""",
        """`2026-03-06_14-30-00__photo.jpg`

- Date : ajoutée au nom
- Tri alphabétique : chronologique""",
        lambda: file_timeline_sorter(cfg),
        key="file_timeline",
    )
    _tool_card(
        "file_str_remover",
        (
            "Copie les fichiers vers le dossier de sortie en supprimant la "
            "chaîne indiquée de leurs noms. Les fichiers source restent "
            "intacts."
        ),
        """`rapport-copie.pdf`

- Texte à supprimer : `-copie`""",
        """`rapport.pdf`

- Texte : supprimé du nom""",
        lambda text="": file_str_remover(cfg, text),
        key="file_remove_text",
        input_label="Chaîne à supprimer",
        input_required=True,
    )
    _tool_card(
        "folder_date_renammer",
        (
            "Copie les dossiers présents dans `data/input` et renomme ceux "
            "qui "
            "contiennent une date française valide au format `AAMMJJ-titre`."
        ),
        """`15 août 2024 - Vacances`

- Date : française et lisible""",
        """`240815-Vacances`

- Date : format AAMMJJ""",
        lambda: folder_date_renammer(cfg),
        key="folder_date",
    )
    _tool_card(
        "cache_nettoyor",
        (
            "Affiche l’espace occupé avant et après nettoyage, puis vide les "
            "caches locaux configurés de Poetry, npm, Windows, Office, "
            "Chrome, "
            "Teams et Firefox."
        ),
        """Caches locaux — 4,2 Go :

- Poetry, npm et Windows
- Chrome, Firefox et Teams
- Office et fichiers temporaires""",
        """Nettoyage terminé :

- Taille restante : 0,8 Go
- Espace libéré : 3,4 Go
- Bilan : affiché dans le journal""",
        cache_nettoyor,
        key="cache_clean",
    )


def _recent_folder_entries(folder: Path, limit: int = 5) -> list[Path]:
    """Return the most recently modified direct children of a folder."""
    if not folder.is_dir():
        return []
    try:
        return sorted(
            (
                path
                for path in folder.iterdir()
                if path.name.casefold() != ".gitkeep"
            ),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )[:limit]
    except OSError:
        return []


def _folder_entry_icon(path: Path) -> str:
    """Choose a compact Material icon for a folder preview entry."""
    if path.is_dir():
        return "folder"
    suffix = path.suffix.lower()
    if suffix in APP_CONFIG.INPUT_ACCEPTED_VIDEO_FILES:
        return "movie"
    if suffix in APP_CONFIG.INPUT_ACCEPTED_AUDIO_FILES:
        return "audio_file"
    if suffix in APP_CONFIG.INPUT_ACCEPTED_IMAGE_FILES:
        return "image"
    if suffix == ".pdf":
        return "picture_as_pdf"
    return "description"


def _folder_summary(folder: Path) -> str:
    """Return a compact, human-readable inventory for a folder preview."""
    try:
        entries = list(folder.iterdir())
    except OSError:
        return "Contenu indisponible"

    counts = {"video": 0, "audio": 0, "image": 0, "pdf": 0, "folder": 0}
    total_bytes = 0
    for entry in entries:
        if entry.is_dir():
            counts["folder"] += 1
            continue
        try:
            total_bytes += entry.stat().st_size
        except OSError:
            continue
        suffix = entry.suffix.lower()
        if suffix in APP_CONFIG.INPUT_ACCEPTED_VIDEO_FILES:
            counts["video"] += 1
        elif suffix in APP_CONFIG.INPUT_ACCEPTED_AUDIO_FILES:
            counts["audio"] += 1
        elif suffix in APP_CONFIG.INPUT_ACCEPTED_IMAGE_FILES:
            counts["image"] += 1
        elif suffix == ".pdf":
            counts["pdf"] += 1

    parts = [
        f"{len(entries)} élément(s)",
        func_global_module.format_bytes(total_bytes),
    ]
    labels = {
        "video": "vidéo(s)",
        "audio": "audio(s)",
        "image": "image(s)",
        "pdf": "PDF",
        "folder": "dossier(s)",
    }
    parts.extend(f"{count} {labels[kind]}" for kind, count in counts.items() if count)
    return " · ".join(parts)


@st.cache_data(show_spinner=False)
def _cached_folder_media_metadata(
    path_text: str, modification_ns: int, size_bytes: int
) -> dict[str, object]:
    """Read FFprobe data once per visible version of a media file."""
    del modification_ns, size_bytes
    try:
        return get_all_metadata(Path(path_text))
    except (OSError, RuntimeError, ValueError):
        return {}


def _folder_entry_details(entry: Path) -> str:
    """Build concise, useful metadata for one folder-preview entry."""
    try:
        stats = entry.stat()
    except OSError:
        return "Informations indisponibles"

    modified = datetime.fromtimestamp(stats.st_mtime).strftime("%d/%m %H:%M")
    if entry.is_dir():
        return f"Dossier · modifié le {modified}"

    details = [func_global_module.format_bytes(stats.st_size), modified]
    suffix = entry.suffix.lower()
    if suffix in APP_CONFIG.INPUT_ACCEPTED_IMAGE_FILES:
        try:
            from PIL import Image

            with Image.open(entry) as image:
                details.append(f"{image.width}×{image.height}")
        except (ImportError, OSError):
            pass
        return " · ".join(details)

    if suffix not in (
        *APP_CONFIG.INPUT_ACCEPTED_VIDEO_FILES,
        *APP_CONFIG.INPUT_ACCEPTED_AUDIO_FILES,
    ):
        return " · ".join(details)

    metadata = _cached_folder_media_metadata(
        str(entry), stats.st_mtime_ns, stats.st_size
    )
    format_info = metadata.get("format")
    streams = metadata.get("streams")
    if not isinstance(format_info, dict) or not isinstance(streams, list):
        return " · ".join(details)

    duration = format_info.get("duration")
    if duration is not None:
        formatted_duration = format_duration_hms(duration)
        if formatted_duration != "N/A":
            details.append(formatted_duration)
    video_stream = next(
        (
            stream
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "video"
        ),
        None,
    )
    audio_stream = next(
        (
            stream
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "audio"
        ),
        None,
    )
    primary_stream = video_stream or audio_stream
    if isinstance(primary_stream, dict):
        codec = primary_stream.get("codec_name")
        if codec:
            details.append(str(codec).upper())
        width, height = primary_stream.get("width"), primary_stream.get("height")
        if isinstance(width, int) and isinstance(height, int):
            details.append(f"{width}×{height}")
        bitrate = primary_stream.get("bit_rate") or format_info.get("bit_rate")
        try:
            details.append(f"{round(float(bitrate) / 1_000):.0f} kb/s")
        except (TypeError, ValueError):
            pass
    return " · ".join(details)


def _render_folder_preview(
    folder: Path, label: str, accent: str, *, border: bool = True
) -> None:
    """Show a small live file browser without leaving the Streamlit page."""
    entries = _recent_folder_entries(folder)
    gitkeep_path = folder / ".gitkeep"
    with st.container(border=border, height=330):
        if not folder.is_dir():
            st.caption(f":{accent}[Dossier {label.lower()} introuvable.]")
            return
        if not entries and not gitkeep_path.is_file():
            st.markdown(f":small[Dossier {label.lower()} vide.]")
            return
        st.markdown(f":small[{_folder_summary(folder)}]")
        st.markdown(":small[Aperçu · 5 plus récents]")
        for entry in entries:
            entry_name = re.sub(r"([\\`*_\[\]])", r"\\\1", entry.name)
            detail_text = re.sub(
                r"([\\`*_\[\]])",
                r"\\\1",
                _folder_entry_details(entry),
            )
            st.markdown(
                f":small[:material/{_folder_entry_icon(entry)}: {entry_name}]"
            )
            st.caption(f"*{detail_text}*")
        if gitkeep_path.is_file():
            st.caption(":gray[:small[:material/description: .gitkeep]]")


def _clear_folder_content(folder: Path) -> int:
    """Delete direct folder contents while retaining its root ``.gitkeep``."""
    if not folder.is_dir():
        raise FileNotFoundError(f"Dossier introuvable : {folder}")

    deleted_count = 0
    for entry in folder.iterdir():
        if entry.name.casefold() == ".gitkeep":
            continue
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()
        deleted_count += 1
    return deleted_count


def _select_files_to_import() -> list[Path] | None:
    """Open Windows' native file picker and return the selected files."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as exc:
        raise RuntimeError("Le sélecteur de fichiers Windows est indisponible.") from exc

    root = None
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askopenfilenames(
            parent=root,
            title="Importer des fichiers dans INPUT",
            filetypes=(("Tous les fichiers", "*.*"),),
        )
    except tk.TclError as exc:
        raise RuntimeError("Impossible d’ouvrir le sélecteur de fichiers.") from exc
    finally:
        if root is not None:
            root.destroy()
    return [Path(path) for path in selected] if selected else None


def _select_export_folder(initial_directory: Path) -> Path | None:
    """Open Windows' native folder picker for an OUTPUT export."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as exc:
        raise RuntimeError("Le sélecteur de dossier Windows est indisponible.") from exc

    root = None
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(
            parent=root,
            title="Choisir le dossier d’export",
            initialdir=str(initial_directory),
            mustexist=True,
        )
    except tk.TclError as exc:
        raise RuntimeError("Impossible d’ouvrir le sélecteur de dossier.") from exc
    finally:
        if root is not None:
            root.destroy()
    return Path(selected) if selected else None


def _available_copy_path(destination: Path, filename: str) -> Path:
    """Return a destination that never overwrites an existing file."""
    candidate = destination / filename
    if not candidate.exists():
        return candidate
    source_path = Path(filename)
    for index in range(1, 10_000):
        candidate = destination / f"{source_path.stem} ({index}){source_path.suffix}"
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"Trop de fichiers portant le nom : {filename}")


def _copy_files_to_folder(sources: list[Path], destination: Path) -> int:
    """Copy files into a folder, preserving metadata and avoiding overwrites."""
    if not destination.is_dir():
        raise FileNotFoundError(f"Dossier de destination introuvable : {destination}")

    copied_count = 0
    for source in sources:
        if not source.is_file():
            continue
        try:
            if source.parent.resolve() == destination.resolve():
                continue
        except OSError:
            pass
        target = _available_copy_path(destination, source.name)
        shutil.copy2(source, target)
        copied_count += 1
    return copied_count


def _export_output_files(output_dir: Path, destination: Path) -> int:
    """Copy OUTPUT files to a chosen folder, excluding the Git placeholder."""
    if not output_dir.is_dir():
        raise FileNotFoundError(f"Dossier OUTPUT introuvable : {output_dir}")
    try:
        if output_dir.resolve() == destination.resolve():
            raise ValueError("Le dossier d’export doit être différent d’OUTPUT.")
    except OSError:
        pass
    sources = [
        path
        for path in output_dir.iterdir()
        if path.is_file() and path.name.casefold() != ".gitkeep"
    ]
    return _copy_files_to_folder(sources, destination)


@st.fragment(key="folder_shortcuts", run_every=2.0)
def _render_folder_shortcuts(cfg: AppConfig) -> None:
    """Render folder actions independently from the rest of the interface."""
    with st.container(border=True):
        input_text, input_icon = st.columns([3.5, 1.5], vertical_alignment="center")
        with input_text:
            st.markdown("## :material/input: :blue[INPUT]")
            if st.button(
                "Import",
                key="import_input_files",
                icon=":material/drive_folder_upload:",
                help="Choisit des fichiers et les copie dans INPUT.",
                type="secondary",
                width="content",
            ):
                try:
                    selected_files = _select_files_to_import()
                    copied_count = (
                        _copy_files_to_folder(selected_files, cfg.INPUT_DIR)
                        if selected_files
                        else 0
                    )
                except (OSError, RuntimeError) as exc:
                    st.error(f"Impossible d’importer les fichiers : {exc}")
                else:
                    if selected_files:
                        st.success(f"{copied_count} fichier(s) importé(s) dans INPUT.")
            if st.button(
                "❌ :red[Clear]",
                key="clear_input_folder",
                help="Supprime tout le contenu sauf le fichier .gitkeep.",
                type="secondary",
                width="content",
            ):
                try:
                    deleted_count = _clear_folder_content(cfg.INPUT_DIR)
                except OSError as exc:
                    st.error(f"Impossible de vider INPUT : {exc}")
                else:
                    st.success(f"INPUT vidé ({deleted_count} élément(s)).")
        with input_icon:
            _folder_open_icon("input", cfg.INPUT_DIR, "INPUT")
        input_path = str(cfg.INPUT_DIR).replace("_", r"\_")
        st.markdown(f":blue[:small[{input_path}]]", wrap=False)
        _render_folder_preview(cfg.INPUT_DIR, "INPUT", accent="red", border=False)
    with st.container(border=True):
        output_text, output_icon = st.columns([3.5, 1.5], vertical_alignment="center")
        with output_text:
            st.markdown("## :material/output: :green[OUTPUT]")
            if st.button(
                "Export",
                key="export_output_files",
                icon=":material/drive_folder_upload:",
                help="Choisit un dossier et y copie les fichiers d’OUTPUT.",
                type="secondary",
                width="content",
            ):
                try:
                    export_folder = _select_export_folder(cfg.OUTPUT_DIR)
                    copied_count = (
                        _export_output_files(cfg.OUTPUT_DIR, export_folder)
                        if export_folder is not None
                        else 0
                    )
                except (OSError, RuntimeError, ValueError) as exc:
                    st.error(f"Impossible d’exporter les fichiers : {exc}")
                else:
                    if export_folder is not None:
                        st.success(
                            f"{copied_count} fichier(s) exporté(s) vers "
                            f"{export_folder}."
                        )
            if st.button(
                "❌ :red[Clear]",
                key="clear_output_folder",
                help="Supprime tout le contenu sauf le fichier .gitkeep.",
                type="secondary",
                width="content",
            ):
                try:
                    deleted_count = _clear_folder_content(cfg.OUTPUT_DIR)
                except OSError as exc:
                    st.error(f"Impossible de vider OUTPUT : {exc}")
                else:
                    st.success(f"OUTPUT vidé ({deleted_count} élément(s)).")
        with output_icon:
            _folder_open_icon("output", cfg.OUTPUT_DIR, "OUTPUT")
        output_path = str(cfg.OUTPUT_DIR).replace("_", r"\_")
        st.markdown(f":green[:small[{output_path}]]", wrap=False)
        _render_folder_preview(
            cfg.OUTPUT_DIR, "OUTPUT", accent="green", border=False
        )
def main() -> None:
    """Build the Streamlit navigation and the selected category view."""
    # Configure the page before creating any Streamlit element.
    st.set_page_config(page_title="toolbox_pb", page_icon="🧰", layout="wide")
    cfg = APP_CONFIG

    # The sidebar contains navigation, folder shortcuts, diagnostics and the
    # legacy CLI entry point. Its settings are stored per browser session.
    with st.sidebar:

        # Store the selected category in session state so it survives reruns.
        st.code(
            """*************************
*        toolbox       *
*                      *
*    PPPPP    BBBBB    *
*    P   P    B   B    *
*    PPPPP    BBBBB    *
*    P        B   B    *
*    P        BBBBB    *
*                      *
************************""",
            language=None,
        )
        st.caption("Outils de traitement multimédia")

        # Default to the video tools when a browser opens the app for the first
        # time, then preserve the selected category across Streamlit reruns.
        if "selected_category" not in st.session_state:
            st.session_state.selected_category = "Vidéo"
        for category_name, icon_path in CATEGORY_ICONS.items():
            icon_column, button_column = st.columns(
                [1.5, 3.5], vertical_alignment="center"
            )
            with icon_column:
                if icon_path is None:
                    st.markdown(":material/language:")
                else:
                    st.image(
                        icon_path,
                        width=56,
                        alt=f"Catégorie {category_name}",
                    )
            with button_column:
                if st.button(
                    category_name,
                    key=f"category_{category_name}",
                    type=(
                        "primary"
                        if st.session_state.selected_category == category_name
                        else "secondary"
                    ),
                    use_container_width=False,
                ):
                    st.session_state.selected_category = category_name
        category = st.session_state.selected_category
        st.divider()

        # Folder buttons live in their own fragment so clicking one does not
        # rerun or visually reset a treatment in the main page.
        _render_folder_shortcuts(cfg)
        st.divider()
        with st.expander("Diagnostic", expanded=False):
            # The launch timestamp is set once per browser session.
            st.code(_startup_report(), language="text")
            st.caption("Versions Python, bibliothèques et outils externes")
            st.code(_environment_report(), language="text")
            st.html(
                """
                <style>
                .st-key-session_flags [data-testid="stCheckbox"] label p {
                    font-size: 0.875rem;
                }
                </style>
                """
            )
            with st.container(key="session_flags", gap="xsmall"):
                st.caption("Flags de cette session")
                for flag in SESSION_FLAGS:
                    if f"flag_{flag}" not in st.session_state:
                        st.session_state[f"flag_{flag}"] = getattr(
                            APP_CONFIG, flag
                        )
                    st.checkbox(flag, key=f"flag_{flag}")
            for value in SESSION_VALUES:
                if f"value_{value}" not in st.session_state:
                    st.session_state[f"value_{value}"] = getattr(
                        APP_CONFIG, value
                    )
                st.number_input(
                    value,
                    min_value=1,
                    step=1,
                    key=f"value_{value}",
                )
            if "value_LOG_LEVEL" not in st.session_state:
                st.session_state.value_LOG_LEVEL = APP_CONFIG.LOG_LEVEL
            st.selectbox(
                "Niveau de journalisation",
                LOG_LEVELS,
                key="value_LOG_LEVEL",
                help=(
                    "DEBUG enregistre les diagnostics détaillés ; INFO "
                    "convient "
                    "à l’usage courant."
                ),
            )
        st.divider()
        # Keep the legacy CLI shortcut at the bottom of the sidebar.
        with st.container(border=True):
            image_column, button_column = st.columns(
                [1, 2], vertical_alignment="center"
            )
            with image_column:
                st.image(LEGACY_CLI_LOGO, width=200)
            with button_column:
                if st.button(
                    "À l’ancienne",
                    key="launch_cli",
                    use_container_width=True,
                    help=(
                        "Ouvre le menu interactif historique dans une "
                        "nouvelle "
                        "fenêtre de commande."
                    ),
                ):
                    _launch_cli()

    # Rebuild the configuration from sidebar values before invoking a tool.
    # This keeps global defaults immutable and session settings isolated.
    cfg = _runtime_config()
    st.title(category)
    st.caption(
        "Dépliez une sous-catégorie pour voir son fonctionnement et la "
        "lancer. "
        "Les fichiers source ne sont pas modifiés."
    )

    # Each category owns its cards; selecting one renders only its controls.
    renderers: dict[str, Callable[[AppConfig], None]] = {
        "Vidéo": _category_video,
        "Image": _category_image,
        "Audio": _category_audio,
        "PDF": _category_pdf,
        "Fichier": _category_file,
        "Web": _category_web,
    }
    renderers[category](cfg)


if __name__ == "__main__":
    main()

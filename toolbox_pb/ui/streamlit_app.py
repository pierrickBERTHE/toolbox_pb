"""Interface Streamlit de la toolbox_pb.

L'application pilote les traitements existants sans dupliquer leur logique :
les fichiers restent lus depuis ``data/input`` et les résultats sont écrits
dans ``data/output``.
"""

from __future__ import annotations

import io
import logging
from queue import Empty, Queue
import subprocess
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

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parents[1]
IMAGE_EXAMPLE_DIR = PROJECT_DIR / "image" / "examples"
FOCUS_EXPLORER_SCRIPT = PACKAGE_DIR / "focus_explorer.ps1"

from toolbox_pb.core.audio.main_audio import audio_compressor
import toolbox_pb.core.func_global as func_global_module
from toolbox_pb.core.config_global import APP_CONFIG, AppConfig, LOG_LEVELS
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
from toolbox_pb.core.video.func_video import find_files_by_extensions
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
)
from toolbox_pb.ui.reductor_workflow import _run_complementary_reductor


ToolRunner = Callable[[], bool | None]
CATEGORY_ICON_DIR = PROJECT_DIR / "image" / "icons" / "categories"
TOOL_ICON_DIR = PROJECT_DIR / "image" / "icons" / "tools"
# Artwork displayed next to the shortcut that opens the historical CLI.
LEGACY_CLI_LOGO = PROJECT_DIR / "image" / "legacy" / "logo_a_l'ancienne.png"
# Boolean settings exposed as per-browser-session controls in the sidebar.
SESSION_FLAGS = (
    "LOG_TO_FILE",
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

    def write(self, text: str) -> int:
        written = super().write(text)
        if text:
            self.job.events.put(("log", text))
        return written


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
        logging.getLogger("toolbox_pb").exception(
            "Le traitement %s a échoué.", job.tool_name
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
            job.status = "done"
            job.is_empty_folder = bool(payload)
            job.output += f"Traitement terminé : {job.tool_name}\n"
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


@st.fragment(run_every="0.5s")
def _render_active_treatment() -> None:
    """Refresh the active treatment without blocking the other controls."""
    job = st.session_state.get("active_treatment")
    if not isinstance(job, TreatmentJob):
        return
    _drain_treatment_events(job)

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


def _run_tool(tool_name: str, runner: ToolRunner) -> None:
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
    job = TreatmentJob(tool_name=tool_name)
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


def _open_in_file_explorer(path: Path, label: str) -> None:
    """Open a configured folder and focus its Explorer window on Windows."""
    if not path.is_dir():
        st.error(f"Le dossier {label.lower()} n’existe pas : {path}")
        return
    try:
        # The helper waits briefly for the new Explorer window in order to
        # bring it forward.  Do not wait for that cosmetic step from the UI:
        # Explorer itself is launched immediately and the Streamlit rerun must
        # remain responsive.
        subprocess.Popen(
            (
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-WindowStyle",
                "Hidden",
                "-File",
                str(FOCUS_EXPLORER_SCRIPT),
                str(path.resolve()),
            ),
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        st.error(f"Impossible d’ouvrir le dossier {label.lower()} : {exc}")


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
    input_required: bool = False,
) -> None:
    """Render one expandable sub-category and its action button."""
    expanded_key = f"{key}_expanded"
    is_expanded = st.session_state.get(expanded_key, False)
    header_icon_column, header_button_column = st.columns(
        [2.1, 7.9], gap=None, vertical_alignment="center"
    )
    with header_icon_column:
        st.image(_tool_icon(key), width=208)
    with header_button_column:
        marker = "▾" if is_expanded else "▸"
        label = f"{marker} {TOOL_NUMBERS[title]}. {title}"
        if st.button(label, key=f"{key}_toggle", use_container_width=True):
            st.session_state[expanded_key] = not is_expanded

    if not st.session_state.get(expanded_key, False):
        return

    with st.container(border=True):
        st.write(description)
        before_column, after_column = st.columns(2)
        with before_column:
            with st.container(border=True):
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
                st.image(icon_path, width=56)
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

        # Show the configured paths separately from the open-folder controls
        # so long Windows paths remain readable in the narrow sidebar.
        # Keep labels and their long filesystem paths separate for readability.
        st.markdown(":green[**Entrée**]")
        st.markdown(
            (
                "<span style='color: #2e8b57; font-size: 0.6rem;'>"
                f"{escape(str(cfg.INPUT_DIR))}</span>"
            ),
            unsafe_allow_html=True,
        )
        if st.button(
            "Ouvrir le dossier d’entrée",
            key="open_input",
            use_container_width=True,
        ):
            _open_in_file_explorer(cfg.INPUT_DIR, "d’entrée")
        st.markdown(":blue[**Sortie**]")
        st.markdown(
            (
                "<span style='color: #1e90ff; font-size: 0.6rem;'>"
                f"{escape(str(cfg.OUTPUT_DIR))}</span>"
            ),
            unsafe_allow_html=True,
        )
        if st.button(
            "Ouvrir le dossier de sortie",
            key="open_output",
            use_container_width=True,
        ):
            _open_in_file_explorer(cfg.OUTPUT_DIR, "de sortie")
        st.divider()
        with st.expander("Diagnostic", expanded=False):
            # The launch timestamp is set once per browser session.
            st.code(_startup_report(), language="text")
            st.caption("Versions Python, bibliothèques et outils externes")
            st.code(_environment_report(), language="text")
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
    }
    renderers[category](cfg)


if __name__ == "__main__":
    main()

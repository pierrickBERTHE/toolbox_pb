"""Interface Streamlit de la toolbox_pb.

L'application pilote les traitements existants sans dupliquer leur logique :
les fichiers restent lus depuis ``data/input`` et les résultats sont écrits
dans ``data/output``.
"""

from __future__ import annotations

import io
import os
import subprocess
import traceback
from contextvars import ContextVar
from datetime import datetime
from contextlib import contextmanager, redirect_stdout
from dataclasses import replace
from html import escape
from pathlib import Path
from time import perf_counter
from typing import Callable, Iterator

import streamlit as st

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parents[1]

from toolbox_pb.core.audio.main_audio import audio_compressor
import toolbox_pb.core.func_global as func_global_module
from toolbox_pb.core.config_global import APP_CONFIG, AppConfig
from toolbox_pb.core.events import use_message_sink
from toolbox_pb.core.progress import use_progress_factory
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
from toolbox_pb.core.pdf.main_pdf import pdf_assemblor, pdf_filigranor, pdf_page_alternator
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


ToolRunner = Callable[[], bool | None]
ACTIVE_PROGRESS_PANEL: ContextVar[object | None] = ContextVar(
    "active_progress_panel", default=None
)
CATEGORY_ICON_DIR = PROJECT_DIR / "image" / "icons" / "categories"
TOOL_ICON_DIR = PROJECT_DIR / "image" / "icons" / "tools"
# Artwork displayed next to the shortcut that opens the historical CLI.
LEGACY_CLI_LOGO = PROJECT_DIR / "image" / "legacy" / "logo_a_l'ancienne.png"
# Boolean settings exposed as per-browser-session controls in the sidebar.
SESSION_FLAGS = (
    "LOG_TO_FILE",
    "ADD_CODEC_NAME_IN_OUTPUT",
    "PRINT_ALL_KEYS_IN_METADATA_SUMMARY",
    "ADD_WITHOUTBG_IN_NAME_IN_OUTPUT",
    "ADD_COMPRESS_TO_IMAGE_NAME_IN_OUTPUT",
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


class StreamlitProgressSlots:
    """Keep the current and overall progress bars in stable UI locations."""

    def __init__(self, progress_panel: object) -> None:
        # ``st.empty()`` replaces its previous child.  Two dedicated slots let
        # nested tqdm bars coexist instead of the most recently-created one
        # replacing the other.
        self._current = progress_panel.empty()
        self._overall = progress_panel.empty()

    def target_for(self, position: int | None) -> object:
        """Return the slot matching the tqdm position used by the core code."""
        return self._overall if position == 1 else self._current


class StreamlitProgressBar:
    """Render a Streamlit progress bar whose percentage is overlaid on it."""

    def __init__(self, target: object) -> None:
        self._target = target

    def progress(self, value: int, *, text: str) -> "StreamlitProgressBar":
        """Update the bar while keeping its percentage visible in the fill area."""
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
                style="position: relative; height: 1.25rem; overflow: hidden;
                       border-radius: 0.625rem; background: rgba(128, 128, 128, 0.25);"
              >
                <div style="width: {percent}%; height: 100%; background: var(--primary-color, #ff4b4b);"></div>
                <span style="position: absolute; inset: 0; display: flex; align-items: center;
                             justify-content: center; color: #111; font-size: 0.75rem;
                             font-weight: 700; text-shadow: 0 0 2px #fff;">
                  {percent} %
                </span>
              </div>
              <div style="margin-top: 0.25rem; font-size: 0.875rem;">{safe_text}</div>
            </div>
            """,
        )
        return self


class StreamlitTqdm:
    """Small ``tqdm`` replacement that reports progress in Streamlit."""

    def __init__(
        self,
        iterable=None,
        total: float | None = None,
        desc: str | None = None,
        unit: str = "élément",
        position: int | None = None,
        **_: object,
    ) -> None:
        self.iterable = iterable
        self.total = total if total is not None else self._get_length(iterable)
        self.n = 0.0
        self.desc = desc or "Traitement"
        self.unit = unit
        self.started_at = perf_counter()
        # A tool run supplies its output tile; fall back to the page otherwise.
        progress_target = ACTIVE_PROGRESS_PANEL.get() or st
        if isinstance(progress_target, StreamlitProgressSlots):
            progress_target = progress_target.target_for(position)
        self._progress = StreamlitProgressBar(progress_target)
        self._progress.progress(0, text=self._label())

    @staticmethod
    def _get_length(iterable) -> int | None:
        try:
            return len(iterable)
        except TypeError:
            return None

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format a duration as a compact, readable time value."""
        seconds = max(0, int(seconds))
        hours, remainder = divmod(seconds, 3_600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def _label(self) -> str:
        """Build a TQDM-like label with elapsed and estimated remaining time."""
        elapsed = perf_counter() - self.started_at
        if self.total:
            completed = min(self.n, self.total)
            percent = min(completed / self.total * 100, 100)
            remaining = elapsed * (self.total - completed) / completed if completed else None
            remaining_text = self._format_duration(remaining) if remaining is not None else "calcul…"
            return (
                f"{self.desc} : {percent:.0f} % — fichier {completed:.0f}/{self.total:.0f} "
                f"— écoulé : {self._format_duration(elapsed)} "
                f"— temps restant estimé : {remaining_text}"
            )
        return f"{self.desc} : {self.n:.0f} {self.unit} — écoulé : {self._format_duration(elapsed)}"

    def update(self, increment: float = 1) -> None:
        self.n += increment
        if self.total:
            percent = min(int(self.n / self.total * 100), 100)
        else:
            percent = 0
        self._progress.progress(percent, text=self._label())

    def __iter__(self):
        if self.iterable is None:
            return iter(())
        for item in self.iterable:
            yield item
            self.update()

    def __enter__(self) -> "StreamlitTqdm":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self.total and self.n >= self.total:
            self._progress.progress(100, text=self._label())


@contextmanager
def _streamlit_progress_bars(progress_panel: StreamlitProgressSlots) -> Iterator[None]:
    """Route core progress events into the current treatment output tile."""
    panel_token = ACTIVE_PROGRESS_PANEL.set(progress_panel)
    try:
        with use_progress_factory(StreamlitTqdm):
            yield
    finally:
        ACTIVE_PROGRESS_PANEL.reset(panel_token)


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
        value: st.session_state.get(f"value_{value}", getattr(APP_CONFIG, value))
        for value in SESSION_VALUES
    })
    return replace(APP_CONFIG, **overrides)


def _startup_report() -> str:
    """Return the CLI-equivalent code version and session launch time."""
    if "code_launch_time" not in st.session_state:
        st.session_state.code_launch_time = datetime.now().isoformat()
    version = func_global_module.format_git_version(func_global_module.get_git_version())
    return f"{version}\n\nCode lancé le : {st.session_state.code_launch_time}"


class StreamlitLog(io.StringIO):
    """Capture ``print`` output and redraw it immediately in a code panel."""

    def __init__(self, output_panel) -> None:
        super().__init__()
        self.output_panel = output_panel

    def write(self, text: str) -> int:
        written = super().write(text)
        if text:
            self.output_panel.code(self.getvalue(), language="text")
        return written


def _run_tool(tool_name: str, runner: ToolRunner) -> None:
    """Execute a legacy tool and show its console output in the interface."""
    st.caption("Sortie du traitement")
    output_panel = st.empty()
    progress_panel = StreamlitProgressSlots(st.container())
    log = StreamlitLog(output_panel)
    output_panel.code("Préparation du traitement…", language="text")
    try:
        with (
            st.spinner(f"Traitement en cours : {tool_name}…"),
            redirect_stdout(log),
            use_message_sink(log.write),
            _streamlit_progress_bars(progress_panel),
        ):
            is_empty_folder = runner()
    except Exception as exc:  # The full trace helps diagnose external tool errors.
        output = log.getvalue().strip()
        _append_to_log(tool_name, output, traceback.format_exc())
        st.error(f"Le traitement « {tool_name} » a échoué : {exc}")
        st.code(output + "\n" + traceback.format_exc(), language="text")
        return

    if is_empty_folder:
        st.warning("Aucun fichier compatible n'a été trouvé dans le dossier d'entrée.")
    else:
        st.success(f"{tool_name} terminé.")
    output = log.getvalue().strip()
    _append_to_log(tool_name, output)


def _append_to_log(tool_name: str, output: str, error: str = "") -> None:
    """Append the Streamlit-captured output to the historical log file."""
    if not st.session_state.get("flag_LOG_TO_FILE", APP_CONFIG.LOG_TO_FILE):
        return

    APP_CONFIG.LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = APP_CONFIG.LOG_DIR / "process_log.txt"
    entry = f"\n{'=' * 72}\n{datetime.now():%Y-%m-%d %H:%M:%S} — {tool_name}\n"
    if output:
        entry += f"{output}\n"
    if error:
        entry += f"ERREUR\n{error}\n"
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(entry)


def _open_in_file_explorer(path: Path, label: str) -> None:
    """Open a configured local folder in Windows File Explorer."""
    if not path.is_dir():
        st.error(f"Le dossier {label.lower()} n’existe pas : {path}")
        return
    try:
        os.startfile(path)  # type: ignore[attr-defined]  # Windows only.
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
    input_label: str | None = None,
    input_help: str | None = None,
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
                st.write(before_example)
        with after_column:
            with st.container(border=True):
                st.markdown("#### Après")
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
                value = st.text_input(input_label, key=f"{key}_value", help=input_help)
        if st.button(f"Lancer {title}", key=f"{key}_run", type="primary"):
            if input_required and (value is None or not str(value).strip()):
                st.warning(f"Renseignez « {input_label} » avant de lancer ce traitement.")
            else:
                _run_tool(title, runner if value is None else lambda: runner(value))


def _category_video(cfg: AppConfig) -> None:
    _tool_card("video_encodor", "Réencode chaque vidéo du dossier d’entrée avec les codecs configurés, compare les tailles avant/après et conserve une trace du traitement dans le MP4 de sortie.", "`vacances.mov` — 2 Go", "Une copie MP4 réencodée — par exemple 700 Mo", lambda: video_encodor(cfg), key="video_encode")
    _tool_card("video_assemblor", "Assemble plusieurs vidéos en un seul fichier. Si `data/segment/segments.csv` existe, il définit l’ordre des clips et leurs points de début et de fin ; sinon, les vidéos sont assemblées selon leurs noms.", "`clip-01.mp4`, `clip-02.mp4`, `clip-03.mp4`", "Une seule vidéo : `assembled...mp4`", lambda: video_assemblor(cfg), key="video_assemble")
    _tool_card("video_audio_decalator", "Avance ou retarde la piste audio d’une vidéo sans réencoder son flux vidéo.", "Une vidéo dont la voix arrive 0,5 seconde trop tard", "La même vidéo, avec la voix de nouveau synchronisée", lambda delay=0.0: video_audio_decalator(cfg, delay), key="video_audio_offset", input_label="Délai de décalage audio (secondes)", input_help="Exemple : -0,5 pour avancer de 0,5 s ; 0,5 pour retarder de 0,5 s.", input_type="number")
    _tool_card("video_volume_adjust", "Applique des variations de volume audio sur les plages temporelles définies dans `data/segment/boosts.csv`, sans réencoder le flux vidéo.", "Un passage de 00:01:00 à 00:01:30 au volume normal", "Ce passage gagne le volume défini dans `boosts.csv`", lambda: video_volume_adjust(cfg), key="video_volume")
    _tool_card("video_srt_extractor", "Extrait la piste de sous-titres intégrée à chaque vidéo vers un fichier `.srt` et crée une copie de la vidéo sans cette piste, sans réencoder l’audio ni la vidéo.", "`interview.mp4` avec des sous-titres intégrés", "`interview.srt` et une copie MP4 sans piste de sous-titres", lambda: video_srt_extractor(cfg), key="video_srt_extract")
    _tool_card("video_srt_integrator", "Intègre `data/segment/sous_titre.srt` comme piste de sous-titres MP4 aux vidéos, sans réencoder l’audio ou la vidéo.", "`film.mp4` et `sous_titre.srt` séparés", "Un MP4 où le lecteur peut activer ou désactiver les sous-titres", lambda: video_srt_integrator(cfg), key="video_srt_integrate")
    _tool_card("video_srt_date_filtrator", "Filtre les fichiers SRT ou TXT afin de ne conserver que la première occurrence de chaque date, avec un bilan avant et après traitement.", "Trois sous-titres contenant « 12/05/2024 »", "Seule la première apparition de « 12/05/2024 » est conservée", lambda: video_srt_date_filtrator(cfg), key="video_srt_filter")
    _tool_card("video_ass_hard_integrator", "Convertit automatiquement les fichiers SRT en ASS, puis incruste les sous-titres de façon permanente dans les vidéos.", "`film.mp4` et ses sous-titres SRT séparés", "Une vidéo où les sous-titres sont inscrits dans l’image", lambda: video_ass_hard_integrator(cfg), key="video_ass")


def _category_image(cfg: AppConfig) -> None:
    _tool_card("image_defilor", "Génère une vidéo verticale défilante pour chaque image source et, pour les PDF, une vidéo par image extraite de chaque page. La hauteur, la vitesse, le FPS et les temps d’arrêt sont paramétrables.", "Une photo panoramique fixe", "Une vidéo verticale qui fait défiler la photo", lambda extra_args="": image_defilor(cfg, extra_args or None), key="image_defilor", input_label="Options ImageMagick (facultatif)", input_help="Exemple : --height 720 --speed 50")
    _tool_card("image_reductor", "Réduit les photos JPEG et PNG sans changer leur format ni leurs dimensions. Les JPEG sont réencodés avec la qualité configurée et les PNG sont optimisés sans perte.", "`photo.jpg` — 8 Mo", "La même image et les mêmes dimensions — par exemple 2 Mo", lambda: image_reductor(cfg), key="image_reduce")
    _tool_card("image_diapo_video_creator", "Assemble toutes les photos du dossier d’entrée dans une vidéo. Une piste audio unique peut être ajoutée et les noms des photos sont intégrés comme sous-titres.", "50 photos de voyage", "Une vidéo MP4 présentant chaque photo pendant la durée configurée", lambda: image_diapo_video_creator(cfg), key="image_diapo")
    _tool_card("image_withoutbg", "Supprime l’arrière-plan de chaque image source et génère un PNG transparent en conservant l’arborescence des sous-dossiers.", "Une photo d’objet sur fond blanc", "Un PNG transparent ne gardant que l’objet", lambda: image_withoutbg(cfg), key="image_withoutbg")


def _category_audio(cfg: AppConfig) -> None:
    _tool_card("audio_compressor", "Convertit les fichiers audio acceptés en MP3 au débit configuré. Les MP3 déjà à un débit inférieur ou égal sont copiés intacts, sans réencodage.", "`concert.flac`", "`concert.mp3` au débit configuré ; un MP3 déjà compressé est simplement copié", lambda: audio_compressor(cfg), key="audio_compress")


def _category_pdf(cfg: AppConfig) -> None:
    _tool_card("pdf_filigranor", "Ajoute à chaque PDF un filigrane textuel diagonal répété. Le préfixe configuré est ajouté automatiquement au destinataire saisi.", "Un PDF sans filigrane et le destinataire « Alice »", "Chaque page porte le texte diagonal « document exclusivement destiné à Alice »", lambda recipient="": pdf_filigranor(cfg, recipient), key="pdf_watermark", input_label="Destinataire du filigrane", input_required=True)
    _tool_card("pdf_assemblor", "Fusionne tous les PDF du dossier d’entrée et de ses sous-dossiers en un unique fichier, dans l’ordre alphabétique de leurs chemins relatifs.", "`01-couverture.pdf`, `02-contrat.pdf`, `03-annexe.pdf`", "Un seul PDF contenant ces documents dans le même ordre", lambda: pdf_assemblor(cfg), key="pdf_assemble")
    _tool_card("pdf_page_alternator", "Alterne les pages de `impaire.pdf` et `paire.pdf` placés dans le dossier d’entrée, en commençant par le fichier impair.", "Un PDF avec les pages 1, 3, 5 et un autre avec les pages 2, 4, 6", "Un PDF aux pages dans l’ordre normal : 1, 2, 3, 4, 5, 6", lambda: pdf_page_alternator(cfg), key="pdf_alternate")


def _category_file(cfg: AppConfig) -> None:
    _tool_card("file_timeline_sorter", "Copie les fichiers vers le dossier de sortie en préfixant leur date de dernière modification afin que le tri alphabétique corresponde à l’ordre chronologique.", "`photo.jpg`, modifiée le 6 mars 2026 à 14:30", "`2026-03-06_14-30-00__photo.jpg`", lambda: file_timeline_sorter(cfg), key="file_timeline")
    _tool_card("file_str_remover", "Copie les fichiers vers le dossier de sortie en supprimant la chaîne indiquée de leurs noms. Les fichiers source restent intacts.", "`rapport-copie.pdf` avec `-copie` comme texte à supprimer", "`rapport.pdf` dans le dossier de sortie", lambda text="": file_str_remover(cfg, text), key="file_remove_text", input_label="Chaîne à supprimer", input_required=True)
    _tool_card("folder_date_renammer", "Copie les dossiers présents dans `data/input` et renomme ceux qui contiennent une date française valide au format `AAMMJJ-titre`.", "`15 août 2024 - Vacances`", "`240815-Vacances` dans le dossier de sortie", lambda: folder_date_renammer(cfg), key="folder_date")
    _tool_card("cache_nettoyor", "Affiche l’espace occupé avant et après nettoyage, puis vide les caches locaux configurés de Poetry, npm, Windows, Office, Chrome, Teams et Firefox.", "4,2 Go de caches locaux", "La taille restante et l’espace effectivement libéré sont affichés", cache_nettoyor, key="cache_clean")


def main() -> None:
    """Build the Streamlit navigation and the selected category view."""
    st.set_page_config(page_title="toolbox_pb", page_icon="🧰", layout="wide")
    cfg = APP_CONFIG

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
        if "selected_category" not in st.session_state:
            st.session_state.selected_category = "Vidéo"
        for category_name, icon_path in CATEGORY_ICONS.items():
            icon_column, button_column = st.columns([1.5, 3.5], vertical_alignment="center")
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
        # Keep labels and their long filesystem paths separate for readability.
        st.markdown(":green[**Entrée**]")
        st.markdown(
            f"<span style='color: #2e8b57; font-size: 0.6rem;'>{escape(str(cfg.INPUT_DIR))}</span>",
            unsafe_allow_html=True,
        )
        if st.button("Ouvrir le dossier d’entrée", key="open_input", use_container_width=True):
            _open_in_file_explorer(cfg.INPUT_DIR, "d’entrée")
        st.markdown(":blue[**Sortie**]")
        st.markdown(
            f"<span style='color: #1e90ff; font-size: 0.6rem;'>{escape(str(cfg.OUTPUT_DIR))}</span>",
            unsafe_allow_html=True,
        )
        if st.button("Ouvrir le dossier de sortie", key="open_output", use_container_width=True):
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
                    st.session_state[f"flag_{flag}"] = getattr(APP_CONFIG, flag)
                st.checkbox(flag, key=f"flag_{flag}")
            for value in SESSION_VALUES:
                if f"value_{value}" not in st.session_state:
                    st.session_state[f"value_{value}"] = getattr(APP_CONFIG, value)
                st.number_input(value, min_value=1, step=1, key=f"value_{value}")
        st.divider()
        # Keep the legacy CLI shortcut at the bottom of the sidebar.
        with st.container(border=True):
            image_column, button_column = st.columns([1, 2], vertical_alignment="center")
            with image_column:
                st.image(LEGACY_CLI_LOGO, width=200)
            with button_column:
                if st.button(
                    "À l’ancienne",
                    key="launch_cli",
                    use_container_width=True,
                    help="Ouvre le menu interactif historique dans une nouvelle fenêtre de commande.",
                ):
                    _launch_cli()

    cfg = _runtime_config()
    st.title(category)
    st.caption("Dépliez une sous-catégorie pour voir son fonctionnement et la lancer. Les fichiers source ne sont pas modifiés.")

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

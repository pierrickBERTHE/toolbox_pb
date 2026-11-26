"""NiceGUI front end for toolbox_pb.

This is the primary graphical interface. It reuses the existing processing
modules and workspace directories without moving or duplicating business
logic. Start it with ``poetry run python -m toolbox_pb.ui.nicegui_app``.
"""

from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import dataclass, field, replace
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
from typing import Any, Callable
import io
import os
import re
import shutil
import subprocess
import traceback
from datetime import datetime
from time import perf_counter

from nicegui import ui

import toolbox_pb.core.func_global as func_global_module
from toolbox_pb.core.audio.main_audio import audio_compressor
from toolbox_pb.core.cancellation import (
    ProcessingCancelled,
    raise_if_cancelled,
    use_cancellation_event,
)
from toolbox_pb.core.config_global import (
    APP_CONFIG,
    AppConfig,
    IMAGE_EXAMPLE_DIR,
    PROJECT_DIR,
)
from toolbox_pb.core.events import configure_file_logging, use_message_sink
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
from toolbox_pb.core.progress import use_progress_factory
from toolbox_pb.core.video.func_video import find_files_by_extensions
from toolbox_pb.core.video.main_video import (
    image_diapo_video_creator,
    video_ass_hard_integrator,
    video_assemblor,
    video_audio_decalator,
    video_encodor,
    video_rotator,
    video_srt_date_filtrator,
    video_srt_extractor,
    video_srt_integrator,
    video_volume_adjust,
)
from toolbox_pb.core.web.main_web import (
    MP3_BITRATES,
    VIDEO_QUALITIES,
    YouTubeDownloadOptions,
)
from toolbox_pb.ui.youtube_workflow import run_youtube_download


# Keep all presentation details in this file; the processing package is untouched.
# ToolSpec is the thin UI-to-core adapter shared by every category card.
CATEGORY_ICONS = {
    "Vidéo": "video.png",
    "Image": "image.png",
    "Audio": "audio.png",
    "PDF": "pdf.png",
    "Fichier": "file.png",
    "Web": "web.png",
}
ICON_DIR = PROJECT_DIR / "image" / "icons"
# The tool artwork lives in ``image/icons/tools``; its file names match
# ``ToolSpec.key`` (e.g. ``video_encode.png``).
TOOL_ICON_DIR = ICON_DIR / "tools"
CATEGORY_ICON_DIR = ICON_DIR / "categories"
FOLDER_ICON_DIR = ICON_DIR / "folders"
LEGACY_CLI_LOGO = PROJECT_DIR / "image" / "legacy" / "logo_a_l'ancienne.png"
NOTEPAD_PLUS_PLUS_ICON = ICON_DIR / "notepad_plus_plus.png"
NOTEPAD_PLUS_PLUS_PATHS = (
    Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    / "Notepad++"
    / "notepad++.exe",
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    / "Notepad++"
    / "notepad++.exe",
)
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
SESSION_VALUES = ("AUDIO_COMPRESSOR_MP3_BITRATE_KBPS",)
COMMON_SESSION_FLAGS = {
    "LOG_TO_FILE",
    "OPEN_OUTPUT_DIR_AFTER_TREATMENT",
}
CATEGORY_SESSION_FLAGS = {
    "Vidéo": {
        "ADD_CODEC_NAME_IN_OUTPUT",
        "VIDEO_ENCODOR_PRINT_ALL_KEYS_IN_METADATA_SUMMARY",
        "VIDEO_ASSEMBLOR_ADD_DATE_SUBTITLES",
        "VIDEO_ASSEMBLOR_EXTRACT_AND_FILTER_DATES",
        # Video_encodor can launch Image_reductor as a complementary action.
        "IMAGE_REDUCTOR_ADD_COMPRESS_TO_IMAGE_NAME_IN_OUTPUT",
    },
    "Image": {
        "IMAGE_WITHOUTBG_ADD_WITHOUTBG_IN_NAME_IN_OUTPUT",
        "IMAGE_REDUCTOR_ADD_COMPRESS_TO_IMAGE_NAME_IN_OUTPUT",
    },
    "Audio": {"AUDIO_COMPRESSOR_COPY_JPEG_FILES"},
    "PDF": set(),
    "Fichier": set(),
    "Web": set(),
}


@dataclass(frozen=True)
class ToolSpec:
    category: str
    title: str
    key: str
    description: str
    before: str
    after: str
    runner: Callable[[AppConfig, Any], object]
    input_label: str | None = None
    input_kind: str = "text"
    options: tuple[Any, ...] = ()
    required: bool = False
    before_image: Path | None = None
    after_image: Path | None = None


TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        "Vidéo",
        "video_encodor",
        "video_encode",
        "Réencode les vidéos du dossier INPUT et conserve les sources intactes.",
        """`vacances.mov` — 2 Go

- Codec vidéo : aucun
- Codec audio : AAC""",
        """`vacances.mov` — 700 Mo

- Codec vidéo : H.265
- Codec audio : AAC (inchangé)""",
        lambda c, _: _run_video_encodor_with_image_reductor(c),
        before_image=IMAGE_EXAMPLE_DIR / "video_encodor_before.gif",
        after_image=IMAGE_EXAMPLE_DIR / "video_encodor_after.gif",
    ),
    ToolSpec(
        "Vidéo",
        "video_assemblor",
        "video_assemble",
        "Assemble les clips vidéo dans l’ordre des noms ou de segments.csv.",
        """3 fichiers :

- `clip-01.mp4` — 00:00:08
- `clip-02.mp4` — 00:00:12
- `clip-03.mp4` — 00:00:10""",
        """1 fichier :

`assembled.mp4`

- Durée : 00:00:30
- Clips : assemblés dans l'ordre alphabétique""",
        lambda c, _: video_assemblor(c),
        before_image=IMAGE_EXAMPLE_DIR / "video_assemblor_before.gif",
        after_image=IMAGE_EXAMPLE_DIR / "video_assemblor_after.gif",
    ),
    ToolSpec(
        "Vidéo",
        "video_audio_decalator",
        "video_audio_offset",
        "Avance ou retarde la piste audio sans réencoder la vidéo.",
        """`video.mp4`

- Décalage audio : +0,5 s
- État : voix en retard""",
        """`video.mp4`

- Correction : −0,5 s
- État : voix synchronisée""",
        lambda c, v: video_audio_decalator(c, float(v)),
        "Délai de décalage audio (secondes)",
        "number",
        before_image=IMAGE_EXAMPLE_DIR / "video_audio_decalator_before.gif",
        after_image=IMAGE_EXAMPLE_DIR / "video_audio_decalator_after.gif",
    ),
    ToolSpec(
        "Vidéo",
        "video_volume_adjust",
        "video_volume",
        "Applique les règles de volume de data/segment/boosts.csv.",
        """`video.mp4`

- Plage : 00:01:00 → 00:01:30
- Volume : niveau initial""",
        """`video.mp4`

- Plage : 00:01:00 → 00:01:30
- Volume : Gain selon `boosts.csv` appliquée""",
        lambda c, _: video_volume_adjust(c),
        before_image=IMAGE_EXAMPLE_DIR / "video_volume_before.gif",
        after_image=IMAGE_EXAMPLE_DIR / "video_volume_after.gif",
    ),
    ToolSpec(
        "Vidéo",
        "video_srt_extractor",
        "video_srt_extract",
        "Extrait les sous-titres intégrés vers un fichier SRT.",
        """1 fichier :

- `interview.mp4` — vidéo avec sous-titres intégrés""",
        """2 fichiers :

- `interview.mp4` — vidéo sans piste de sous-titres
- `interview.srt` — sous-titres extraits""",
        lambda c, _: video_srt_extractor(c),
        before_image=IMAGE_EXAMPLE_DIR / "video_srt_extract_before.gif",
        after_image=IMAGE_EXAMPLE_DIR / "video_srt_extract_after.gif",
    ),
    ToolSpec(
        "Vidéo",
        "video_srt_integrator",
        "video_srt_integrate",
        "Ajoute sous_titre.srt comme piste activable dans les MP4.",
        """2 fichiers :

- `film.mp4` — vidéo source
- `sous_titre.srt` — sous-titres séparés""",
        """1 fichier :

- `film.mp4` — vidéo avec sous-titres intégrés (activable ou désactivable)""",
        lambda c, _: video_srt_integrator(c),
        before_image=IMAGE_EXAMPLE_DIR / "video_srt_integrate_before.gif",
        after_image=IMAGE_EXAMPLE_DIR / "video_srt_integrate_after.gif",
    ),
    ToolSpec(
        "Vidéo",
        "video_srt_date_filtrator",
        "video_srt_filter",
        "Ne conserve que la première occurrence de chaque date dans les SRT/TXT.",
        """`sous_titre.srt` 

— 3 occurrences de date :

- 00:00:02 — « 12/05/2024 »
- 00:00:18 — « 12/05/2024 »
- 00:00:35 — « 12/05/2024 »""",
        """`sous_titre.srt` 

— date conservée :

- 00:00:02 — « 12/05/2024 »
- 2 doublons supprimés""",
        lambda c, _: video_srt_date_filtrator(c),
    ),
    ToolSpec(
        "Vidéo",
        "video_ass_hard_integrator",
        "video_ass",
        "Incruste définitivement les sous-titres dans l’image.",
        """2 fichiers :

- `film.mp4` — vidéo source
- `sous_titre.srt` — sous-titres séparés""",
        """1 fichier :

- `film.mp4` - sous-titres visibles, non désactivables""",
        lambda c, _: video_ass_hard_integrator(c),
        before_image=IMAGE_EXAMPLE_DIR / "video_ass_before.gif",
        after_image=IMAGE_EXAMPLE_DIR / "video_ass_after.gif",
    ),
    ToolSpec(
        "Vidéo",
        "video_rotator",
        "video_rotator",
        "Pivote chaque vidéo dans le sens horaire.",
        "`portrait_mal_orienté.mp4`\n\n- Orientation : paysage\n- Image : couchée",
        "`portrait.mp4`\n\n- Rotation : 270°\n- Orientation : portrait",
        lambda c, v: video_rotator(c, str(v)),
        "Angle de rotation (90°, 180° ou 270°)",
        "select",
        (90, 180, 270),
        before_image=IMAGE_EXAMPLE_DIR / "video_rotator_before.gif",
        after_image=IMAGE_EXAMPLE_DIR / "video_rotator_after_video.gif",
    ),
    ToolSpec(
        "Image",
        "image_defilor",
        "image_defilor",
        "Transforme les images et PDF en vidéos verticales défilantes.",
        """`rapport.pdf`

- Document PDF statique
- Page de rapport à parcourir""",
        """`rapport.mp4`

- Format : vidéo verticale
- Mouvement : défilement du haut vers le bas""",
        lambda c, v: image_defilor(c, str(v) or None),
        "Options ImageMagick (facultatif)",
        before_image=IMAGE_EXAMPLE_DIR / "image_defilor_pdf_before.png",
        after_image=IMAGE_EXAMPLE_DIR / "image_defilor_pdf_after.gif",
    ),
    ToolSpec(
        "Image",
        "image_reductor",
        "image_reduce",
        "Réduit les JPEG et optimise les PNG sans modifier les sources.",
        """`photo.jpg`

- Taille : 8 Mo
- Dimensions : 4000 × 3000 px""",
        """`photo.jpg`

- Taille : 2 Mo
- Dimensions : 4000 × 3000 px (inchangées)
- Qualité JPEG : valeur configurée (75% par défaut)""",
        lambda c, _: image_reductor(c),
        before_image=IMAGE_EXAMPLE_DIR / "image_reductor_before.png",
        after_image=IMAGE_EXAMPLE_DIR / "image_reductor_after.jpg",
    ),
    ToolSpec(
        "Image",
        "image_diapo_video_creator",
        "image_diapo",
        "Crée un diaporama vidéo, avec musique et noms des photos.",
        """3 fichiers :

- `01-plage.jpg`
- `02-montagne.jpg`
- `musique.mp3`""",
        """1 fichier :

- `diaporama.mp4`

    - Photos : affichées dans l'ordre
    - Audio : `musique.mp3`
    - Sous-titres : noms des photos""",
        lambda c, _: image_diapo_video_creator(c),
        before_image=IMAGE_EXAMPLE_DIR / "image_diapo_files_before.png",
        after_image=IMAGE_EXAMPLE_DIR / "image_diapo_files_after.gif",
    ),
    ToolSpec(
        "Image",
        "image_withoutbg",
        "image_withoutbg",
        "Supprime le fond des images et produit des PNG transparents.",
        """`produit.jpg`

- Arrière-plan : blanc""",
        """`produit.png`

- Arrière-plan : transparent""",
        lambda c, _: image_withoutbg(c),
        before_image=IMAGE_EXAMPLE_DIR / "image_withoutbg_before.png",
        after_image=IMAGE_EXAMPLE_DIR / "image_withoutbg_after.png",
    ),
    ToolSpec(
        "Audio",
        "audio_compressor",
        "audio_compress",
        "Convertit les fichiers audio en MP3 au débit configuré.",
        """`concert.flac`

- Taille : 16 Mo
- Débit : 256 kbps""",
        """`concert.mp3`

- Taille : 7 Mo
- Débit : valeur configurée (160 kbps par défaut)
- MP3 déjà assez compressé : copié intact""",
        lambda c, _: audio_compressor(c),
        before_image=IMAGE_EXAMPLE_DIR / "audio_compressor_spectrum.gif",
        after_image=IMAGE_EXAMPLE_DIR / "audio_compressor_spectrum.gif",
    ),
    ToolSpec(
        "PDF",
        "pdf_filigranor",
        "pdf_watermark",
        "Ajoute un filigrane diagonal répété aux PDF.",
        """`contrat.pdf`

- Pages : sans filigrane""",
        """`contrat.pdf`

- Pages : filigrane diagonal répété
- Texte : « document exclusivement destiné à Alice »""",
        lambda c, v: pdf_filigranor(c, str(v)),
        "Destinataire du filigrane",
        required=True,
        before_image=IMAGE_EXAMPLE_DIR / "pdf_filigranor_before.png",
        after_image=IMAGE_EXAMPLE_DIR / "pdf_filigranor_after.png",
    ),
    ToolSpec(
        "PDF",
        "pdf_assemblor",
        "pdf_assemble",
        "Fusionne tous les PDF de INPUT et de ses sous-dossiers.",
        """3 fichiers :

- `01-couverture.pdf`
- `02-contrat.pdf`
- `03-annexe.pdf`""",
        """1 fichier :

- `assembled.pdf`
    - Documents : fusionnés
    - Ordre : couverture → contrat → annexe""",
        lambda c, _: pdf_assemblor(c),
        before_image=IMAGE_EXAMPLE_DIR / "pdf_assemble_before.png",
        after_image=IMAGE_EXAMPLE_DIR / "pdf_assemble_after.png",
    ),
    ToolSpec(
        "PDF",
        "pdf_page_alternator",
        "pdf_alternate",
        "Alterne les pages de impaire.pdf et paire.pdf.",
        """2 fichiers :

- `impaire.pdf` — pages 1, 3, 5
- `paire.pdf` — pages 2, 4, 6""",
        """1 fichier :

- `alternated.pdf`

    - Pages : 1, 2, 3, 4, 5, 6""",
        lambda c, _: pdf_page_alternator(c),
        before_image=IMAGE_EXAMPLE_DIR / "pdf_alternate_before.png",
        after_image=IMAGE_EXAMPLE_DIR / "pdf_alternate_after.png",
    ),
    ToolSpec(
        "Fichier",
        "file_timeline_sorter",
        "file_timeline",
        "Préfixe les fichiers par leur date de modification.",
        """`photo.jpg`

- Modifiée : 6 mars 2026 à 14:30""",
        """`2026-03-06_14-30-00__photo.jpg`

- Date : ajoutée dans le nom""",
        lambda c, _: file_timeline_sorter(c),
    ),
    ToolSpec(
        "Fichier",
        "file_str_remover",
        "file_remove_text",
        "Supprime une chaîne des noms en copiant les fichiers vers OUTPUT.",
        """4 fichiers :

- `rapport-copie.pdf`
- `contrat-copie.pdf`
- `facture-copie.pdf`
- `annexe-copie.pdf`

    => Texte à supprimer : `-copie`""",
        """4 fichiers renommés :

- `rapport.pdf`
- `contrat.pdf`
- `facture.pdf`
- `annexe.pdf`

    => Texte supprimé du nom""",
        lambda c, v: file_str_remover(c, str(v)),
        "Chaîne à supprimer",
        required=True,
    ),
    ToolSpec(
        "Fichier",
        "folder_date_renammer",
        "folder_date",
        "Renomme les dossiers contenant une date française valide.",
        """`15 août 2024 - Vacances`

- Date : française et lisible""",
        """`240815-Vacances`

- Date : format AAMMJJ""",
        lambda c, _: folder_date_renammer(c),
    ),
    ToolSpec(
        "Fichier",
        "cache_nettoyor",
        "cache_clean",
        "Nettoie les caches locaux configurés et affiche le bilan.",
        """Caches locaux — 4,2 Go :

- Poetry, npm et Windows
- Chrome, Firefox et Teams
- Office et fichiers temporaires""",
        """Nettoyage terminé => Caches locaux — 0,8 Go : :

- Espace libéré : 3,4 Go""",
        # This cleaner has no runtime configuration argument.
        lambda _, __: cache_nettoyor(),
    ),
    ToolSpec(
        "Web",
        "youtube_downloader",
        "youtube_downloader",
        "Télécharge une vidéo YouTube que vous êtes autorisé à conserver en MP3 dans OUTPUT.",
        """**Vidéo présente sur le Web**

`https://www.youtube.com/watch?v=exemple`

- Hébergée sur YouTube""",
        f"""**Fichier multimédia présent sur le PC**

`{APP_CONFIG.OUTPUT_DIR}\\video_download.mp4`

- Fichier local MP4 ou MP3""",
        lambda _c, _v: None,
        "URL YouTube",
        required=True,
        before_image=IMAGE_EXAMPLE_DIR / "youtube_downloader_before.png",
        after_image=IMAGE_EXAMPLE_DIR / "youtube_downloader_after.png",
    ),
)


@dataclass
class Job:
    # One job is kept per browser page so simultaneous visitors stay isolated.
    name: str = ""
    events: Queue[tuple[str, Any]] = field(default_factory=Queue)
    cancel: Event = field(default_factory=Event)
    thread: Thread | None = None
    output: list[str] = field(default_factory=list)
    error: str | None = None
    failed: bool = False
    finished: bool = False
    progress: int = 0
    progress_label: str = ""

    @property
    def active(self) -> bool:
        """Return whether this job still owns a live worker thread."""
        return self.thread is not None and self.thread.is_alive()


class QueuedProgress:
    """Send core progress updates from a worker to the NiceGUI page."""

    def __init__(
        self,
        job: Job,
        iterable: Any = None,
        total: float | None = None,
        desc: str | None = None,
        unit: str = "élément",
        **_: object,
    ) -> None:
        """Initialize a queue-backed progress reporter for one background job."""
        self.job = job
        self.iterable = iterable
        self.total = total if total is not None else self._get_length(iterable)
        self.n = 0.0
        self.desc = desc or "Traitement"
        self.unit = unit
        self.started_at = perf_counter()
        self._publish()

    @staticmethod
    def _get_length(iterable: Any) -> int | None:
        """Return an iterable length when the iterable exposes one."""
        try:
            return len(iterable)
        except TypeError:
            return None

    def _label(self) -> str:
        """Build the compact status text displayed beside the progress bar."""
        elapsed = max(0, int(perf_counter() - self.started_at))
        minutes, seconds = divmod(elapsed, 60)
        elapsed_text = f"{minutes:02d}:{seconds:02d}"
        if self.total:
            completed = min(self.n, self.total)
            return f"{self.desc} — {completed:.0f}/{self.total:.0f} {self.unit} — écoulé : {elapsed_text}"
        return (
            f"{self.desc} — {self.n:.0f} {self.unit} — écoulé : {elapsed_text}"
        )

    def _publish(self) -> None:
        """Queue the current percentage and status for the UI thread."""
        percent = min(int(self.n / self.total * 100), 100) if self.total else 0
        self.job.events.put(("progress", (percent, self._label())))

    def update(self, increment: float = 1) -> None:
        """Advance progress while keeping it within the known total."""
        raise_if_cancelled()
        self.n += increment
        self._publish()

    def __iter__(self):
        """Yield the wrapped iterable and publish progress after every item."""
        if self.iterable is None:
            return iter(())
        for item in self.iterable:
            raise_if_cancelled()
            yield item
            self.update()

    def __enter__(self) -> "QueuedProgress":
        """Publish the initial state when used as a context manager."""
        return self

    def __exit__(self, *_: object) -> None:
        """Finalize the progress display when the context ends."""
        self.close()

    def close(self) -> None:
        """Publish the final progress state without forcing completion."""
        if self.total and self.n >= self.total:
            self._publish()


def _run_video_encodor_with_image_reductor(cfg: AppConfig) -> bool:
    """Keep the dashboard video action aligned with the historical workflow."""
    video_folder_is_empty = video_encodor(cfg)
    image_files = find_files_by_extensions(
        cfg.INPUT_DIR, cfg.INPUT_ACCEPTED_IMAGE_FILES
    )
    if not image_files:
        return video_folder_is_empty
    from toolbox_pb.core.events import emit

    emit("\nImages détectées : lancement complémentaire de Image_reductor…")
    image_folder_is_empty = image_reductor(cfg)
    return video_folder_is_empty and image_folder_is_empty


def _open_folder_native(folder: Path) -> None:
    """Open a local folder without touching NiceGUI objects from a worker."""
    subprocess.Popen(["explorer", str(folder)])


def _open_folder(folder: Path) -> None:
    """Open an existing workspace folder or show a NiceGUI error message."""
    if not folder.is_dir():
        ui.notify(f"Dossier introuvable : {folder}", type="negative")
        return
    _open_folder_native(folder)


def _open_process_log() -> None:
    """Open the persistent text log in Notepad++ when it is available."""
    log_path = APP_CONFIG.LOG_DIR / "process_log.txt"
    if not log_path.is_file():
        ui.notify(
            "Aucun fichier log n’est disponible pour le moment.",
            type="warning",
        )
        return
    notepad_plus_plus = next(
        (path for path in NOTEPAD_PLUS_PLUS_PATHS if path.is_file()), None
    )
    if notepad_plus_plus is None:
        ui.notify(
            "Notepad++ est introuvable sur cet ordinateur.", type="negative"
        )
        return
    subprocess.Popen([str(notepad_plus_plus), str(log_path)])


def _select_export_folder(initial_dir: Path) -> Path | None:
    """Show the local folder picker used to choose an export destination."""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askdirectory(
            initialdir=str(initial_dir), title="Exporter OUTPUT vers…"
        )
    finally:
        root.destroy()
    return Path(selected) if selected else None


def _export_output_files(output_dir: Path, destination: Path) -> int:
    """Copy OUTPUT recursively into a user-selected folder."""
    if not output_dir.is_dir():
        raise FileNotFoundError(f"Dossier OUTPUT introuvable : {output_dir}")
    if output_dir.resolve() == destination.resolve():
        raise ValueError("Choisissez un dossier différent de OUTPUT.")
    copied = 0
    for source in output_dir.rglob("*"):
        if not source.is_file() or source.name.casefold() == ".gitkeep":
            continue
        target = destination / source.relative_to(output_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied += 1
    return copied


def _launch_legacy_cli() -> None:
    """Open the historical interactive menu in its own terminal window."""
    subprocess.Popen(
        ("cmd.exe", "/k", "poetry run python -m toolbox_pb.ui.cli"),
        cwd=PROJECT_DIR,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )


def _recent_folder_entries(folder: Path, limit: int = 5) -> list[Path]:
    """Return recent visible entries, keeping the project marker hidden."""
    if not folder.is_dir():
        return []
    return sorted(
        (
            path
            for path in folder.iterdir()
            if path.name.casefold() != ".gitkeep"
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[:limit]


def _clear_folder_content(folder: Path) -> int:
    """Empty one workspace folder while preserving its .gitkeep marker."""
    if not folder.is_dir():
        return 0
    deleted = 0
    for path in folder.iterdir():
        if path.name.casefold() == ".gitkeep":
            continue
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
        deleted += 1
    return deleted


def _startup_report() -> str:
    """Return the version header displayed at application startup."""
    version = func_global_module.format_git_version(
        func_global_module.get_git_version()
    )
    return f"{version}\n\nCode lancé le : {datetime.now().isoformat(timespec='seconds')}"


def _environment_report() -> str:
    """Capture the existing CLI diagnostic without writing it to the terminal."""
    report = io.StringIO()
    with redirect_stdout(report):
        func_global_module.print_system_info()
    return report.getvalue().strip()


def _run_job(
    job: Job, name: str, runner: Callable[[], object], cfg: AppConfig
) -> None:
    """Run one tool in a worker thread and relay its events to the page."""
    job.name, job.output, job.error, job.failed, job.finished = (
        name,
        [],
        None,
        False,
        False,
    )
    job.progress, job.progress_label = 0, ""
    job.cancel.clear()

    def worker() -> None:
        """Execute the runner outside the UI event loop."""
        def sink(message: str) -> None:
            """Normalize core output and forward progress-like download lines."""
            visible_message = message.replace("\r\n", "\n").replace("\r", "\n")
            for match in re.finditer(
                r"\[download\]\s+(\d+(?:\.\d+)?)%\s+of\s+([^\n]+)",
                visible_message,
            ):
                percentage = float(match.group(1))
                job.events.put(
                    (
                        "progress",
                        (
                            round(percentage),
                            f"Téléchargement YouTube — {percentage:.1f} % — {match.group(2).strip()}",
                        ),
                    )
                )
            if visible_message:
                job.events.put(("log", visible_message))

        try:
            configure_file_logging(
                cfg.LOG_DIR, enabled=cfg.LOG_TO_FILE, level=cfg.LOG_LEVEL
            )
            with (
                use_message_sink(sink),
                use_progress_factory(
                    lambda *args, **kwargs: QueuedProgress(
                        job, *args, **kwargs
                    )
                ),
                use_cancellation_event(job.cancel),
                redirect_stdout(io.StringIO()),
            ):
                runner()
        except ProcessingCancelled:
            job.events.put(("log", "\nTraitement arrêté par l’utilisateur.\n"))
        except Exception as exc:
            job.error = traceback.format_exc()
            job.failed = True
            job.events.put(
                (
                    "log",
                    f"\nLe traitement a échoué : {exc}. "
                    "Consultez le détail ci-dessous.\n",
                )
            )
        finally:
            if (
                not job.failed
                and not job.cancel.is_set()
                and cfg.OPEN_OUTPUT_DIR_AFTER_TREATMENT
            ):
                try:
                    _open_folder_native(cfg.OUTPUT_DIR)
                    job.events.put(
                        ("log", "\nDossier OUTPUT ouvert automatiquement.\n")
                    )
                except OSError as exc:
                    job.events.put(
                        ("log", f"\nImpossible d’ouvrir OUTPUT : {exc}\n")
                    )
            job.finished = True

    job.thread = Thread(target=worker, daemon=True, name=f"toolbox-{name}")
    job.thread.start()


def _runtime_config(settings: dict[str, Any]) -> AppConfig:
    """Build one immutable runtime configuration from the page controls."""
    overrides = {flag: bool(settings[flag].value) for flag in SESSION_FLAGS}
    overrides.update(
        {value: int(settings[value].value) for value in SESSION_VALUES}
    )
    overrides["LOG_LEVEL"] = str(settings["LOG_LEVEL"].value)
    return replace(APP_CONFIG, **overrides)


def _tool_icon(spec: ToolSpec) -> str | None:
    """Return the available artwork path for a tool, if it exists."""
    path = TOOL_ICON_DIR / f"{spec.key}.png"
    return str(path) if path.is_file() else None


@ui.page("/", title="toolbox_pb", dark=True)
def toolbox_page() -> None:
    """Render the complete NiceGUI workspace, navigation, and tool cards."""
    # Page-local state deliberately avoids sharing UI state between users.
    job = Job()
    selected = {"category": "Vidéo"}
    settings: dict[str, Any] = {}
    setting_rows: dict[str, Any] = {}
    setting_value_rows: dict[str, Any] = {}
    ui.colors(primary="#6d5dfc", secondary="#0f9b8e", accent="#ff8a4c")
    ui.add_head_html("""<style>
        body { background: radial-gradient(circle at 70% -10%, #28235b 0, transparent 36rem), #0f1220; }
        .nicegui-content { max-width: 1440px; margin: auto; padding-top: 0 !important; }
        .toolbox-drawer { background: linear-gradient(165deg, #171a35 0%, #111426 62%, #0d1020 100%); }
        .brand-mark { background: linear-gradient(135deg, #887bff, #56d5c8); box-shadow: 0 12px 30px rgba(109,93,252,.34); }
        .nav-item { border-radius: 12px; color: #bac2dc; transition: all .18s ease; }
        .nav-item:hover { color: white; background: rgba(255,255,255,.08); transform: translateX(2px); }
        .nav-active { color: white !important; background: linear-gradient(90deg, rgba(132,116,255,.40), rgba(132,116,255,.13)) !important; box-shadow: inset 3px 0 #9b8fff; }
        .glass-header { background: rgba(20,24,43,.82); backdrop-filter: blur(18px); border-bottom: 1px solid rgba(164,175,223,.16); }
        .hero-card { border-radius: 22px; background: linear-gradient(125deg, #201e48, #3e3a8f 60%, #4d82b5); box-shadow: 0 18px 42px rgba(50,47,127,.22); }
        /* QExpansionItem creates its own header and content surfaces. Style all
           of them so a tool never falls back to Quasar's light card colour. */
        .tool-card, .tool-card .q-expansion-item__container,
        .tool-card .q-expansion-item__content { border-radius: 18px; border: 1px solid #2c3457; background: #171c30 !important; overflow: hidden; transition: transform .18s ease, box-shadow .18s ease; }
        .tool-card .q-item { background: linear-gradient(105deg, #1e2540, #171c30) !important; }
        .tool-card .q-expansion-item__content { border-top: 1px solid #2c3457; }
        .tool-card:hover { border-color: #5965a5; box-shadow: 0 10px 26px rgba(0,0,0,.36); }
        .tool-card .q-field__control { background: #11172a !important; color: #f4f6ff !important; }
        .tool-card .q-field__label, .tool-card .q-field__native,
        .tool-card .q-field__input, .tool-card .q-field__marginal,
        .tool-card .q-toggle__label { color: #e3e9ff !important; }
        .tool-card .q-field--outlined .q-field__control:before { border-color: #7180aa !important; }
        .tool-card .q-field--outlined.q-field--focused .q-field__control:after { border-color: #aaa1ff !important; }
        .subtitle-file-card { align-items: center; background: #262d49 !important; border-color: #596891 !important; display: flex; flex-direction: column; justify-content: center; min-height: 5.5rem; text-align: center; }
        .before-card { border-radius: 14px; border: 1px solid #353e62; background: #20263e !important; }
        .after-card { border-radius: 14px; border: 1px solid #25615b; background: #173b3a !important; }
        .before-card, .after-card { min-width: 0; overflow: hidden; }
        .before-card .nicegui-markdown, .after-card .nicegui-markdown { min-width: 0; overflow-wrap: anywhere; word-break: break-word; }
        .before-card code, .after-card code { white-space: normal; overflow-wrap: anywhere; word-break: break-word; }
        .diapo-animation { position: relative; padding-right: 2.4rem; }
        .diapo-note { position: absolute; color: #6d5dfc; filter: drop-shadow(0 3px 4px rgba(71,56,180,.24)); animation: float-note 2.4s ease-in-out infinite; }
        .diapo-note-one { right: .1rem; top: 18%; font-size: 1.45rem; }
        .diapo-note-two { right: .8rem; top: 47%; font-size: 1.05rem; animation-delay: .6s; }
        .diapo-note-three { right: .05rem; bottom: 11%; font-size: 1.25rem; animation-delay: 1.2s; }
        @keyframes float-note { 0%, 100% { transform: translateY(7px) rotate(-8deg); opacity: .45; } 50% { transform: translateY(-9px) rotate(7deg); opacity: 1; } }
        .job-panel { border-radius: 18px; background: #202349 !important; box-shadow: 0 10px 24px rgba(0,0,0,.24); }
        .job-panel .text-indigo-900 { color: #eceaff !important; }
        .stat-card { border-radius: 14px; background: rgba(255,255,255,.13); border: 1px solid rgba(255,255,255,.18); }
        .workspace-upload .q-uploader { width: 100%; min-height: 0; background: transparent; box-shadow: none; border: 0; border-radius: 8px; transition: background .18s ease; }
        .workspace-upload .q-uploader:hover { background: rgba(109,93,252,.16); }
        .workspace-upload .q-uploader__header { min-height: 34px; padding: 0 8px; background: transparent; color: #ffffff; font-weight: 700; }
        .workspace-upload .q-uploader__header .q-btn,
        .workspace-upload .q-uploader__header .q-uploader__subtitle,
        .workspace-upload .q-uploader__header .q-uploader__title { color: #ffffff !important; }
        .workspace-upload .q-uploader__list { display: none; }
        .drawer-settings .q-field__control { background: rgba(255,255,255,.09); border-radius: 10px; color: #f5f7ff; }
        .drawer-settings .q-field__label, .drawer-settings .q-field__native, .drawer-settings .q-field__input, .drawer-settings .q-field__marginal, .drawer-settings .q-toggle__label { color: #e2e7ff !important; }
        .drawer-settings .q-toggle { width: 100%; }
        .drawer-settings .q-toggle__label { font-size: .5rem !important; letter-spacing: -.02em; line-height: 1 !important; white-space: nowrap; }
        .drawer-settings .q-field--outlined .q-field__control:before { border-color: rgba(205,213,255,.45); }
        .drawer-settings .q-field--outlined.q-field--focused .q-field__control:after { border-color: #a69bff; }
        body.body--dark .text-slate-800, body.body--dark .text-slate-700 { color: #f0f2ff !important; }
        body.body--dark .text-slate-600 { color: #c2c9e6 !important; }
        body.body--dark .text-slate-500 { color: #aeb8d7 !important; }
        body.body--dark .text-slate-400 { color: #92a0c5 !important; }
        body.body--dark .text-emerald-900 { color: #d1fae5 !important; }
        body.body--dark .text-emerald-600 { color: #7cf0c3 !important; }
        body.body--dark .text-indigo-900 { color: #eceaff !important; }
        body.body--dark .bg-white { background: #191e33 !important; }
        body.body--dark .bg-slate-50 { background: #20263e !important; }
        body.body--dark .bg-emerald-50 { background: #173b3a !important; }
        body.body--dark .bg-indigo-50 { background: #202349 !important; }
        body.body--dark .border-slate-300 { border-color: #69769d !important; }
    </style>""")

    def drawer_image_button(
        label: str,
        image_path: Path,
        callback: Callable[[], None],
        *,
        active: bool = False,
    ) -> Any:
        """Create one sidebar button using the artwork already in the project."""
        with (
            ui.button(on_click=callback)
            .props("flat no-caps")
            .classes(
                "nav-item w-full justify-start"
                + (" nav-active" if active else "")
            ) as button
        ):
            if image_path.is_file():
                ui.image(str(image_path)).classes(
                    "w-7 h-7 object-contain mr-1"
                )
            else:
                ui.icon("folder").classes("text-lg")
            ui.label(label).classes("font-medium")
        return button

    with ui.left_drawer(value=True, bordered=False).classes(
        "toolbox-drawer text-slate-100 p-4"
    ) as drawer:
        with ui.row().classes("items-center gap-3 mb-1"):
            ui.icon("auto_awesome").classes(
                "brand-mark text-white text-2xl p-2 rounded-xl"
            )
            with ui.column().classes("gap-0"):
                ui.label("toolbox_pb").classes(
                    "text-xl font-bold tracking-tight text-white"
                )
                ui.label("Multimédia, sans friction").classes(
                    "text-xs text-indigo-200"
                )
        ui.label("CATÉGORIES").classes(
            "text-xs font-bold tracking-widest text-slate-500 mt-7 mb-2"
        )
        nav = ui.column().classes("w-full gap-1")
        ui.separator().classes("my-4")
        ui.label("ESPACE DE TRAVAIL").classes(
            "text-xs font-bold tracking-widest text-slate-500 mb-1"
        )
        workspace_panel = ui.column().classes("w-full gap-3")

        def receive_upload(event: Any) -> None:
            """Save an uploaded source file into the INPUT workspace."""
            destination = APP_CONFIG.INPUT_DIR / event.file.name
            event.file.save(destination)
            refresh_workspace()
            ui.notify(
                f"{event.file.name} importé dans INPUT.", type="positive"
            )

        with ui.expansion("Diagnostic et session", icon="settings").classes(
            "drawer-settings w-full mt-4 text-slate-200"
        ):
            ui.label("Version de la toolbox").classes(
                "text-xs font-bold tracking-wide text-indigo-200 mt-2"
            )
            ui.code(_startup_report(), language="text").classes(
                "w-full text-xs rounded-lg"
            )
            ui.label(
                "Versions Python, bibliothèques et outils externes"
            ).classes("text-xs font-bold tracking-wide text-indigo-200 mt-3")
            ui.code(_environment_report(), language="text").classes(
                "w-full text-xs rounded-lg"
            )
            ui.separator().classes("my-3 opacity-30")
            ui.label("Réglages de cette session").classes(
                "text-xs font-bold tracking-wide text-indigo-200"
            )
            ui.label("Flags de cette session").classes(
                "text-xs text-slate-400 mt-1"
            )
            for flag in SESSION_FLAGS:
                with ui.row().classes("w-full") as setting_row:
                    settings[flag] = ui.switch(
                        flag,
                        value=bool(getattr(APP_CONFIG, flag)),
                    ).classes("text-[8px] w-full")
                setting_rows[flag] = setting_row
            ui.label("Valeurs de cette session").classes(
                "text-xs text-slate-400 mt-3"
            )
            for value in SESSION_VALUES:
                with ui.row().classes("w-full") as setting_value_row:
                    settings[value] = ui.number(
                        value,
                        value=int(getattr(APP_CONFIG, value)),
                        min=1,
                        step=1,
                    ).classes("w-full")
                setting_value_rows[value] = setting_value_row
            settings["LOG_LEVEL"] = ui.select(
                ["DEBUG", "INFO", "WARNING", "ERROR"],
                value=APP_CONFIG.LOG_LEVEL,
                label="Niveau de journalisation",
            ).classes("w-full")
        ui.separator().classes("my-4")
        with ui.card().classes(
            "w-full min-h-72 rounded-xl bg-white/5 border border-white/10 p-3 shadow-none"
        ):
            if LEGACY_CLI_LOGO.is_file():
                ui.image(str(LEGACY_CLI_LOGO)).classes(
                    "w-32 h-36 max-w-full object-contain self-center"
                )

            def launch_cli() -> None:
                """Launch the standalone CLI without blocking the web page."""
                try:
                    _launch_legacy_cli()
                except OSError as exc:
                    ui.notify(
                        f"Impossible d’ouvrir le mode CLI : {exc}",
                        type="negative",
                    )
                else:
                    ui.notify(
                        "Le mode CLI est ouvert dans une nouvelle fenêtre.",
                        type="positive",
                    )

            ui.button(
                "À l’ancienne", icon="terminal", on_click=launch_cli
            ).props("outline no-caps color=white").classes(
                "rounded-xl mt-3 self-center"
            )
        with (
            ui.button(on_click=_open_process_log)
            .props("flat no-caps")
            .classes("w-full justify-start text-indigo-200 mt-3 rounded-lg")
        ):
            if NOTEPAD_PLUS_PLUS_ICON.is_file():
                ui.image(str(NOTEPAD_PLUS_PLUS_ICON)).classes(
                    "w-5 h-5 object-contain mr-2"
                )
            else:
                ui.icon("article").classes("mr-2")
            ui.label("Ouvrir le log")

    with ui.header(elevated=False).classes(
        "glass-header text-slate-800 items-center px-3"
    ):
        ui.button(icon="menu", on_click=drawer.toggle).props(
            "flat round dense"
        ).classes("text-slate-600")
        ui.label("Atelier multimédia").classes(
            "font-semibold text-slate-800 ml-2"
        )
        ui.space()
        ui.button(icon="refresh", on_click=ui.navigate.reload).props(
            "flat round dense"
        ).classes("text-slate-600").tooltip("Recharger l’interface")
        ui.badge("NiceGUI", color="primary").props("outline").classes("mr-2")
        ui.badge("Prêt", color="positive").props("rounded")

    with ui.column().classes("w-full p-4 md:p-7 gap-5"):
        with ui.card().classes("hero-card w-full p-2 text-white"):
            with ui.row().classes(
                "w-full items-start justify-between gap-5 flex-wrap"
            ):
                with ui.column().classes("gap-1"):
                    ui.label("Boîte à outils").classes(
                        "text-sm font-medium text-indigo-100"
                    )
                    title = ui.label().classes(
                        "text-2xl font-bold tracking-tight"
                    )
                ui.icon("dashboard_customize").classes(
                    "text-3xl text-white/80"
                )
            with ui.row().classes("mt-1 gap-2 flex-wrap"):
                with ui.card().classes("stat-card px-3 py-1 min-w-28"):
                    ui.label("6").classes("text-lg font-bold")
                    ui.label("catégories").classes("text-xs text-indigo-100")
                with ui.card().classes("stat-card px-3 py-1 min-w-28"):
                    ui.label(str(len(TOOLS))).classes("text-lg font-bold")
                    ui.label("outils disponibles").classes(
                        "text-xs text-indigo-100"
                    )
                with ui.card().classes("stat-card px-3 py-1 min-w-28"):
                    job_status_title = ui.label("Prêt").classes(
                        "text-lg font-bold"
                    )
                    job_status_detail = ui.label(
                        "Aucun traitement en cours"
                    ).classes("text-xs text-indigo-100")

        workspace_previews: dict[str, Any] = {}

        def refresh_workspace() -> None:
            """Refresh the lightweight previews for INPUT and OUTPUT folders."""
            # Rebuild only the lightweight previews; tool cards stay untouched.
            for label, folder, accent in (
                ("INPUT", APP_CONFIG.INPUT_DIR, "text-sky-600"),
                ("OUTPUT", APP_CONFIG.OUTPUT_DIR, "text-emerald-600"),
            ):
                preview = workspace_previews.get(label)
                if preview is None:
                    continue
                entries = _recent_folder_entries(folder)
                preview.clear()
                with preview:
                    visible_count = (
                        sum(
                            1
                            for path in folder.iterdir()
                            if path.name.casefold() != ".gitkeep"
                        )
                        if folder.is_dir()
                        else 0
                    )
                    ui.label(
                        f"{visible_count} élément(s) · aperçu des 5 plus récents"
                    ).classes("text-xs text-slate-400 mb-2")
                    if not entries:
                        ui.label("Le dossier est vide.").classes(
                            "text-sm text-slate-400 italic py-3"
                        )
                    for entry in entries:
                        modified = datetime.fromtimestamp(
                            entry.stat().st_mtime
                        ).strftime("%d/%m/%Y %H:%M")
                        with ui.row().classes(
                            "w-full items-center gap-2 py-1"
                        ):
                            ui.icon(
                                "folder" if entry.is_dir() else "description"
                            ).classes(accent)
                            ui.label(entry.name).classes(
                                "text-sm text-slate-200 grow truncate"
                            )
                            ui.label(modified).classes(
                                "text-xs text-slate-500"
                            )

        def confirm_clear(folder: Path, label: str) -> None:
            """Ask for confirmation before deleting a workspace folder's content."""
            with (
                ui.dialog() as dialog,
                ui.card().classes("rounded-2xl min-w-80"),
            ):
                ui.icon("warning_amber").classes("text-amber-500 text-4xl")
                ui.label(f"Vider {label} ?").classes(
                    "text-xl font-bold text-slate-800"
                )
                ui.label(
                    "Tous les fichiers et sous-dossiers seront supprimés. "
                    "Le dossier lui-même sera conservé."
                ).classes("text-slate-500")

                def clear_confirmed() -> None:
                    """Clear the selected workspace folder after confirmation."""
                    try:
                        count = _clear_folder_content(folder)
                    except OSError as exc:
                        ui.notify(
                            f"Impossible de vider {label} : {exc}",
                            type="negative",
                        )
                    else:
                        refresh_workspace()
                        ui.notify(
                            f"{label} vidé ({count} élément(s)).",
                            type="positive",
                        )
                    dialog.close()

                with ui.row().classes("w-full justify-end gap-2 mt-4"):
                    ui.button("Annuler", on_click=dialog.close).props(
                        "flat no-caps"
                    )
                    ui.button(
                        f"Vider {label}",
                        icon="delete_forever",
                        on_click=clear_confirmed,
                        color="negative",
                    ).props("unelevated no-caps")
            dialog.open()

        def export_output() -> None:
            """Prompt for a destination and copy all generated output files."""
            try:
                destination = _select_export_folder(APP_CONFIG.OUTPUT_DIR)
                if destination is None:
                    return
                copied = _export_output_files(
                    APP_CONFIG.OUTPUT_DIR, destination
                )
            except (OSError, ValueError) as exc:
                ui.notify(f"Export impossible : {exc}", type="negative")
            else:
                ui.notify(
                    f"OUTPUT exporté : {copied} fichier(s).", type="positive"
                )

        active_panel = ui.card().classes(
            "job-panel w-full border border-indigo-100 bg-indigo-50 hidden"
        )
        with active_panel:
            status = ui.label().classes("font-semibold text-indigo-900")
            progress = ui.linear_progress(0, show_value=False).classes(
                "w-full"
            )
            console = (
                ui.textarea(label="Journal du traitement")
                .props("readonly outlined rows=18")
                .classes("w-full")
            )
            with ui.row().classes("w-full justify-between"):
                stop = ui.button(
                    "Arrêter", icon="stop_circle", color="negative"
                )
                ui.button(
                    "Ouvrir OUTPUT",
                    icon="folder_open",
                    on_click=lambda: _open_folder(APP_CONFIG.OUTPUT_DIR),
                ).props("outline")

        tool_actions = ui.row().classes(
            "w-full items-center justify-end gap-2"
        )
        cards = ui.column().classes("w-full gap-3")
        nav_buttons: dict[str, Any] = {}
        category_expansions: list[Any] = []

        def update_session_settings(category: str) -> None:
            """Show only settings that affect the selected tool category."""
            visible_flags = (
                COMMON_SESSION_FLAGS | CATEGORY_SESSION_FLAGS[category]
            )
            for flag, row in setting_rows.items():
                row.set_visibility(flag in visible_flags)
            for value, row in setting_value_rows.items():
                row.set_visibility(category == "Audio")

        def render_category(category: str) -> None:
            """Replace the main content with the selected tool category."""
            selected["category"] = category
            update_session_settings(category)
            title.set_text(category)
            for name, button in nav_buttons.items():
                if name == category:
                    button.classes(add="nav-active")
                else:
                    button.classes(remove="nav-active")
            category_expansions.clear()
            tool_actions.clear()
            with tool_actions:
                ui.label("Sous-catégories").classes(
                    "text-sm text-slate-500 mr-auto"
                )
                ui.button(
                    "Tout ouvrir",
                    icon="unfold_more",
                    on_click=lambda: [
                        expansion.open() for expansion in category_expansions
                    ],
                ).props("outline no-caps dense").classes("rounded-lg")
                ui.button(
                    "Tout refermer",
                    icon="unfold_less",
                    on_click=lambda: [
                        expansion.close() for expansion in category_expansions
                    ],
                ).props("outline no-caps dense").classes("rounded-lg")
            cards.clear()
            with cards:
                for index, spec in enumerate(
                    tool for tool in TOOLS if tool.category == category
                ):
                    render_tool(spec, index + 1)

        def render_tool(spec: ToolSpec, number: int) -> None:
            """Render a tool card, its input controls, and launch action."""
            icon = _tool_icon(spec)
            example_image_classes = "w-1/2 self-center rounded-lg mt-3"
            volume_example_image_classes = (
                "w-3/5 min-h-44 self-center rounded-lg mt-3 object-contain"
            )
            rotated_after_image_classes = (
                "w-44 h-80 self-center rounded-lg mt-3 object-contain"
            )
            expansion = ui.expansion().classes("w-full bg-white tool-card")
            category_expansions.append(expansion)
            # QExpansionItem exposes a header slot: use the project artwork
            # here instead of its default Material "build" (wrench) icon.
            with expansion.add_slot("header"):
                with ui.row().classes("w-full items-center gap-3 px-1"):
                    if icon:
                        ui.image(icon).classes(
                            "w-11 h-11 object-contain rounded-xl bg-slate-50 p-1"
                        )
                    else:
                        ui.icon("auto_awesome").classes(
                            "text-primary text-2xl"
                        )
                    with ui.column().classes("gap-0"):
                        ui.label(spec.title).classes(
                            "font-semibold text-slate-800"
                        )
                        ui.label(f"Outil {number:02d}").classes(
                            "text-xs text-slate-400"
                        )
            with expansion:
                with ui.column().classes("w-full p-3 md:p-5 gap-5"):
                    ui.label(spec.description).classes(
                        "text-slate-600 leading-relaxed"
                    )
                    with ui.row().classes("w-full gap-4 flex-wrap"):
                        with ui.card().classes(
                            "before-card flex-1 min-w-64 bg-slate-50"
                        ):
                            ui.label("Avant").classes(
                                "text-lg font-bold tracking-tight text-slate-800 "
                                "border-b-2 border-slate-300 pb-2 mt-2"
                            )
                            if spec.key == "folder_date":
                                with ui.row().classes(
                                    "items-center gap-2 mt-4"
                                ):
                                    ui.icon("folder").classes(
                                        "text-amber-400 text-2xl"
                                    )
                                    ui.label(
                                        "15 août 2024 - Vacances"
                                    ).classes("font-semibold text-slate-800")
                                ui.label("Date française et lisible").classes(
                                    "mt-2 text-sm text-slate-600"
                                )
                            elif (
                                spec.before_image
                                and spec.before_image.is_file()
                            ):
                                if spec.key in {
                                    "video_srt_integrate",
                                    "video_ass",
                                }:
                                    with ui.row().classes(
                                        "w-full max-w-md self-center mt-3 items-center gap-2"
                                    ):
                                        ui.image(
                                            str(spec.before_image)
                                        ).classes("rounded-lg").style(
                                            "width: 56%"
                                        )
                                        with (
                                            ui.card()
                                            .classes(
                                                "subtitle-file-card border border-slate-200 p-2 shadow-none"
                                            )
                                            .style("width: 40%")
                                        ):
                                            ui.label("sous_titre.srt").classes(
                                                "text-[10px] font-bold text-slate-800 whitespace-nowrap leading-tight"
                                            )
                                            ui.label(
                                                "00:00:00 → 00:00:04"
                                            ).classes(
                                                "text-[10px] text-slate-500 whitespace-nowrap leading-tight mt-1"
                                            )
                                else:
                                    ui.image(str(spec.before_image)).classes(
                                        volume_example_image_classes
                                        if spec.key == "video_volume"
                                        else example_image_classes
                                    )
                            if spec.key != "folder_date":
                                ui.markdown(spec.before).classes(
                                    "mt-3 text-slate-600"
                                )
                        with ui.card().classes(
                            "after-card flex-1 min-w-64 bg-emerald-50"
                        ):
                            ui.label("Après").classes(
                                "text-lg font-bold tracking-tight text-emerald-900 "
                                "border-b-2 border-emerald-400 pb-2 mt-2"
                            )
                            if spec.key == "folder_date":
                                with ui.row().classes(
                                    "items-center gap-2 mt-4"
                                ):
                                    ui.icon("folder").classes(
                                        "text-amber-300 text-2xl"
                                    )
                                    ui.label("240815-Vacances").classes(
                                        "font-semibold text-emerald-900"
                                    )
                                ui.label(
                                    "Date renommée au format AAMMJJ"
                                ).classes("mt-2 text-sm text-emerald-900")
                            elif (
                                spec.after_image and spec.after_image.is_file()
                            ):
                                if spec.key == "image_diapo":
                                    with ui.element("div").classes(
                                        "diapo-animation w-1/2 self-center mt-3"
                                    ):
                                        ui.image(
                                            str(spec.after_image)
                                        ).classes("w-full rounded-lg")
                                        ui.icon("music_note").classes(
                                            "diapo-note diapo-note-one"
                                        )
                                        ui.icon("music_note").classes(
                                            "diapo-note diapo-note-two"
                                        )
                                        ui.icon("music_note").classes(
                                            "diapo-note diapo-note-three"
                                        )
                                elif spec.key == "video_srt_extract":
                                    with ui.row().classes(
                                        "w-full max-w-md self-center mt-3 items-center gap-2"
                                    ):
                                        ui.image(
                                            str(spec.after_image)
                                        ).classes("rounded-lg").style(
                                            "width: 56%"
                                        )
                                        with (
                                            ui.card()
                                            .classes(
                                                "subtitle-file-card border border-emerald-200 p-2 shadow-none"
                                            )
                                            .style("width: 40%")
                                        ):
                                            ui.label("sous_titre.srt").classes(
                                                "text-[10px] font-bold text-emerald-900 whitespace-nowrap leading-tight"
                                            )
                                            ui.label(
                                                "00:00:00 → 00:00:04"
                                            ).classes(
                                                "text-[10px] text-slate-500 whitespace-nowrap leading-tight mt-1"
                                            )
                                else:
                                    ui.image(str(spec.after_image)).classes(
                                        rotated_after_image_classes
                                        if spec.key == "video_rotator"
                                        else volume_example_image_classes
                                        if spec.key == "video_volume"
                                        else example_image_classes
                                    )
                            if spec.key != "folder_date":
                                ui.markdown(spec.after).classes(
                                    "mt-3 text-emerald-900"
                                )
                    value: Any = None
                    download_format: Any = None
                    mp3_bitrate: Any = None
                    video_quality: Any = None
                    download_subtitles: Any = None
                    if spec.key == "youtube_downloader":
                        value = ui.input(
                            "URL YouTube",
                            placeholder="https://www.youtube.com/watch?v=…",
                        ).classes("w-full")
                        download_format = ui.select(
                            ["MP3", "MP4"],
                            value="MP3",
                            label="Format de sortie",
                        ).classes("w-full")
                        mp3_bitrate = ui.select(
                            list(MP3_BITRATES),
                            value="160",
                            label="Débit audio MP3",
                        ).classes("w-full")
                        video_quality = ui.select(
                            list(VIDEO_QUALITIES),
                            value="1080",
                            label="Qualité vidéo maximale",
                        ).classes("w-full")
                        download_subtitles = ui.switch(
                            "Extraire les sous-titres SRT",
                            value=False,
                        ).classes("text-sm")

                        def sync_download_controls(_event: Any = None) -> None:
                            """Show only controls relevant to the selected media format."""
                            is_video = download_format.value == "MP4"
                            mp3_bitrate.set_visibility(not is_video)
                            video_quality.set_visibility(is_video)

                        download_format.on_value_change(sync_download_controls)
                        sync_download_controls()
                    elif spec.input_label:
                        if spec.input_kind == "number":
                            value = ui.number(
                                spec.input_label, value=0, step=0.1
                            ).classes("w-full")
                        elif spec.input_kind == "select":
                            value = ui.select(
                                list(spec.options),
                                label=spec.input_label,
                                value=spec.options[0],
                            ).classes("w-full")
                        else:
                            value = ui.input(spec.input_label).classes(
                                "w-full"
                            )

                    def launch(
                        _: ToolSpec = spec, control: Any = value
                    ) -> None:
                        """Validate card input and start the corresponding background job."""
                        if job.active:
                            ui.notify(
                                "Un traitement est déjà en cours.",
                                type="warning",
                            )
                            return
                        argument = (
                            control.value if control is not None else None
                        )
                        if _.required and not str(argument or "").strip():
                            ui.notify(
                                f"Renseignez « {_.input_label} ». ",
                                type="warning",
                            )
                            return
                        config = _runtime_config(settings)
                        if _.key == "youtube_downloader":
                            options = YouTubeDownloadOptions(
                                url=str(argument),
                                output_dir=config.OUTPUT_DIR,
                                media_format=str(download_format.value),
                                video_quality=str(video_quality.value),
                                mp3_bitrate=str(mp3_bitrate.value),
                                download_subtitles=bool(
                                    download_subtitles.value
                                ),
                            )
                            runner = lambda: run_youtube_download(
                                options, config
                            )
                        else:
                            runner = lambda: _.runner(config, argument)
                        _run_job(job, _.title, runner, config)
                        job_status_title.set_text("Traitement en cours")
                        job_status_detail.set_text(f"Progression · {_.title}")
                        active_panel.classes(remove="hidden")
                        ui.notify(f"{_.title} démarré.", type="positive")

                    ui.button(
                        f"Lancer {spec.title}",
                        icon="play_arrow",
                        on_click=launch,
                        color="primary",
                    ).props("unelevated no-caps").classes(
                        "rounded-xl px-5 self-start"
                    )

        def refresh_job() -> None:
            """Apply queued worker updates from the UI thread."""
            # Worker threads only write to Job; all NiceGUI updates happen here.
            changed = False
            while True:
                try:
                    event, payload = job.events.get_nowait()
                    if event == "log":
                        job.output.append(str(payload))
                    elif event == "progress":
                        job.progress, job.progress_label = payload
                    changed = True
                except Empty:
                    break
            if job.active:
                active_panel.classes(remove="hidden")
                status.set_text(f"{job.name} en cours…")
                job_status_title.set_text("Traitement en cours")
                job_status_detail.set_text(
                    job.progress_label or f"Progression · {job.name}"
                )
                progress.props(remove="indeterminate")
                progress.set_value(job.progress / 100)
            elif job.finished:
                progress.props(remove="indeterminate")
                progress.set_value(1)
                status.set_text(
                    f"{job.name} terminé."
                    if not job.failed
                    else f"{job.name} a échoué."
                )
                job_status_title.set_text("Terminé")
                job_status_detail.set_text(
                    job.name if not job.failed else f"{job.name} · erreur"
                )
            if changed:
                console.value = "".join(job.output)[-12000:]
                console.update()
            if job.error:
                console.value = f"{console.value}\n\n{job.error}"
                console.update()
                job.error = None

        def stop_job() -> None:
            """Request cooperative cancellation of the active background job."""
            if job.active:
                job.cancel.set()
                ui.notify(
                    "Arrêt demandé : le traitement s’interrompra dès que possible.",
                    type="warning",
                )

        stop.on_click(stop_job)
        # ``nav`` was created in the drawer above. Re-enter its context here
        # so the category buttons always remain in the left-hand panel.
        with nav:
            for category, filename in CATEGORY_ICONS.items():
                nav_buttons[category] = drawer_image_button(
                    category,
                    CATEGORY_ICON_DIR / filename,
                    lambda c=category: render_category(c),
                    active=category == selected["category"],
                )
        # Insert the workspace previews into their reserved location in the
        # drawer, while keeping their rendering logic close to the page state.
        with workspace_panel:
            for label, folder, color, artwork in (
                (
                    "INPUT",
                    APP_CONFIG.INPUT_DIR,
                    "sky",
                    FOLDER_ICON_DIR / "input_box.svg",
                ),
                (
                    "OUTPUT",
                    APP_CONFIG.OUTPUT_DIR,
                    "emerald",
                    FOLDER_ICON_DIR / "output_box.svg",
                ),
            ):
                with ui.card().classes(
                    "w-full rounded-xl bg-white/5 border border-white/10 p-3 shadow-none"
                ):
                    with ui.row().classes("w-full items-center"):
                        with ui.row().classes("items-center gap-2"):
                            if artwork.is_file():
                                folder_image = ui.image(str(artwork)).classes(
                                    "w-8 h-8 object-contain cursor-pointer "
                                    "transition-transform hover:scale-110"
                                )
                                folder_image.on(
                                    "click",
                                    lambda path=folder: _open_folder(path),
                                )
                                folder_image.tooltip(f"Ouvrir {label}")
                            else:
                                ui.icon("folder").classes(
                                    f"text-{color}-300 text-lg"
                                )
                            ui.label(label).classes(
                                "font-bold text-slate-100 text-sm"
                            )
                    if label == "INPUT":
                        ui.upload(
                            on_upload=receive_upload,
                            multiple=True,
                            auto_upload=True,
                            label="Importer dans INPUT",
                        ).props("flat").classes("workspace-upload w-full mt-3")
                    workspace_previews[label] = ui.column().classes(
                        "w-full mt-2"
                    )
                    ui.button(
                        f"Vider {label}",
                        icon="delete_outline",
                        on_click=lambda path=folder, name=label: confirm_clear(
                            path, name
                        ),
                        color="negative",
                    ).props("flat no-caps dense").classes(
                        "rounded-lg mt-2 self-start"
                    )
                    if label == "OUTPUT":
                        ui.button(
                            "Exporter OUTPUT",
                            icon="drive_file_move",
                            on_click=export_output,
                            color="primary",
                        ).props("flat no-caps dense").classes(
                            "rounded-lg mt-1 self-start"
                        )
            ui.button(
                "Data/Segment",
                icon="folder_open",
                on_click=lambda: _open_folder(APP_CONFIG.SEGMENT_DIR),
            ).props("flat no-caps align=left").classes(
                "w-full justify-start text-slate-200 hover:bg-white/10 rounded-lg"
            ).tooltip("Ouvrir le dossier data/segment")
        refresh_workspace()
        ui.timer(0.5, refresh_job)
        ui.timer(2.0, refresh_workspace)
        render_category("Vidéo")


def _development_reload_enabled() -> bool:
    """Return whether file watching is explicitly enabled for development."""
    return os.environ.get("TOOLBOX_RELOAD", "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


if __name__ in {"__main__", "__mp_main__"}:
    reload_enabled = _development_reload_enabled()
    ui.run(
        title="toolbox_pb",
        favicon="🧰",
        # File watching is opt-in: on Windows, repeated process spawning while
        # saving application and test files can interrupt NiceGUI imports.
        reload=reload_enabled,
        port=int(os.environ.get("TOOLBOX_PORT", "8080")),
        uvicorn_reload_dirs=str(PROJECT_DIR) if reload_enabled else None,
        cache_control_directives="no-store",
    )

"""Terminal-only input helpers used by the CLI interface."""

from toolbox_pb.core.config_global import AppConfig
from toolbox_pb.core.image.main_image import image_defilor
from toolbox_pb.core.video.main_video import video_audio_decalator, video_rotator
from toolbox_pb.core.web.main_web import (
    MP3_BITRATES,
    VIDEO_QUALITIES,
    YouTubeDownloadOptions,
    download_youtube_media,
)


def run_image_defilor_interactive(cfg: AppConfig) -> bool:
    """Ask for optional defilor settings, then invoke the core operation."""
    while True:
        print("\nOptions disponibles: --height --speed --fps --hold-start --hold-end --codec --crf")
        answer = input("Ajouter des options ? (o/n) : ").strip().lower()
        if answer not in {"o", "oui", "y", "yes", "n", "non", "no"}:
            print("Réponse invalide, veuillez entrer 'o' ou 'n'.\n")
            continue
        extra_args = input("Entrez les options (ex: --height 720 --speed 50): ").strip() if answer in {"o", "oui", "y", "yes"} else None
        try:
            return image_defilor(cfg, extra_args=extra_args)
        except ValueError as exc:
            print(f"Arguments invalides pour Image_defilor: {exc}")
            print("Veuillez réessayer.\n")
            return True


def run_video_audio_decalator_interactive(cfg: AppConfig) -> bool:
    """Ask the terminal user for an audio offset before invoking core logic."""
    while True:
        user_input = input(
            "Entrez le délai de décalage audio en secondes "
            "(ex: -0.5 pour avancer de 0.5s, 0.5 pour retarder de 0.5s) : "
        )
        try:
            return video_audio_decalator(cfg, float(user_input))
        except ValueError:
            print("Format invalide. Entrer un nombre valide (ex : -0.5, 0.5).")


def run_video_rotator_interactive(cfg: AppConfig) -> bool:
    """Ask for a supported rotation angle before invoking the core operation."""
    while True:
        angle = input("Entrez l’angle de rotation (90°, 180° ou 270°) : ")
        try:
            return video_rotator(cfg, angle)
        except ValueError as exc:
            print(f"Angle invalide : {exc}")


def run_youtube_downloader_interactive(cfg: AppConfig) -> bool | None:
    """Collect YouTube download settings from the terminal and run yt-dlp."""
    print(
        "\nTéléchargez uniquement vos propres vidéos ou du contenu dont le "
        "téléchargement est autorisé."
    )
    url = input("URL YouTube (ou q pour annuler) : ").strip()
    if url.casefold() == "q":
        print("Téléchargement YouTube annulé.")
        return None
    if not url:
        print("L’URL YouTube ne peut pas être vide.")
        return None

    media_choice = input("Format (1. Audio MP3, 2. Vidéo MP4) [1] : ").strip()
    media_choice = media_choice or "1"
    if media_choice == "1":
        media_format = "MP3"
        bitrate = input(
            f"Débit MP3 en kb/s ({', '.join(MP3_BITRATES)}) [160] : "
        ).strip() or "160"
        if bitrate not in MP3_BITRATES:
            print("Débit MP3 invalide.")
            return None
        video_quality = "1080"
    elif media_choice == "2":
        media_format = "MP4"
        video_quality = input(
            f"Qualité vidéo maximale ({', '.join(VIDEO_QUALITIES)}p) [1080] : "
        ).strip() or "1080"
        if video_quality not in VIDEO_QUALITIES:
            print("Qualité vidéo invalide.")
            return None
        bitrate = "160"
    else:
        print("Format invalide : choisissez 1 pour MP3 ou 2 pour MP4.")
        return None

    try:
        downloaded_files = download_youtube_media(
            YouTubeDownloadOptions(
                url=url,
                output_dir=cfg.OUTPUT_DIR,
                media_format=media_format,
                video_quality=video_quality,
                mp3_bitrate=bitrate,
            )
        )
    except ValueError as exc:
        print(exc)
        return None

    print("\nFichier(s) téléchargé(s) :")
    for downloaded_file in downloaded_files:
        print(f"- {downloaded_file}")
    return False

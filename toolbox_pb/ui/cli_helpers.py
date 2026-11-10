"""Terminal-only input helpers used by the CLI interface."""

from toolbox_pb.core.config_global import AppConfig
from toolbox_pb.core.image.main_image import image_defilor
from toolbox_pb.core.video.main_video import video_audio_decalator, video_rotator


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

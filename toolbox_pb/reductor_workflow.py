"""Workflow shared by the image and video reduction menu actions."""

from collections.abc import Callable
import math
import sys
import time
from pathlib import Path
from typing import Any


def _read_timed_confirmation(timeout_seconds: int) -> str | None:
    """
    Read a console answer, accepting automatically after a timeout.

    Windows and Linux do not expose the same non-blocking console API.  On
    Windows, ``msvcrt`` reads characters as they are typed.  On Linux (notably
    in the Docker image), ``select`` waits briefly for a complete line.  In
    both cases, ``None`` means that the timeout has expired.
    """
    # Store the last displayed value to avoid redrawing the countdown multiple
    # times within the same second.
    last_remaining = None

    # Compute the deadline once so the timeout is not extended by the loop.
    deadline = time.monotonic() + timeout_seconds

    # Windows uses msvcrt to inspect keyboard input without blocking the app.
    if sys.platform == "win32":
        import msvcrt

        # Keep each typed character until the user validates with Enter.
        answer_chars = []
        while time.monotonic() < deadline:
            remaining = max(0, math.ceil(deadline - time.monotonic()))

            # Refresh the visible countdown only when the remaining second
            # changes, which keeps the console readable.
            if remaining != last_remaining:
                print(
                    f"\rValidation automatique dans {remaining:2d} s... ",
                    end="",
                    flush=True,
                )
                last_remaining = remaining

            # Read a keystroke only when one is already available; this keeps
            # the loop responsive to the timeout.
            if msvcrt.kbhit():
                char = msvcrt.getwch()
                # Enter validates the current answer.
                if char in {"\r", "\n"}:
                    return "".join(answer_chars).strip().lower()

                # Backspace removes the final typed character from the answer.
                if char == "\b":
                    if answer_chars:
                        answer_chars.pop()
                        print("\b \b", end="", flush=True)
                    continue

                # Arrow and function keys are sent as a two-character sequence
                # and must not become part of the textual answer.
                if char in {"\x00", "\xe0"}:
                    if msvcrt.kbhit():
                        msvcrt.getwch()
                    continue
                answer_chars.append(char)
                print(char, end="", flush=True)

            # Avoid using an entire CPU core while waiting for input.
            time.sleep(0.05)
        return None

    # Docker runs on Linux. select() lets the same timeout work in a TTY
    # without creating an input-reading background thread.
    try:
        import select

        while time.monotonic() < deadline:
            remaining = max(0, math.ceil(deadline - time.monotonic()))
            # Apply the same once-per-second countdown refresh as on Windows.
            if remaining != last_remaining:
                print(
                    f"\rValidation automatique dans {remaining:2d} s... ",
                    end="",
                    flush=True,
                )
                last_remaining = remaining

            # Wait at most 100 ms so that the timeout and countdown remain
            # accurate even when the user does not type anything.
            ready, _, _ = select.select([sys.stdin], [], [], 0.1)
            if ready:
                return sys.stdin.readline().strip().lower()

    # Some non-interactive consoles do not support select() on stdin.  Treat
    # this as no answer so the caller can apply its automatic default.
    except (OSError, ValueError):
        return None
    return None


def _ask_to_run_complementary_reductor(tool_name: str) -> bool:
    """
    Ask whether to run the matching image or video reducer.

    The default is affirmative: an empty answer, an unavailable console, or a
    timeout proceeds with the complementary reducer.  Only an explicit
    negative answer prevents its launch.
    """
    # Display the matching tool name so the user knows exactly what will run.
    print(
        f"\nDes fichiers compatibles avec {tool_name} ont été détectés. "
        f"Lancer {tool_name} maintenant ? [O/n]"
    )

    # The helper returns None after ten seconds, which is intentionally treated
    # as the default affirmative choice below.
    answer = _read_timed_confirmation(timeout_seconds=10)

    # Erase the countdown line before printing the outcome.
    print("\r" + " " * 45 + "\r", end="")

    # Accept the common French and English negative forms.
    if answer in {"n", "non", "no"}:
        print("Traitement complémentaire ignoré.")
        return False

    # Unknown answers preserve the automatic affirmative behaviour while
    # making that decision explicit in the console output.
    if answer not in {"o", "oui", "y", "yes", None, ""}:
        print("Réponse invalide : oui appliqué automatiquement.")
    elif answer is None:
        print("Aucune réponse reçue : oui appliqué automatiquement.")
    return True


def _run_complementary_reductor(
    cfg: Any,
    primary_reductor: str,
    find_files: Callable[[Path, list[str]], list[Path]],
    video_runner: Callable[[Any], bool],
    image_runner: Callable[[Any], bool],
) -> bool | None:
    """
    Run the other reducer when matching files are found in the input tree.

    Dependencies are passed as arguments instead of imported here.  This keeps
    the workflow independent from the menu module, prevents circular imports,
    and lets tests replace the file finder and runners easily.

    Returns the complementary runner's result, or ``None`` when no matching
    file is found or the user declines the additional processing.
    """
    # If image reduction was selected first, look for videos to process next.
    if primary_reductor == "image":
        files = find_files(cfg.INPUT_DIR, cfg.INPUT_ACCEPTED_VIDEO_FILES)
        tool_name, runner = "Video_reductor", video_runner

    else:
        # Video reduction was selected first, so search for compatible images.
        files = find_files(cfg.INPUT_DIR, cfg.INPUT_ACCEPTED_IMAGE_FILES)
        tool_name, runner = "Image_reductor", image_runner

    # Do not prompt unnecessarily when the complementary file type is absent.
    # The same branch handles an explicit refusal from the user.
    if not files or not _ask_to_run_complementary_reductor(tool_name):
        return None

    # Start the chosen reducer with the exact configuration selected at launch.
    print(f"\nLancement du {tool_name}...")
    return runner(cfg)

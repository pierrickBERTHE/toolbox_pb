"""
Ce fichier contient des fonctions pour les actions sur les images

Authors:
Pierrick BERTHE
mail: pierrick.berthe@gmx.fr
February 2026
"""
# Imports standard
import argparse
import json
from pathlib import Path
import subprocess
import shlex
from func_global import consume_ffmpeg_progress


def parse_defilor_extra_args(raw_args: str | None) -> argparse.Namespace:
    """
    Parse optional CLI-like arguments for image_defilor.
    Example:
    "--height 720 --speed 50 --hold-start 2 --hold-end 2 --codec libx264"
    """
    # Create a parser for the extra arguments useful for image_defilor
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--speed", type=float, default=35.0)
    parser.add_argument("--fps", type=int, default=60)
    parser.add_argument("--hold-start", type=float, default=5.0)
    parser.add_argument("--hold-end", type=float, default=5.0)
    parser.add_argument("--codec", type=str, default="libx265")
    parser.add_argument("--crf", type=int, default=18)

    # Tokenize the raw arguments string to handle quoted values properly.
    tokens = shlex.split(raw_args) if raw_args else []
    
    # Parse the arguments and handle errors gracefully.
    try:
        args, unknown = parser.parse_known_args(tokens)
    except SystemExit as exc:
        raise ValueError("Invalid extra arguments.") from exc
    if unknown:
        raise ValueError(f"Unknown arguments: {' '.join(unknown)}")

    return args


def get_image_size(image_path: Path) -> tuple[int, int]:
    """
    Read image width/height with ffprobe and return (width, height).
    """
    # Validate the input path before running ffprobe
    if not image_path.exists() or not image_path.is_file():
        raise FileNotFoundError(f"Image not found or invalid: {image_path}")

    # Use ffprobe to get image metadata in JSON format
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        str(image_path),
    ]

    # Run the command subprocess and handle potential errors with messages
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "ffprobe not found. Install FFmpeg and add it to PATH."
        ) from exc
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(
            "Unable to read image metadata.\n"
            f"- File: {image_path}\n"
            f"- Command: {' '.join(cmd)}\n"
            f"- ffprobe details: {details if details else 'no details'}"
        ) from exc

    # Parse the ffprobe output and extract width and height, with error handling 
    payload = json.loads(result.stdout)
    streams = payload.get("streams", [])
    if not streams:
        raise RuntimeError(f"No image stream detected in {image_path}")

    # Extract width and height, ensuring they are valid integers
    width = streams[0].get("width")
    height = streams[0].get("height")
    if not width or not height:
        raise RuntimeError(f"Invalid dimensions for {image_path}")
    return int(width), int(height)


def build_scroll_expression(
    image_height: int,
    output_height: int,
    hold_start: float,
    hold_end: float,
    scroll_speed_px_s: float,
) -> tuple[str, float]:
    """
    Build FFmpeg y expression and total duration. The y expression is piecewise:
    - Hold at the top (y=0) for hold_start seconds
    - Scroll linearly from 0 to travel_px at the specified speed
    - Hold at the bottom (y=travel_px) for hold_end seconds
    """
    # Calculate the total vertical distance to scroll and the corresponding duration.
    travel_px = max(image_height - output_height, 0)
    if travel_px == 0:
        total_duration = hold_start + hold_end + 1.0
        return "0", total_duration

    # calculate the duration of the scrolling phase based on the scroll speed
    scroll_duration = travel_px / scroll_speed_px_s
    
    # Calculate the total duration of the video
    total_duration = hold_start + scroll_duration + hold_end

    # Build the FFmpeg y expression for vertical cropping over time
    y_expr = (
        f"if(lt(t,{hold_start}),0,"
        f"if(lt(t,{hold_start + scroll_duration}),"
        f"(t-{hold_start})*{scroll_speed_px_s},"
        f"{travel_px}))"
    )

    return y_expr, total_duration


def generate_image_defilor(
    image_path: Path,
    output_path: Path,
    output_height: int,
    fps: int,
    scroll_speed_px_s: float,
    hold_start: float,
    hold_end: float,
    codec: str,
    crf: int,
) -> None:
    """
    Generate a smooth vertical scrolling video from a single image.
    The output keeps the source width and crops vertically over time.
    """
    # Validate input parameters and get image dimensions
    image_width, image_height = get_image_size(image_path)
    if output_height <= 0:
        raise ValueError("output_height must be > 0")
    if fps <= 0:
        raise ValueError("fps must be > 0")
    if scroll_speed_px_s <= 0:
        raise ValueError("scroll_speed_px_s must be > 0")
    if output_height > image_height:
        raise ValueError(
            f"output_height ({output_height}) > image height ({image_height})"
        )

    # Build the FFmpeg y expression for vertical cropping and calculate total duration
    y_expr, duration = build_scroll_expression(
        image_height=image_height,
        output_height=output_height,
        hold_start=hold_start,
        hold_end=hold_end,
        scroll_speed_px_s=scroll_speed_px_s,
    )

    # Ensure the output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Crop vertically using a time-based y expression, then enforce 4:2:0 output.
    vf = (
        f"crop={image_width}:{output_height}:0:'{y_expr}',"
        "format=yuv420p"
    )

    # Build the ffmpeg command with progress output and error handling
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostats",
        "-progress",
        "pipe:1",
        "-y",
        "-loop",
        "1",
        "-i",
        str(image_path),
        "-vf",
        vf,
        "-t",
        f"{duration:.3f}",
        "-r",
        str(fps),
        "-c:v",
        codec,
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]

    # Run the command and parse progress, with error handling and messages.
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        # Parse FFmpeg progress output with the shared progress helper.
        print()
        desc = f"Image defilor: {image_path.name}"
        error_lines = consume_ffmpeg_progress(
            proc,
            duration=duration,
            desc=desc
        )

        # Wait for the process to finish and check for errors
        proc.wait()
        if proc.returncode != 0:
            details = " | ".join(error_lines[-3:]).strip()
            raise subprocess.CalledProcessError(
                proc.returncode,
                cmd,
                output=details,
            )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "ffmpeg not found. Install FFmpeg and add it to PATH."
        ) from exc
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout or exc.output or "").strip()
        raise RuntimeError(
            f"ffmpeg failed: {details if details else 'no details'}"
        ) from exc

    # Print a summary of the created video with key parameters and values.
    print("\nVideo created successfully:")
    print(f"- Source image : {image_path}")
    print(f"- Output       : {output_path}")
    print(f"- Video width  : {image_width}px (full source width)")
    print(f"- Video height : {output_height}px")
    print(f"- FPS          : {fps}")
    print(f"- Scroll speed : {scroll_speed_px_s:.2f} px/s")
    print(f"- Total length : {duration:.2f} s")

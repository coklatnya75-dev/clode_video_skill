"""Render short-form videos from a validated JSON edit plan using FFmpeg.

This MVP intentionally performs deterministic media operations only. It does not
call transcription, text-to-speech, or generative-video providers.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


class VideoEditError(RuntimeError):
    """Raised when an edit plan is invalid or FFmpeg fails."""


def _require_file(value: str, label: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise VideoEditError(f"{label} file not found: {path}")
    return path


def _escape_filter_path(path: Path) -> str:
    # Escape characters meaningful to FFmpeg filter arguments.
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def validate_plan(plan: dict[str, Any]) -> None:
    clips = plan.get("clips")
    if not isinstance(clips, list) or not clips:
        raise VideoEditError("Plan must contain a non-empty 'clips' list.")
    for index, clip in enumerate(clips):
        if not isinstance(clip, dict) or not isinstance(clip.get("path"), str):
            raise VideoEditError(f"clips[{index}] must include a path.")
        start = clip.get("start", 0)
        end = clip.get("end")
        if not isinstance(start, (int, float)) or start < 0:
            raise VideoEditError(f"clips[{index}].start must be >= 0.")
        if not isinstance(end, (int, float)) or end <= start:
            raise VideoEditError(f"clips[{index}].end must be greater than start.")
    output = plan.get("output")
    if not isinstance(output, dict) or not isinstance(output.get("path"), str):
        raise VideoEditError("Plan must include output.path.")
    if plan.get("subtitles") is not None and not isinstance(plan["subtitles"], str):
        raise VideoEditError("subtitles must be a file path or null.")
    if plan.get("audio") is not None and not isinstance(plan["audio"], str):
        raise VideoEditError("audio must be a file path or null.")


def build_ffmpeg_command(plan: dict[str, Any]) -> list[str]:
    validate_plan(plan)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise VideoEditError("FFmpeg is not installed or is not on PATH.")

    clips = plan["clips"]
    output_cfg = plan["output"]
    width = int(output_cfg.get("width", 1080))
    height = int(output_cfg.get("height", 1920))
    fps = int(output_cfg.get("fps", 30))
    if width < 2 or height < 2 or fps < 1:
        raise VideoEditError("Output width/height must be >= 2 and fps >= 1.")

    command = [ffmpeg, "-y"]
    filters: list[str] = []
    for i, clip in enumerate(clips):
        source = _require_file(clip["path"], f"clips[{i}]")
        command += ["-i", str(source)]
        start, end = float(clip.get("start", 0)), float(clip["end"])
        filters.append(
            f"[{i}:v]trim=start={start}:end={end},setpts=PTS-STARTPTS,"
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},fps={fps},setsar=1,format=yuv420p[v{i}]"
        )

    concat_inputs = "".join(f"[v{i}]" for i in range(len(clips)))
    filters.append(f"{concat_inputs}concat=n={len(clips)}:v=1:a=0[vout]")

    audio_path = plan.get("audio")
    if audio_path:
        audio = _require_file(audio_path, "audio")
        command += ["-i", str(audio)]
    subtitles_path = plan.get("subtitles")
    if subtitles_path:
        subtitles = _require_file(subtitles_path, "subtitles")
        escaped = _escape_filter_path(subtitles)
        filters[-1] += f";[vout]subtitles='{escaped}'[vsub]"
        video_map = "[vsub]"
    else:
        video_map = "[vout]"

    command += [
        "-filter_complex", ";".join(filters),
        "-map", video_map,
    ]
    if audio_path:
        command += ["-map", f"{len(clips)}:a:0", "-c:a", "aac", "-b:a", "192k", "-shortest"]
    else:
        command += ["-an"]

    destination = Path(output_cfg["path"]).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    command += [
        "-c:v", "libx264", "-preset", str(output_cfg.get("preset", "medium")),
        "-crf", str(int(output_cfg.get("crf", 20))),
        "-movflags", "+faststart", str(destination),
    ]
    return command


def render_video(plan: dict[str, Any], *, timeout: int = 3600) -> str:
    """Render a video and return its absolute output path."""
    command = build_ffmpeg_command(plan)
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise VideoEditError(f"FFmpeg timed out after {timeout} seconds.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "Unknown FFmpeg error")[-4000:]
        raise VideoEditError(f"FFmpeg failed:\n{detail}") from exc
    return str(Path(plan["output"]["path"]).expanduser().resolve())


def render_plan_file(plan_path: str) -> str:
    """Load a JSON edit plan and render it."""
    path = _require_file(plan_path, "Plan")
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise VideoEditError(f"Invalid JSON plan: {exc}") from exc
    if not isinstance(plan, dict):
        raise VideoEditError("The JSON plan root must be an object.")
    return render_video(plan)

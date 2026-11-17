"""Inspect local video assets and extract representative frames for visual review.

This tool gathers technical metadata with ffprobe and frame samples with ffmpeg.
It does not infer scene semantics or generate tags; those remain editable inputs
for the media matcher until a vision-model adapter is configured.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}


class MediaInspectionError(RuntimeError):
    """Raised when media inspection or frame extraction fails."""


def _run(command: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command, check=True, capture_output=True, text=True, timeout=timeout
        )
    except FileNotFoundError as exc:
        raise MediaInspectionError(f"Required executable not found: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaInspectionError(f"Command timed out: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise MediaInspectionError(detail) from exc


def probe_video(path: str | Path) -> dict[str, Any]:
    """Read duration, dimensions, frame rate, and codec from a video file."""
    source = Path(path).expanduser()
    if not source.is_file():
        raise MediaInspectionError(f"Video file not found: {source}")
    result = _run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate",
        "-of", "json", str(source),
    ])
    try:
        payload = json.loads(result.stdout)
        duration = float(payload["format"]["duration"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise MediaInspectionError(f"Invalid ffprobe metadata for {source}") from exc
    video_stream = next(
        (stream for stream in payload.get("streams", []) if stream.get("codec_type") == "video"),
        None,
    )
    if video_stream is None or duration <= 0:
        raise MediaInspectionError(f"No valid video stream found: {source}")
    return {
        "duration": duration,
        "width": video_stream.get("width"),
        "height": video_stream.get("height"),
        "frame_rate": video_stream.get("avg_frame_rate"),
        "codec": video_stream.get("codec_name"),
    }


def extract_sample_frames(
    video_path: str | Path,
    destination: str | Path,
    *,
    duration: float,
    samples: int = 3,
) -> list[str]:
    """Extract evenly spaced JPG frames, avoiding the first/last boundary."""
    if isinstance(samples, bool) or not isinstance(samples, int) or not 1 <= samples <= 20:
        raise MediaInspectionError("samples must be an integer between 1 and 20.")
    if duration <= 0:
        raise MediaInspectionError("duration must be positive.")
    source = Path(video_path).expanduser()
    folder = Path(destination).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for index in range(samples):
        timestamp = duration * (index + 1) / (samples + 1)
        frame_path = folder / f"{source.stem}_frame_{index + 1:02d}.jpg"
        _run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{timestamp:.3f}", "-i", str(source),
            "-frames:v", "1", "-q:v", "3", str(frame_path),
        ])
        if not frame_path.is_file() or frame_path.stat().st_size == 0:
            raise MediaInspectionError(f"Frame extraction produced no image: {frame_path}")
        paths.append(str(frame_path.resolve()))
    return paths


def inspect_media_directory(
    source_dir: str | Path,
    output_dir: str | Path,
    *,
    samples: int = 3,
    recursive: bool = True,
) -> dict[str, Any]:
    """Create a catalog with technical metadata and contact-frame references."""
    source = Path(source_dir).expanduser().resolve()
    output = Path(output_dir).expanduser().resolve()
    if not source.is_dir():
        raise MediaInspectionError(f"Media directory not found: {source}")
    ffprobe, ffmpeg = shutil.which("ffprobe"), shutil.which("ffmpeg")
    if not ffprobe or not ffmpeg:
        missing = "ffprobe" if not ffprobe else "ffmpeg"
        raise MediaInspectionError(f"{missing} is required and must be on PATH.")

    files = source.rglob("*") if recursive else source.glob("*")
    videos = sorted(path for path in files if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS)
    if not videos:
        raise MediaInspectionError(f"No supported video files found in {source}")

    output.mkdir(parents=True, exist_ok=True)
    frame_root = output / "frames"
    assets = []
    failures = []
    for video in videos:
        try:
            metadata = probe_video(video)
            relative = video.relative_to(source)
            frames = extract_sample_frames(
                video, frame_root / relative.parent / relative.stem,
                duration=metadata["duration"], samples=samples,
            )
            assets.append({
                "path": str(video),
                "start": 0,
                "end": round(metadata["duration"], 3),
                "tags": [],
                "description": "",
                "metadata": metadata,
                "sample_frames": frames,
                "needs_visual_review": True,
            })
        except MediaInspectionError as exc:
            failures.append({"path": str(video), "error": str(exc)})

    if not assets:
        raise MediaInspectionError("No videos could be inspected. " + json.dumps(failures))
    catalog = {
        "schema_version": 1,
        "source_directory": str(source),
        "inspection_method": "ffprobe metadata + evenly spaced ffmpeg frame samples",
        "notice": "No AI visual recognition was performed. Add tags and descriptions after reviewing sample_frames.",
        "assets": assets,
        "failures": failures,
    }
    (output / "media_catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return catalog


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect videos and create a reviewable media catalog.")
    parser.add_argument("media_dir", help="Directory containing source video files.")
    parser.add_argument("--output-dir", default="output/media_inspection")
    parser.add_argument("--samples", type=int, default=3, help="Representative frames per video (1-20).")
    parser.add_argument("--non-recursive", action="store_true")
    args = parser.parse_args()
    try:
        result = inspect_media_directory(
            args.media_dir, args.output_dir, samples=args.samples,
            recursive=not args.non_recursive,
        )
    except (OSError, MediaInspectionError) as exc:
        print(f"media-inspector: {exc}", file=sys.stderr)
        return 1
    print(
        f"Inspected {len(result['assets'])} video(s); "
        f"{len(result['failures'])} failure(s). "
        f"Catalog: {Path(args.output_dir).resolve() / 'media_catalog.json'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

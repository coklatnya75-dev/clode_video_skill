"""Local speech-to-subtitle adapter using the OpenAI Whisper CLI.

Install Whisper separately (pip install -U openai-whisper) and FFmpeg.
No API key or network service is used by this adapter at runtime.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


class TranscriptionError(RuntimeError):
    """Raised when local Whisper transcription fails."""


def transcribe_to_srt(
    media_path: str,
    *,
    output_dir: str | None = None,
    language: str = "Indonesian",
    model: str = "small",
    timeout: int = 1800,
) -> str:
    """Transcribe a media file with local Whisper and return the SRT path."""
    media = Path(media_path).expanduser().resolve()
    if not media.is_file():
        raise TranscriptionError(f"Media file not found: {media}")
    if not language.strip():
        raise TranscriptionError("language must not be empty.")
    if not model.strip():
        raise TranscriptionError("model must not be empty.")
    if isinstance(timeout, bool) or timeout < 1:
        raise TranscriptionError("timeout must be a positive integer.")

    whisper = shutil.which("whisper")
    if not whisper:
        raise TranscriptionError(
            "Whisper CLI is not installed or not on PATH. "
            "Install it with: pip install -U openai-whisper"
        )

    destination = Path(output_dir).expanduser().resolve() if output_dir else media.parent
    destination.mkdir(parents=True, exist_ok=True)
    expected_srt = destination / f"{media.stem}.srt"
    command = [
        whisper, str(media), "--model", model, "--language", language,
        "--task", "transcribe", "--output_format", "srt",
        "--output_dir", str(destination),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise TranscriptionError(f"Whisper timed out after {timeout} seconds.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "Unknown Whisper error")[-4000:]
        raise TranscriptionError(f"Whisper failed:\n{detail}") from exc

    if not expected_srt.is_file() or expected_srt.stat().st_size == 0:
        raise TranscriptionError(
            f"Whisper finished but the expected SRT was not created: {expected_srt}"
        )
    return str(expected_srt)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create Indonesian SRT subtitles with local Whisper.")
    parser.add_argument("media", help="Input audio or video file.")
    parser.add_argument("--output-dir", help="Directory for the generated SRT (defaults to media folder).")
    parser.add_argument("--language", default="Indonesian", help="Spoken language; default: Indonesian.")
    parser.add_argument("--model", default="small", help="Whisper model: tiny, base, small, medium, large.")
    parser.add_argument("--timeout", type=int, default=1800, help="Timeout in seconds.")
    args = parser.parse_args()
    try:
        result = transcribe_to_srt(
            args.media, output_dir=args.output_dir, language=args.language,
            model=args.model, timeout=args.timeout,
        )
    except (TranscriptionError, OSError) as exc:
        print(f"video-transcribe: {exc}", file=sys.stderr)
        return 1
    print(f"Subtitles: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

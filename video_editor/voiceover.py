"""Indonesian neural text-to-speech adapter using the edge-tts CLI.

This optional adapter calls Microsoft's online Edge TTS service through the
community edge-tts package. It requires internet access; no API key is used.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


class VoiceoverError(RuntimeError):
    """Raised when text-to-speech generation fails."""


def generate_voiceover(
    text: str,
    output_path: str,
    *,
    voice: str = "id-ID-ArdiNeural",
    rate: str = "+0%",
    pitch: str = "+0Hz",
    timeout: int = 300,
) -> str:
    """Generate an MP3 voice-over and return its absolute path."""
    if not isinstance(text, str) or not text.strip():
        raise VoiceoverError("Voice-over text must not be empty.")
    if len(text) > 50000:
        raise VoiceoverError("Text is too long (maximum 50,000 characters per request).")
    if not isinstance(voice, str) or not voice.strip():
        raise VoiceoverError("voice must be a non-empty voice identifier.")
    if not isinstance(rate, str) or not rate.strip():
        raise VoiceoverError("rate must be a non-empty Edge TTS rate value.")
    if not isinstance(pitch, str) or not pitch.strip():
        raise VoiceoverError("pitch must be a non-empty Edge TTS pitch value.")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 1:
        raise VoiceoverError("timeout must be a positive integer.")

    destination = Path(output_path).expanduser().resolve()
    if destination.suffix.lower() != ".mp3":
        raise VoiceoverError("Output file must use the .mp3 extension.")

    edge_tts = shutil.which("edge-tts")
    if not edge_tts:
        raise VoiceoverError(
            "edge-tts CLI is not installed or not on PATH. "
            "Install it with: pip install edge-tts"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        edge_tts, "--voice", voice, "--text", text,
        "--rate", rate, "--pitch", pitch, "--write-media", str(destination),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise VoiceoverError(f"Edge TTS timed out after {timeout} seconds.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "Unknown Edge TTS error")[-4000:]
        raise VoiceoverError(f"Edge TTS failed:\\n{detail}") from exc

    if not destination.is_file() or destination.stat().st_size == 0:
        raise VoiceoverError(f"Edge TTS did not create a non-empty MP3: {destination}")
    return str(destination)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an Indonesian neural voice-over MP3.")
    parser.add_argument("text", help="Text to speak.")
    parser.add_argument("output", help="Destination MP3 path.")
    parser.add_argument("--voice", default="id-ID-ArdiNeural", help="Voice ID; default: id-ID-ArdiNeural.")
    parser.add_argument("--rate", default="+0%", help="Speech rate, for example +10%% or -10%%.")
    parser.add_argument("--pitch", default="+0Hz", help="Voice pitch, for example +2Hz or -2Hz.")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout in seconds.")
    args = parser.parse_args()
    try:
        result = generate_voiceover(
            args.text, args.output, voice=args.voice, rate=args.rate,
            pitch=args.pitch, timeout=args.timeout,
        )
    except (VoiceoverError, OSError) as exc:
        print(f"video-voiceover: {exc}", file=sys.stderr)
        return 1
    print(f"Voice-over: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

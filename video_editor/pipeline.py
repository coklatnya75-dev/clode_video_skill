"""Orchestrate storyboard matching, Indonesian voice-over, subtitles, and rendering.

The pipeline uses the existing local/online adapters and requires user-provided
media metadata. It does not generate footage or semantically inspect media.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .editor import render_video
from .media_matcher import match_media_to_scenes
from .storyboard import build_storyboard, sync_storyboard_to_duration
from .transcribe import transcribe_to_srt
from .voiceover import generate_voiceover
from .visual_captioner import caption_media_catalog


class PipelineError(RuntimeError):
    """Raised when an automatic production stage fails."""



def probe_audio_duration(audio_path: str) -> float:
    """Return audio duration in seconds using FFprobe."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise PipelineError("FFprobe is required to synchronize scenes to voice-over; install FFmpeg/FFprobe or disable sync.")
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            check=True, capture_output=True, text=True, timeout=30,
        )
        duration = float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError, subprocess.TimeoutExpired) as exc:
        raise PipelineError(f"Could not read voice-over duration: {exc}") from exc
    if duration <= 0:
        raise PipelineError("Voice-over duration reported by FFprobe must be positive.")
    return duration


def run_pipeline(
    script: str,
    catalog: list[dict[str, Any]] | dict[str, Any],
    *,
    output_video: str = "output/shorts.mp4",
    work_dir: str = "output/pipeline",
    voice: str = "id-ID-ArdiNeural",
    rate: str = "+0%",
    pitch: str = "+0Hz",
    wpm: int = 135,
    whisper_model: str = "small",
    minimum_match_score: float = 0.08,
    auto_caption: bool = False,
    semantic_match: bool = False,
    semantic_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    caption_model: str = "Salesforce/blip-image-captioning-base",
    caption_device: str = "auto",
    render: bool = True,
    sync_scenes_to_voiceover: bool = True,
) -> dict[str, Any]:
    """Run the complete script-to-MP4 workflow and return artifact paths."""
    workspace = Path(work_dir).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    captioned_catalog_path = None
    if auto_caption:
        if not isinstance(catalog, dict) or not isinstance(catalog.get("assets"), list):
            raise PipelineError(
                "Automatic visual captioning requires an inspector catalog object "
                "with an assets list and sample_frames."
            )
        try:
            catalog = caption_media_catalog(
                catalog, model_name=caption_model, device=caption_device
            )
        except Exception as exc:
            raise PipelineError(f"Visual captioning failed: {exc}") from exc
        captioned_catalog_path = workspace / "media_catalog_captioned.json"
        captioned_catalog_path.write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    # Build temporary placeholder scenes so the matcher can map each narration
    # sentence to catalog metadata without requiring a pre-existing media list.
    sentences = []
    from .storyboard import split_script
    sentences = split_script(script)
    scene_stub = [
        {"scene": index, "narration": sentence}
        for index, sentence in enumerate(sentences, start=1)
    ]
    matched = match_media_to_scenes(
        scene_stub, catalog, minimum_score=minimum_match_score,
        semantic_match=semantic_match, semantic_model_name=semantic_model,
    )
    storyboard = build_storyboard(
        script, matched["media_manifest"], output_path=output_video, wpm=wpm
    )

    storyboard_path = workspace / "storyboard.json"
    matches_path = workspace / "media_matches.json"
    voiceover_path = workspace / "voiceover.mp3"
    subtitles_dir = workspace / "subtitles"
    plan_path = workspace / "edit_plan.json"

    storyboard_path.write_text(
        json.dumps(storyboard, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    matches_path.write_text(
        json.dumps(matched, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    try:
        voiceover_file = generate_voiceover(
            script, str(voiceover_path), voice=voice, rate=rate, pitch=pitch
        )
        subtitle_file = transcribe_to_srt(
            voiceover_file, output_dir=str(subtitles_dir),
            language="Indonesian", model=whisper_model,
        )
        if sync_scenes_to_voiceover:
            measured_duration = probe_audio_duration(voiceover_file)
            storyboard = sync_storyboard_to_duration(storyboard, measured_duration)
            storyboard_path.write_text(
                json.dumps(storyboard, ensure_ascii=False, indent=2) + "\\n",
                encoding="utf-8",
            )
        edit_plan = storyboard["edit_plan"]
        edit_plan["audio"] = voiceover_file
        edit_plan["subtitles"] = subtitle_file
        plan_path.write_text(
            json.dumps(edit_plan, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        rendered_path = render_video(edit_plan) if render else None
    except Exception as exc:
        raise PipelineError(
            f"Production stopped before completion: {exc}. "
            f"Intermediate storyboard and media matches are saved in {workspace}."
        ) from exc

    return {
        "status": "rendered" if render else "plan_ready",
        "storyboard": str(storyboard_path),
        "media_matches": str(matches_path),
        "captioned_catalog": str(captioned_catalog_path) if captioned_catalog_path else None,
        "voiceover": voiceover_file,
        "subtitles": subtitle_file,
        "edit_plan": str(plan_path),
        "video": rendered_path,
        "note": (
            "Review the generated voice-over, subtitle timing, scene matches, "
            "and final video before publishing."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a vertical video from a script and tagged media catalog."
    )
    parser.add_argument("script", help="UTF-8 narration script file.")
    parser.add_argument("catalog", help="JSON array or inspector report object with an assets array.")
    parser.add_argument("--output-video", default="output/shorts.mp4")
    parser.add_argument("--work-dir", default="output/pipeline")
    parser.add_argument("--voice", default="id-ID-ArdiNeural")
    parser.add_argument("--rate", default="+0%")
    parser.add_argument("--pitch", default="+0Hz")
    parser.add_argument("--wpm", type=int, default=135)
    parser.add_argument("--whisper-model", default="small")
    parser.add_argument("--minimum-match-score", type=float, default=0.08)
    parser.add_argument("--semantic-match", action="store_true",
                        help="Use optional multilingual embeddings to match Indonesian narration with catalog captions.")
    parser.add_argument("--semantic-model", default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    parser.add_argument("--auto-caption", action="store_true",
                        help="Use BLIP to caption sample_frames in an inspector catalog.")
    parser.add_argument("--caption-model", default="Salesforce/blip-image-captioning-base")
    parser.add_argument("--caption-device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--plan-only", action="store_true", help="Prepare all assets and edit plan but do not render.")
    parser.add_argument("--no-sync-scenes", action="store_true", help="Keep estimated scene durations instead of syncing to measured voice-over length.")
    args = parser.parse_args()

    try:
        script_text = Path(args.script).read_text(encoding="utf-8")
        catalog = json.loads(Path(args.catalog).read_text(encoding="utf-8"))
        result = run_pipeline(
            script_text, catalog,
            output_video=args.output_video,
            work_dir=args.work_dir,
            voice=args.voice,
            rate=args.rate,
            pitch=args.pitch,
            wpm=args.wpm,
            whisper_model=args.whisper_model,
            minimum_match_score=args.minimum_match_score,
            auto_caption=args.auto_caption,
            semantic_match=args.semantic_match,
            semantic_model=args.semantic_model,
            caption_model=args.caption_model,
            caption_device=args.caption_device,
            render=not args.plan_only,
            sync_scenes_to_voiceover=not args.no_sync_scenes,
        )
    except (OSError, json.JSONDecodeError, PipelineError, ValueError) as exc:
        print(f"video-pipeline: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

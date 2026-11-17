"""Create a reviewable scene storyboard and renderer plan from a script.

This is a deterministic planning helper: users supply the media-to-scene mapping.
It does not perform semantic AI media selection or inspect clip contents.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


class StoryboardError(ValueError):
    """Raised when script or scene media input is invalid."""


def split_script(script: str) -> list[str]:
    """Split a script into scene-sized units using paragraphs and sentence endings."""
    if not isinstance(script, str) or not script.strip():
        raise StoryboardError("Script must not be empty.")
    units: list[str] = []
    for paragraph in re.split(r"\n\s*\n", script.strip()):
        # Keep punctuation attached to each sentence.
        sentences = re.split(r"(?<=[.!?。！？])\s+", paragraph.strip())
        units.extend(sentence.strip() for sentence in sentences if sentence.strip())
    return units


def build_storyboard(
    script: str,
    media: list[dict[str, Any]],
    *,
    output_path: str = "output/shorts.mp4",
    wpm: int = 135,
    min_scene_seconds: float = 2.0,
    max_scene_seconds: float = 8.0,
    audio_path: str | None = None,
    subtitles_path: str | None = None,
) -> dict[str, Any]:
    """Pair each script unit with one explicitly supplied media clip."""
    scenes_text = split_script(script)
    if not isinstance(media, list) or len(media) != len(scenes_text):
        raise StoryboardError(
            f"Media count ({len(media) if isinstance(media, list) else 'invalid'}) "
            f"must exactly match scene count ({len(scenes_text)})."
        )
    if isinstance(wpm, bool) or not isinstance(wpm, int) or wpm < 40 or wpm > 300:
        raise StoryboardError("wpm must be an integer between 40 and 300.")
    if min_scene_seconds <= 0 or max_scene_seconds < min_scene_seconds:
        raise StoryboardError("Scene duration bounds are invalid.")
    if not isinstance(output_path, str) or not output_path.strip():
        raise StoryboardError("output_path must be a non-empty string.")

    scenes = []
    clips = []
    for index, (text, item) in enumerate(zip(scenes_text, media), start=1):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not item["path"].strip():
            raise StoryboardError(f"media[{index - 1}] must include a non-empty path.")
        start = item.get("start", 0)
        end = item.get("end")
        if isinstance(start, bool) or not isinstance(start, (int, float)) or start < 0:
            raise StoryboardError(f"media[{index - 1}].start must be >= 0.")
        if isinstance(end, bool) or not isinstance(end, (int, float)) or end <= start:
            raise StoryboardError(f"media[{index - 1}].end must be greater than start.")
        words = len(text.split())
        estimate = min(max(words / wpm * 60, min_scene_seconds), max_scene_seconds)
        clip_duration = float(end) - float(start)
        scenes.append({
            "scene": index,
            "narration": text,
            "estimated_voiceover_seconds": round(estimate, 2),
            "media_path": item["path"],
            "media_start": float(start),
            "media_end": float(end),
            "media_duration_seconds": round(clip_duration, 2),
            "duration_note": (
                "Clip duration differs from estimated narration; review pacing."
                if abs(clip_duration - estimate) > 1.5 else "Duration is reasonably close."
            ),
        })
        clips.append({"path": item["path"], "start": start, "end": end})

    edit_plan = {
        "clips": clips,
        "audio": audio_path,
        "subtitles": subtitles_path,
        "output": {
            "path": output_path,
            "width": 1080,
            "height": 1920,
            "fps": 30,
        },
    }
    return {
        "title": "Script-to-video storyboard",
        "planning_method": "sentence splitting + word-count duration estimate",
        "voiceover_words_per_minute": wpm,
        "scenes": scenes,
        "edit_plan": edit_plan,
    }



def sync_storyboard_to_duration(storyboard: dict[str, Any], voiceover_seconds: float) -> dict[str, Any]:
    """Scale scene display durations to the measured voice-over length."""
    if isinstance(voiceover_seconds, bool) or not isinstance(voiceover_seconds, (int, float)) or voiceover_seconds <= 0:
        raise StoryboardError("voiceover_seconds must be a positive number.")
    scenes = storyboard.get("scenes")
    clips = storyboard.get("edit_plan", {}).get("clips")
    if not isinstance(scenes, list) or not scenes or not isinstance(clips, list) or len(scenes) != len(clips):
        raise StoryboardError("Storyboard scenes and edit-plan clips must have matching entries.")
    weights = [max(float(scene.get("estimated_voiceover_seconds", 0)), 0.01) for scene in scenes]
    weight_total = sum(weights)
    durations = [float(voiceover_seconds) * weight / weight_total for weight in weights]
    # Round all but the last scene; assign the remainder to avoid cumulative drift.
    rounded = [round(value, 3) for value in durations[:-1]]
    rounded.append(round(float(voiceover_seconds) - sum(rounded), 3))
    for scene, clip, duration in zip(scenes, clips, rounded):
        scene["synchronized_voiceover_seconds"] = duration
        scene["duration_note"] = "Output scene duration is aligned proportionally to measured voice-over length."
        clip["output_duration"] = duration
    storyboard["voiceover_duration_seconds"] = round(float(voiceover_seconds), 3)
    storyboard["duration_sync"] = "Scene durations distributed by estimated narration word-count weights."
    return storyboard



def _srt_seconds(timestamp: str) -> float:
    """Convert an SRT timestamp (HH:MM:SS,mmm) to seconds."""
    hours, minutes, remainder = timestamp.replace(",", ".").split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(remainder)


def sync_storyboard_to_srt(
    storyboard: dict[str, Any],
    srt_path: str,
    voiceover_seconds: float | None = None,
) -> dict[str, Any]:
    """Align scene boundaries to Whisper subtitle cue timing using word positions."""
    srt_file = Path(srt_path).expanduser()
    if not srt_file.is_file():
        raise StoryboardError(f"Subtitle file not found: {srt_file}")
    raw = srt_file.read_text(encoding="utf-8-sig")
    cue_pattern = re.compile(
        r"(?m)^(\\d{2}:\\d{2}:\\d{2}[,.]\\d{3})\\s*-->\\s*"
        r"(\\d{2}:\\d{2}:\\d{2}[,.]\\d{3}).*$"
    )
    cues = []
    for match in cue_pattern.finditer(raw):
        block_end = raw.find("\n\n", match.end())
        block = raw[match.end():] if block_end < 0 else raw[match.end():block_end]
        words = re.findall(r"\\w+", block, flags=re.UNICODE)
        start, end = _srt_seconds(match.group(1)), _srt_seconds(match.group(2))
        if words and end > start:
            cues.append({"start": start, "end": end, "word_count": len(words)})
    scenes = storyboard.get("scenes")
    clips = storyboard.get("edit_plan", {}).get("clips")
    if not cues:
        raise StoryboardError("SRT contains no valid timed subtitle cues.")
    if not isinstance(scenes, list) or not scenes or not isinstance(clips, list) or len(scenes) != len(clips):
        raise StoryboardError("Storyboard scenes and edit-plan clips must have matching entries.")
    scene_counts = [max(1, len(re.findall(r"\\w+", str(scene.get("narration", "")), flags=re.UNICODE))) for scene in scenes]
    total_scene_words = sum(scene_counts)
    total_cue_words = sum(cue["word_count"] for cue in cues)
    if total_scene_words <= 0 or total_cue_words <= 0:
        raise StoryboardError("Scene narration and SRT must contain recognizable words.")
    duration = float(voiceover_seconds) if voiceover_seconds is not None else cues[-1]["end"]
    if duration <= 0 or cues[-1]["end"] > duration + 0.5:
        raise StoryboardError("SRT cue timing is inconsistent with voice-over duration.")

    def locate_boundary(target_word: float) -> float:
        consumed = 0
        for cue in cues:
            next_consumed = consumed + cue["word_count"]
            if target_word <= next_consumed:
                fraction = min(1.0, max(0.0, (target_word - consumed) / cue["word_count"]))
                return cue["start"] + fraction * (cue["end"] - cue["start"])
            consumed = next_consumed
        return cues[-1]["end"]

    boundaries = [0.0]
    cumulative = 0
    for count in scene_counts[:-1]:
        cumulative += count
        boundaries.append(locate_boundary(total_cue_words * cumulative / total_scene_words))
    boundaries.append(duration)
    # Enforce strictly increasing boundaries for very short or imperfect transcripts.
    for index in range(1, len(boundaries)):
        boundaries[index] = max(boundaries[index], boundaries[index - 1] + 0.001)
    if boundaries[-1] > duration:
        boundaries[-1] = duration
        for index in range(len(boundaries) - 2, -1, -1):
            boundaries[index] = min(boundaries[index], boundaries[index + 1] - 0.001)
    for index, (scene, clip) in enumerate(zip(scenes, clips)):
        start, end = boundaries[index], boundaries[index + 1]
        scene["voiceover_start_seconds"] = round(start, 3)
        scene["voiceover_end_seconds"] = round(end, 3)
        scene["synchronized_voiceover_seconds"] = round(end - start, 3)
        scene["duration_note"] = "Scene boundary estimated from Whisper SRT cue timing and narration word position."
        clip["output_duration"] = round(end - start, 3)
    storyboard["voiceover_duration_seconds"] = round(duration, 3)
    storyboard["duration_sync"] = "Whisper SRT cue timing mapped to script scene word positions."
    storyboard["duration_sync_method"] = "srt_word_position"
    return storyboard


def create_storyboard_file(
    script_path: str,
    media_manifest_path: str,
    destination_path: str,
    *,
    output_path: str = "output/shorts.mp4",
    wpm: int = 135,
    audio_path: str | None = None,
    subtitles_path: str | None = None,
) -> str:
    script_file = Path(script_path).expanduser()
    manifest_file = Path(media_manifest_path).expanduser()
    if not script_file.is_file():
        raise StoryboardError(f"Script file not found: {script_file}")
    if not manifest_file.is_file():
        raise StoryboardError(f"Media manifest not found: {manifest_file}")
    try:
        media = json.loads(manifest_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StoryboardError(f"Invalid media manifest JSON: {exc}") from exc
    result = build_storyboard(
        script_file.read_text(encoding="utf-8"),
        media,
        output_path=output_path,
        wpm=wpm,
        audio_path=audio_path,
        subtitles_path=subtitles_path,
    )
    destination = Path(destination_path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(destination.resolve())


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a storyboard and FFmpeg edit plan from a script.")
    parser.add_argument("script", help="UTF-8 text file containing the narration script.")
    parser.add_argument("media_manifest", help="JSON array: one {path,start,end} item per scene.")
    parser.add_argument("--output", default="storyboard.json", help="Storyboard JSON destination.")
    parser.add_argument("--video-output", default="output/shorts.mp4", help="Rendered MP4 path stored in the plan.")
    parser.add_argument("--wpm", type=int, default=135, help="Estimated narration speed in words per minute.")
    parser.add_argument("--audio", help="Optional existing voice-over/music file path.")
    parser.add_argument("--subtitles", help="Optional existing SRT subtitle file path.")
    args = parser.parse_args()
    try:
        result = create_storyboard_file(
            args.script, args.media_manifest, args.output,
            output_path=args.video_output, wpm=args.wpm,
            audio_path=args.audio, subtitles_path=args.subtitles,
        )
    except (StoryboardError, OSError) as exc:
        print(f"storyboard: {exc}", file=sys.stderr)
        return 1
    print(f"Storyboard created: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

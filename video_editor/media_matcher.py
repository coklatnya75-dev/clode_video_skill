"""Transparent keyword-based matching of storyboard scenes to a user media catalog.

This is a lightweight baseline, not a vision model: catalog tags/descriptions are
provided by the user and every suggested match includes an explainable score.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


class MediaMatchError(ValueError):
    """Raised for invalid catalog data or scenes without usable matches."""


_STOPWORDS = {
    "dan", "atau", "yang", "di", "ke", "dari", "ini", "itu", "untuk", "dengan",
    "pada", "adalah", "karena", "dalam", "ada", "akan", "juga", "bisa", "punya",
    "sangat", "lebih", "serta", "sebuah", "para", "kita", "mereka", "seperti",
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "is", "are",
}


def _tokens(value: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", value.lower())
    return {word for word in words if len(word) > 2 and word not in _STOPWORDS}


def _catalog_tokens(item: dict[str, Any]) -> set[str]:
    tags = item.get("tags", [])
    description = item.get("description", "")
    if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
        raise MediaMatchError("Each catalog item's tags must be a list of strings.")
    if not isinstance(description, str):
        raise MediaMatchError("Each catalog item's description must be a string.")
    return _tokens(" ".join(tags) + " " + description)


def match_media_to_scenes(
    scenes: list[dict[str, Any]],
    catalog: list[dict[str, Any]],
    *,
    minimum_score: float = 0.08,
    allow_reuse: bool = False,
) -> dict[str, Any]:
    """Rank catalog items for each scene using normalized keyword overlap."""
    if not isinstance(scenes, list) or not scenes:
        raise MediaMatchError("Storyboard must contain a non-empty scenes list.")
    if not isinstance(catalog, list) or not catalog:
        raise MediaMatchError("Media catalog must be a non-empty list.")
    if not 0 <= minimum_score <= 1:
        raise MediaMatchError("minimum_score must be between 0 and 1.")

    prepared = []
    for index, item in enumerate(catalog):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not item["path"].strip():
            raise MediaMatchError(f"catalog[{index}] must include a non-empty path.")
        start, end = item.get("start", 0), item.get("end")
        if isinstance(start, bool) or not isinstance(start, (int, float)) or start < 0:
            raise MediaMatchError(f"catalog[{index}].start must be >= 0.")
        if isinstance(end, bool) or not isinstance(end, (int, float)) or end <= start:
            raise MediaMatchError(f"catalog[{index}].end must be greater than start.")
        prepared.append((item, _catalog_tokens(item)))

    used: set[int] = set()
    matches = []
    manifest = []
    for scene_index, scene in enumerate(scenes):
        if not isinstance(scene, dict) or not isinstance(scene.get("narration"), str):
            raise MediaMatchError(f"scenes[{scene_index}] must include narration text.")
        query = _tokens(scene["narration"])
        ranked = []
        for media_index, (item, media_tokens) in enumerate(prepared):
            if not allow_reuse and media_index in used:
                continue
            overlap = query & media_tokens
            score = len(overlap) / len(query) if query else 0.0
            ranked.append((score, len(overlap), media_index, overlap))
        ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
        if not ranked or ranked[0][0] < minimum_score or ranked[0][1] == 0:
            scene_number = scene.get("scene", scene_index + 1)
            raise MediaMatchError(
                f"No suitable media match for scene {scene_number}. "
                "Add relevant tags/description or lower minimum_score."
            )
        score, _, media_index, overlap = ranked[0]
        item = prepared[media_index][0]
        used.add(media_index)
        entry = {"path": item["path"], "start": item.get("start", 0), "end": item["end"]}
        manifest.append(entry)
        matches.append({
            "scene": scene.get("scene", scene_index + 1),
            "narration": scene["narration"],
            "matched_media": item["path"],
            "score": round(score, 3),
            "matched_keywords": sorted(overlap),
            "review_required": True,
        })

    return {
        "method": "keyword_overlap",
        "notice": "Suggestions are based on user-provided tags/descriptions, not visual understanding. Review every match.",
        "matches": matches,
        "media_manifest": manifest,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Match storyboard scenes to a tagged media catalog.")
    parser.add_argument("storyboard", help="Storyboard JSON produced by video_editor.storyboard.")
    parser.add_argument("catalog", help="JSON array of media objects with path/start/end/tags/description.")
    parser.add_argument("--output", default="media_matches.json", help="Output JSON file.")
    parser.add_argument("--minimum-score", type=float, default=0.08)
    parser.add_argument("--allow-reuse", action="store_true", help="Allow one media file to serve multiple scenes.")
    args = parser.parse_args()
    try:
        storyboard = json.loads(Path(args.storyboard).read_text(encoding="utf-8"))
        catalog = json.loads(Path(args.catalog).read_text(encoding="utf-8"))
        result = match_media_to_scenes(
            storyboard.get("scenes") if isinstance(storyboard, dict) else None,
            catalog,
            minimum_score=args.minimum_score,
            allow_reuse=args.allow_reuse,
        )
        destination = Path(args.output).expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, json.JSONDecodeError, AttributeError, MediaMatchError) as exc:
        print(f"media-matcher: {exc}", file=sys.stderr)
        return 1
    print(f"Media matches created: {destination.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

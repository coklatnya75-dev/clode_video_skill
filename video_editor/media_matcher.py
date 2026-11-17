"""Explainable keyword and optional multilingual semantic media matching."""
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


def _catalog_text(item: dict[str, Any]) -> str:
    tags = item.get("tags", [])
    description = item.get("description", "")
    if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
        raise MediaMatchError("Each catalog item's tags must be a list of strings.")
    if not isinstance(description, str):
        raise MediaMatchError("Each catalog item's description must be a string.")
    return " ".join(tags) + " " + description


def _load_semantic_encoder(model_name: str):
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise MediaMatchError(
            "Semantic matching requires sentence-transformers. Install it with "
            "'pip install sentence-transformers'."
        ) from exc
    try:
        return SentenceTransformer(model_name)
    except Exception as exc:
        raise MediaMatchError(f"Could not load semantic model {model_name!r}: {exc}") from exc


def _semantic_scores(query: str, candidates: list[str], encoder: Any) -> list[float]:
    """Return cosine similarities using a normalized multilingual sentence encoder."""
    try:
        vectors = encoder.encode(
            [query, *candidates], convert_to_numpy=True, normalize_embeddings=True
        )
        similarities = vectors[1:] @ vectors[0]
        return [max(0.0, min(1.0, float(value))) for value in similarities]
    except Exception as exc:
        raise MediaMatchError(f"Semantic encoding failed: {exc}") from exc


def match_media_to_scenes(
    scenes: list[dict[str, Any]],
    catalog: list[dict[str, Any]] | dict[str, Any],
    *,
    minimum_score: float = 0.08,
    allow_reuse: bool = False,
    semantic_match: bool = False,
    semantic_model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    _semantic_encoder: Any = None,
) -> dict[str, Any]:
    """Rank media by keyword overlap, optionally blended with multilingual similarity.

    Semantic mode combines 35% keyword overlap and 65% cosine similarity.
    The optional encoder is injectable for deterministic unit tests.
    """
    if not isinstance(scenes, list) or not scenes:
        raise MediaMatchError("Storyboard must contain a non-empty scenes list.")
    if isinstance(catalog, dict):
        catalog = catalog.get("assets")
    if not isinstance(catalog, list) or not catalog:
        raise MediaMatchError("Media catalog must be a non-empty list or an inspector report with an assets list.")
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
        text = _catalog_text(item)
        prepared.append((item, _tokens(text), text))

    encoder = (_semantic_encoder or _load_semantic_encoder(semantic_model_name)) if semantic_match else None
    used: set[int] = set()
    matches = []
    manifest = []
    for scene_index, scene in enumerate(scenes):
        if not isinstance(scene, dict) or not isinstance(scene.get("narration"), str):
            raise MediaMatchError(f"scenes[{scene_index}] must include narration text.")
        narration = scene["narration"]
        query = _tokens(narration)
        candidates = [entry[2] for entry in prepared]
        semantic_values = _semantic_scores(narration, candidates, encoder) if semantic_match else [0.0] * len(prepared)
        ranked = []
        for media_index, (item, media_tokens, _) in enumerate(prepared):
            if not allow_reuse and media_index in used:
                continue
            overlap = query & media_tokens
            keyword_score = len(overlap) / len(query) if query else 0.0
            semantic_score = semantic_values[media_index]
            score = 0.35 * keyword_score + 0.65 * semantic_score if semantic_match else keyword_score
            ranked.append((score, len(overlap), media_index, overlap, semantic_score, keyword_score))
        ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
        if not ranked or ranked[0][0] < minimum_score or (not semantic_match and ranked[0][1] == 0):
            scene_number = scene.get("scene", scene_index + 1)
            raise MediaMatchError(
                f"No suitable media match for scene {scene_number}. "
                "Add relevant tags/description, enable semantic matching, or lower minimum_score."
            )
        score, _, media_index, overlap, semantic_score, keyword_score = ranked[0]
        item = prepared[media_index][0]
        used.add(media_index)
        manifest.append({"path": item["path"], "start": item.get("start", 0), "end": item["end"]})

        def confidence_label(value: float) -> str:
            if value >= 0.65:
                return "high"
            if value >= 0.35:
                return "medium"
            return "low"

        alternatives = []
        for candidate_score, _, candidate_index, candidate_overlap, candidate_semantic, candidate_keyword in ranked[1:4]:
            candidate = prepared[candidate_index][0]
            alternative = {
                "path": candidate["path"],
                "start": candidate.get("start", 0),
                "end": candidate["end"],
                "score": round(candidate_score, 3),
                "matched_keywords": sorted(candidate_overlap),
            }
            if semantic_match:
                alternative["keyword_score"] = round(candidate_keyword, 3)
                alternative["semantic_similarity"] = round(candidate_semantic, 3)
            alternatives.append(alternative)

        match = {
            "scene": scene.get("scene", scene_index + 1),
            "narration": narration,
            "matched_media": item["path"],
            "source_start": item.get("start", 0),
            "source_end": item["end"],
            "description": item.get("description", ""),
            "tags": item.get("tags", []),
            "score": round(score, 3),
            "confidence": confidence_label(score),
            "matched_keywords": sorted(overlap),
            "alternatives": alternatives,
            "review_required": True,
        }
        if semantic_match:
            match["keyword_score"] = round(keyword_score, 3)
            match["semantic_similarity"] = round(semantic_score, 3)
        matches.append(match)

    return {
        "method": "hybrid_keyword_multilingual_semantic" if semantic_match else "keyword_overlap",
        "notice": (
            "Hybrid scores combine 35% keyword overlap and 65% multilingual embedding similarity. "
            "Similarity is a suggestion, not proof of visual relevance; review every match."
            if semantic_match else
            "Suggestions use user-provided tags/descriptions, not visual understanding. Review every match."
        ),
        "matches": matches,
        "media_manifest": manifest,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Match storyboard scenes to a tagged media catalog.")
    parser.add_argument("storyboard")
    parser.add_argument("catalog")
    parser.add_argument("--output", default="media_matches.json")
    parser.add_argument("--minimum-score", type=float, default=0.08)
    parser.add_argument("--allow-reuse", action="store_true")
    parser.add_argument("--semantic-match", action="store_true",
                        help="Enable multilingual sentence embeddings (optional dependency).")
    parser.add_argument("--semantic-model",
                        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    args = parser.parse_args()
    try:
        storyboard = json.loads(Path(args.storyboard).read_text(encoding="utf-8"))
        catalog = json.loads(Path(args.catalog).read_text(encoding="utf-8"))
        result = match_media_to_scenes(
            storyboard.get("scenes") if isinstance(storyboard, dict) else None,
            catalog, minimum_score=args.minimum_score, allow_reuse=args.allow_reuse,
            semantic_match=args.semantic_match, semantic_model_name=args.semantic_model,
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

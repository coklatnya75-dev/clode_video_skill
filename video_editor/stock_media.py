"""Download royalty-free stock video from Pixabay for a narration script.

Requires PIXABAY_API_KEY. Each narration sentence gets a relevant, distinct clip.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .storyboard import split_script


class StockMediaError(RuntimeError):
    """Raised when stock footage cannot be found or downloaded."""


STOPWORDS = {
    "yang", "dan", "di", "ke", "dari", "ini", "itu", "ada", "adalah",
    "dengan", "untuk", "pada", "atau", "karena", "mereka", "kita",
    "akan", "bisa", "sangat", "salah", "satu", "para", "sebuah",
    "the", "a", "an", "of", "in", "on", "to", "and", "is", "are",
}


def search_terms(sentence: str, limit: int = 5) -> str:
    """Build a short stock-search phrase from meaningful narration words."""
    words = re.findall(r"[a-zA-ZÀ-ÿ0-9]+", sentence.lower())
    selected = [word for word in words if len(word) > 2 and word not in STOPWORDS]
    return " ".join(selected[:limit]) or "nature wildlife"


def _json_request(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "clode-video-skill/1.0"})
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise StockMediaError(f"Pixabay API request failed: {exc}") from exc


def download_pixabay_video(
    query: str, destination: Path, api_key: str, *, used_ids: set[int] | None = None
) -> dict:
    """Search Pixabay and download the best available MP4 for a query."""
    used_ids = used_ids if used_ids is not None else set()
    params = urlencode({
        "key": api_key, "q": query, "video_type": "film",
        "safesearch": "true", "per_page": 30, "order": "popular",
    })
    data = _json_request("https://pixabay.com/api/videos/?" + params)
    hits = data.get("hits", [])
    candidates = [hit for hit in hits if hit.get("id") not in used_ids and hit.get("videos", {}).get("medium", {}).get("url")]
    if not candidates:
        raise StockMediaError(f"No unused Pixabay video found for: {query}")
    candidates.sort(key=lambda hit: (hit.get("duration", 0) >= 3, hit.get("views", 0)), reverse=True)
    hit = candidates[0]
    video = hit["videos"].get("medium") or hit["videos"].get("small")
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(video["url"], headers={"User-Agent": "clode-video-skill/1.0"})
    try:
        with urlopen(request, timeout=90) as response, destination.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise StockMediaError(f"Could not download Pixabay clip for '{query}': {exc}") from exc
    if destination.stat().st_size < 1024:
        destination.unlink(missing_ok=True)
        raise StockMediaError(f"Downloaded clip is empty or invalid for: {query}")
    used_ids.add(hit["id"])
    return {
        "id": hit["id"], "page_url": hit.get("pageURL"),
        "creator": hit.get("user"), "tags": hit.get("tags", ""),
        "duration": hit.get("duration"), "query": query,
    }


def build_catalog(script: str, output_dir: str, api_key: str | None = None) -> dict:
    """Download one distinct stock clip per script sentence and write a catalog."""
    key = api_key or os.environ.get("PIXABAY_API_KEY")
    if not key:
        raise StockMediaError("PIXABAY_API_KEY is missing. Add it as a GitHub Actions secret.")
    scenes = split_script(script)
    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    assets, used_ids = [], set()
    for index, sentence in enumerate(scenes, start=1):
        query = search_terms(sentence)
        path = root / f"scene_{index:02d}.mp4"
        metadata = download_pixabay_video(query, path, key, used_ids=used_ids)
        duration = float(metadata.get("duration") or 0)
        if duration <= 0:
            raise StockMediaError(f"Pixabay returned an invalid duration for scene {index}.")
        assets.append({
            "path": str(path), "start": 0, "end": duration,
            "tags": [tag.strip().lower() for tag in metadata["tags"].split(",") if tag.strip()],
            "description": metadata["tags"],
            "source": "Pixabay", "source_page": metadata["page_url"],
            "creator": metadata["creator"], "search_query": query,
        })
        print(f"[{index}/{len(scenes)}] Downloaded: {query}", flush=True)
        time.sleep(0.15)
    catalog = {"assets": assets, "source": "Pixabay", "license_note": "Review Pixabay Content License and each asset page before publication."}
    catalog_path = root / "media_catalog.json"
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"catalog": str(catalog_path), "assets": len(assets), "source": "Pixabay"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Find and download Pixabay footage for each narration scene.")
    parser.add_argument("script", help="Narration script file.")
    parser.add_argument("--output-dir", default="media/downloaded")
    args = parser.parse_args()
    try:
        script = Path(args.script).read_text(encoding="utf-8")
        print(json.dumps(build_catalog(script, args.output_dir), ensure_ascii=False, indent=2))
    except (OSError, StockMediaError, ValueError) as exc:
        print(f"stock-media: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

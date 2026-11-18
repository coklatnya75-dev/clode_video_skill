"""Download reusable stock footage from Pixabay or Wikimedia Commons.

Pixabay is preferred when PIXABAY_API_KEY is configured. Without a key, the
module searches Wikimedia Commons for openly licensed video files.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
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
    "setelah", "selama", "demi", "agar", "tetap", "sang", "ayah",
    "the", "a", "an", "of", "in", "on", "to", "and", "is", "are",
}


def search_terms(sentence: str, limit: int = 5) -> str:
    """Build a short stock-search phrase from meaningful narration words."""
    words = re.findall(r"[a-zA-ZÀ-ÿ0-9]+", sentence.lower())
    selected = [word for word in words if len(word) > 2 and word not in STOPWORDS]
    return " ".join(selected[:limit]) or "wildlife nature"


def _json_request(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "clode-video-skill/1.0 (stock video downloader)"})
    try:
        with urlopen(request, timeout=40) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise StockMediaError(f"Video search request failed: {exc}") from exc


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": "clode-video-skill/1.0 (stock video downloader)"})
    try:
        with urlopen(request, timeout=120) as response, destination.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise StockMediaError(f"Could not download video: {exc}") from exc
    if destination.stat().st_size < 1024:
        destination.unlink(missing_ok=True)
        raise StockMediaError("Downloaded video is empty or invalid.")


def _probe_duration(path: Path) -> float:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            check=True, capture_output=True, text=True, timeout=45,
        )
        duration = float(result.stdout.strip())
    except (OSError, subprocess.CalledProcessError, ValueError, subprocess.TimeoutExpired) as exc:
        path.unlink(missing_ok=True)
        raise StockMediaError(f"Could not inspect downloaded video duration: {exc}") from exc
    if duration <= 0:
        path.unlink(missing_ok=True)
        raise StockMediaError("Downloaded video has no valid duration.")
    return duration


def download_pixabay_video(query: str, destination: Path, api_key: str, *, used_ids: set[int] | None = None) -> dict:
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
    _download(video["url"], destination)
    duration = float(hit.get("duration") or _probe_duration(destination))
    used_ids.add(hit["id"])
    return {
        "id": hit["id"], "page_url": hit.get("pageURL"),
        "creator": hit.get("user"), "tags": hit.get("tags", ""),
        "duration": duration, "query": query, "source": "Pixabay",
        "license": "Pixabay Content License; review asset page before publication",
    }


def download_commons_video(query: str, destination: Path, *, used_ids: set[str] | None = None) -> dict:
    """Search Wikimedia Commons for a downloadable openly licensed video."""
    used_ids = used_ids if used_ids is not None else set()
    params = urlencode({
        "action": "query", "format": "json", "formatversion": 2,
        "generator": "search", "gsrnamespace": 6, "gsrlimit": 30,
        "gsrsearch": f"filetype:video {query}",
        "prop": "imageinfo", "iiprop": "url|extmetadata|mime",
    })
    data = _json_request("https://commons.wikimedia.org/w/api.php?" + params)
    pages = data.get("query", {}).get("pages", [])
    allowed = ("cc0", "public domain", "cc by", "cc-by", "cc by-sa", "cc-by-sa")
    candidates = []
    for page in pages:
        title = page.get("title", "")
        if title in used_ids:
            continue
        info_list = page.get("imageinfo") or []
        if not info_list:
            continue
        info = info_list[0]
        mime = (info.get("mime") or "").lower()
        ext = Path(info.get("url", "").split("?")[0]).suffix.lower()
        if not mime.startswith("video/") and ext not in (".mp4", ".webm", ".ogv", ".ogg", ".mov"):
            continue
        metadata = info.get("extmetadata") or {}
        license_name = metadata.get("LicenseShortName", {}).get("value", "")
        license_url = metadata.get("LicenseUrl", {}).get("value", "")
        normalized = re.sub(r"<[^>]+>", "", license_name).lower()
        if not any(item in normalized for item in allowed):
            continue
        if not info.get("url"):
            continue
        candidates.append((page, info, license_name, license_url, metadata))
    if not candidates:
        raise StockMediaError(f"No openly licensed Wikimedia Commons video found for: {query}")
    page, info, license_name, license_url, metadata = candidates[0]
    source_url = info["url"]
    extension = Path(source_url.split("?")[0]).suffix.lower() or ".webm"
    destination = destination.with_suffix(extension)
    _download(source_url, destination)
    duration = _probe_duration(destination)
    used_ids.add(page.get("title", ""))
    description = re.sub(r"<[^>]+>", "", metadata.get("ImageDescription", {}).get("value", ""))
    creator = re.sub(r"<[^>]+>", "", metadata.get("Artist", {}).get("value", ""))
    return {
        "id": page.get("pageid"), "page_url": page.get("fullurl"),
        "creator": creator, "tags": f"{page.get('title', '')} {description}",
        "duration": duration, "query": query, "source": "Wikimedia Commons",
        "license": license_name, "license_url": license_url,
        "path": str(destination),
    }


def build_catalog(script: str, output_dir: str, api_key: str | None = None) -> dict:
    """Download one distinct clip per script sentence, using Pixabay or Commons."""
    key = api_key or os.environ.get("PIXABAY_API_KEY")
    provider = "Pixabay" if key else "Wikimedia Commons"
    scenes = split_script(script)
    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    assets, used_ids = [], set()
    for index, sentence in enumerate(scenes, start=1):
        query = search_terms(sentence)
        destination = root / f"scene_{index:02d}.mp4"
        if key:
            metadata = download_pixabay_video(query, destination, key, used_ids=used_ids)
            media_path = destination
        else:
            metadata = download_commons_video(query, destination, used_ids=used_ids)
            media_path = Path(metadata["path"])
        duration = float(metadata["duration"])
        tags = [tag.strip().lower() for tag in re.split(r"[,\s]+", metadata.get("tags", "")) if tag.strip()]
        assets.append({
            "path": str(media_path), "start": 0, "end": duration,
            "tags": tags, "description": metadata.get("tags", ""),
            "source": metadata["source"], "source_page": metadata.get("page_url"),
            "creator": metadata.get("creator"), "license": metadata.get("license"),
            "license_url": metadata.get("license_url"), "search_query": query,
        })
        print(f"[{index}/{len(scenes)}] Downloaded from {provider}: {query}", flush=True)
        time.sleep(0.2)
    catalog = {
        "assets": assets, "source": provider,
        "license_note": "Check every source page and comply with its stated license and attribution requirements before publishing.",
    }
    catalog_path = root / "media_catalog.json"
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"catalog": str(catalog_path), "assets": len(assets), "source": provider}


def main() -> int:
    parser = argparse.ArgumentParser(description="Download openly licensed stock footage for each narration scene.")
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

"""Optional BLIP image captioning for sampled video frames.

This describes representative still frames; it does not understand motion or
guarantee that a caption captures the whole clip.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

class VisualCaptionError(RuntimeError):
    """Raised for invalid catalog data or unavailable vision dependencies."""

def _load_caption_model(model_name: str, device: str):
    try:
        import torch
        from transformers import BlipForConditionalGeneration, BlipProcessor
    except ImportError as exc:
        raise VisualCaptionError(
            "Visual captioning needs optional packages: pip install torch transformers pillow"
        ) from exc
    selected = device
    if selected == "auto":
        selected = "cuda" if torch.cuda.is_available() else "cpu"
    if selected not in {"cpu", "cuda"}:
        raise VisualCaptionError("device must be auto, cpu, or cuda.")
    if selected == "cuda" and not torch.cuda.is_available():
        raise VisualCaptionError("CUDA was requested but is not available.")
    processor = BlipProcessor.from_pretrained(model_name)
    model = BlipForConditionalGeneration.from_pretrained(model_name).to(selected)
    model.eval()
    return processor, model, torch, selected

def caption_image(image_path: str | Path, *, model_name: str = "Salesforce/blip-image-captioning-base",
                 device: str = "auto", max_new_tokens: int = 40) -> str:
    """Generate one English caption for a local image using BLIP."""
    image_file = Path(image_path).expanduser()
    if not image_file.is_file():
        raise VisualCaptionError(f"Sample frame not found: {image_file}")
    if isinstance(max_new_tokens, bool) or not isinstance(max_new_tokens, int) or not 1 <= max_new_tokens <= 128:
        raise VisualCaptionError("max_new_tokens must be an integer from 1 to 128.")
    try:
        from PIL import Image
    except ImportError as exc:
        raise VisualCaptionError("Install Pillow: pip install pillow") from exc
    processor, model, torch, selected = _load_caption_model(model_name, device)
    try:
        with Image.open(image_file) as image:
            inputs = processor(images=image.convert("RGB"), return_tensors="pt")
        inputs = {key: value.to(selected) for key, value in inputs.items()}
        with torch.no_grad():
            output = model.generate(**inputs, max_new_tokens=max_new_tokens)
        caption = processor.decode(output[0], skip_special_tokens=True).strip()
    except Exception as exc:
        raise VisualCaptionError(f"Could not caption frame {image_file}: {exc}") from exc
    if not caption:
        raise VisualCaptionError(f"Vision model returned an empty caption for {image_file}")
    return caption

def caption_media_catalog(catalog: dict[str, Any], *, model_name: str = "Salesforce/blip-image-captioning-base",
                          device: str = "auto", max_new_tokens: int = 40) -> dict[str, Any]:
    """Add frame captions and an aggregate description to each catalog asset."""
    if not isinstance(catalog, dict) or not isinstance(catalog.get("assets"), list) or not catalog["assets"]:
        raise VisualCaptionError("Catalog must be an object containing a non-empty assets list.")
    # Load once and reuse the model for all sampled frames.
    try:
        import torch
        from transformers import BlipForConditionalGeneration, BlipProcessor
        from PIL import Image
    except ImportError as exc:
        raise VisualCaptionError("Install optional dependencies: pip install torch transformers pillow") from exc
    selected = device
    if selected == "auto":
        selected = "cuda" if torch.cuda.is_available() else "cpu"
    if selected not in {"cpu", "cuda"} or (selected == "cuda" and not torch.cuda.is_available()):
        raise VisualCaptionError("device must be auto, cpu, or available cuda.")
    processor = BlipProcessor.from_pretrained(model_name)
    model = BlipForConditionalGeneration.from_pretrained(model_name).to(selected)
    model.eval()
    for index, asset in enumerate(catalog["assets"]):
        if not isinstance(asset, dict):
            raise VisualCaptionError(f"assets[{index}] must be an object.")
        frames = asset.get("sample_frames", [])
        if not isinstance(frames, list):
            raise VisualCaptionError(f"assets[{index}].sample_frames must be a list.")
        captions = []
        for frame in frames:
            path = Path(frame).expanduser()
            if not path.is_file():
                raise VisualCaptionError(f"Sample frame not found: {path}")
            try:
                with Image.open(path) as image:
                    inputs = processor(images=image.convert("RGB"), return_tensors="pt")
                inputs = {key: value.to(selected) for key, value in inputs.items()}
                with torch.no_grad():
                    generated = model.generate(**inputs, max_new_tokens=max_new_tokens)
                caption = processor.decode(generated[0], skip_special_tokens=True).strip()
            except Exception as exc:
                raise VisualCaptionError(f"Could not caption {path}: {exc}") from exc
            if caption:
                captions.append(caption)
        asset["frame_captions"] = captions
        if captions:
            asset["description"] = " ".join(dict.fromkeys(captions))
        asset["caption_model"] = model_name
        asset["needs_visual_review"] = True
    catalog["captioning"] = {
        "method": "BLIP image captioning on sampled frames",
        "model": model_name,
        "notice": "Captions describe still samples, may be inaccurate, and do not describe motion. Review before use."
    }
    return catalog

def caption_catalog_file(catalog_path: str | Path, output_path: str | Path, **options) -> dict[str, Any]:
    source = Path(catalog_path).expanduser()
    try:
        catalog = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VisualCaptionError(f"Cannot read catalog {source}: {exc}") from exc
    result = caption_media_catalog(catalog, **options)
    destination = Path(output_path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result

def main() -> int:
    parser = argparse.ArgumentParser(description="Caption sampled frames in a video media catalog with BLIP.")
    parser.add_argument("catalog", help="media_catalog.json from video_editor.media_inspector")
    parser.add_argument("--output", default="output/media_inspection/media_catalog_captioned.json")
    parser.add_argument("--model", default="Salesforce/blip-image-captioning-base")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--max-new-tokens", type=int, default=40)
    args = parser.parse_args()
    try:
        result = caption_catalog_file(args.catalog, args.output, model_name=args.model,
                                      device=args.device, max_new_tokens=args.max_new_tokens)
    except (OSError, VisualCaptionError, ValueError) as exc:
        print(f"visual-captioner: {exc}", file=sys.stderr)
        return 1
    print(f"Captioned {len(result['assets'])} asset(s): {Path(args.output).resolve()}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

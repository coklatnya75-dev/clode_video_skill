"""Command-line entry point: python -m video_editor PLAN.json."""
import argparse
import sys

from .editor import VideoEditError, render_plan_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a short-form video from a JSON edit plan.")
    parser.add_argument("plan", help="Path to the JSON edit plan.")
    parser.add_argument("--timeout", type=int, default=3600, help="FFmpeg timeout in seconds.")
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error("--timeout must be a positive integer.")
    try:
        output = render_plan_file(args.plan, timeout=args.timeout)
    except (VideoEditError, OSError) as exc:
        print(f"video-editor: {exc}", file=sys.stderr)
        return 1
    print(f"Rendered: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# Video Editor MVP

A small FFmpeg-powered renderer for TikTok, YouTube Shorts, and Instagram Reels.
It can trim clips, concatenate them in order, center-crop/pad-to-fill them into
a vertical frame, burn SRT subtitles, and add an external voice-over/music track.

## Requirements

- Python 3.10+
- FFmpeg installed and available on `PATH` (including `libx264` and the subtitles
  filter / libass support).

No Python third-party packages are required.

## Example edit plan

Save as `edit_plan.json`:

```json
{
  "clips": [
    {"path": "media/intro.mp4", "start": 0, "end": 4.5},
    {"path": "media/main.mp4", "start": 2, "end": 12}
  ],
  "audio": "media/voiceover.mp3",
  "subtitles": "media/captions.srt",
  "output": {
    "path": "output/shorts.mp4",
    "width": 1080,
    "height": 1920,
    "fps": 30,
    "crf": 20,
    "preset": "medium"
  }
}
```

Run from the repository root:

```bash
python -c "from video_editor.editor import render_plan_file; print(render_plan_file('edit_plan.json'))"
```

Set `audio` or `subtitles` to `null` to omit that track. The external audio
track is mapped as the output audio and trimmed to the video duration.

## Scope and safety

This is the deterministic editing/rendering layer only. It does not yet generate
captions from speech, synthesize voice, generate video, or select music. Those
features need separate provider adapters and credentials configured outside the
repository (for example, environment variables or a secret manager). Never commit
API keys or media files containing private information.

Input paths in an edit plan must refer to local files available to the process.
The renderer invokes FFmpeg with an argument array (not through a shell) and
validates required files before rendering.

# Video Editor MVP

A small FFmpeg-powered renderer for TikTok, YouTube Shorts, and Instagram Reels.
It can trim clips, concatenate them in order, center-crop/pad-to-fill them into
a vertical frame, apply optional video/audio fades, burn SRT subtitles, and add
an external voice-over/music track.

## Requirements

- Python 3.10+
- FFmpeg installed and available on `PATH` (including `libx264` and the subtitles
  filter / libass support).
- Optional automatic transcription: install local Whisper with
  `pip install -U openai-whisper`. Whisper also requires FFmpeg.

The video renderer itself has no Python third-party dependencies. Whisper is
an optional dependency used only by the transcription command.

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
    "fade_in": 0.4,
    "fade_out": 0.6,
    "audio_fade_in": 0.2,
    "audio_fade_out": 0.5,
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
track is mapped as the output audio and trimmed to the video duration. Optional
fade controls (`fade_in`, `fade_out`, `audio_fade_in`, and
`audio_fade_out`) are specified in seconds in the output object. Fade
durations must fit within the total assembled clip duration; fade-in and fade-out
for the same stream may not overlap.

## Automatic subtitles with local Whisper

Install Whisper on the machine that will run the editor:

```bash
pip install -U openai-whisper
```

Generate an Indonesian SRT file from an audio or video file:

```bash
python -m video_editor.transcribe media/video.mp4
python -m video_editor.transcribe media/video.mp4 --model base --output-dir output
```

The default model is `small`; choose `tiny` or `base` for faster, less
resource-intensive runs, or larger models for potentially better accuracy.
Whisper downloads its model the first time it is used, so an internet connection
may be needed for that initial download. Transcription then runs locally.
Review the SRT for names, numbers, punctuation, and regional-language accuracy
before publishing. The generated SRT can be passed as the plan's `subtitles`
value and burned into the final video.

## Scope and safety

This adds speech-to-SRT transcription, not AI voice synthesis or generative
video. It does not select music or guarantee perfect transcription. Never commit
API keys or media files containing private information.

Input paths in an edit plan must refer to local files available to the process.
The renderer invokes FFmpeg with an argument array (not through a shell) and
validates required files before rendering.

## CLI and tests

The same renderer is available as a command-line module:

```bash
python -m video_editor edit_plan.json
python -m video_editor edit_plan.json --timeout 1800
```

Run the unit tests from the repository root:

```bash
python -m unittest discover -s tests -v
```

The tests cover plan validation, fade filter construction, missing-input handling,
and the Whisper adapter command using mocks. They do not replace an end-to-end
transcription or render test with real media files and local dependencies.

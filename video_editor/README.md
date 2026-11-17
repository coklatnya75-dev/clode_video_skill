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
- Optional neural voice-over: install `edge-tts` with `pip install edge-tts`
  and an active internet connection.

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

## Indonesian AI voice-over

Install the optional Edge TTS client:

```bash
pip install edge-tts
```

Generate a male Indonesian neural voice:

```bash
python -m video_editor.voiceover "Halo, selamat datang di video hari ini!" output/voiceover.mp3
```

Choose the female Indonesian voice and adjust delivery:

```bash
python -m video_editor.voiceover "Yuk, simak faktanya!" output/narasi.mp3 --voice id-ID-GadisNeural --rate +5% --pitch +1Hz
```

The default voice is `id-ID-ArdiNeural`; `id-ID-GadisNeural` is another
Indonesian voice option. Edge TTS sends text to Microsoft's online speech
service through the community client, so internet access is required and
availability/voice IDs may change. Do not submit confidential text. Check the
generated audio and pronunciation before publishing. The resulting MP3 can be
used as the edit plan's `audio` track.

## Scope and safety

The project now includes local Whisper transcription and an optional online
neural voice-over adapter. It still does not generate video scenes, select
music automatically, or guarantee perfect transcription/pronunciation. Never
commit API keys or media files containing private information.

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
and mocked Whisper/Edge TTS adapter commands. They do not replace end-to-end
transcription, speech synthesis, or rendering with real media and services.


## Script-to-storyboard planner

The planner turns a narration script into a reviewable scene list and an edit
plan that the FFmpeg renderer can consume. It splits the script at sentence
boundaries (blank lines are also supported), estimates narration duration from
word count, and pairs each scene with one clip from a media manifest.

Create `script.txt`:

```text
Gurita memiliki tiga jantung.
Darahnya berwarna biru karena mengandung hemocyanin.
```

Create `media.json` with exactly one entry per resulting scene. Each clip
needs a local path and an explicit source end time:

```json
[
  {"path": "media/octopus_intro.mp4", "start": 0, "end": 4},
  {"path": "media/octopus_underwater.mp4", "start": 2, "end": 7}
]
```

Generate the storyboard:

```bash
python -m video_editor.storyboard script.txt media.json --output storyboard.json --video-output output/shorts.mp4
```

The resulting JSON contains `scenes` (narration, estimated speaking time,
media mapping, and a pacing note) plus `edit_plan`. To render it, extract the
`edit_plan` object into a standalone JSON file, then run:

```bash
python -m video_editor edit_plan.json
```

Optional existing audio and subtitle files can be attached during planning with
`--audio output/narasi.mp3 --subtitles output/captions.srt`. The WPM estimate
can be adjusted with `--wpm 150`. Estimates are guidance only: actual speech
timing varies, and the planner does not measure clip duration or generate,
understand, or automatically select media. Review scene pacing and paths before
rendering. This milestone establishes a transparent, deterministic workflow;
semantic AI scene matching is a later feature.


## Tagged media matcher (keyword baseline)

The next workflow stage can suggest clips for each storyboard scene using a
catalog that you prepare. This first matcher is intentionally explainable: it
compares words in each narration sentence with the catalog's `tags` and
`description`, then writes a ranked-choice report and a media manifest.

Example `media_catalog.json`:

```json
[
  {
    "path": "media/laut.mp4",
    "start": 0,
    "end": 5,
    "tags": ["laut", "bawah laut", "ikan", "berenang"],
    "description": "pemandangan terumbu karang dan kehidupan bawah laut"
  },
  {
    "path": "media/gurita.mp4",
    "start": 1,
    "end": 7,
    "tags": ["gurita", "hewan", "tentakel"],
    "description": "gurita bergerak di dasar laut"
  }
]
```

Run after creating `storyboard.json`:

```bash
python -m video_editor.media_matcher storyboard.json media_catalog.json --output media_matches.json
```

The output contains per-scene suggestions, overlap scores, matched keywords,
and a `media_manifest` that can be passed to the storyboard planner. The
matcher does not inspect pixels, watch video, or understand visual context;
it only compares user-entered metadata. Each asset is used at most once by
default. Use `--allow-reuse` to permit reuse, and adjust
`--minimum-score 0.05` only if you understand the trade-off. Every suggestion
is flagged for human review before rendering.


## Automatic production pipeline

The pipeline now orchestrates the existing components in one command:
1. Split the narration into scene-sized sentences.
2. Match each scene to a tagged catalog asset.
3. Save the storyboard and match report.
4. Generate Indonesian voice-over with Edge TTS.
5. Transcribe that voice-over with local Whisper to create SRT subtitles.
6. Build the FFmpeg edit plan and optionally render the vertical MP4.

Example:

```bash
python -m video_editor.pipeline script.txt media_catalog.json \
  --output-video output/shorts.mp4 \
  --work-dir output/project
```

Prepare a catalog with one suitable, uniquely tagged media asset per sentence.
Example item:

```json
{
  "path": "media/gurita.mp4",
  "start": 0,
  "end": 6,
  "tags": ["gurita", "tentakel", "hewan laut"],
  "description": "Gurita berenang di dasar laut"
}
```

Use `--plan-only` to prepare the assets and edit plan without invoking FFmpeg.
The pipeline still generates voice-over and subtitles in plan-only mode.
Optional controls include `--voice id-ID-GadisNeural`, `--rate +5%`,
`--pitch +1Hz`, `--wpm 150`, and `--whisper-model base`.

Install the optional tools before running:

```bash
pip install edge-tts
pip install -U openai-whisper
```

FFmpeg must also be installed. Edge TTS requires internet access and sends the
script text to Microsoft's online speech service; Whisper runs locally after
its model is available. The media matcher uses user-provided tags and
descriptions, not computer vision. The pipeline does not download footage,
create original images, or guarantee narration/clip duration alignment.
Inspect the storyboard, generated voice, SRT timing, and final render before
publishing. If voice-over is shorter than the assembled footage, the current
renderer may end output at the shorter audio track because it uses
`-shortest`; adjust media trims or narration length after review.


## Video asset inspection and frame sampling

Before matching a script to your footage, scan a folder of local videos:

```bash
python -m video_editor.media_inspector media/ --output-dir output/media_inspection --samples 3
```

The tool uses FFprobe to collect duration, resolution, frame rate, and codec,
then FFmpeg to extract evenly spaced representative JPG frames. It writes
`output/media_inspection/media_catalog.json` with one asset per video,
including the source path, trim range, technical metadata, and sample-frame
paths. Open the sampled frames, then fill in each asset's `tags` and
`description` fields with accurate visual details. The matcher and production
pipeline accept this inspector report directly.

This is a media preparation/visual-review aid, not AI image recognition:
the tool does not infer objects, actions, or scene meaning from frames. No
external service receives your footage. Supported video extensions are MP4,
MOV, MKV, WEBM, AVI, and M4V. FFmpeg and FFprobe must be installed and
available on PATH.


## Optional AI visual captions for sampled frames

After inspecting a video folder and extracting sample frames, you can use the
optional BLIP image-captioning model to create draft descriptions:

```bash
pip install torch transformers pillow
python -m video_editor.visual_captioner output/media_inspection/media_catalog.json \
  --output output/media_inspection/media_catalog_captioned.json
```

The first run downloads the model `Salesforce/blip-image-captioning-base` from
Hugging Face and may require substantial disk space, memory, and internet access.
Use `--device cpu` to force CPU or `--device cuda` when a compatible CUDA
setup is available. The generated descriptions are added from the sampled
frames; existing tags are not invented or overwritten. You can review and edit
the descriptions/tags, then pass the captioned catalog directly to
`video_editor.media_matcher` or `video_editor.pipeline`.

This is a real image-captioning model, but it only sees a few still frames per
video. It may miss actions, context, objects between samples, and can produce
incorrect captions. Captions are generated locally after the model is
downloaded; no video or frame is uploaded by this tool. Always inspect the
sample frames and correct captions before using them to select footage.


### One-command pipeline with optional visual captioning

You can now pass the inspector report directly to the production pipeline and
enable BLIP captions as part of the workflow:

```bash
python -m video_editor.media_inspector media/ --output-dir output/inspection --samples 3

python -m video_editor.pipeline script.txt output/inspection/media_catalog.json \
  --auto-caption \
  --caption-device auto \
  --output-video output/shorts.mp4 \
  --work-dir output/project
```

With `--auto-caption`, the pipeline captions each sampled frame first, saves
`media_catalog_captioned.json` in the work directory, then matches the
narration scenes against the generated descriptions and any manually entered
tags. You can select a model with `--caption-model` and a device with
`--caption-device cpu` or `--caption-device cuda`. Omit `--auto-caption`
to use an already tagged catalog without loading the vision model.

Automatic captioning requires the optional `torch`, `transformers`, and
`pillow` packages and downloads model weights on first use. The pipeline also
continues to require Edge TTS, local Whisper, and FFmpeg for voice-over,
subtitles, and rendering. Caption matching remains a suggestion: review the
captioned catalog and every scene match before publishing.

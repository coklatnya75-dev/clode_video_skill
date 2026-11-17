"""Unit tests for edit-plan validation and command construction."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_editor.editor import VideoEditError, build_ffmpeg_command, validate_plan


class VideoEditorTests(unittest.TestCase):
    def base_plan(self, media: str) -> dict:
        return {
            "clips": [{"path": media, "start": 0, "end": 3}],
            "output": {"path": "out.mp4"},
        }

    def test_rejects_empty_clips(self):
        with self.assertRaises(VideoEditError):
            validate_plan({"clips": [], "output": {"path": "out.mp4"}})

    def test_rejects_odd_dimensions(self):
        plan = {"clips": [{"path": "x.mp4", "end": 2}],
                "output": {"path": "out.mp4", "width": 1079}}
        with self.assertRaisesRegex(VideoEditError, "even"):
            validate_plan(plan)

    def test_builds_vertical_render_command(self):
        with tempfile.TemporaryDirectory() as temp:
            media = Path(temp) / "input.mp4"
            media.touch()
            plan = self.base_plan(str(media))
            plan["output"]["path"] = str(Path(temp) / "out.mp4")
            with patch("video_editor.editor.shutil.which", return_value="/usr/bin/ffmpeg"):
                command = build_ffmpeg_command(plan)
            self.assertIn("1080:1920", " ".join(command))
            self.assertIn("libx264", command)
            self.assertIn("-an", command)

    def test_output_duration_trims_or_freeze_frames_scene(self):
        with tempfile.TemporaryDirectory() as temp:
            media = Path(temp) / "input.mp4"
            media.touch()
            plan = self.base_plan(str(media))
            plan["clips"][0]["output_duration"] = 5
            with patch("video_editor.editor.shutil.which", return_value="/usr/bin/ffmpeg"):
                command = build_ffmpeg_command(plan)
            graph = command[command.index("-filter_complex") + 1]
            self.assertIn("tpad=stop_mode=clone:stop_duration=2.0", graph)

    def test_fade_filters_are_added(self):
        with tempfile.TemporaryDirectory() as temp:
            media = Path(temp) / "input.mp4"
            audio = Path(temp) / "voice.mp3"
            media.touch()
            audio.touch()
            plan = self.base_plan(str(media))
            plan["audio"] = str(audio)
            plan["output"].update({
                "path": str(Path(temp) / "out.mp4"),
                "fade_in": 0.5,
                "fade_out": 1,
                "audio_fade_in": 0.25,
                "audio_fade_out": 0.75,
            })
            with patch("video_editor.editor.shutil.which", return_value="/usr/bin/ffmpeg"):
                command = build_ffmpeg_command(plan)
            graph = command[command.index("-filter_complex") + 1]
            self.assertIn("fade=t=in:st=0:d=0.5", graph)
            self.assertIn("fade=t=out:st=2.0:d=1.0", graph)
            self.assertIn("afade=t=in:st=0:d=0.25", graph)
            self.assertIn("afade=t=out:st=2.25:d=0.75", graph)
            self.assertIn("[aout]", graph)


    def test_builds_crossfade_transition_between_clips(self):
        with tempfile.TemporaryDirectory() as temp:
            first = Path(temp) / "first.mp4"
            second = Path(temp) / "second.mp4"
            first.touch()
            second.touch()
            plan = {
                "clips": [
                    {"path": str(first), "start": 0, "end": 3},
                    {"path": str(second), "start": 1, "end": 5},
                ],
                "output": {
                    "path": str(Path(temp) / "out.mp4"),
                    "transition": "dissolve",
                    "transition_duration": 0.5,
                    "fade_out": 0.5,
                },
            }
            with patch("video_editor.editor.shutil.which", return_value="/usr/bin/ffmpeg"):
                command = build_ffmpeg_command(plan)
            graph = command[command.index("-filter_complex") + 1]
            self.assertIn("xfade=transition=dissolve:duration=0.5:offset=2.5", graph)
            # Crossfade overlap reduces total duration from 7s to 6.5s.
            self.assertIn("fade=t=out:st=6.0:d=0.5", graph)

    def test_rejects_transition_longer_than_a_clip(self):
        plan = {
            "clips": [
                {"path": "a.mp4", "end": 2},
                {"path": "b.mp4", "end": 3},
            ],
            "output": {"path": "out.mp4", "transition_duration": 2.5},
        }
        with self.assertRaisesRegex(VideoEditError, "cannot exceed any clip"):
            validate_plan(plan)

    def test_rejects_overlapping_video_fades(self):
        plan = self.base_plan("input.mp4")
        plan["output"].update({"fade_in": 2, "fade_out": 2})
        with self.assertRaisesRegex(VideoEditError, "cannot overlap"):
            validate_plan(plan)

    def test_missing_media_is_reported(self):
        plan = self.base_plan("/path/that/does/not/exist.mp4")
        with patch("video_editor.editor.shutil.which", return_value="/usr/bin/ffmpeg"):
            with self.assertRaisesRegex(VideoEditError, "not found"):
                build_ffmpeg_command(plan)


if __name__ == "__main__":
    unittest.main()

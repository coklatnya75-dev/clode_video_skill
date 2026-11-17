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

    def test_missing_media_is_reported(self):
        plan = self.base_plan("/path/that/does/not/exist.mp4")
        with patch("video_editor.editor.shutil.which", return_value="/usr/bin/ffmpeg"):
            with self.assertRaisesRegex(VideoEditError, "not found"):
                build_ffmpeg_command(plan)


if __name__ == "__main__":
    unittest.main()

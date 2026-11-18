import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from video_editor.media_inspector import (
    MediaInspectionError,
    extract_sample_frames,
    inspect_media_directory,
    probe_video,
)


class MediaInspectorTests(unittest.TestCase):
    def test_probe_video_parses_metadata(self):
        payload = {
            "format": {"duration": "12.5"},
            "streams": [{
                "codec_type": "video", "codec_name": "h264",
                "width": 1920, "height": 1080, "avg_frame_rate": "30/1",
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "clip.mp4"
            source.touch()
            with patch("video_editor.media_inspector._run") as run:
                run.return_value = SimpleNamespace(stdout=json.dumps(payload))
                result = probe_video(source)
        self.assertEqual(result["duration"], 12.5)
        self.assertEqual(result["width"], 1920)

    def test_extract_frames_creates_sample_files(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "clip.mp4"
            source.touch()
            output = Path(directory) / "frames"
            def fake_run(command, timeout=120):
                Path(command[-1]).write_bytes(b"jpg")
                return SimpleNamespace(stdout="")
            with patch("video_editor.media_inspector._run", side_effect=fake_run):
                frames = extract_sample_frames(source, output, duration=10, samples=2)
            self.assertEqual(len(frames), 2)
            self.assertTrue(all(Path(frame).is_file() for frame in frames))

    def test_inspector_writes_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "media"
            source.mkdir()
            (source / "a.mp4").touch()
            output = Path(directory) / "report"
            metadata = {"duration": 8.0, "width": 1280, "height": 720, "frame_rate": "30/1", "codec": "h264"}
            with patch("video_editor.media_inspector.shutil.which", return_value="/usr/bin/tool"), \
                 patch("video_editor.media_inspector.probe_video", return_value=metadata), \
                 patch("video_editor.media_inspector.extract_sample_frames", return_value=["/tmp/frame.jpg"]):
                result = inspect_media_directory(source, output, samples=1)
            self.assertEqual(len(result["assets"]), 1)
            self.assertEqual(result["assets"][0]["tags"], [])
            self.assertTrue((output / "media_catalog.json").is_file())

    def test_segments_long_video_into_time_windows(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "media"
            source.mkdir()
            (source / "long.mp4").touch()
            output = Path(directory) / "report"
            metadata = {"duration": 8.0, "width": 1280, "height": 720, "frame_rate": "30/1", "codec": "h264"}
            calls = []
            def fake_frames(video, destination, **kwargs):
                calls.append(kwargs["start_time"])
                folder = Path(destination)
                folder.mkdir(parents=True, exist_ok=True)
                frame = folder / "frame.jpg"
                frame.write_bytes(b"jpg")
                return [str(frame)]
            with patch("video_editor.media_inspector.shutil.which", return_value="/usr/bin/tool"), \
                 patch("video_editor.media_inspector.probe_video", return_value=metadata), \
                 patch("video_editor.media_inspector.extract_sample_frames", side_effect=fake_frames):
                result = inspect_media_directory(source, output, samples=1, segment_duration=3)
            self.assertEqual([(a["start"], a["end"]) for a in result["assets"]],
                             [(0.0, 3.0), (3.0, 6.0), (6.0, 8.0)])
            self.assertEqual(calls, [0.0, 3.0, 6.0])

    def test_rejects_invalid_sample_count(self):
        with self.assertRaises(MediaInspectionError):
            extract_sample_frames("clip.mp4", "frames", duration=4, samples=0)


if __name__ == "__main__":
    unittest.main()

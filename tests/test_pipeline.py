import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_editor.pipeline import run_pipeline


class PipelineTests(unittest.TestCase):
    def test_pipeline_runs_all_stages_and_renders(self):
        catalog = [
            {"path": "media/sea.mp4", "start": 0, "end": 4, "tags": ["laut"], "description": "laut biru"},
            {"path": "media/octopus.mp4", "start": 0, "end": 5, "tags": ["gurita"], "description": "gurita"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            def fake_voice(text, path, **kwargs):
                Path(path).write_bytes(b"fake mp3")
                return str(Path(path))
            def fake_transcribe(media, **kwargs):
                target = Path(kwargs["output_dir"]) / "voiceover.srt"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("1\n00:00:00,000 --> 00:00:01,000\nTes\n", encoding="utf-8")
                return str(target)
            def fake_render(plan):
                return plan["output"]["path"]

            with patch("video_editor.pipeline.generate_voiceover", side_effect=fake_voice), \
                 patch("video_editor.pipeline.transcribe_to_srt", side_effect=fake_transcribe), \
                 patch("video_editor.pipeline.probe_audio_duration", return_value=6.25), \
                 patch("video_editor.pipeline.render_video", side_effect=fake_render):
                result = run_pipeline(
                    "Gurita hidup di laut. Gurita punya tentakel.",
                    catalog,
                    work_dir=directory,
                    output_video="final.mp4",
                )
            self.assertEqual(result["status"], "rendered")
            self.assertTrue(Path(result["edit_plan"]).is_file())
            self.assertEqual(result["video"], "final.mp4")
            import json
            plan = json.loads(Path(result["edit_plan"]).read_text(encoding="utf-8"))
            self.assertAlmostEqual(sum(clip["output_duration"] for clip in plan["clips"]), 6.25, places=3)

    def test_auto_caption_uses_captioned_inspector_catalog(self):
        catalog = {
            "assets": [
                {"path": "media/one.mp4", "start": 0, "end": 4,
                 "tags": ["gurita"], "description": "",
                 "sample_frames": ["/tmp/frame.jpg"]}
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            def fake_voice(text, path, **kwargs):
                Path(path).write_bytes(b"fake")
                return str(Path(path))
            def fake_transcribe(media, **kwargs):
                target = Path(kwargs["output_dir"]) / "voiceover.srt"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("subtitle", encoding="utf-8")
                return str(target)
            captioned = {
                "assets": [
                    {"path": "media/one.mp4", "start": 0, "end": 4,
                     "tags": ["gurita"], "description": "gurita berenang"}
                ]
            }
            with patch("video_editor.pipeline.caption_media_catalog", return_value=captioned) as caption_mock, \
                 patch("video_editor.pipeline.generate_voiceover", side_effect=fake_voice), \
                 patch("video_editor.pipeline.transcribe_to_srt", side_effect=fake_transcribe), \
                 patch("video_editor.pipeline.probe_audio_duration", return_value=3.0), \
                 patch("video_editor.pipeline.render_video"):
                result = run_pipeline(
                    "Gurita berenang di laut.", catalog,
                    work_dir=directory, auto_caption=True, render=False
                )
            caption_mock.assert_called_once()
            self.assertTrue(Path(result["captioned_catalog"]).is_file())
            self.assertEqual(result["status"], "plan_ready")

    def test_plan_only_skips_renderer(self):
        catalog = [
            {"path": "media/one.mp4", "start": 0, "end": 4, "tags": ["gurita"], "description": "gurita"}
        ]
        with tempfile.TemporaryDirectory() as directory:
            def fake_voice(text, path, **kwargs):
                Path(path).write_bytes(b"fake")
                return str(Path(path))
            def fake_transcribe(media, **kwargs):
                target = Path(kwargs["output_dir"]) / "voiceover.srt"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("subtitle", encoding="utf-8")
                return str(target)
            with patch("video_editor.pipeline.generate_voiceover", side_effect=fake_voice), \
                 patch("video_editor.pipeline.transcribe_to_srt", side_effect=fake_transcribe), \
                 patch("video_editor.pipeline.probe_audio_duration", return_value=3.0), \
                 patch("video_editor.pipeline.render_video") as render_mock:
                result = run_pipeline("Gurita hidup di laut.", catalog, work_dir=directory, render=False)
            render_mock.assert_not_called()
            self.assertEqual(result["status"], "plan_ready")


if __name__ == "__main__":
    unittest.main()

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
                 patch("video_editor.pipeline.render_video") as render_mock:
                result = run_pipeline("Gurita hidup di laut.", catalog, work_dir=directory, render=False)
            render_mock.assert_not_called()
            self.assertEqual(result["status"], "plan_ready")


if __name__ == "__main__":
    unittest.main()

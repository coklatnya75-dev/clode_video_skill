"""Tests for the optional local Whisper subtitle adapter."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_editor.transcribe import TranscriptionError, transcribe_to_srt


class TranscriptionTests(unittest.TestCase):
    def test_missing_media_is_reported(self):
        with self.assertRaisesRegex(TranscriptionError, "not found"):
            transcribe_to_srt("/missing/media.mp4")

    def test_whisper_command_creates_srt(self):
        with tempfile.TemporaryDirectory() as temp:
            media = Path(temp) / "contoh.mp4"
            media.touch()
            def fake_run(command, **kwargs):
                Path(command[command.index("--output_dir") + 1], "contoh.srt").write_text(
                    "1\\n00:00:00,000 --> 00:00:01,000\\nHalo dunia.\\n",
                    encoding="utf-8",
                )
            with patch("video_editor.transcribe.shutil.which", return_value="/usr/bin/whisper"):
                with patch("video_editor.transcribe.subprocess.run", side_effect=fake_run) as run:
                    result = transcribe_to_srt(str(media))
            self.assertTrue(Path(result).is_file())
            command = run.call_args.args[0]
            self.assertIn("Indonesian", command)
            self.assertIn("--output_format", command)
            self.assertIn("srt", command)

    def test_missing_whisper_is_actionable(self):
        with tempfile.TemporaryDirectory() as temp:
            media = Path(temp) / "voice.wav"
            media.touch()
            with patch("video_editor.transcribe.shutil.which", return_value=None):
                with self.assertRaisesRegex(TranscriptionError, "pip install"):
                    transcribe_to_srt(str(media))


if __name__ == "__main__":
    unittest.main()

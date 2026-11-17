"""Tests for the optional Edge TTS voice-over adapter."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_editor.voiceover import VoiceoverError, generate_voiceover


class VoiceoverTests(unittest.TestCase):
    def test_rejects_empty_text(self):
        with self.assertRaisesRegex(VoiceoverError, "must not be empty"):
            generate_voiceover("  ", "voice.mp3")

    def test_rejects_non_mp3_output(self):
        with self.assertRaisesRegex(VoiceoverError, ".mp3"):
            generate_voiceover("Halo", "voice.wav")

    def test_generates_mp3_using_requested_voice(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "hasil.mp3"

            def fake_run(command, **kwargs):
                Path(command[command.index("--write-media") + 1]).write_bytes(b"fake-mp3")

            with patch("video_editor.voiceover.shutil.which", return_value="/usr/bin/edge-tts"):
                with patch("video_editor.voiceover.subprocess.run", side_effect=fake_run) as run:
                    result = generate_voiceover(
                        "Halo semuanya!", str(destination), voice="id-ID-GadisNeural",
                        rate="+5%", pitch="+1Hz",
                    )

            self.assertEqual(result, str(destination.resolve()))
            command = run.call_args.args[0]
            self.assertIn("id-ID-GadisNeural", command)
            self.assertIn("Halo semuanya!", command)
            self.assertTrue(destination.is_file())

    def test_missing_edge_tts_is_actionable(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch("video_editor.voiceover.shutil.which", return_value=None):
                with self.assertRaisesRegex(VoiceoverError, "pip install edge-tts"):
                    generate_voiceover("Halo", str(Path(temp) / "voice.mp3"))


if __name__ == "__main__":
    unittest.main()

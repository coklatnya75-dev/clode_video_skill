import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_editor.visual_captioner import VisualCaptionError, caption_media_catalog

class VisualCaptionerTests(unittest.TestCase):
    def test_rejects_invalid_catalog(self):
        with self.assertRaises(VisualCaptionError):
            caption_media_catalog({"assets": []})

    def test_adds_frame_captions_to_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            frame = Path(directory) / "frame.jpg"
            frame.write_bytes(b"placeholder")
            catalog = {"assets": [{"path": "clip.mp4", "sample_frames": [str(frame)], "tags": []}]}
            class FakeTorch:
                class cuda:
                    @staticmethod
                    def is_available(): return False
                class no_grad:
                    def __enter__(self): return self
                    def __exit__(self, *args): return False
            class FakeImage:
                def __init__(self): pass
                def convert(self, mode): return self
                def __enter__(self): return self
                def __exit__(self, *args): return False
            class FakeImageModule:
                @staticmethod
                def open(path): return FakeImage()
            class FakeProcessor:
                def __call__(self, **kwargs): return {"pixel_values": FakeTensor()}
                def decode(self, output, skip_special_tokens=True): return "an octopus underwater"
            class FakeTensor:
                def to(self, device): return self
            class FakeModel:
                def to(self, device): return self
                def eval(self): pass
                def generate(self, **kwargs): return ["caption"]
            with patch.dict("sys.modules", {
                "torch": FakeTorch,
                "transformers": type("Transformers", (), {
                    "BlipProcessor": type("BP", (), {"from_pretrained": staticmethod(lambda name: FakeProcessor())}),
                    "BlipForConditionalGeneration": type("BM", (), {"from_pretrained": staticmethod(lambda name: FakeModel())})
                }),
                "PIL": type("PIL", (), {"Image": FakeImageModule})
            }):
                result = caption_media_catalog(catalog)
            self.assertEqual(result["assets"][0]["description"], "an octopus underwater")
            self.assertTrue(result["assets"][0]["needs_visual_review"])

if __name__ == "__main__":
    unittest.main()

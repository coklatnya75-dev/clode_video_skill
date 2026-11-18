import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_editor.stock_media import build_catalog, search_terms


class StockMediaTests(unittest.TestCase):
    def test_search_terms_uses_meaningful_words(self):
        self.assertEqual(search_terms("Penguin kaisar menjaga telur di Antarktika"), "penguin kaisar menjaga telur antarktika")

    def test_build_catalog_uses_commons_without_pixabay_key(self):
        def fake_download(query, destination, *, used_ids=None):
            destination = destination.with_suffix(".webm")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"x" * 2048)
            used_ids.add("File:Penguin.webm")
            return {
                "id": 1, "page_url": "https://commons.wikimedia.org/wiki/File:Penguin.webm",
                "creator": "Sample", "tags": "penguin antarctica",
                "duration": 12, "source": "Wikimedia Commons",
                "license": "CC BY-SA 4.0", "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
                "path": str(destination),
            }

        with tempfile.TemporaryDirectory() as directory, patch(
            "video_editor.stock_media.download_commons_video", side_effect=fake_download
        ), patch.dict("os.environ", {}, clear=True):
            result = build_catalog(
                "Penguin hidup di Antarktika. Penguin jantan menjaga telur.",
                directory,
            )
            self.assertEqual(result["assets"], 2)
            self.assertEqual(result["source"], "Wikimedia Commons")
            catalog = Path(result["catalog"]).read_text(encoding="utf-8")
            self.assertIn("scene_01.webm", catalog)
            self.assertIn("CC BY-SA 4.0", catalog)

    def test_pixabay_key_selects_pixabay_provider(self):
        def fake_download(query, destination, api_key, *, used_ids=None):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"x" * 2048)
            used_ids.add(123)
            return {
                "id": 123, "page_url": "https://pixabay.com/videos/example/",
                "creator": "Sample", "tags": "penguin, antarctica",
                "duration": 12, "source": "Pixabay", "license": "Pixabay Content License",
            }

        with tempfile.TemporaryDirectory() as directory, patch(
            "video_editor.stock_media.download_pixabay_video", side_effect=fake_download
        ):
            result = build_catalog("Penguin hidup di Antarktika.", directory, api_key="test-key")
            self.assertEqual(result["source"], "Pixabay")


if __name__ == "__main__":
    unittest.main()

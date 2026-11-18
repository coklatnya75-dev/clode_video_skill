import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_editor.stock_media import StockMediaError, build_catalog, search_terms


class StockMediaTests(unittest.TestCase):
    def test_search_terms_uses_meaningful_words(self):
        self.assertEqual(search_terms("Penguin kaisar menjaga telur di Antarktika"), "penguin kaisar menjaga telur Antarktika")

    def test_build_catalog_downloads_one_distinct_clip_per_sentence(self):
        def fake_download(query, destination, api_key, *, used_ids=None):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"x" * 2048)
            asset_id = len(used_ids) + 1
            used_ids.add(asset_id)
            return {
                "id": asset_id, "page_url": f"https://pixabay.com/videos/{asset_id}/",
                "creator": "sample", "tags": "penguin, antarctica",
                "duration": 12,
            }

        with tempfile.TemporaryDirectory() as directory, patch(
            "video_editor.stock_media.download_pixabay_video", side_effect=fake_download
        ):
            result = build_catalog(
                "Penguin hidup di Antarktika. Penguin jantan menjaga telur.",
                directory, api_key="test-key",
            )
            self.assertEqual(result["assets"], 2)
            catalog = Path(result["catalog"]).read_text(encoding="utf-8")
            self.assertIn("scene_01.mp4", catalog)
            self.assertIn("scene_02.mp4", catalog)

    def test_missing_api_key_fails_with_actionable_message(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(StockMediaError, "PIXABAY_API_KEY"):
                build_catalog("Penguin hidup di Antarktika.", "unused")


if __name__ == "__main__":
    unittest.main()

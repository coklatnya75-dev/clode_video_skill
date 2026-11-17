import unittest

from video_editor.media_matcher import MediaMatchError, match_media_to_scenes


class MediaMatcherTests(unittest.TestCase):
    def setUp(self):
        self.scenes = [
            {"scene": 1, "narration": "Gurita berenang di dalam laut."},
            {"scene": 2, "narration": "Gurita memiliki tiga jantung."},
        ]
        self.catalog = [
            {"path": "ocean.mp4", "start": 0, "end": 4, "tags": ["laut", "berenang"], "description": "pemandangan bawah laut"},
            {"path": "octopus.mp4", "start": 1, "end": 5, "tags": ["gurita", "hewan"], "description": "gurita bergerak"},
        ]

    def test_matches_by_keyword_and_returns_manifest(self):
        result = match_media_to_scenes(self.scenes, self.catalog)
        self.assertEqual(result["media_manifest"][0]["path"], "ocean.mp4")
        self.assertEqual(result["media_manifest"][1]["path"], "octopus.mp4")
        self.assertTrue(all(match["review_required"] for match in result["matches"]))

    def test_accepts_inspector_report_object(self):
        report = {"assets": self.catalog}
        result = match_media_to_scenes(self.scenes, report)
        self.assertEqual(result["media_manifest"][0]["path"], "ocean.mp4")

    def test_rejects_unmatched_scene(self):
        with self.assertRaises(MediaMatchError):
            match_media_to_scenes(
                [{"narration": "Sejarah kerajaan kuno"}],
                self.catalog,
            )

    def test_prevents_reuse_by_default(self):
        with self.assertRaises(MediaMatchError):
            match_media_to_scenes(
                [{"narration": "gurita laut"}, {"narration": "gurita laut"}],
                [self.catalog[0]],
            )

    def test_can_allow_reuse(self):
        result = match_media_to_scenes(
            [{"narration": "gurita laut"}, {"narration": "gurita laut"}],
            [self.catalog[0]],
            allow_reuse=True,
        )
        self.assertEqual(len(result["media_manifest"]), 2)


if __name__ == "__main__":
    unittest.main()

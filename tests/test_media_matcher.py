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


    def test_semantic_matching_can_match_cross_language_descriptions(self):
        class FakeVectors:
            def __getitem__(self, key):
                return self
            def __matmul__(self, other):
                return [0.95, 0.0]

        class FakeEncoder:
            def encode(self, texts, **kwargs):
                # Query is Indonesian; first catalog description is an English
                # paraphrase and is deliberately close in embedding space.
                return FakeVectors()

        scenes = [{"scene": 1, "narration": "Makhluk laut bergerak di samudra."}]
        catalog = [
            {"path": "underwater.mp4", "start": 0, "end": 4,
             "tags": ["ocean animal"], "description": "an animal swimming underwater"},
            {"path": "castle.mp4", "start": 0, "end": 4,
             "tags": ["old building"], "description": "a medieval stone castle"},
        ]
        result = match_media_to_scenes(
            scenes, catalog, semantic_match=True, minimum_score=0.1,
            _semantic_encoder=FakeEncoder(),
        )
        self.assertEqual(result["media_manifest"][0]["path"], "underwater.mp4")
        self.assertEqual(result["method"], "hybrid_keyword_multilingual_semantic")
        self.assertGreater(result["matches"][0]["semantic_similarity"], 0.9)

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

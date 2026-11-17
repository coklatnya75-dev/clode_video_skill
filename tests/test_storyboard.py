import unittest

from video_editor.storyboard import StoryboardError, build_storyboard, split_script


class StoryboardTests(unittest.TestCase):
    def test_split_script_by_sentences_and_paragraphs(self):
        self.assertEqual(
            split_script("Halo semua. Ini fakta unik!\n\nSampai jumpa."),
            ["Halo semua.", "Ini fakta unik!", "Sampai jumpa."],
        )

    def test_builds_renderer_compatible_plan(self):
        result = build_storyboard(
            "Gurita punya tiga jantung. Darahnya berwarna biru.",
            [
                {"path": "media/a.mp4", "start": 0, "end": 3},
                {"path": "media/b.mp4", "start": 1, "end": 5},
            ],
            audio_path="output/narasi.mp3",
        )
        self.assertEqual(len(result["scenes"]), 2)
        self.assertEqual(result["edit_plan"]["clips"][1]["end"], 5)
        self.assertEqual(result["edit_plan"]["audio"], "output/narasi.mp3")
        self.assertEqual(result["edit_plan"]["output"]["width"], 1080)

    def test_requires_exact_media_scene_mapping(self):
        with self.assertRaises(StoryboardError):
            build_storyboard("Satu kalimat. Kalimat kedua.", [{"path": "a.mp4", "end": 3}])

    def test_rejects_invalid_clip_range(self):
        with self.assertRaises(StoryboardError):
            build_storyboard("Satu kalimat.", [{"path": "a.mp4", "start": 4, "end": 3}])


if __name__ == "__main__":
    unittest.main()

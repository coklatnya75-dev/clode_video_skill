import unittest

from video_editor.storyboard import StoryboardError, build_storyboard, split_script, sync_storyboard_to_duration


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

    def test_syncs_scene_durations_to_measured_voiceover(self):
        result = build_storyboard(
            "Satu dua tiga empat. Lima enam.",
            [
                {"path": "a.mp4", "start": 0, "end": 2},
                {"path": "b.mp4", "start": 0, "end": 2},
            ],
        )
        synced = sync_storyboard_to_duration(result, 10.0)
        durations = [clip["output_duration"] for clip in synced["edit_plan"]["clips"]]
        self.assertAlmostEqual(sum(durations), 10.0, places=3)
        self.assertAlmostEqual(durations[0] / durations[1], 2.0, places=2)
        self.assertEqual(synced["voiceover_duration_seconds"], 10.0)

    def test_rejects_non_positive_voiceover_duration(self):
        result = build_storyboard("Satu kalimat.", [{"path": "a.mp4", "start": 0, "end": 2}])
        with self.assertRaises(StoryboardError):
            sync_storyboard_to_duration(result, 0)

    def test_requires_exact_media_scene_mapping(self):
        with self.assertRaises(StoryboardError):
            build_storyboard("Satu kalimat. Kalimat kedua.", [{"path": "a.mp4", "end": 3}])

    def test_rejects_invalid_clip_range(self):
        with self.assertRaises(StoryboardError):
            build_storyboard("Satu kalimat.", [{"path": "a.mp4", "start": 4, "end": 3}])


if __name__ == "__main__":
    unittest.main()

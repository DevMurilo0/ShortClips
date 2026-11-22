import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from shortforge import media
from shortforge.scoring import pick_segments


class SmartClipTests(unittest.TestCase):
    def test_sustained_audio_and_nonoverlap(self):
        # Um pico de 1 segundo não deve dominar uma cena inteira de 45s.
        energy = [0.12] * 600
        energy[130] = 10.0
        for i in range(300, 345):
            energy[i] = 1.6
        clips = pick_segments(600, count=3, clip_seconds=45, energies=energy)
        self.assertTrue(clips)
        self.assertTrue(all(30 <= c.length <= 60 for c in clips))
        self.assertTrue(any(c.start <= 320 < c.end for c in clips))
        for a, b in zip(clips, clips[1:]):
            self.assertLessEqual(a.end, b.start)

    def test_caption_cards_short_and_monotonic(self):
        words = [
            SimpleNamespace(word=word, start=i * .36, end=(i + 1) * .36)
            for i, word in enumerate(
                "Olha só esse jogo como ficou incrível cara isso é muito bom mesmo".split()
            )
        ]
        segment = SimpleNamespace(start=0, end=len(words)*.36, text="", words=words)
        model = SimpleNamespace(transcribe=lambda *args, **kw: ([segment], None))
        with tempfile.TemporaryDirectory() as tmp, patch.object(media, 'ffprobe',
                                                                return_value={'duration':45}):
            target = Path(tmp)/"legendas.srt"
            count = media.make_srt(model, Path("source.mp4"), target, lambda _:None)
            cues = media.validate_srt(target, 45)
            self.assertEqual(count, len(cues))
            self.assertGreater(count, 1)
            self.assertTrue(all(len(cue_text.replace("\n", " ").split()) <= 5
                                for _, _, cue_text in cues))
            self.assertTrue(all(len(line) <= 26 for _, _, cue_text in cues
                                for line in cue_text.splitlines()))
            self.assertTrue(all(start < end for start, end, _ in cues))

    def test_subtitle_style_scales_and_stays_vertical(self):
        for width in (720,1080):
            rendered = media.build_filters((4,4,200,200), width)
            self.assertIn("Bold=1", rendered)
            self.assertIn("Outline=3", rendered)
            self.assertIn("vstack=inputs=2", rendered)


if __name__ == "__main__":
    unittest.main()

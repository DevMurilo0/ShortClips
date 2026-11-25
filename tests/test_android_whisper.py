import unittest
from unittest.mock import patch
from shortforge.android_whisper import parse_segments
from shortforge import pipeline

class AndroidWhisperTests(unittest.TestCase):
    def test_offsets_are_milliseconds(self):
        segments=parse_segments({'transcription':[{'offsets':{'from':1200,'to':2900},'text':' Olá mundo '}]})
        self.assertEqual((segments[0].start,segments[0].end,segments[0].text),(1.2,2.9,'Olá mundo'))
        self.assertIsNone(segments[0].words)

    def test_empty_transcript(self):
        self.assertEqual(parse_segments({'transcription':[]}),[])
        with self.assertRaises(RuntimeError):
            parse_segments({})

    def test_invalid_timestamps(self):
        with self.assertRaises(RuntimeError):
            parse_segments({'transcription':[{'offsets':{'from':'nan','to':1000},'text':'x'}]})

    def test_native_dispatch(self):
        with patch.dict('os.environ',{'SHORTFORGE_ANDROID_NATIVE':'1'}), patch('shortforge.android_whisper.AndroidWhisper') as engine:
            self.assertIs(pipeline._load_whisper('tiny'),engine.return_value)
            engine.assert_called_once_with('tiny')

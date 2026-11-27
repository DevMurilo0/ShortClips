import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from shortforge import youtube_upload as y

class YoutubeTests(unittest.TestCase):
    def test_options_requires_explicit_consent(self):
        with patch.object(y,'connected',return_value={'id':'abc','title':'Canal'}):
            p=dict(enabled=True,channel='abc',privacy='private',interval=0,made_for_kids=False)
            with self.assertRaises(ValueError): y.options(p)
            p['confirmed']=True
            self.assertEqual(y.options(p)['channel'],'abc')
            p['channel']='other'
            with self.assertRaises(ValueError): y.options(p)

    def test_metadata(self):
        job=SimpleNamespace(title='A'*200,url='https://youtu.be/abcdefghijk')
        m=y.metadata(job,{'number':1},{'privacy':'private','made_for_kids':False})
        self.assertLessEqual(len(m['snippet']['title']),100)
        self.assertEqual(m['status']['privacyStatus'],'private')

    def test_session_host(self):
        with self.assertRaises(RuntimeError): y.check_session('https://evil.example/upload/youtube/v3/videos')
        self.assertTrue(y.check_session('https://www.googleapis.com/upload/youtube/v3/videos?upload_id=a'))

    def test_enqueue_only_completed_and_dedup(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);path=root/'short_01.mp4';path.write_bytes(b'test')
            job=SimpleNamespace(id='abc',title='x',url='https://youtu.be/abcdefghijk',count=1,status='partial',destination=root,
                youtube=dict(channel='abc',privacy='private',interval=0,made_for_kids=False),clips=[dict(number=1,name=path.name,status='ready',audio=True,subtitles_burned=True)])
            with patch.object(y,'HOME',root/'private'):
                y.enqueue(job);self.assertEqual(y.status('abc'),[])
                job.status='completed';y.enqueue(job);y.enqueue(job)
                self.assertEqual(len(y.status('abc')),1)

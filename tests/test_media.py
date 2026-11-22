import concurrent.futures
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from shortforge import media
from shortforge.runtime import cancel_event, Cancelled

class MediaTests(unittest.TestCase):
    def test_timestamps(self):
        self.assertEqual(media.srt_time(3661.025),'01:01:01,025')
        self.assertEqual(media.srt_time(59.9999),'00:01:00,000')
        self.assertEqual(media.timestamp(712.8),'00:11:52.800')
        for x in (-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):media.timestamp(x)

    def test_srt_generation_and_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'legendas.srt'
            segment=SimpleNamespace(start=0,end=6,text='ação çãõ <b> {teste} '+'a'*100,words=None)
            model=SimpleNamespace(transcribe=lambda *a,**k:([segment],None))
            with patch.object(media,'ffprobe',return_value={'duration':45}):
                count=media.make_srt(model,Path('source'),p,lambda m:None)
            cues=media.validate_srt(p,45)
            self.assertEqual(count,len(cues));self.assertIn('ação',p.read_text())
            import html
            self.assertTrue(all(len(html.unescape(line))<=28 for a,b,t in cues for line in t.splitlines()))
            self.assertTrue(all(len(t.splitlines())<=2 for a,b,t in cues))
            for raw in ('','1\n00:60:00,000 --> 00:60:01,000\nOi',
                        '1\n00:00:02,000 --> 00:00:01,000\nOi',
                        '1\n00:00:00,000 --> 00:01:00,000\nOi'):
                p.write_text(raw)
                with self.assertRaises(ValueError):media.validate_srt(p,45)

    def test_silent_transcript_fails(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(media,'ffprobe',return_value={'duration':45}):
            with self.assertRaisesRegex(RuntimeError,'não encontrou fala'):
                media.make_srt(SimpleNamespace(transcribe=lambda *a,**k:([],None)),Path('x'),Path(tmp)/'x.srt',lambda m:None)

    def test_filter_build(self):
        for width in (720,1080):
            f=media.build_filters((10,20,200,180),width)
            self.assertIn('subtitles=filename=captions.srt',f)
            self.assertIn('vstack=inputs=2',f)
            self.assertIn('force_original_aspect_ratio=decrease',f)
            self.assertIn(f'crop={width}:{width*8//9}',f)

    def test_paths_and_isolated_render_directories(self):
        with tempfile.TemporaryDirectory(prefix="ação [x], d'água: ") as tmp:
            root=Path(tmp); calls=[]; barrier=threading.Barrier(2)
            def fake_run(cmd,**kw):
                cwd=kw['cwd'];self.assertTrue((cwd/'captions.srt').is_file())
                self.assertEqual((cwd/'captions.srt').read_text(),'1\n00:00:00,000 --> 00:00:01,000\nOlá\n')
                calls.append(cwd);barrier.wait(timeout=5)
                Path(cmd[-1]).write_bytes(b'mp4')
            src=root/'vídeo.mp4';src.touch()
            srt=root/"outra 'legenda', [x]: ç.srt";srt.write_text('1\n00:00:00,000 --> 00:00:01,000\nOlá\n')
            probe={'duration':45,'width':1280,'height':720,'has_audio':True}
            with patch.object(media,'ffprobe',return_value=probe),patch.object(media,'run',side_effect=fake_run),patch.object(media,'validate_output',return_value=probe):
                with concurrent.futures.ThreadPoolExecutor(2) as pool:
                    fs=[pool.submit(media.render_split,src,srt,root/f'short{i}.mp4',(0,0,200,200),720,lambda m:None) for i in range(2)]
                    for f in fs:f.result()
            self.assertNotEqual(*calls);self.assertTrue(all(not c.exists() for c in calls))

    def test_missing_srt_fails_before_render(self):
        with patch.object(media,'ffprobe',return_value={'duration':45,'has_audio':True}):
            with self.assertRaises(FileNotFoundError):
                media.render_split(Path('x'),Path('/nonexistent/caption.srt'),Path('out'),(0,0,10,10),720,None)

    def test_output_requires_audio_and_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'x.mp4';path.write_bytes(b'x')
            for duration,audio in ((5,True),(61,True),(45,False)):
                with patch.object(media,'ffprobe',return_value={'duration':duration,'has_audio':audio,'has_video':True,'width':720,'height':1280,'streams':[]}):
                    with self.assertRaises(RuntimeError):media.validate_output(path,decode=False)

    def test_subprocess_failure_and_cancellation(self):
        import sys
        with self.assertRaisesRegex(RuntimeError,'erro real'):
            media.run([sys.executable,'-c',"import sys;sys.stderr.write('erro real');sys.exit(3)"])
        event=threading.Event();token=cancel_event.set(event)
        timer=threading.Timer(.3,event.set);timer.start();start=time.monotonic()
        try:
            with self.assertRaises(Cancelled):media.run([sys.executable,'-c','import time;time.sleep(30)'])
            self.assertLess(time.monotonic()-start,3)
        finally:cancel_event.reset(token);timer.join()

    def test_no_facecam_detectable(self):
        import cv2
        import numpy as np
        class Capture:
            def isOpened(self):return True
            def get(self,key):return {cv2.CAP_PROP_FRAME_WIDTH:640,cv2.CAP_PROP_FRAME_HEIGHT:360,cv2.CAP_PROP_FRAME_COUNT:1350,cv2.CAP_PROP_FPS:30}.get(key,0)
            def set(self,*a):pass
            def read(self):return True,np.zeros((360,640,3),dtype=np.uint8)
            def release(self):pass
        with patch.object(cv2,'VideoCapture',return_value=Capture()):
            with self.assertRaises(media.FacecamNotFound):media.identify_facecam(Path('blank'))
            box,description=media.identify_facecam(Path('blank'),manual_box=[.7,.4,.2,.3])
            self.assertIn('manualmente',description)

    def test_real_pyav_whisper_audio_compatibility(self):
        import av
        import wave
        import numpy as np
        from faster_whisper.audio import decode_audio
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'audio.wav'
            with wave.open(str(p),'wb') as f:
                f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(np.zeros(16000,dtype='<i2').tobytes())
            with av.open(str(p),metadata_errors='ignore') as container:
                self.assertIsNotNone(container.streams.audio)
            self.assertEqual(len(decode_audio(str(p))),16000)

class SceneTests(unittest.TestCase):
    def test_visual_gate_and_moving_gameplay(self):
        import cv2
        import numpy as np
        class Capture:
            def __init__(self,mode):self.mode=mode;self.rng=np.random.default_rng(123)
            def isOpened(self):return True
            def get(self,k):return 1350 if k==cv2.CAP_PROP_FRAME_COUNT else 30
            def set(self,*a):pass
            def release(self):pass
            def read(self):
                frame=self.rng.integers(25,255,(180,320,3),dtype=np.uint8)
                if self.mode=='static':frame[:]=80
                if self.mode=='insert':
                    frame[:,:30]=0;frame[:,-30:]=0;frame[78:120,-30:]=150
                return True,frame
        for mode in ('insert','static'):
            with patch.object(cv2,'VideoCapture',return_value=Capture(mode)),patch.object(media,'menu_header_text',return_value=''):
                with self.assertRaises(media.UnsuitableScene):media.assess_scene(Path('x'))
        with patch.object(cv2,'VideoCapture',return_value=Capture('game')),patch.object(media,'menu_header_text',return_value=''):
            metrics=media.assess_scene(Path('x'));self.assertGreater(metrics['mean_motion'],1)
        with patch.object(cv2,'VideoCapture',return_value=Capture('game')),patch.object(media,'menu_header_text',return_value='CONFIGURAÇÕES'):
            with self.assertRaisesRegex(media.UnsuitableScene,'Menus/mapa'):media.assess_scene(Path('x'))


class MenuTests(unittest.TestCase):
    def test_headers_are_not_gameplay_subtitles(self):
        for text in ('CONFIGURAÇÕES\nCONTROLE', 'HISTÓRIA', 'MAPA REGISTRO PROGRESSO','OPÇÕES VER COMENTÁRIOS VOLTAR','ROLAR TELA SAIR'):
            self.assertTrue(media.is_menu_header(text))
        for text in ('Bora pra praia, mano.', 'Abra o mapa', '(9) TT EA'):
            self.assertFalse(media.is_menu_header(text))

class OCRModelTests(unittest.TestCase):
    def test_verified_download_is_atomic(self):
        import hashlib,io
        from shortforge import ocr
        data=b'verified model fixture'
        with tempfile.TemporaryDirectory() as tmp:
            model=Path(tmp)/'por.traineddata'
            with patch.object(ocr,'MODEL',model),patch.object(ocr,'TESSDATA',Path(tmp)),patch.object(ocr,'SHA256',hashlib.sha256(data).hexdigest()),patch.object(ocr,'urlopen',return_value=io.BytesIO(data)):
                self.assertEqual(ocr.ensure_model(),Path(tmp));self.assertEqual(model.read_bytes(),data)
                self.assertFalse(model.with_suffix('.download').exists())
    def test_invalid_download_is_not_promoted(self):
        import io
        from shortforge import ocr
        with tempfile.TemporaryDirectory() as tmp:
            model=Path(tmp)/'por.traineddata'
            with patch.object(ocr,'MODEL',model),patch.object(ocr,'TESSDATA',Path(tmp)),patch.object(ocr,'urlopen',return_value=io.BytesIO(b'corrupt')):
                with self.assertRaisesRegex(RuntimeError,'Checksum'):ocr.ensure_model()
                self.assertFalse(model.exists());self.assertFalse(model.with_suffix('.download').exists())

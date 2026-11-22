"""Real FFmpeg regression: burn captions from an unrelated, hostile-looking path."""
from pathlib import Path
import tempfile
import unittest
import numpy as np
from shortforge.media import run, render_split, identify_facecam, FacecamNotFound

class FFmpegIntegrationTests(unittest.TestCase):
    def test_real_render_subtitles_and_special_paths(self):
        with tempfile.TemporaryDirectory(prefix="ShortForge ação d'água [x],: ") as tmp:
            root=Path(tmp);work=root/'corte 01';work.mkdir();out=root/'saída final.mp4'
            source=work/'vídeo original.mp4';srt=work/"palavras 'pt' [á],:.srt"
            run(['ffmpeg','-v','error','-nostdin','-y','-f','lavfi','-i','color=c=blue:s=320x180:r=30:d=30',
                 '-f','lavfi','-i','sine=frequency=400:duration=30','-c:v','libx264','-threads','2','-preset','ultrafast','-c:a','aac','-shortest',str(source)])
            with self.assertRaises(FacecamNotFound):
                identify_facecam(source)
            srt.write_text('1\n00:00:00,000 --> 00:00:03,000\nAÇÃO: olá, português!\n',encoding='utf-8')
            data=render_split(source,srt,out,(0,0,160,142),720,lambda m:None)
            self.assertTrue(data['has_audio']);self.assertEqual((data['width'],data['height']),(720,1280))
            # A solid blue source has no white pixels. Check decoded pixels, not SRT existence.
            import subprocess
            raw=subprocess.run(['ffmpeg','-v','error','-ss','1','-i',str(out),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],capture_output=True,check=True).stdout
            pixels=np.frombuffer(raw,dtype=np.uint8).reshape(1280,720,3)
            self.assertGreater(int(np.all(pixels[900:]>210,axis=2).sum()),100)
            self.assertFalse(list(work.glob('render_*')))

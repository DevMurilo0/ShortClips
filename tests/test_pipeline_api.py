import copy
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request,urlopen
from unittest.mock import patch
import zipfile
import app
from shortforge import pipeline as p

class URLTests(unittest.TestCase):
    def test_invalid_urls(self):
        for u in ('https://youtube.com/watch','https://youtube.com/watch?v=x','https://youtu.be/abc/def',
                  'https://user:pass@youtube.com/watch?v=yWvnOWILFk0','https://youtube.com/watching?v=yWvnOWILFk0',
                  'https://youtu.be/yWvnOWILFk0:evil','https://youtu.be:99/yWvnOWILFk0','https://youtube.com/playlist?list=x'):
            with self.subTest(u=u),self.assertRaises(ValueError):p.validate_url(u)
    def test_manual_validation(self):
        for value in ([0,0,101,1],[0,0,-1,2],[1,2,3],[float('nan'),0,2,2]):
            with self.assertRaises(ValueError):p.validate_manual_box(value)
        self.assertEqual(p.validate_manual_box([79,43,21,25]),[.79,.43,.21,.25])

class PipelineTests(unittest.TestCase):
    def test_zip_persistence_and_partial_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);job=p.Job('abc','https://youtu.be/yWvnOWILFk0',2,45,720,'auto','base',root/'abc')
            job.destination.mkdir();folder=job.destination/'corte_01';folder.mkdir()
            (folder/'legendas.srt').write_text('legenda');(job.destination/'short_01.mp4').write_bytes(b'mp4')
            job.clips=[dict(number=1,status='ready',name='short_01.mp4'),dict(number=2,status='failed',error='erro verdadeiro')]
            p._finish(job)
            self.assertEqual(job.status,'partial');self.assertIn('erro verdadeiro',job.errors[0])
            with zipfile.ZipFile(job.destination/job.zip_name) as z:
                self.assertIsNone(z.testzip());self.assertEqual(set(z.namelist()),{'short_01.mp4','legendas/short_01.srt','relatorio.json'})
            restored=p.restore_jobs(root)['abc'];self.assertEqual(restored.clips,job.clips)
            restored.status='running';restored.persist()
            self.assertEqual(p.restore_jobs(root)['abc'].status,'failed')
    def test_job_failure_is_not_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            job=p.Job('abc','https://youtu.be/yWvnOWILFk0',1,45,720,'auto','base',Path(tmp))
            with patch.object(p,'require_dependencies',side_effect=RuntimeError('libass ausente')):p.execute(job)
            self.assertEqual(job.status,'failed');self.assertEqual(job.progress,0)
            self.assertIn('libass ausente',job.message)
    def test_reject_visual_candidate_and_select_distinct_reserve(self):
        from shortforge.media import UnsuitableScene
        with tempfile.TemporaryDirectory() as tmp:
            job=p.Job('abc','https://youtu.be/yWvnOWILFk0',1,45,720,'auto','base',Path(tmp))
            from shortforge.scoring import Segment
            pool=[Segment(60,105,.9,'audio'),Segment(180,225,.8,'audio')]
            def download(url,start,end,folder,notify):
                path=folder/'original.mp4';path.write_bytes(b'source');return path
            def captions(model,video,target,notify):target.write_text('SRT');return 1
            def render(video,srt,out,*a):
                out.write_bytes(b'MP4');return dict(duration=45,width=720,height=1280,has_audio=True)
            with patch.object(p,'require_dependencies'),patch.object(p,'metadata_youtube',return_value={'duration':500,'heatmap':[{'start_time':60,'end_time':70,'value':.9}]}),patch.object(p,'pick_segments',return_value=pool),patch.object(p,'download_section',side_effect=download),patch.object(p,'identify_facecam',return_value=((0,0,100,100),'face')),patch('shortforge.media.run'),patch.object(p,'assess_scene',side_effect=[UnsuitableScene('TV inserida'),{'mean_motion':20}]),patch.object(p,'_load_whisper'),patch.object(p,'make_srt',side_effect=captions),patch.object(p,'render_split',side_effect=render):
                p.execute(job)
            self.assertEqual(job.status,'completed')
            self.assertEqual(job.clips[0]['start'],180)
            self.assertEqual(len(job.clips[0]['rejected_candidates']),1)
            self.assertTrue((job.destination/'corte_01/descartado_01/original.mp4').is_file())

    def test_retry_only_failed_clip(self):
        with tempfile.TemporaryDirectory() as tmp:
            job=p.Job('abc','https://youtu.be/yWvnOWILFk0',2,45,720,'auto','base',Path(tmp))
            job.clips=[dict(number=1,status='ready',name='short_01.mp4'),dict(number=2,start=60,end=105,status='failed')]
            first=copy.deepcopy(job.clips[0])
            with patch.object(p,'require_dependencies'),patch.object(p,'download_section',side_effect=RuntimeError('rede caiu')) as download,patch.object(p,'_finish'):
                p.execute(job,2)
            self.assertEqual(download.call_count,1);self.assertEqual(job.clips[0],first)
            self.assertEqual(job.clips[1]['error'],'rede caiu')

class APITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.saved=app.JOBS;app.JOBS={}
        self.out=patch.object(app,'OUT',self.root);self.out.start()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        self.thread=threading.Thread(target=self.server.serve_forever);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();app.JOBS=self.saved;self.out.stop();self.tmp.cleanup()
    def request(self,path,body=None):
        req=Request(self.url+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
        try:
            with urlopen(req) as r:return r.status,r.read()
        except HTTPError as e:
            with e:return e.code,e.read()
    def test_interface_and_errors(self):
        self.assertEqual(self.request('/')[0],200)
        self.assertEqual(self.request('/static/app.js')[0],200)
        self.assertEqual(self.request('/api/jobs/latest')[0],200)
        self.assertEqual(self.request('/api/jobs/nope')[0],404)
        for body in ([],{'url':'evil'},{'url':'https://youtu.be/yWvnOWILFk0','length':5},{'url':'https://youtu.be/yWvnOWILFk0','resolution':500}):
            self.assertEqual(self.request('/api/jobs',body)[0],400)
    def test_create_conflict_and_cancel(self):
        with patch.object(app,'execute'):
            status,raw=self.request('/api/jobs',{'url':'https://youtu.be/yWvnOWILFk0','count':1})
            self.assertEqual(status,201);jid=json.loads(raw)['job']['id']
            self.assertEqual(self.request('/api/jobs',{'url':'https://youtu.be/yWvnOWILFk0'})[0],409)
            self.assertEqual(self.request('/api/jobs/'+jid+'/cancel',{})[0],202)
            self.assertTrue(app.JOBS[jid].cancel.is_set())
    def test_cancel_endpoint_stops_real_subprocess(self):
        import sys,time
        from shortforge.media import run
        from shortforge.runtime import cancel_event,Cancelled
        started=threading.Event();finished=threading.Event()
        def worker(job,*args):
            token=cancel_event.set(job.cancel)
            job.status='running';started.set()
            try:
                run([sys.executable,'-c','import time;time.sleep(30)'])
            except Cancelled:
                job.status='cancelled'
            finally:
                cancel_event.reset(token);finished.set()
        with patch.object(app,'execute',side_effect=worker):
            status,raw=self.request('/api/jobs',{'url':'https://youtu.be/yWvnOWILFk0','count':1})
            self.assertEqual(status,201);jid=json.loads(raw)['job']['id']
            self.assertTrue(started.wait(2))
            self.assertEqual(self.request('/api/jobs/'+jid+'/cancel',{})[0],202)
            self.assertTrue(finished.wait(3));self.assertEqual(app.JOBS[jid].status,'cancelled')

    def test_atomic_replacement_cannot_truncate_active_download(self):
        job=p.Job('abc','u',1,45,720,'auto','base',self.root/'abc');job.destination.mkdir()
        original=job.destination/'short_01.mp4';original.write_bytes(b'old complete content')
        replacement=job.destination/'new.mp4';replacement.write_bytes(b'new')
        job.status='completed';job.clips=[dict(number=1,status='ready',name='short_01.mp4')];app.JOBS[job.id]=job
        headers=app.Handler._headers
        def replace_after_headers(handler,*args,**kwargs):
            headers(handler,*args,**kwargs)
            replacement.replace(original)
        with patch.object(app.Handler,'_headers',replace_after_headers):
            self.assertEqual(self.request('/downloads/abc/short_01.mp4'),(200,b'old complete content'))
        self.assertEqual(original.read_bytes(),b'new')

    def test_download_and_traversal(self):
        job=p.Job('abc','u',1,45,720,'auto','base',self.root/'abc');job.destination.mkdir()
        (job.destination/'short_01.mp4').write_bytes(b'actual bytes')
        job.clips=[dict(number=1,status='ready',name='short_01.mp4')];job.status='completed';app.JOBS[job.id]=job
        self.assertEqual(self.request('/downloads/abc/short_01.mp4'),(200,b'actual bytes'))
        self.assertEqual(self.request('/downloads/abc/%2e%2e%2fapp.py')[0],404)
        self.assertEqual(self.request('/api/jobs/abc/retry',{'number':1})[0],400)

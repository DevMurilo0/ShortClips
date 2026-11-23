"""Local API security checks; no media, cloud services or jobs are created."""
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch
import json
import os
import threading
import unittest
import app
from shortforge.pipeline import validate_url

class LocalSecurityTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ, {'SHORTFORGE_WORKER_SECRET':'local-test-secret', 'SHORTFORGE_LOCAL_CONTROLLED':'1'})
        self.env.start()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        self.thread=threading.Thread(target=self.server.serve_forever);self.thread.start()
        self.base='http://127.0.0.1:'+str(self.server.server_port)
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.env.stop()
    def post(self,payload,secret='local-test-secret',origin=None):
        headers={'Content-Type':'application/json','X-ShortForge-Worker-Secret':secret}
        if origin:headers['Origin']=origin
        req=Request(self.base+'/api/jobs',data=json.dumps(payload).encode(),headers=headers)
        try:
            with urlopen(req) as r:return r.status,json.load(r)
        except HTTPError as e:return e.code,json.load(e)
    def test_direct_api_needs_server_secret(self):
        self.assertEqual(self.post({},secret='')[0],401)
    def test_foreign_origin_rejected_even_with_server_secret(self):
        self.assertEqual(self.post({},origin='https://untrusted.invalid')[0],403)
    def test_rights_and_budgets_rejected_without_creating_job(self):
        before=set(app.JOBS)
        for fields in ({}, {'rights_confirmed':True,'count':10}, {'rights_confirmed':True,'resolution':1080}):
            status,body=self.post({'url':'https://youtu.be/abcdefghijk','count':1,'length':30,**fields})
            self.assertEqual(status,400)
        self.assertEqual(set(app.JOBS),before)
    def test_source_restrictions(self):
        for url in ('http://youtu.be/abcdefghijk','https://127.0.0.1/test',
                    'https://youtu.be/abcdefghijk?list=abc',
                    'https://youtube.com/watch?v=abcdefghijk&v=otherfilm12'):
            with self.assertRaises(ValueError):validate_url(url)

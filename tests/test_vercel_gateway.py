"""Testes de rotas e autorização da API Python na Vercel, sem rede externa."""
import importlib.util
import json
import os
from pathlib import Path
from http.server import ThreadingHTTPServer
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

API_FILE = Path(__file__).resolve().parents[1]/"backend_vercel"/"api"/"index.py"
spec = importlib.util.spec_from_file_location("shortforge_vercel_gateway", API_FILE)
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)

VARIABLES = {
    "SHORTFORGE_WORKER_URL": "https://worker.example",
    "SHORTFORGE_WORKER_SECRET": "worker-private-secret",
    "SHORTFORGE_FRONTEND_ORIGIN": "https://frontend.example",
    "SHORTFORGE_PUBLIC_ACCESS_KEY": "access-key-for-one-person",
}

class FakeResponse:
    status = 201
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, limit=None):
        return json.dumps({"job": {"id": "abc12345", "status": "queued"}}).encode()

class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(("127.0.0.1",0),gateway.handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.base=f"http://127.0.0.1:{cls.server.server_port}"
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()

    def request(self,path,body=None,token=None,origin=None,method=None):
        headers={}
        if body is not None: headers["Content-Type"]="application/json"
        if token: headers["Authorization"]="Bearer "+token
        if origin: headers["Origin"]=origin
        data=json.dumps(body).encode() if body is not None else None
        req=Request(self.base+path,data=data,headers=headers,method=method)
        try:
            with urlopen(req) as res: return res.status,json.loads(res.read() or b"{}")
        except HTTPError as exc:
            with exc:
                raw=exc.read()
                return exc.code,json.loads(raw or b"{}")

    def test_health_unconfigured_reports_not_ready(self):
        with patch.dict(os.environ,{},clear=True):
            status,data=self.request("/api/health")
            self.assertEqual(status,200)
            self.assertFalse(data["ready"])

    def test_post_unconfigured_does_not_claim_success(self):
        with patch.dict(os.environ,{},clear=True):
            status,data=self.request("/api/jobs",{"url":"https://youtu.be/yWvnOWILFk0"})
            self.assertEqual(status,503)
            self.assertIn("não",data["error"].lower())

    def test_rejects_missing_credentials_and_bad_origin(self):
        with patch.dict(os.environ,VARIABLES,clear=True):
            self.assertEqual(self.request("/api/jobs/latest")[0],401)
            self.assertEqual(self.request("/api/jobs/latest",token="wrong")[0],401)
            self.assertEqual(self.request("/api/jobs/latest",token=VARIABLES["SHORTFORGE_PUBLIC_ACCESS_KEY"],
                                          origin="https://other.example")[0],403)

    def test_health_ready_and_proxy_success(self):
        with patch.dict(os.environ,VARIABLES,clear=True),patch.object(gateway,"urlopen",return_value=FakeResponse()) as proxied:
            status,health=self.request("/api/health")
            self.assertEqual(status,200)
            self.assertTrue(health["ready"])
            status,data=self.request("/api/jobs",{"url":"https://youtu.be/yWvnOWILFk0"},
                                     token=VARIABLES["SHORTFORGE_PUBLIC_ACCESS_KEY"],
                                     origin=VARIABLES["SHORTFORGE_FRONTEND_ORIGIN"])
            self.assertEqual(status,201)
            self.assertEqual(data["job"]["id"],"abc12345")
            req=proxied.call_args.args[0]
            self.assertEqual(req.headers["X-shortforge-worker-secret"],"worker-private-secret")

    def test_download_without_storage_is_unavailable(self):
        with patch.dict(os.environ,VARIABLES,clear=True):
            status,data=self.request("/downloads/abc12345/short_01.mp4",
                                     token=VARIABLES["SHORTFORGE_PUBLIC_ACCESS_KEY"])
            self.assertEqual(status,501)
            self.assertIn("armazenamento",data["error"].lower())

    def test_cors_preflight(self):
        with patch.dict(os.environ,VARIABLES,clear=True):
            status,_=self.request("/api/jobs",origin=VARIABLES["SHORTFORGE_FRONTEND_ORIGIN"],method="OPTIONS")
            self.assertEqual(status,204)

if __name__=="__main__":
    unittest.main()

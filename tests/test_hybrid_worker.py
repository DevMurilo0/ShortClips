"""Loopback/Vercel hybrid HTTP contract; never processes or downloads media."""
from __future__ import annotations

import http.client
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

import app


ALLOWED = "https://short-clips-test123-murilo15.vercel.app"
UNTRUSTED = "https://untrusted.example"


class HybridWorkerHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def request(self, method, path, headers=None):
        headers = dict(headers or {})
        headers.setdefault("Host", f"127.0.0.1:{self.port}")
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request(method, path, headers=headers)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_authorized_vercel_preview_can_reach_local_health(self):
        with patch.object(app, "PORT", self.port), patch.object(app, "ALLOW_TEAM_PREVIEWS", True):
            status, headers, body = self.request(
                "GET", "/api/health", {"Origin": ALLOWED})
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), ALLOWED)
        self.assertIn(b'"mode": "local"', body)
        self.assertIn(b'"ready": true', body)

    def test_preflight_allows_only_owner_origin_and_private_network(self):
        with patch.object(app, "PORT", self.port), patch.object(app, "ALLOW_TEAM_PREVIEWS", True):
            status, headers, _ = self.request(
                "OPTIONS", "/api/jobs", {
                    "Origin": ALLOWED,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Private-Network": "true",
                })
            denied, _, _ = self.request("OPTIONS", "/api/jobs", {"Origin": UNTRUSTED})
        self.assertEqual(status, 204)
        self.assertEqual(headers.get("Access-Control-Allow-Private-Network"), "true")
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), ALLOWED)
        self.assertEqual(denied, 403)

    def test_rejects_foreign_web_origin_and_dns_rebinding(self):
        with patch.object(app, "PORT", self.port), patch.object(app, "ALLOW_TEAM_PREVIEWS", True):
            denied_origin, _, _ = self.request(
                "GET", "/api/health", {"Origin": UNTRUSTED})
            denied_host, _, _ = self.request(
                "GET", "/api/health", {
                    "Host": "unexpected.example",
                    "Origin": ALLOWED,
                })
        self.assertEqual(denied_origin, 403)
        self.assertEqual(denied_host, 403)

    def test_media_byte_ranges_support_inline_video_and_reject_invalid_ranges(self):
        self.assertEqual(app.parse_single_byte_range('bytes=0-3',10),(0,3))
        self.assertEqual(app.parse_single_byte_range('bytes=-4',10),(6,9))
        self.assertEqual(app.parse_single_byte_range('bytes=8-',10),(8,9))
        with self.assertRaises(ValueError):
            app.parse_single_byte_range('bytes=15-17',10)
        with TemporaryDirectory() as temporary:
            folder=Path(temporary)
            (folder/'short_01.mp4').write_bytes(b'0123456789')
            job=SimpleNamespace(destination=folder,
                clips=[{'status':'ready','name':'short_01.mp4','number':1}],
                zip_name=None)
            url='/downloads/abc123/short_01.mp4?inline=1'
            with patch.object(app,'PORT',self.port), \\
                 patch.object(app,'ALLOW_TEAM_PREVIEWS',True), \\
                 patch.dict(app.JOBS,{'abc123':job}), \\
                 patch.dict('os.environ',{'SHORTFORGE_WORKER_SECRET':''}):
                status,headers,body=self.request('GET',url,
                    {'Origin':ALLOWED,'Range':'bytes=2-5'})
                denied,invalid_headers,_=self.request('GET',url,
                    {'Origin':ALLOWED,'Range':'bytes=20-30'})
            self.assertEqual(status,206)
            self.assertEqual(body,b'2345')
            self.assertEqual(headers.get('Content-Range'),'bytes 2-5/10')
            self.assertEqual(headers.get('Content-Length'),'4')
            self.assertIn('inline',headers.get('Content-Disposition',''))
            self.assertEqual(denied,416)
            self.assertEqual(invalid_headers.get('Content-Range'),'bytes */10')

    def test_production_origin_allowlist_without_wildcard(self):
        with patch.object(app, "PORT", self.port), patch.object(app, "ALLOW_TEAM_PREVIEWS", True):
            self.assertTrue(app.allowed_browser_origin(ALLOWED))
            self.assertFalse(app.allowed_browser_origin("https://short-clips-evil.com"))
            self.assertFalse(app.allowed_browser_origin("https://other-murilo15.vercel.app"))


if __name__ == "__main__":
    unittest.main()

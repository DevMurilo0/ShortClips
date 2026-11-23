#!/usr/bin/env python3
"""Loopback-only development servers; credentials stay between Python handlers."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.client import HTTPConnection
from pathlib import Path
import os
import fcntl
import secrets
import socket
import threading

ROOT = Path(__file__).resolve().parent

def available_port(preferred):
    for port in range(preferred, preferred + 30):
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try: probe.bind(('127.0.0.1', port))
            except OSError: continue
            return port
    raise RuntimeError(f'Nenhuma porta disponível a partir de {preferred}.')

def main():
    runtime = ROOT / ".local"
    runtime.mkdir(exist_ok=True)
    lock = (runtime / "server.lock").open("w")
    try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError: raise SystemExit("ShortForge local já está rodando.")
    frontend_port = available_port(int(os.getenv('SHORTFORGE_FRONTEND_PORT', '5173')))
    backend_port = available_port(int(os.getenv('SHORTFORGE_BACKEND_PORT', '8000')))
    origin = f'http://localhost:{frontend_port}'
    secret = secrets.token_urlsafe(48)
    # Never inherit cloud credentials/configuration into the local service.
    for name in list(os.environ):
        if name.startswith(('VERCEL_', 'BLOB_', 'SHORTFORGE_')):
            del os.environ[name]
    os.environ.update(SHORTFORGE_HOST='127.0.0.1', SHORTFORGE_PORT=str(backend_port),
                      SHORTFORGE_WORKER_SECRET=secret, SHORTFORGE_ALLOWED_ORIGINS=origin,
                      SHORTFORGE_NO_BROWSER='1', SHORTFORGE_LOCAL_CONTROLLED='1',
                      OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2', MKL_NUM_THREADS='2')
    import app
    app.OUT = ROOT / 'resultados-local'

    class Proxy(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        def log_message(self, *args): pass
        def forward(self):
            host = self.headers.get('Host', '')
            request_origin = self.headers.get('Origin', '')
            if (host != f'localhost:{frontend_port}'
                    or request_origin and request_origin != origin
                    or self.headers.get('Sec-Fetch-Site') == 'cross-site'):
                self.send_error(403, 'Origem local nao permitida'); return
            if self.command not in ('GET','POST','OPTIONS','HEAD'):
                self.send_error(405); return
            try: size = int(self.headers.get('Content-Length', '0'))
            except ValueError: self.send_error(400); return
            if not 0 <= size <= 16384:
                self.send_error(413); return
            if self.headers.get('Transfer-Encoding'):
                self.send_error(400); return
            headers = {'X-ShortForge-Worker-Secret': secret}
            for key in ('Content-Type', 'Origin', 'Access-Control-Request-Method', 'Access-Control-Request-Headers'):
                if key in self.headers: headers[key] = self.headers[key]
            conn = HTTPConnection('127.0.0.1', backend_port, timeout=30)
            try:
                conn.request(self.command, self.path, body=self.rfile.read(size) if size else None, headers=headers)
                response = conn.getresponse()
                self.send_response(response.status)
                for key, value in response.getheaders():
                    if key.lower() not in ('connection', 'server', 'date', 'transfer-encoding'):
                        self.send_header(key,value)
                self.send_header('Connection','close'); self.end_headers()
                while chunk := response.read(256*1024): self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError): pass
            except OSError:
                self.close_connection = True
            finally: conn.close()
        do_GET = do_POST = do_OPTIONS = do_HEAD = forward
    proxy = ThreadingHTTPServer(('127.0.0.1', frontend_port), Proxy)
    thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    thread.start()
    print(f'Frontend: {origin}\nBackend: http://localhost:{backend_port}\nCtrl+C ou ./stop-local.sh para encerrar.', flush=True)
    pidfile = runtime / "server.pid"
    pidfile.write_text(str(os.getpid()))
    try: app.main()
    finally:
        proxy.shutdown(); proxy.server_close(); thread.join(timeout=3)
        pidfile.unlink(missing_ok=True)

if __name__ == '__main__': main()

#!/usr/bin/env python3
"""Interface web LOCAL. Não envia vídeos ou senhas a um servidor nosso."""
from __future__ import annotations

from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import json
import hmac
import mimetypes
from pathlib import Path
import threading
import uuid
import webbrowser
import os
import re
import signal
from urllib.parse import urlparse, unquote, parse_qs

from shortforge.pipeline import Job, execute, validate_url, validate_manual_box, restore_jobs

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'resultados'
HOST=os.getenv('SHORTFORGE_HOST','127.0.0.1')
ALLOWED_ORIGINS={v.strip().rstrip('/') for v in os.getenv('SHORTFORGE_ALLOWED_ORIGINS','').split(',') if v.strip()}
# Accept only this user's exact ShortForge deployment pattern, never *.vercel.app.
TEAM_PREVIEW_ORIGIN=re.compile(r'https://short-clips-[a-z0-9]+-murilo15\.vercel\.app')
ALLOW_TEAM_PREVIEWS=os.getenv('SHORTFORGE_ALLOW_TEAM_PREVIEWS')=='1'
PORT=int(os.getenv('SHORTFORGE_PORT','8765'))


def allowed_browser_origin(origin: str) -> bool:
    return origin in ALLOWED_ORIGINS or (
        ALLOW_TEAM_PREVIEWS and bool(TEAM_PREVIEW_ORIGIN.fullmatch(origin))
    )
JOBS={}
WORKERS={}
JOBS_LOCK=threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def _local_host_allowed(self):
        # Limit DNS rebinding exposure: the browser must contact loopback,
        # even when it loaded the static frontend from Vercel.
        if not ALLOW_TEAM_PREVIEWS:
            return True
        host=self.headers.get('Host','')
        if host not in (f'127.0.0.1:{PORT}',f'localhost:{PORT}',f'[::1]:{PORT}'):
            self._json({'error':'Host local inválido.'},403)
            return False
        return True

    def _worker_authorized(self):
        secret=os.getenv('SHORTFORGE_WORKER_SECRET','').strip()
        if not secret:
            return True  # Local mode only; main() blocks public bind without secret.
        supplied=self.headers.get('X-ShortForge-Worker-Secret','')
        if hmac.compare_digest(supplied,secret):
            return True
        self._json({'error':'Acesso ao worker não autorizado.'},401)
        return False

    def log_message(self,fmt,*args):
        if not self.path.startswith('/api/jobs/'):
            print('Web: '+(fmt%args))

    def _headers(self,status=200,content_type='application/json; charset=utf-8',length=None,extra=None):
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        if length is not None: self.send_header('Content-Length',str(length))
        origin=self.headers.get('Origin','').rstrip('/')
        if origin and allowed_browser_origin(origin):
            self.send_header('Access-Control-Allow-Origin',origin)
            self.send_header('Vary','Origin')
        for k,v in (extra or {}).items(): self.send_header(k,v)
        self.end_headers()

    def _json(self,data,status=200):
        raw=json.dumps(data,ensure_ascii=False).encode('utf-8')
        self._headers(status,length=len(raw))
        self.wfile.write(raw)

    def _asset(self,path:Path):
        if not path.is_file():return self._json({'error':'Arquivo não encontrado'},404)
        raw=path.read_bytes()
        mime=mimetypes.guess_type(path.name)[0] or 'text/plain'
        self._headers(content_type=mime,length=len(raw))
        self.wfile.write(raw)

    def do_GET(self):
        if not self._local_host_allowed(): return
        p=urlparse(self.path).path
        origin=self.headers.get('Origin','').rstrip('/')
        if origin and not allowed_browser_origin(origin) and origin != f'http://{self.headers.get("Host")}':
            return self._json({'error':'Origem não permitida.'},403)
        if p in ('/','/index.html'):
            return self._asset(ROOT/'web'/'index.html')
        if p in ('/static/style.css','/static/app.js','/style.css','/app.js'):
            return self._asset(ROOT/'web'/p.rsplit('/',1)[-1])
        if p=='/config.js':
            raw=('window.SHORTFORGE_API_URL='+json.dumps(os.getenv('SHORTFORGE_API_URL',''))+';window.SHORTFORGE_LOCAL_CONTROLLED='+json.dumps(os.getenv('SHORTFORGE_LOCAL_CONTROLLED')=='1')+';').encode('utf-8')
            self._headers(content_type='text/javascript; charset=utf-8',length=len(raw))
            return self.wfile.write(raw)
        if p=='/api/health':
            return self._json({'ok':True,'service':'ShortForge Local',
                               'mode':'local','ready':True})
        if (p.startswith('/api/jobs/') or p.startswith('/downloads/')) and not self._worker_authorized():
            return
        if p=='/api/jobs/latest':
            with JOBS_LOCK:
                job=next(reversed(JOBS.values()),None) if JOBS else None
            return self._json({'job':job.asdict() if job else None})
        preview=re.fullmatch(r'/api/jobs/([a-f0-9]+)/clips/(\d+)/preview',p)
        if preview:
            with JOBS_LOCK: job=JOBS.get(preview[1])
            if not job or not any(c['number']==int(preview[2]) for c in job.clips):
                return self._json({'error':'Corte não encontrado'},404)
            return self._asset(job.destination/f'corte_{int(preview[2]):02d}'/'previa.jpg')
        if p.startswith('/api/jobs/'):
            jid=p.rsplit('/',1)[-1]
            with JOBS_LOCK: job=JOBS.get(jid)
            if not job:return self._json({'error':'Tarefa não encontrada'},404)
            return self._json(job.asdict())
        if p.startswith('/downloads/'):
            parts=p.split('/')
            if len(parts)!=4:return self._json({'error':'Caminho inválido'},400)
            _,_,jid,name=parts
            with JOBS_LOCK: job=JOBS.get(jid)
            if not job:return self._json({'error':'Tarefa não encontrada'},404)
            name=unquote(name)
            allowed={'relatorio.json'}|({job.zip_name} if job.zip_name else set())|{e['name'] for e in job.clips if e.get('status')=='ready'}
            if name not in allowed:return self._json({'error':'Arquivo indisponível'},404)
            file=(job.destination/name).resolve()
            if not file.is_relative_to(job.destination.resolve()) or not file.is_file():
                return self._json({'error':'Arquivo não encontrado'},404)
            # Open first: an atomic ZIP replacement during a retry must not
            # change the body after Content-Length was measured.
            with file.open('rb') as f:
                inline = name.endswith('.mp4') and parse_qs(urlparse(self.path).query).get('inline')==['1']
                disposition='inline' if inline else 'attachment'
                self._headers(content_type='application/zip' if name.endswith('.zip') else ('video/mp4' if name.endswith('.mp4') else 'application/json'),
                              length=os.fstat(f.fileno()).st_size,extra={'Content-Disposition':f'{disposition}; filename="{name}"'})
                while b:=f.read(1024*256):
                    try:self.wfile.write(b)
                    except (BrokenPipeError,ConnectionResetError):break
            return
        self._json({'error':'Página não encontrada'},404)

    def do_OPTIONS(self):
        if not self._local_host_allowed(): return
        origin=self.headers.get('Origin','').rstrip('/')
        if not allowed_browser_origin(origin):
            return self._json({'error':'Origem não permitida.'},403)
        extras={'Access-Control-Allow-Methods':'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers':'Content-Type'}
        if self.headers.get('Access-Control-Request-Private-Network','').lower()=='true':
            extras['Access-Control-Allow-Private-Network']='true'
        self._headers(204,length=0,extra=extras)

    def do_POST(self):
        if not self._local_host_allowed(): return
        if not self._worker_authorized():
            return
        origin=self.headers.get('Origin','').rstrip('/')
        same_origin=f'http://{self.headers.get("Host")}'
        if origin and origin!=same_origin and not allowed_browser_origin(origin):
            return self._json({'error':'Origem não permitida.'},403)
        route=urlparse(self.path).path
        if route!='/api/jobs' and not re.fullmatch(r'/api/jobs/[a-f0-9]+/(?:cancel|retry)',route):
            return self._json({'error':'Rota não encontrada'},404)
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size<=0 or size>16*1024: raise ValueError('Solicitação inválida.')
            payload=json.loads(self.rfile.read(size))
            if not isinstance(payload,dict): raise ValueError('Esperado um objeto JSON.')
            if route.endswith('/cancel'):
                with JOBS_LOCK:
                    job=JOBS.get(route.split('/')[3])
                    if not job: return self._json({'error':'Tarefa não encontrada'},404)
                    with job.lock:
                        if job.status not in ('queued','running','cancelling'):
                            return self._json({'error':'Tarefa já encerrada.'},409)
                        job.cancel.set(); job.status='cancelling'; job.message='Cancelando subprocessos...'; job.persist()
                return self._json({'job':job.asdict()},202)
            retry_number=None
            with JOBS_LOCK:
                if any(j.status in ('queued','running','cancelling') for j in JOBS.values()):
                    return self._json({'error':'Uma tarefa já está rodando. Aguarde ou cancele antes de iniciar outra.'},409)
                if route.endswith('/retry'):
                    job=JOBS.get(route.split('/')[3])
                    if not job: return self._json({'error':'Tarefa não encontrada'},404)
                    retry_number=int(payload.get('number',0))
                    clip=next((c for c in job.clips if c['number']==retry_number),None)
                    if not clip or clip['status']!='failed':
                        raise ValueError('Escolha um corte que falhou.')
                    manual=validate_manual_box(payload['manual_box']) if 'manual_box' in payload else job.manual_box
                    job.manual_box=manual; job.cancel.clear(); job.status='queued'; job.stage='queued'
                    job.message=f'Aguardando nova tentativa do corte {retry_number}.'
                    clip['status']='queued'; job.persist()
                else:
                    url=validate_url(str(payload.get('url','')))
                    if any(isinstance(payload.get(k), (bool, float, dict, list)) for k in ('count','length','resolution')):
                        raise ValueError('Quantidade, duração e resolução devem ser números inteiros.')
                    count=int(payload.get('count',5)); length=int(payload.get('length',45))
                    resolution=int(payload.get('resolution',720)); facecam=str(payload.get('facecam','auto'))
                    model=str(payload.get('model','base'))
                    manual=validate_manual_box(payload.get('manual_box'))
                    if not 1<=count<=10: raise ValueError('Quantidade entre 1 e 10.')
                    if not 30<=length<=60: raise ValueError('Duração entre 30 e 60 segundos.')
                    if resolution not in (720,1080): raise ValueError('Resolução inválida.')
                    if model not in ('tiny','base','small'): raise ValueError('Modelo inválido.')
                    if facecam not in ('auto','superior-esquerdo','superior-direito','inferior-esquerdo','inferior-direito'):
                        raise ValueError('Posição da facecam inválida.')
                    if os.getenv('SHORTFORGE_LOCAL_CONTROLLED')=='1':
                        if payload.get('rights_confirmed') is not True:
                            raise ValueError('Confirme que possui autorização para processar este vídeo.')
                        if count > 5 or length > 45 or resolution != 720:
                            raise ValueError('Modo local: até 5 Shorts de 30–45s em 720p.')
                    jid=uuid.uuid4().hex[:12]
                    job=Job(jid,url,count,length,resolution,facecam,model,OUT/jid,manual_box=manual)
                    job.persist(); JOBS[jid]=job
                thread=threading.Thread(target=execute,args=(job,retry_number),daemon=True,name='shortforge-'+job.id)
                WORKERS[job.id]=thread
                thread.start()
            return self._json({'job':job.asdict()},202 if retry_number else 201)
        except (ValueError,TypeError,OverflowError,json.JSONDecodeError) as e:
            return self._json({'error':str(e)},400)


def main():
    if HOST not in ('127.0.0.1','localhost','::1') and not os.getenv('SHORTFORGE_WORKER_SECRET','').strip():
        raise RuntimeError('Não exponha o worker sem SHORTFORGE_WORKER_SECRET. Defina um segredo forte e use HTTPS.')
    def stop_server(signum,frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop_server)
    OUT.mkdir(exist_ok=True)
    server=ThreadingHTTPServer((HOST,PORT),Handler)
    # Restore only after binding succeeds. Importing app in tests/tools is read-only.
    JOBS.update(restore_jobs(OUT))
    address=f'http://{HOST}:{PORT}'
    print('\n'+'='*60)
    print('SHORTFORGE LOCAL — cole o link do YouTube no navegador')
    print(address)
    print('Os arquivos gerados ficam na pasta resultados/')
    print('Ctrl+C para encerrar a interface.')
    print('='*60+'\n')
    if not os.environ.get('SHORTFORGE_NO_BROWSER'):
        threading.Timer(1.0,lambda:webbrowser.open(address)).start()
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        with JOBS_LOCK:
            active=[j for j in JOBS.values() if j.status in ('queued','running','cancelling')]
            for job in active:
                with job.lock:
                    job.cancel.set(); job.status='cancelling'; job.stage='cancelling'
                    job.message='Servidor encerrando; cancelamento solicitado.'; job.persist()
        server.server_close()
        for worker in list(WORKERS.values()): worker.join(timeout=10)
        # Native inference may not return before shutdown. Persist interruption
        # now; its cancellation event prevents any later promotion to ready.
        for job in active:
            with job.lock:
                if job.status in ('queued','running','cancelling'):
                    job.status='cancelled'; job.stage='cancelled'
                    job.message='Servidor encerrado durante o processamento. Repita os cortes pendentes.'
                    for clip in job.clips:
                        if clip['status']!='ready': clip.update(status='failed',error=job.message)
                    job.persist()

if __name__=='__main__':
    main()

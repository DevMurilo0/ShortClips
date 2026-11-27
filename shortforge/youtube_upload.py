"""Local OAuth and resumable YouTube uploads. No third-party Python packages."""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, urlparse, parse_qs
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

HOME = Path.home()/'.config'/'shortforge-youtube'
AUTH = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN = 'https://oauth2.googleapis.com/token'
API = 'https://www.googleapis.com/youtube/v3'
UPLOAD = 'https://www.googleapis.com/upload/youtube/v3/videos'
SCOPES = 'https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly'
REDIRECT = 'http://127.0.0.1:8766/oauth/callback'
LOCK = threading.RLock()
CHUNK = 4*1024*1024

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def request(url, method='GET', data=None, headers=None):
    try:
        with build_opener(NoRedirect()).open(Request(url, data=data, headers=headers or {}, method=method), timeout=90) as res:
            return res.status, res.headers, res.read()
    except HTTPError as e:
        return e.code, e.headers, e.read()
    except (URLError, TimeoutError, OSError) as e:
        raise RuntimeError('Falha de conexão com Google. Use retomar sem criar outro envio.') from None

def private_dir():
    HOME.mkdir(mode=0o700, parents=True, exist_ok=True)
    HOME.chmod(0o700)

def save(name, data):
    private_dir()
    tmp = HOME/(name+'.tmp')
    fd = os.open(tmp, os.O_WRONLY|os.O_CREAT|os.O_TRUNC, 0o600)
    with os.fdopen(fd,'w') as out:
        json.dump(data,out)
    tmp.chmod(0o600)
    tmp.replace(HOME/name)

def read(name):
    return json.loads((HOME/name).read_text(encoding='utf-8'))

def client():
    raw=read('client.json')
    data=raw.get('web') or raw.get('installed')
    if not data or not data.get('client_id') or not data.get('client_secret'):
        raise ValueError('Credencial OAuth inválida. Use o JSON de cliente OAuth.')
    return data

def token_exchange(fields):
    c=client()
    status,_,body=request(TOKEN,'POST',urlencode(dict(fields,client_id=c['client_id'],client_secret=c['client_secret'])).encode(),{'Content-Type':'application/x-www-form-urlencoded'})
    if status!=200: raise RuntimeError('Google recusou a autorização/renovação (HTTP %s). Reconecte a conta.'%status)
    value=json.loads(body)
    if not value.get('access_token'): raise RuntimeError('Token ausente.')
    value['expires_at']=time.time()+int(value.get('expires_in',3600))-90
    return value

def auth_headers():
    with LOCK:
        data=read('token.json')
        if data.get('expires_at',0)<=time.time():
            refreshed=token_exchange({'grant_type':'refresh_token','refresh_token':data['refresh_token']})
            refreshed.setdefault('refresh_token',data['refresh_token'])
            save('token.json',refreshed)
            data=refreshed
        return {'Authorization':'Bearer '+data['access_token']}

def channel():
    code,_,body=request(API+'/channels?part=id,snippet&mine=true',headers=auth_headers())
    if code!=200: raise RuntimeError('Não foi possível verificar o canal (HTTP %s).'%code)
    items=json.loads(body).get('items',[])
    if len(items)!=1: raise RuntimeError('Selecione exatamente um canal na autorização Google.')
    return {'id':items[0]['id'],'title':items[0]['snippet']['title']}

def connected():
    try: return read('channel.json') if (HOME/'token.json').is_file() else None
    except (OSError,ValueError): return None

def login(source):
    if connected(): raise RuntimeError('Desconecte primeiro a conta anterior; não misture filas de canais.')
    data=json.loads(Path(source).expanduser().read_text())
    save('client.json',data)
    c=client()
    verifier=secrets.token_urlsafe(64)
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    state=secrets.token_urlsafe(32)
    result={}
    class Callback(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_GET(self):
            p=urlparse(self.path)
            q=parse_qs(p.query)
            if p.path!='/oauth/callback' or q.get('state')!=[state]:
                self.send_error(400); return
            result.update(q)
            self.send_response(200)
            self.send_header('Content-Type','text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write('Autorização recebida. Volte ao terminal.'.encode())
    with HTTPServer(('127.0.0.1',8766),Callback) as server:
        server.timeout=1
        print('Abra este link no navegador DESTE aparelho:\n'+AUTH+'?'+urlencode({'client_id':c['client_id'],'redirect_uri':REDIRECT,'response_type':'code','scope':SCOPES,'access_type':'offline','prompt':'consent select_account','state':state,'code_challenge':challenge,'code_challenge_method':'S256'}),flush=True)
        deadline=time.monotonic()+300
        while not result and time.monotonic()<deadline: server.handle_request()
    if not result.get('code'): raise RuntimeError('Autorização não concluída.')
    token=token_exchange({'grant_type':'authorization_code','code':result['code'][0],'redirect_uri':REDIRECT,'code_verifier':verifier})
    if not token.get('refresh_token'): raise RuntimeError('Google não concedeu acesso offline. Revogue o consentimento anterior e tente novamente.')
    save('token.json',token)
    try: save('channel.json',channel())
    except Exception:
        (HOME/'token.json').unlink(missing_ok=True)
        raise
    print('Canal conectado:',connected()['title'])

def db():
    private_dir()
    path=HOME/'uploads.sqlite3'
    con=sqlite3.connect(path,timeout=30)
    path.chmod(0o600)
    con.row_factory=sqlite3.Row
    con.execute('''CREATE TABLE IF NOT EXISTS uploads (
        channel TEXT, job TEXT, number INTEGER, digest TEXT, path TEXT,
        metadata TEXT, session TEXT, video_id TEXT, state TEXT, error TEXT,
        PRIMARY KEY(channel,job,number), UNIQUE(channel,digest))''')
    return con

def options(payload):
    if payload is None: return None
    if not isinstance(payload,dict) or payload.get('enabled') is not True: raise ValueError('Configuração de publicação inválida.')
    account=connected()
    if not account or payload.get('channel')!=account['id']: raise ValueError('Conecte/confirme o canal no painel.')
    privacy=payload.get('privacy')
    if privacy not in ('private','public','unlisted'): raise ValueError('Visibilidade inválida.')
    if payload.get('confirmed') is not True or type(payload.get('made_for_kids')) is not bool: raise ValueError('Confirme publicação e público infantil.')
    interval=payload.get('interval',0)
    if type(interval) is not int or interval not in (0,30,60,120,1440): raise ValueError('Intervalo inválido.')
    if interval and privacy!='public': raise ValueError('Agendamento requer visibilidade pública.')
    return dict(channel=account['id'],privacy=privacy,interval=interval,made_for_kids=payload['made_for_kids'])

def metadata(job,clip,opt,when=None):
    # Descriptive metadata, no invented quotations or unrelated tags.
    title=' '.join((job.title or 'Vídeo').replace('<','').replace('>','').split())
    suffix=' | Corte %02d #Shorts'%clip['number']
    status={'privacyStatus':opt['privacy'],'selfDeclaredMadeForKids':opt['made_for_kids']}
    if when:
        status.update(privacyStatus='private',publishAt=when.isoformat().replace('+00:00','Z'))
    return {'snippet':{'title':title[:100-len(suffix)]+suffix,'description':'Corte %02d do vídeo original: %s\n#Shorts'%(clip['number'],job.url),'categoryId':'22','tags':['Shorts']},'status':status}

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while chunk:=f.read(CHUNK): h.update(chunk)
    return h.hexdigest()

def enqueue(job):
    opt=job.youtube
    if not opt or job.status!='completed' or len(job.clips)!=job.count: return
    if any(c.get('status')!='ready' or not c.get('audio') or not c.get('subtitles_burned') for c in job.clips): return
    start=datetime.now(timezone.utc)+timedelta(minutes=10)
    with LOCK, db() as con:
        for index,clip in enumerate(sorted(job.clips,key=lambda c:c['number'])):
            path=(job.destination/clip['name']).resolve()
            if not path.is_relative_to(job.destination.resolve()) or not path.is_file() or path.suffix!='.mp4': raise RuntimeError('MP4 validado não encontrado.')
            when=start+timedelta(minutes=index*opt['interval']) if opt['interval'] else None
            con.execute('INSERT OR IGNORE INTO uploads VALUES(?,?,?,?,?,?,NULL,NULL,?,NULL)',(opt['channel'],job.id,clip['number'],digest(path),str(path),json.dumps(metadata(job,clip,opt,when)), 'pending'))

def update(con,row,**values):
    assert set(values)<= {'session','video_id','state','error'}
    con.execute('UPDATE uploads SET '+','.join(k+'=?' for k in values)+' WHERE channel=? AND job=? AND number=?',(*values.values(),row['channel'],row['job'],row['number']))
    con.commit()

def check_session(url):
    p=urlparse(url)
    if p.scheme!='https' or p.hostname not in ('www.googleapis.com','youtube.googleapis.com') or p.username or p.password or p.port not in (None,443) or not p.path.startswith('/upload/youtube/v3/videos'):
        raise RuntimeError('URL de upload inválida.')
    return url

def send_row(con,row):
    path=Path(row['path'])
    if not path.is_file() or digest(path)!=row['digest']: raise RuntimeError('Arquivo local foi alterado ou removido.')
    total=path.stat().st_size
    session=row['session']
    if not session:
        body=row['metadata'].encode()
        code,headers,_=request(UPLOAD+'?uploadType=resumable&part=snippet,status','POST',body,dict(auth_headers(),**{'Content-Type':'application/json','X-Upload-Content-Type':'video/mp4','X-Upload-Content-Length':str(total)}))
        if code not in (200,201) or not headers.get('Location'): raise RuntimeError('Não foi possível iniciar upload (HTTP %s).'%code)
        session=check_session(headers['Location'])
        update(con,row,session=session,state='uploading',error=None)
    else:
        check_session(session)
    def put(data,range_value):
        return request(session,'PUT',data,dict(auth_headers(),**{'Content-Type':'video/mp4','Content-Range':range_value}))
    def position(response):
        code,headers,body=response
        if code in (200,201):
            video=json.loads(body).get('id')
            if not video or not re.fullmatch(r'[A-Za-z0-9_-]{11}',video): raise RuntimeError('Resposta de conclusão sem ID. Confira YouTube Studio antes de reenviar.')
            update(con,row,video_id=video,state='uploaded',error=None)
            return None
        if code in (404,410): raise RuntimeError('Sessão expirada. Confira YouTube Studio; não será criado outro upload automaticamente.')
        if code!=308: raise RuntimeError('Upload interrompido (HTTP %s). Use retomar.'%code)
        value=headers.get('Range')
        if not value: return 0
        match=re.fullmatch(r'bytes=0-(\d+)',value)
        if not match or int(match[1])+1>total: raise RuntimeError('Intervalo de upload inválido.')
        return int(match[1])+1
    offset=position(put(b'','bytes */%d'%total))
    with path.open('rb') as source:
        while offset is not None:
            if offset>=total: raise RuntimeError('Conclusão não confirmada. Use retomar.')
            source.seek(offset)
            data=source.read(CHUNK)
            next_offset=position(put(data,'bytes %d-%d/%d'%(offset,offset+len(data)-1,total)))
            if next_offset is not None and next_offset<=offset: raise RuntimeError('Upload sem avanço. Use retomar.')
            offset=next_offset

def run_pending(job_id=None):
    with LOCK:
        account=connected()
        if not account: raise RuntimeError('Canal desconectado.')
        if channel()['id']!=account['id']: raise RuntimeError('O canal autorizado mudou. Envio bloqueado.')
        with db() as con:
            query='SELECT * FROM uploads WHERE channel=? AND state!=?'
            args=[account['id'],'uploaded']
            if job_id: query+=' AND job=?';args.append(job_id)
            for row in con.execute(query+' ORDER BY job,number',args).fetchall():
                try: send_row(con,row)
                except Exception as exc:
                    # Do not leak upload session URLs or tokens.
                    message=str(exc) if isinstance(exc,RuntimeError) else 'Erro local durante upload. Consulte o terminal.'
                    update(con,row,state='paused',error=message)
                    break

def status(job_id):
    if not (HOME/'uploads.sqlite3').is_file(): return []
    with db() as con:
        return [dict(r) for r in con.execute('SELECT number,video_id,state,error FROM uploads WHERE job=? ORDER BY number',(job_id,))]

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest='action',required=True)
    sub.add_parser('connect').add_argument('client_json')
    sub.add_parser('status')
    sub.add_parser('resume')
    sub.add_parser('disconnect')
    args=p.parse_args()
    if args.action=='connect': login(args.client_json)
    elif args.action=='resume': run_pending()
    elif args.action=='status': print(connected() or 'Desconectado')
    else:
        for name in ('token.json','channel.json','client.json'): (HOME/name).unlink(missing_ok=True)
        print('Credenciais locais removidas. Revogue também em https://myaccount.google.com/permissions')
if __name__=='__main__': main()

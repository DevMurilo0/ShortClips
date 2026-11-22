"""Browser integration against simulated API; no cloud or real video playback."""
from pathlib import Path
import json
import os
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
job_id='a'*32
job={'id':job_id,'count':5,'status':'completed','stage':'completed','progress':100,'title':'Teste de integração',
     'message':'5 Shorts armazenados.','errors':[], 'clips':[
       {'number':i,'status':'ready','name':f'short_{i:02d}.mp4','width':720,'height':1280,'duration':45,
        'download_endpoint':f'/api/download?pathname=short_{i:02d}.mp4'} for i in range(1,6)],
     'zip_name':'shorts_prontos.zip','zip_download_endpoint':'/api/download?pathname=shorts_prontos.zip'}
requests=[]

def route_request(route):
    req=route.request;path=urlsplit(req.url).path
    if req.url.startswith('https://backend.test'):
        requests.append((path,req.headers.get('authorization')))
        if path=='/api/health': data={'ok':True,'ready':True,'mode':'sandbox'}
        elif path=='/api/usage': data={'jobs_month':0}
        elif path=='/api/jobs/latest': data={'job':None}
        elif path=='/api/jobs' or path.endswith('/cancel'): data={'job':job}
        elif path.startswith('/api/jobs/'): data=job
        elif path=='/api/download': data={'url':'https://test.private.blob.vercel-storage.com/test?signature=test'}
        else: raise AssertionError('Unexpected API route '+path)
        route.fulfill(status=200,content_type='application/json',body=json.dumps(data));return
    if req.url.startswith('https://test.private.blob'):
        route.fulfill(status=200,content_type='video/mp4',body=b'fixture');return
    if req.url.startswith('https://frontend.test'):
        name=path.lstrip('/') or 'index.html'
        if name=='config.js':
            route.fulfill(content_type='text/javascript',body="window.SHORTFORGE_API_URL='https://backend.test';");return
        file=ROOT/'web'/name
        if file.is_file():
            route.fulfill(path=str(file));return
    route.abort()

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path=os.getenv('SHORTFORGE_BROWSER_EXECUTABLE'))
    for width in (375,1280):
        page=browser.new_page(viewport={'width':width,'height':900})
        errors=[];page.on('pageerror',lambda e: errors.append(str(e)))
        page.route('**/*',route_request)
        page.goto('https://frontend.test')
        page.locator('#backendAccessKey').fill('x'*40)
        page.locator('#saveBackend').click()
        page.wait_for_function("!document.getElementById('submit').disabled")
        page.locator('#url').fill('https://youtu.be/yWvnOWILFk0')
        page.locator('#submit').click()
        page.wait_for_function("document.querySelectorAll('#clipGrid .clip').length === 5")
        assert page.get_by_role('button',name='Baixar MP4 ↓',exact=True).count()==5
        assert page.get_by_role('button',name='Assistir Short',exact=True).count()==5
        page.get_by_role('button',name='Assistir Short',exact=True).first.click()
        page.wait_for_selector('video[controls]')
        assert requests[-1]==('/api/download','Bearer '+'x'*40)
        page.evaluate("render({id:'"+job_id+"',count:5,status:'expired',stage:'expired',message:'Arquivos expirados',clips:[]})")
        assert page.locator('#statusTag').inner_text()=='Expirado'
        assert page.locator('#clipGrid .clip').count()==0
        assert not page.locator('#submit').is_disabled()
        page.evaluate("render({id:'"+job_id+"',count:5,status:'cancelled',stage:'cancelled',message:'Cancelado',clips:[]})")
        assert page.locator('#statusTag').inner_text()=='Cancelado'
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not errors,errors
        print(json.dumps({'viewport':width,'five_clips':True,'authenticated_download':True,'expired':True,'cancelled':True,'overflow':False,'page_errors':errors}))
        page.close()
    browser.close()

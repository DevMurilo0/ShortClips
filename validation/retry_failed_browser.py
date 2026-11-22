"""Retry the failed clip through the actual interface; record hashes of ready files."""
from pathlib import Path
import hashlib,json
from urllib.request import urlopen
from playwright.sync_api import sync_playwright
jid=Path('validation/real_5_id.txt').read_text().strip()
with urlopen('http://127.0.0.1:8765/api/jobs/'+jid) as r:job=json.load(r)
assert job['status'] in ('partial','failed'),job['status']
Path('validation/real_5_antes_retry.json').write_text(json.dumps(job,ensure_ascii=False,indent=2))
ready={c['name']:hashlib.sha256((Path('resultados')/jid/c['name']).read_bytes()).hexdigest() for c in job['clips'] if c['status']=='ready'}
Path('validation/real_5_preservados.json').write_text(json.dumps(ready,indent=2))
failed=[c['number'] for c in job['clips'] if c['status']=='failed']
number=failed[0]
with sync_playwright() as p:
 exe=next((Path.home()/'.cache/ms-playwright/chromium-1243').rglob('chrome'))
 browser=p.chromium.launch(headless=True,executable_path=str(exe))
 page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:8765/')
 card=page.locator('article.clip').filter(has=page.get_by_role('heading',name=f'Corte {number} · Falhou'))
 button=card.get_by_role('button',name='Repetir este corte');button.wait_for(timeout=10000)
 with page.expect_response('**/retry') as response:button.click()
 assert response.value.status==202
 print('Retry pelo navegador: corte',number,'HTTP 202; arquivos preservados:',list(ready),flush=True)
 browser.close();assert not errors,errors

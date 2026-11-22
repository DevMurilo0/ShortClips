from pathlib import Path
import hashlib,json
from playwright.sync_api import sync_playwright
jid=Path('validation/real_5_id.txt').read_text().strip();results=[]
with sync_playwright() as p:
 exe=next((Path.home()/'.cache/ms-playwright/chromium-1243').rglob('chrome'))
 browser=p.chromium.launch(headless=True,executable_path=str(exe));errors=[]
 for width,height in ((1440,1000),(390,844)):
  page=browser.new_page(viewport={'width':width,'height':height},accept_downloads=True)
  page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto('http://127.0.0.1:8765/');page.get_by_text('5 de 5 arquivos validados',exact=True).wait_for(timeout=15000)
  assert page.locator('article.clip').count()==5
  assert page.get_by_role('link',name='Baixar MP4 ↓').count()==5
  assert page.get_by_role('link',name='Baixar todos os Shorts (.ZIP) ↓').is_visible()
  assert page.locator('#cancelJob').is_hidden()
  assert page.locator('#submit').is_enabled()
  assert page.locator('body').evaluate('(e)=>e.scrollWidth<=window.innerWidth')
  page.locator('summary').click()
  assert page.locator('#manualBox').is_visible()
  if width==1440:
   with page.expect_download() as event:page.get_by_role('link',name='Baixar MP4 ↓').first.click()
   download=event.value;assert download.failure() is None
   path=Path('validation/download_browser_short_01.mp4');download.save_as(path)
   original=Path('resultados')/jid/'short_01.mp4'
   assert hashlib.sha256(path.read_bytes()).digest()==hashlib.sha256(original.read_bytes()).digest()
  page.screenshot(path=f'validation/interface_final_{width}.png',full_page=True)
  results.append({'viewport':[width,height],'ready_cards':5,'mp4_links':5,'zip_link':True,'overflow':False})
  page.close()
 browser.close();assert not errors,errors
 Path('validation/browser_final.json').write_text(json.dumps({'results':results,'javascript_errors':errors,'mp4_download_sha256_matches':True},indent=2))
 print('Desktop e mobile: 5 cards, 5 MP4s, ZIP, sem overflow/erros JS; MP4 baixado e conferido byte a byte.')

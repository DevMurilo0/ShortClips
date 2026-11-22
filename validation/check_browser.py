"""Browser checks against the real local server, using cached Chromium."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parent
with sync_playwright() as p:
    executable=next((Path.home()/'.cache/ms-playwright/chromium-1243').rglob('chrome'))
    browser=p.chromium.launch(headless=True,executable_path=str(executable))
    errors=[]
    for width,height in ((1440,1000),(390,844)):
        page=browser.new_page(viewport={'width':width,'height':height},accept_downloads=True)
        page.on('pageerror',lambda e:errors.append(str(e)))
        response=page.goto('http://127.0.0.1:8765/');assert response.status==200
        page.wait_for_timeout(1000)
        assert page.locator('#url').input_value()=='https://youtu.be/yWvnOWILFk0'
        assert page.locator('body').evaluate('(e)=>e.scrollWidth<=window.innerWidth')
        page.locator('summary').click()
        assert page.locator('#manualBox').is_visible()
        page.screenshot(path=str(root/f'interface_{width}.png'),full_page=True)
        page.close()
    browser.close()
    (root/'browser_resultado.json').write_text(json.dumps({'viewports':[[1440,1000],[390,844]],'javascript_errors':errors},indent=2))
    assert not errors,errors
    print('Desktop/mobile: HTTP 200, formulário e ajuste manual visíveis, sem overflow e sem erros JavaScript.')

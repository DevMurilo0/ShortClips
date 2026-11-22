import json
from pathlib import Path
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    exe=next((Path.home()/'.cache/ms-playwright/chromium-1243').rglob('chrome'))
    browser=p.chromium.launch(headless=True,executable_path=str(exe))
    page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8765/')
    button=page.get_by_role('button',name='Repetir este corte')
    button.wait_for(timeout=10000)
    assert page.get_by_role('link',name='Ver quadro original').is_visible()
    with page.expect_response('**/retry') as response:button.click()
    assert response.value.status==202
    page.wait_for_timeout(2000)
    assert page.locator('#submit').is_disabled()
    browser.close()
    assert not errors,errors
    print('Falha exibida com prévia e botão. Nova tentativa iniciada pelo navegador: HTTP 202.')

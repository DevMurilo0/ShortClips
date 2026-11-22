# Integração ShortForge cloud — 22/11/2026

Branch `fix/cloud-download-integration`, baseada em `origin/feat/smart-clips-vercel`.
Nenhum deploy/push. Layout e CSS existentes preservados.

- Conexão exige health pronto e consulta autenticada. A chave permanece na aba,
  sem ser publicada em config.js. Última tarefa é recuperada após conexão.
- Resultados Sandbox usam `download_endpoint`/`zip_download_endpoint`: fetch
  com Bearer ao clicar, depois abre URL temporária retornada pelo backend.
- Cinco cards e controles de vídeo sob demanda; `uploading` não anuncia pronto.
- `expired` e `cancelled` são terminais, param polling e liberam novo envio.
- Polling a cada sete segundos e mensagens de erro de consulta/download.
- Retry e prévia de arquivo local ocultos no cloud enquanto não há suporte.
- URLs de resultado do gateway anterior e modo local foram preservados.

Validação: build estático aprovado e teste Playwright
`tests/check_cloud_browser.py` com API **simulada**, Chromium headless em
375×900 e 1280×900. Cinco cards, Bearer no pedido de download, controles de
vídeo, estados cancelado/expirado, sem overflow horizontal nem pageerror.
Não comprova API cloud, playback real, download real ou dispositivo físico.

Exemplo de execução, com Playwright instalado e browser disponível:

```bash
python tests/check_cloud_browser.py
```

`SHORTFORGE_BROWSER_EXECUTABLE` pode indicar um Chromium local compatível.
Não colocar chaves em scripts de teste. O teste usa somente uma chave fictícia.

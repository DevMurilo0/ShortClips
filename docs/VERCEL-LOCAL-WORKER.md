# ShortForge híbrido: site na Vercel + CPU/RAM do próprio PC

Este modo foi feito para uma única pessoa usando o navegador **no mesmo PC
Arch Linux** onde o worker é executado. O processamento local original
suporta vídeos do YouTube de 30 segundos a **6 horas**; o limite de fonte de
120 segundos era apenas do ensaio caro com Vercel Sandbox.

## Como funciona

```text
Vercel: HTML/CSS/JS ── navegador do próprio PC ── http://127.0.0.1:8765
                                                │
                                    Python / yt-dlp / FFmpeg
                                    OpenCV / Faster-Whisper
                                                │
                                  resultados locais: MP4 e ZIP
```

O computador precisa estar ligado e com o processo local ativo durante toda
a análise/geração. O site estático pode abrir de qualquer lugar, mas **só
consegue renderizar no próprio computador que estiver rodando o worker**.
Para processar pelo celular ou de outro PC seria necessária arquitetura
adicional; não exponha o worker com `0.0.0.0` ou um túnel público.

**Não usa Vercel Sandbox, Vercel Blob nem a chave de acesso do backend em
nuvem**. A hospedagem do frontend continua sujeita às franquias gratuitas
da Vercel, mas o processamento de vídeo é pago somente em recursos locais
(CPU, memória, eletricidade e internet do seu PC).

## Preparar / iniciar

Na branch `feat/vercel-ui-local-worker` do repositório
`DevMurilo0/ShortClips`:

```bash
# Uma vez após atualizar o checkout:
cd ~/TopClipsBr/ferramente/ShortClips_Cloud
git fetch origin
git switch feat/vercel-ui-local-worker

# Cada vez que quiser gerar vídeos:
bash ./start-hybrid-worker.sh
```

O launcher reutiliza o script de instalação do projeto, mantém o worker
**somente em 127.0.0.1:8765**, permite a origem Production
`https://short-clips-tan.vercel.app` e os Previews com o padrão estrito
`https://short-clips-<id>-murilo15.vercel.app` no CORS. Ele não inicia
um segundo frontend local. Encerre com **Ctrl+C**.

O diretório real do checkout pode ter outro nome: encontre o repositório
`ShortClips` que contém `app.py` e `iniciar.sh`; não crie cópias
duplicadas nem rode o script no repositório `BackendShortClips`.

Verifique a API local no navegador:
`http://127.0.0.1:8765/api/health`.

Depois abra o **novo deployment frontend** da Vercel nessa branch, clique
em **Verificar meu computador** (se necessário), permita o acesso à
rede local se o navegador solicitar e cole um link do YouTube autorizado.
Você pode pedir um Short de 30s para testar, mas o motor local também
suporta fontes longas. Não há regra de 2 minutos no worker local.

Os vídeos e ZIPs serão gravados em
`<pasta-ShortClips>/resultados/<id-da-tarefa>/`.

## Se a conexão falhar

- Confirme que `bash ./start-hybrid-worker.sh` ainda está em execução.
- Confirme `127.0.0.1:8765/api/health` no mesmo PC.
- Veja se o navegador exibiu pedido de permissão de rede local (Chromium).
- O navegador pode tratar acesso `https://Vercel` →
  `http://127.0.0.1` de modo diferente; teste primeiro no navegador
  usado para geração, sem desabilitar proteções globais do navegador.
- Garanta que a página hospedada está usando o **novo build**; os Previews
  antigos continuam apontando para o backend cloud e não mudam sem deploy.
- Não cole senhas de Vercel nem tokens no navegador.

## Limites e segurança

O worker atende apenas loopback. CORS aceita somente o domínio Production
configurado e nomes de Preview do projeto/equipe, com checagem de `Host`
para reduzir risco de DNS rebinding. Não configura portas abertas na rede,
não usa credenciais de Vercel e não faz upload de resultados para a Vercel.

O acesso pelo navegador ao loopback **não é autenticação geral**. Não use
este modo para atender pessoas fora do seu PC. Não adicione origens
arbitrárias à allowlist nem exponha a porta 8765 na internet.

## Homologação pendente

- Rodar `python -m unittest discover -s tests -v` e `npm test`.
- Publicar um novo Preview frontend após autorização e testar em navegador
  real com permissão de rede local.
- Gerar um MP4 + ZIP de verdade com um vídeo autorizado; verificar
  áudio, legendas e reprodução. Nunca afirmar sucesso antes.

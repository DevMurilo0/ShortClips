# ShortForge híbrido: site na Vercel + CPU/RAM do próprio PC

Este modo foi feito para uma única pessoa usando o navegador **no mesmo PC
Arch Linux** onde o worker é executado. O processamento local original
suporta vídeos do YouTube de 30 segundos a **6 horas**; o limite de fonte de
120 segundos era apenas do ensaio caro com Vercel Sandbox.

## Celular — acesso pelo navegador, mesmo no 4G/5G

Para gerar Shorts no navegador do celular, o processador continua rodando no
**seu computador Arch Linux**. Use Tailscale Serve para criar uma conexão HTTPS
privada entre o celular e o computador. Não usa Vercel Sandbox nem abre a
porta 8765 para a internet.

No PC, configure o Tailscale uma única vez:

```bash
sudo pacman -S --needed tailscale
sudo systemctl enable --now tailscaled
sudo tailscale up
```

Faça login no Tailscale pelo link indicado, se aparecer. Habilite MagicDNS
e HTTPS caso o Tailscale solicite. Instale o aplicativo Tailscale no celular,
entre com a **mesma conta/tailnet** e mantenha-o conectado.

Abra **um terminal** no diretório ShortClips no PC:

```bash
bash ./start-hybrid-worker.sh
```

Quando a API estiver pronta, abra **um segundo terminal**:

```bash
tailscale serve 8765
```

O segundo comando imprime um endereço parecido com
`https://seu-pc.sua-tailnet.ts.net`. É um **exemplo**, não uma URL
que você deva copiar literalmente. O Tailscale Serve só disponibiliza
essa conexão aos dispositivos autenticados na sua tailnet; **não
utilize `tailscale funnel`** para esse fluxo pessoal.

Agora, no **navegador do celular**:

1. Abra o deployment **atualizado** do ShortForge na Vercel.
2. No campo **Endereço do processador (PC ou celular)**, cole a URL
   HTTPS do Tailscale Serve impressa no terminal.
3. Toque **Conectar este dispositivo**. O site salva o endereço
   localmente no navegador do celular, sem enviar senhas ao frontend.
4. Cole um vídeo autorizado, gere os Shorts e use os downloads/players
   no celular. Os arquivos originais continuam no PC.

Funciona usando Wi-Fi ou 4G/5G, desde que **ambos estejam conectados ao
Tailscale e o PC esteja ligado**. No PC, você pode continuar usando
`http://127.0.0.1:8765` no campo do processador.

Se quiser acesso sem instalar Tailscale no celular, seria necessário
outro esquema de túnel e autenticação. Isso **não está implementado**:
abrir o worker diretamente para a internet sem autenticação colocaria
a CPU e a RAM do PC à disposição de terceiros.

O Tailscale Serve usa HTTPS privado, conforme:
https://tailscale.com/docs/features/tailscale-serve
https://tailscale.com/docs/reference/tailscale-cli/serve

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
consegue renderizar com uma conexão ao worker**. No mesmo PC, use o
endereço local; no celular, use Tailscale Serve e a URL HTTPS privada.
Não exponha o worker com `0.0.0.0` nem com um túnel público.

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

O worker atende apenas loopback. Tailscale Serve encaminha conexões privadas
ao loopback por HTTPS, autorizando apenas os dispositivos conectados à
tailnet. CORS aceita somente o domínio Production configurado e nomes de
Preview do projeto/equipe, com checagem de `Host` local ou do hostname
Tailscale exato detectado. Não configura portas abertas na internet,
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

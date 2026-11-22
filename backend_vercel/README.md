# ShortForge API na Vercel (preparação segura)

Esta pasta é um **projeto Vercel separado** da interface. Usa o runtime Python
serverless apenas para API de controle, sem importar FFmpeg, OpenCV ou Whisper.

**IMPORTANTE: não está pronta para gerar Shorts na Vercel sem um WORKER real.**
O gateway retorna **503** caso a integração necessária não esteja configurada,
em vez de inventar arquivos ou tarefas. Ele não serve MP4 pelo limite de resposta
de funções da Vercel. Os MP4/ZIP remotos precisarão ser gravados em armazenamento
de objetos (por exemplo, Vercel Blob) e entregues por URLs temporárias ou públicas
conforme a política de privacidade.

## Implantação dos dois projetos

**Projeto A — Site:**
- Git: DevMurilo0/ShortClips, branch de testes.
- Root Directory: **raiz do repositório**.
- Framework: Other; \`vercel.json\` usa \`public/\` como resultado.
- Opcional \`SHORTFORGE_PUBLIC_API_URL=https://seu-backend.vercel.app\`.
- Nunca coloque segredos em \`SHORTFORGE_PUBLIC_API_URL\` nem no build do frontend.

**Projeto B — API Python:**
- Mesmo Git/repo e branch.
- Root Directory: **backend_vercel**.
- Framework: Other (Python Functions detectadas em \`api/index.py\`).
- Rotas: \`GET /api/health\`, \`POST /api/jobs\`, \`GET /api/jobs/latest\`,
  \`GET /api/jobs/<id>\`, \`POST /api/jobs/<id>/cancel\` e \`/retry\`.
- Sem worker ativo, \`GET /api/health\` informa \`"ready":false\`,
  e \`POST /api/jobs\` retorna **503** deliberadamente.

## Variáveis de ambiente da API

| Nome | Descrição |
| --- | --- |
| \`SHORTFORGE_FRONTEND_ORIGIN\` | Origem exata do site, por exemplo \`https://meusite.vercel.app\` (sem barra final) |
| \`SHORTFORGE_PUBLIC_ACCESS_KEY\` | Chave longa, aleatória e privada de acesso à geração. Introduzida pelo usuário no painel (NUNCA embutir no JavaScript público) |
| \`SHORTFORGE_WORKER_URL\` | Endereço HTTPS de um worker ShortForge seguro |
| \`SHORTFORGE_WORKER_SECRET\` | Segredo de comunicação gateway/worker, diferente da chave pública do usuário |

Todas as variáveis precisam estar presentes para o gateway sinalizar \`ready:true\`.
Essa configuração representa apenas um protótipo **de usuário único**; para disponibilizar
o processamento a todos são necessários autenticação por conta, autorização por tarefa,
rate limits centralizados, quotas, proteção contra abuso, storage durável e filas.

Não coloque tokens no GitHub, nas capturas de tela nem em mensagens.


## Alternativa melhor para um único celular: Vercel Sandbox sob demanda

A Vercel lançou o SDK Python 1.0 de Sandbox em novembro de 2026.
Um **Sandbox sob demanda** pode executar a renderização somente quando um
usuário pedir Shorts, evitando uma instância Daemon permanente. Em planos
Hobby, a duração máxima documentada da execução é de aproximadamente **45
minutos**; mesmo assim, um vídeo de várias horas pode exceder o limite de
tempo, RAM, rede ou recursos de armazenamento. O uso não é ilimitado/gratuito
por definição; confira as quotas da conta antes de ativar.

Essa rota ainda requer código adicional e validação real:
- API inicia um Sandbox isolado e registra um job durável.
- O processo prepara FFmpeg/OpenCV/Faster-Whisper e executa `shortforge.pipeline`.
- Progresso deve ser gravado em armazenamento persistente, não RAM.
- MP4/ZIP devem ser enviados ao Vercel Blob; a API devolve URLs autorizadas.
- Processo deve finalizar em caso de timeout, cancelamento ou falha.

**Essa integração ainda NÃO foi implementada nem implantada neste repositório.**
Não confunda a existência da API em `api/index.py` com Shorts remotos
funcionando. Nunca configure a chave Blob no frontend.

## Etapa que ainda falta: worker de vídeo

O projeto local \`app.py\` mantém tarefas em memória e grava vídeos no filesystem
do computador. Isso não funciona diretamente em Vercel Functions:

- funções podem ser encerradas ao atingir limite de tempo;
- processos e diretórios locais não são armazenamento compartilhado e durável;
- downloads de MP4/ZIP não devem passar por uma resposta de função grande.

Uma implantação completa com recursos Vercel pode usar:
1. API Python (aqui);
2. Vercel Queue ou outro sistema durável de fila;
3. Vercel Daemon em Docker com FFmpeg, yt-dlp, OpenCV e Whisper;
4. Vercel Blob para armazenar MP4/ZIP, mais banco de estado para jobs.

A disponibilidade do Daemon e as quotas/custos dependem da conta e das
configurações; configurar uma instância continuamente ativa pode consumir
recursos mesmo com apenas um celular conectado. Essa etapa exige conferir
recursos da sua conta e aprovar possíveis custos antes de implantar.

## Checagens

- \`GET /api/health\` sempre informa o estado real de configuração.
- Testes locais: \`python -m unittest discover -s tests -v\` na raiz do repositório.
- Após implantação: abrir \`https://SEU-BACKEND.vercel.app/api/health\`.

Não exponha \`app.py\` diretamente à internet; uma allowlist CORS não é
autenticação. Habilite um segredo \`SHORTFORGE_WORKER_SECRET\` no processo local
antes de qualquer ligação por HTTPS/Tunnel e não use a URL interna para arquivos
públicos.

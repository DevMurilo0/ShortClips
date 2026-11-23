# ShortForge — Cloud privado e Production sem chave no navegador

**Estado:** código preparado. Não significa que Production foi publicada, que a
franquia Hobby foi comprovada ou que um vídeo real foi gerado. Faça
homologação real primeiro. Nenhum passo deste documento exige instalar algo
no celular ou executar comandos no computador do usuário.

## Arquitetura

- Site HTML/CSS/JS original hospedado na Vercel; mantém layout responsivo.
- A pessoa abre o site no celular ou desktop, autentica-se pelo **login
  Vercel**, cola um link do YouTube autorizado e pede cortes.
- Uma Function privada de mesma origem `/api/backend` recebe o pedido e
  usa as credenciais **somente no servidor**, nunca embutidas no JavaScript.
- O backend usa Blob privado para estado e saídas e cria um Sandbox temporário
  (2 vCPU, 4 GiB, **até 20 minutos** em Production), que analisa o vídeo,
  seleciona trechos via heatmap real ou heurística de energia de áudio,
  detecta facecam, transcreve com Faster-Whisper, renderiza 9:16 e entrega
  MP4 + ZIP autenticados. Resultados expiram em 24 horas.
- Os vídeos longos são aceitos até **6 horas**, sem baixar a gravação
  original inteira em vídeo; a execução baixa o áudio sob limite de 128 MiB
  e trechos selecionados sob limite de tempo. Isso pode falhar dependendo do
  formato disponibilizado pelo YouTube, rede ou tempo do Sandbox.
- A seleção e a detecção de facecam são heurísticas: resultados precisam de
  revisão humana; não prometer virais, rosto correto, cortes perfeitos nem
  legendas sem erros.

## Requisitos obrigatórios para Production

1. Os projetos Vercel existentes `short-clips` e `backend-short-clips`
   devem estar acessíveis pelo mesmo operador, no plano **Hobby**, sem novos
   projetos nem recursos pagos.
2. Em **ambos os projetos**, habilitar **Vercel Authentication → All
   Deployments** e comprovar que um navegador anônimo não consegue acessar a
   Production. Documentação:
   https://vercel.com/changelog/protect-production-deployments-for-free-on-every-plan
3. No backend Production, configurar **somente no lado servidor**:
   - `SHORTFORGE_ENGINE=sandbox`
   - `SHORTFORGE_STORAGE_PREFIX=shortforge`
   - `SHORTFORGE_CLOUD_PRODUCTION_APPROVED=1` **apenas após homologação**
   - `SHORTFORGE_MAX_JOBS_MONTH=1` (teto do projeto, não da conta inteira)
   - `SHORTFORGE_FRONTEND_ORIGIN=https://short-clips-tan.vercel.app`
   - `SHORTFORGE_PUBLIC_API_URL=https://backend-short-clips.vercel.app`
   - `BLOB_READ_WRITE_TOKEN` válido, para **Blob privado**
   - `SHORTFORGE_PUBLIC_ACCESS_KEY` aleatória de pelo menos 32 caracteres
   - `SHORTFORGE_WORKER_SECRET` aleatória, distinta e de pelo menos 32 caracteres
   - `SHORTFORGE_VERCEL_PROTECTION_BYPASS` = bypass de automação permitido
     pela proteção do **backend**, somente para chamadas internas do worker.
4. No frontend Production, configurar variáveis privadas de Function:
   - `SHORTFORGE_PUBLIC_API_URL=https://backend-short-clips.vercel.app`
     (endereço público, não credencial)
   - `SHORTFORGE_OWNER_PRODUCTION_ENABLED=1` **após verificar proteção**
   - `SHORTFORGE_PRODUCTION_ADMISSION=0` **até autorizar o primeiro job real**
   - `SHORTFORGE_OWNER_ACCESS_KEY` = mesmo valor privado do
     `SHORTFORGE_PUBLIC_ACCESS_KEY` do backend
   - `SHORTFORGE_BACKEND_PROTECTION_BYPASS` = bypass de automação autorizado
     no **backend** (não o login da pessoa).
5. Fazer deployments **Preview protegidos**, validar ambos os `/api/health`
   e gateway `/api/backend?path=%2Fapi%2Fhealth` sem revelar segredos.
6. Confirmar o saldo real das franquias Sandbox, Blob, funções e rede do time.
   Como este app **não consegue** consultar com garantia o saldo completo da
   conta ou de outros projetos, **não abrir admissão** se isso não estiver
   confirmado. Um cap interno de 1 job/mês e 20 min de VM *reduz*, mas
   **não garante** nunca cobrar se houver consumo externo.
7. Homologar um job com vídeo de propriedade/autorizado, por exemplo
   `https://www.youtube.com/watch?v=NZRCjPMb0AY`, conferindo:
   título/duração real, seleção de cenas, facecam, MP4 com áudio, legendas,
   ZIP, download autenticado, limpeza do Sandbox e custos efetivos.
8. Só então definir `SHORTFORGE_PRODUCTION_ADMISSION=1`, promover o código
   aprovado e conferir a Production pelo navegador em celular e desktop.
   Sem testes reais, permanecer com a admissão desativada.

## Outras garantias e restrições

- Em Production, o frontend não solicita **chave manual**. A autenticação é
  feita pela própria Vercel no início da sessão.
- A API proxy recusa origens arbitrárias, domínios não homologados e pedidos
  de geração acima de 3 Shorts, 45 segundos ou 720p.
- A API backend exige `SHORTFORGE_CLOUD_PRODUCTION_APPROVED=1`,
  `SHORTFORGE_MAX_JOBS_MONTH=1` e bypass privado antes de aceitar tarefas.
- Todos os dados, chaves e downloads ficam em serviços protegidos; não
  imprimir valores de secrets em logs, testes ou PRs.
- O vídeo YouTube **não** é publicado nem redistribuído automaticamente.
- É necessária autorização para processar o vídeo, confirmada pelo usuário.
- Recursos de processamento são de terceiros; o YouTube pode negar acesso,
  exigir autenticação ou alterar seus protocolos.
- Não usar `tailscale serve`, PC local, porta 8765 nem scripts em celulares
  neste modo.
- Nunca criar um segundo projeto Vercel com o nome de um já existente.

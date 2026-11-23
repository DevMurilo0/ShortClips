# ShortForge — acesso individual sem chave no navegador (Preview)

Esta branch prepara o **Preview protegido** para uso de um único proprietário. O
campo de chave desaparece do site Preview; não há autenticação anônima nem chave
embutida nos assets HTML/JS. O frontend chama `/api/backend` na mesma origem,
e a Function envia a credencial privada ao backend autorizado.

## Requisitos obrigatórios antes de permitir criar um Short

1. Habilitar **Vercel Authentication** (Deployment Protection) para o frontend
   Preview e o backend Preview. **Sem essa proteção, não habilitar admissão**:
   cabeçalhos Origin não autenticam clientes de scripts.
2. Frontend Preview (variáveis privadas, nunca comitar):
   - `SHORTFORGE_PUBLIC_API_URL`: URL exata e imutável do backend Preview
     (formato `https://backend-short-clips-<id>-murilo15.vercel.app`).
   - `SHORTFORGE_PREVIEW_ACCESS_KEY`: mesmo segredo privado de
     `SHORTFORGE_PUBLIC_ACCESS_KEY` do backend; comprimento mínimo de 32.
   - `SHORTFORGE_BACKEND_PREVIEW_SHARE`: share autorizado **para esse
     deployment backend específico**, jamais exposto ao navegador.
   - `SHORTFORGE_PREVIEW_ADMISSION`: omitir ou `0` até confirmar direitos de
     uso do vídeo, orçamento da Vercel, os dois deploys e o callback; só então
     definir `1` **exclusivamente no Preview** e publicar essa configuração.
3. Backend Preview (somente esse deployment, nunca Production):
   - `SHORTFORGE_ENGINE=sandbox`;
   - `SHORTFORGE_STORAGE_PREFIX=shortforge-preview/<namespace-isolado>`;
   - `SHORTFORGE_PREVIEW_AUTHORIZED_YOUTUBE` = URL canônica de **um vídeo**
     individual de 30 a 120 segundos, do proprietário ou autorizado;
   - `SHORTFORGE_PREVIEW_RIGHTS_CONFIRMED=1`;
   - `SHORTFORGE_PUBLIC_ACCESS_KEY` e `SHORTFORGE_WORKER_SECRET` distintos,
     secretos, de pelo menos 32 caracteres;
   - `SHORTFORGE_VERCEL_PROTECTION_BYPASS`: bypass de automação autorizado
     apenas para o worker chamar o callback protegido; se a correção do PR
     backend de bypass automático tiver sido aplicada, pode-se usar o segredo de
     sistema `VERCEL_AUTOMATION_BYPASS_SECRET` quando presente.
   - `BLOB_READ_WRITE_TOKEN` real do Blob **privado**; nunca o placeholder
     `[SENSITIVE]`.
   - `SHORTFORGE_MAX_JOBS_MONTH=1` no namespace de homologação.
   - Não configurar um `SHORTFORGE_PUBLIC_API_URL` apontando para outro
     deployment; o backend confere `VERCEL_URL` quando disponível.
4. Confirmar o `/api/health` do backend (`ready=true`) e o
   `/api/backend?path=%2Fapi%2Fhealth` do frontend
   (`ready=true` e `admission_ready=true`) **antes** de criar qualquer VM.
   Desabilitar admissão se houver falha, sem impedir cancelamentos.
5. A primeira solicitação exige `rights_confirmed=true`, `count=1`,
   `length=30`, `resolution=720` e `manual_box=[x,y,w,h]` em porcentagens.
   O backend deve recusar outras fontes e manter o marcador create-only de
   **um único processamento**, até 10min, 2 vCPUs/4 GB, sem repetição paga.
6. Verificar estado, callback, MP4+ZIP assinados, encerramento/remoção da
   máquina e consumo na Vercel; não declarar homologado antes do teste real.

## Escopo

- A Function `api/backend.js` e o modo da UI são **Preview-only** por código.
  A Production anterior continua desativada; não habilitar sem aprovação
  específica e proteção adequada.
- Não é necessário definir `SHORTFORGE_PREVIEW_PROXY` para habilitar a UI no
  Preview: a build identifica `VERCEL_ENV=preview`.
- A admissão é uma chave administrativa, **não** a chave de acesso do usuário.
  Deve permanecer exclusivamente no servidor.
- Sem uma configuração segura do backend, o frontend exibirá uma mensagem
  explícita de bloqueio em vez de simular um Short.
- Vercel Authentication pode proteger Production no Hobby mediante opção
  **All Deployments**, mas isso não torna este Preview apto à produção sem uma
  homologação real, limites e uma autorização de lançamento.

Nenhum destes passos de nuvem foi executado automaticamente nesta branch.

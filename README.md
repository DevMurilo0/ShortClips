# ShortForge Local — Shorts automáticos com facecam + gameplay

**Do link do YouTube para vídeos MP4 e um ZIP, sem créditos do vidIQ.**

Projeto com interface web local. Você abre uma vez no VS Code, cola um link e clica em **Gerar Shorts**. Ele tenta:

1. Consultar o gráfico *Mais reproduzido* (heatmap), **se estiver disponível** na informação do vídeo extraída pelo yt-dlp.
2. Se não estiver, baixar apenas o áudio e escolher momentos por uma **heurística de energia/variação do som**. Isso NÃO equivale a descobrir quais trechos tiveram mais visualizações ou repetições reais.
3. Baixar as partes correspondentes do vídeo original do YouTube (sem você baixar ou anexar nada manualmente).
4. Detectar a webcam/facecam com OpenCV. Em cima: crop do rosto. Embaixo: gameplay completa, ajustada proporcionalmente sobre fundo desfocado.
5. Gerar legendas em português com Faster-Whisper (local), montar vídeos **9:16**, com áudio original.
6. Disponibilizar MP4s e ZIP, somente se a duração final estiver entre 30 e 60 segundos, com áudio e decodificação válidos.

## Requisitos

- Linux Arch / derivados (também funciona em outras distribuições que tenham Python 3.10+ e FFmpeg com libass).
- CPU moderna o bastante para transcrição e espaço em disco para vídeo e áudio. Um vídeo de **3 horas pode demorar bastante**, conforme a conexão e o hardware.
- Internet para acessar o YouTube e baixar o modelo Faster-Whisper na primeira execução.
- O vídeo deve estar acessível e você deve ter autorização para reutilizar seu conteúdo.

## Guia rápido — Arch Linux

Abra a pasta `ShortForge_Local` no VS Code. Em um terminal **dentro da pasta**:

```bash
sudo pacman -S --needed python python-pip ffmpeg tesseract
chmod +x iniciar.sh
./iniciar.sh
```

Se preferir usar apenas o VS Code, pressione **Ctrl+Shift+P → Tasks: Run Task → Iniciar ShortForge**. Depois, só use a interface do navegador.

O launcher cria `.venv`, confere `requirements.txt` na primeira execução e quando seu conteúdo mudar, abre a interface local e mostra o endereço no terminal.

Caso o navegador não abra sozinho: **http://127.0.0.1:8765**

**A partir daí, basta colar o link**, escolher a quantidade (padrão 5) e clicar em gerar.

As saídas também ficam na pasta `resultados/<id-da-tarefa>/`, e a interface oferece links para baixar.

### Exemplo para testar

`https://youtu.be/yWvnOWILFk0`

Para testar mais rápido, em **Configurações avançadas**, escolha **1 Short** e **720 × 1280**. Quando o teste estiver correto, escolha cinco e 1080 × 1920.


## Correção do erro `metadata_errors` (versão corrigida)

Se você usou uma versão anterior do ShortForge e apareceu:

```text
open() got an unexpected keyword argument 'metadata_errors'
```

O problema é a incompatibilidade entre `faster-whisper` e a versão 19 do PyAV.
Esta versão do projeto fixa **PyAV 18.1.0** e o `./iniciar.sh` corrige automaticamente
ambientes virtuais que já tinham as dependências instaladas.

Se preferir corrigir sem baixar outro ZIP, execute na pasta do projeto:

```bash
.venv/bin/python -m pip install "av==18.1.0"
./iniciar.sh
```

Não é necessário atualizar todo o Arch Linux nem apagar a pasta `.venv`.

## Sobre a detecção automática da facecam

O OpenCV agrupa rostos detectados em posições persistentes nas laterais do trecho, contando quadros distintos. A webcam pode estar no meio de uma lateral. A detecção exige pelo menos 45% dos quadros amostrados e não confirma automaticamente um rosto se esse limiar falhar. Personagens imóveis ou outras faces persistentes ainda podem provocar falsos positivos: confira a montagem antes de publicar.

Quando a detecção falha, o corte aparece como **Falhou**, com acesso a uma prévia do quadro original. Nas configurações avançadas, informe uma região manual em porcentagens: `x y largura altura`, medidos a partir do canto superior esquerdo. Por exemplo: `79 43 21 25`. Clique em **Repetir este corte**; os demais MP4s prontos são preservados. A escolha por canto continua disponível para novos trabalhos, mas é identificada como manual quando nenhum rosto é confirmado.

A metade inferior mantém a composição original inteira, proporcionalmente, sem esticar nem remover as bordas da gameplay. O espaço excedente usa uma cópia desfocada; isso preserva o personagem e o contexto sem barras pretas adicionadas. Não há reconhecimento semântico nem rastreamento do personagem.

## Sobre legendas

Faster-Whisper roda na CPU. O primeiro uso baixa o modelo. A legenda segue os tempos detectados pelo Whisper, mas pode cometer erros em nomes, palavrões, ruídos, inglês e falas sobrepostas. Confira antes de publicar. Os arquivos `.srt` estão no ZIP para ajustes posteriores.

## Limitações importantes

- O YouTube pode bloquear downloads, exigir login, limitar vídeos ou mudar de funcionamento. O projeto não contorna restrições e não garante que **todo link** possa ser processado.
- `yt-dlp --download-sections` depende de recursos do site e do FFmpeg. Se falhar, aparece erro na interface, sem inventar um arquivo de saída.
- Sem heatmap, a análise automática de áudio é **estimativa**, não uma métrica real de audiência/virais.
- Para vídeos muito grandes, o processo pode gastar muitos minutos e centenas de megabytes de espaço. As ferramentas são gratuitas/open source, mas processamento e download consomem recursos da máquina.
- O ShortForge não publica vídeos, não cria contas e não pede sua senha do YouTube.
- O servidor abre apenas no endereço `127.0.0.1` (seu computador).

## Como mudar o layout

Edite `render_split` no arquivo `shortforge/media.py`. Atualmente cada região ocupa 50% da altura (facecam em cima, gameplay embaixo), com legendas na região inferior.

## Licença

Código de exemplo fornecido para uso e adaptação. Dependências e o conteúdo dos vídeos seguem suas próprias licenças e termos.

## Estados, cancelamento e recuperação

A interface informa a etapa em execução e quantos arquivos foram realmente validados. A barra representa arquivos prontos, não uma estimativa de tempo de download ou transcrição. Cortes que falharam ficam visíveis com o erro real e botão para repetição individual. O cancelamento interrompe subprocessos (incluindo os filhos do yt-dlp); uma inferência nativa já iniciada pode levar até o retorno do próximo segmento para observar o cancelamento.

O estado fica em `resultados/<id>/tarefa.json` e é restaurado no reinício. Tarefas interrompidas são marcadas como falhas. MP4s prontos continuam disponíveis. Diretórios de renderização são exclusivos e removidos ao terminar, inclusive em falhas. Originais e downloads parciais são mantidos para diagnóstico/repetição, sem limpeza automática dos resultados do usuário.

O ZIP contém somente MP4s validados, seus SRTs e `relatorio.json`. A presença de SRT não é usada como prova de incorporação: a renderização aplica o filtro `subtitles` obrigatoriamente, e os testes verificam pixels do MP4 decodificado.

## Testes

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m pip check
node --check web/app.js
bash -n iniciar.sh
```

Com o servidor aberto, o teste real (faz download e processamento) é:

```bash
.venv/bin/python validation/run_real.py 1
# Depois de inspecionar e validar o primeiro MP4:
.venv/bin/python validation/run_real.py 5
```

As evidências desta investigação ficam em `validation/`. A seleção por áudio considera energia, variação e pausas próximas ao início; ela não identifica com certeza menus, continuidade narrativa ou frases completas. Uma verificação visual posterior rejeita imagens praticamente estáticas e molduras persistentes de vídeo inserido/TV, tentando candidatos de reserva distintos. Isso reduz alguns falsos destaques, mas não substitui entendimento semântico da cena. O alvo é 45 segundos e os intervalos selecionados não se sobrepõem. Sem dados suficientes, o programa entrega menos cortes e informa resultado parcial.

A verificação de menus usa OCR local com Tesseract e um modelo português de aproximadamente 2 MB, baixado do projeto oficial `tesseract-ocr/tessdata_fast` e verificado por SHA-256. O modelo fica em `modelos/tessdata/por.traineddata`; as imagens analisadas permanecem locais. Cabeçalhos de configurações/mapa e controles de celular no rodapé em 20% ou mais das amostras levam à escolha de outro candidato. Isso é uma heurística e pode deixar de reconhecer interfaces de outros jogos/idiomas. O manifesto do modelo identifica origem, revisão e licença.

## Melhorias de seleção e legendas (branch smart-clips)

A seleção continua sendo uma **heurística**, não um modelo semântico que assiste
ao vídeo inteiro. Agora a classificação avalia **toda a janela de 30–60 s**,
compara sua intensidade média aos picos do próprio trecho, penaliza cortes em
fronteiras muito barulhentas e incentiva variedade ao longo de vídeos extensos.
O gráfico real "Mais reproduzido", quando disponível, ainda tem prioridade.
A verificação por OCR e movimento descarta trechos suspeitos de menus e pausas.

O Faster-Whisper continua gerando timestamps por palavra, mas as legendas são
organizadas em cartões curtos (aproximadamente 2–5 palavras), com quebra de
linha controlada, letras mais legíveis e contorno mais forte. Não há promessa
de transcrição perfeita: nomes e falas sobrepostas exigem revisão humana.

## Publicação da interface na Vercel

**A Vercel hospeda somente a interface HTML/CSS/JS.** O Python, FFmpeg, yt-dlp,
OpenCV e Whisper **não rodam apenas em um `index.html`**, e o motor de vídeo
não cabe no padrão de funções serverless curtas. Publicar esta branch na
Vercel disponibiliza um site público, mas **a geração de Shorts só funciona
quando uma API de processamento separada estiver implantada e conectada**.

1. Na Vercel, importe `DevMurilo0/ShortClips` e escolha a branch desejada.
2. Mantenha o framework como **Other**, o build `node scripts/build_static.mjs`
   e o diretório de saída `public`. O `vercel.json` já define isso.
3. Opcionalmente, configure `SHORTFORGE_PUBLIC_API_URL=https://api.seudominio.com`
   nas variáveis de ambiente da Vercel (endereço **público**, nunca token).
4. Sem API implantada, a página exibe o painel "Conectar o motor de processamento"
   e desabilita geração; não exibe resultados fictícios.

Para testar o build em sua máquina: `node scripts/build_static.mjs`.
Serão produzidos `public/index.html`, `public/style.css`,
`public/app.js` e `public/config.js`.

### API remota e segurança

O servidor atual (`app.py`) foi criado para **uso local** e escuta por padrão
em `127.0.0.1:8765`. É possível configurar `SHORTFORGE_HOST` e a variável
`SHORTFORGE_ALLOWED_ORIGINS` (origens exatas separadas por vírgula) para
testar uma interface em outro domínio, com `/api/health` para verificação.
**CORS não é autenticação**, e não é seguro abrir este servidor sem controles
adicionais: a API atual expõe tarefas e downloads sem isolamento por usuário.
Para disponibilizar geração ao público são necessários, antes da exposição:
autenticação e autorização por tarefa, limites de requisição e de duração,
fila com workers, armazenamento durável, expiração/limpeza de arquivos,
HTTPS e proteção contra abuso/custos. Use essas medidas em um backend
dedicado ou um proxy autenticado. Não configure `SHORTFORGE_HOST=0.0.0.0`
diretamente na internet sem essas proteções.

Um computador local pode servir como worker de testes, mas precisa permanecer
ligado, e um endereço `127.0.0.1` não é acessível aos visitantes da Vercel.


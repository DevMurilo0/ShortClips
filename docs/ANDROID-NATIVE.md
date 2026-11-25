# ShortForge nativo no Termux (Android ARM64)

Não requer Ubuntu, PRoot, root, Vercel ou outro computador. Utilize Termux
atualizado de uma fonte oficial. Instale dentro de $HOME, não /sdcard (o
armazenamento compartilhado não permite executar os binários normalmente).

```bash
pkg update && pkg upgrade -y
pkg install -y git
git clone https://github.com/DevMurilo0/ShortClips.git
cd ShortClips
bash instalar-android.sh
./iniciar-android.sh
```

O instalador habilita o repositório oficial x11 apenas para obter OpenCV e
suas dependências; não é necessário instalar ou abrir um servidor gráfico.
Usa NumPy e OpenCV do pkg, ambiente Python com acesso aos pacotes do sistema,
yt-dlp/EJS/Node, FFmpeg, Tesseract e compila whisper.cpp v1.7.6 nativamente.
Baixa o modelo multilíngue Tiny (~75 MiB), com checksum publicado; Base e
Small são obtidos sob demanda. Não instala PyAV/Faster-Whisper no Android.

Abra http://127.0.0.1:8765 no navegador do celular. Os vídeos e ZIPs podem ser
baixados no navegador, sem permissão de armazenamento no Termux.

## Próximos usos

```bash
cd ~/ShortClips
termux-wake-lock
./iniciar-android.sh
```

Ctrl+C encerra o servidor. Use termux-wake-unlock depois.
Para atualizar: git pull --ff-only origin main. Se mudar a dependência
ou Python do Termux, repita bash instalar-android.sh.

## Configuração recomendada

Primeiro um corte, 30 segundos, 720p, Tiny e facecam automática. Depois
cinco cortes, se houver RAM, disco e tempo disponíveis. O mesmo pipeline
seleciona trechos e renderiza facecam + gameplay + legendas; o adaptador
Whisper.cpp fornece tempos por segmento, e o agrupamento existente estima
os tempos de cartões menores (não equivale a timestamps por palavra).
O motor usa dois threads para transcrição e codificação. Vídeos longos
continuam aceitos, mas Android pode encerrar processos por temperatura,
memória ou política de bateria. Mantenha espaço livre e o Termux ativo.
O acesso autorizado ao YouTube permanece sujeito às restrições do serviço.

## Verificação

```bash
./iniciar-android.sh --check
```

O preflight confere Node/EJS, FFmpeg (libass/x264), OCR, cascata facial,
Whisper CLI e leitura de um MP4 sintético por OpenCV. Não gera Shorts reais.
A instalação em Android físico ainda precisa ser confirmada. PC e PRoot
continuam com os launchers anteriores.

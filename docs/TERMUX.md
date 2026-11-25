# ShortForge no Android pelo Termux

Perfil: Android ARM64, Termux atualizado (F-Droid/GitHub oficial), Ubuntu 24.04
ARM64 via PRoot-Distro 5 ou superior. Não precisa de root, Vercel, computador
externo ou Tailscale. O Ubuntu é um ambiente local dentro do próprio celular.
Não tente instalar as dependências nativas do motor diretamente no Python do
Termux (Android usa Bionic, as wheels Linux ARM64 usam glibc).

## Primeira instalação (no Termux)

```bash
pkg update && pkg upgrade -y
pkg install -y proot-distro
proot-distro install ubuntu:24.04 --name shortforge
proot-distro login shortforge
```

No Ubuntu aberto pelo comando acima:

```bash
apt-get update
apt-get install -y git ca-certificates
git clone https://github.com/DevMurilo0/ShortClips.git ~/ShortClips
cd ~/ShortClips
bash instalar-termux.sh
./iniciar-termux.sh
```

Abra http://127.0.0.1:8765 no navegador do próprio Android. Os downloads
MP4/ZIP usam a interface. Não é necessário expor portas.

## Próximos usos (no Termux)

```bash
termux-wake-lock
proot-distro login shortforge -- bash -lc 'cd ~/ShortClips && ./iniciar-termux.sh'
```

Para parar use Ctrl+C; depois, `termux-wake-unlock`. Permita execução em segundo
plano nas configurações de bateria do Android/HyperOS. O Android ainda pode
encerrar processos por memória, temperatura ou restrições do fabricante.
Mantenha espaço disponível (recomendação inicial: pelo menos 5–8 GB),
Wi-Fi e ventilação; vídeos longos podem exigir mais espaço.

## Configuração inicial recomendada

1 corte, 30 segundos, 720p, Whisper Tiny para testar, facecam automática.
Depois escolha 5 cortes e Base se o desempenho permitir. O perfil mobile limita
threads de Whisper e FFmpeg a 2; o PC continua com 4. Vídeos de duas horas
continuam aceitos, sem limite da Vercel. A duração de processamento depende do
aparelho e do acesso ao YouTube. Não há promessa de que todos os vídeos funcionem.

## Atualizar

Dentro do Ubuntu: `cd ~/ShortClips && git pull --ff-only origin main`.
Se as dependências mudarem, execute novamente `bash instalar-termux.sh`.
Para apenas checar as dependências: `./iniciar-termux.sh --check`.

O preflight verifica imports, CPU int8, ONNX, cascata facial, libass,
libx264, Node e EJS. Não cria tarefas ou baixa modelos Whisper. Os modelos
são baixados no primeiro processamento. O perfil foi preparado para Linux
ARM64 via PRoot, mas precisa de validação em um Android físico.

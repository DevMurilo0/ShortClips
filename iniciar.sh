#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v python >/dev/null 2>&1; then
  echo 'Python não encontrado. No Arch: sudo pacman -S python python-pip'
  exit 1
fi
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo 'FFmpeg não encontrado. No Arch: sudo pacman -S ffmpeg'
  exit 1
fi
if ! command -v ffprobe >/dev/null 2>&1; then
  echo 'ffprobe não encontrado. No Arch: sudo pacman -S ffmpeg'
  exit 1
fi
if ! command -v tesseract >/dev/null 2>&1; then
  echo 'Tesseract não encontrado. No Arch: sudo pacman -S tesseract'
  exit 1
fi
if [ ! -d .venv ]; then
  echo 'Criando ambiente Python isolado...'
  python -m venv .venv
fi
source .venv/bin/activate
requirements_hash=$(sha256sum requirements.txt | cut -d ' ' -f 1)
installed_hash=$(cat .venv/shortforge-dependencies-ready 2>/dev/null || true)
if [ "$requirements_hash" != "$installed_hash" ]; then
  echo 'Conferindo dependências do projeto...'
  python -m pip install -r requirements.txt
  printf '%s\n' "$requirements_hash" > .venv/shortforge-dependencies-ready
fi
# Corrige automaticamente ambientes criados antes do ajuste de compatibilidade.
# O marcador antigo de dependências já instaladas não deve impedir o conserto.
if ! python -c 'import av; assert av.__version__ == "18.1.0"' >/dev/null 2>&1; then
  echo 'Ajustando PyAV para uma versão compatível com as legendas (18.1.0)...'
  python -m pip install 'av==18.1.0'
fi
python app.py

#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ -z "${PREFIX:-}" ] || [ ! -x "$PREFIX/bin/pkg" ]; then
  echo 'Execute no Termux nativo.' >&2; exit 1
fi
if [ ! -x .venv-android/bin/python ]; then
  echo 'Execute primeiro bash instalar-android.sh.' >&2; exit 1
fi
export SHORTFORGE_ANDROID_NATIVE=1 SHORTFORGE_TERMUX=1 SHORTFORGE_NO_BROWSER=1 SHORTFORGE_HOST=127.0.0.1
export SHORTFORGE_WHISPER_CLI="$HOME/.local/share/shortforge/whisper.cpp-v1.7.6/build/bin/whisper-cli"
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
unset SHORTFORGE_WORKER_SECRET SHORTFORGE_ALLOWED_ORIGINS SHORTFORGE_API_URL
.venv-android/bin/python scripts/check_android.py
if [ "${1:-}" = --check ]; then exit 0; fi
echo 'Abra no navegador: http://127.0.0.1:8765'
exec .venv-android/bin/python app.py

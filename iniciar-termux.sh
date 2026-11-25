#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv-termux/bin/python ]; then
  echo 'Execute primeiro ./instalar-termux.sh dentro do Ubuntu.' >&2; exit 1
fi
export PATH="$HOME/.local/share/shortforge/node-v22.23.5/bin:$PATH"
export SHORTFORGE_TERMUX=1 SHORTFORGE_NO_BROWSER=1 SHORTFORGE_HOST=127.0.0.1
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 TOKENIZERS_PARALLELISM=false
unset SHORTFORGE_WORKER_SECRET SHORTFORGE_ALLOWED_ORIGINS SHORTFORGE_API_URL
.venv-termux/bin/python scripts/check_termux.py
if [ "${1:-}" = --check ]; then exit 0; fi
echo 'Abra no navegador do Android: http://127.0.0.1:8765'
exec .venv-termux/bin/python app.py

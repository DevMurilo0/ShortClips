#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$ROOT/.local"
if [[ -f "$ROOT/.local/server.pid" ]]; then
  read -r SERVER_PID < "$ROOT/.local/server.pid"
  if [[ "$SERVER_PID" =~ ^[0-9]+$ ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "ShortForge já está rodando. Use ./stop-local.sh para encerrar."
    exit 1
  fi
fi
if [[ -n "${SHORTFORGE_PYTHON:-}" ]]; then
  PYTHON="$SHORTFORGE_PYTHON"
elif [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
elif [[ -x "$ROOT/../ShortForge_Local/.venv/bin/python" ]]; then
  PYTHON="$ROOT/../ShortForge_Local/.venv/bin/python"
else
  python -m venv "$ROOT/.venv"
  "$ROOT/.venv/bin/pip" install -r "$ROOT/requirements.txt"
  PYTHON="$ROOT/.venv/bin/python"
fi
"$PYTHON" -c 'import cv2, numpy, faster_whisper, av, yt_dlp'
for tool in ffmpeg ffprobe tesseract; do
  command -v "$tool" >/dev/null || { echo "Dependência ausente: $tool" >&2; exit 1; }
done
if [[ "${1:-}" == '--background' ]]; then
  nohup setsid "$PYTHON" "$ROOT/local_dev.py" > "$ROOT/.local/server.log" 2>&1 < /dev/null &
  sleep 2
  if ! kill -0 "$!" 2>/dev/null; then cat "$ROOT/.local/server.log"; exit 1; fi
  head -3 "$ROOT/.local/server.log"
  echo "Logs: $ROOT/.local/server.log"
  echo "Encerrar: $ROOT/stop-local.sh"
else
  exec "$PYTHON" "$ROOT/local_dev.py"
fi

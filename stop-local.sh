#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python - "$ROOT" <<'PY'
from pathlib import Path
import os, signal, sys, time
root=Path(sys.argv[1]); pidfile=root/'.local/server.pid'
if not pidfile.exists():
    print('ShortForge local já está parado.'); raise SystemExit(0)
pid=int(pidfile.read_text())
try: cmd=Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
except FileNotFoundError:
    pidfile.unlink(missing_ok=True);print('Processo já encerrado.');raise SystemExit(0)
if str(root/'local_dev.py').encode() not in cmd:
    raise SystemExit('PID pertence a outro processo; nenhum sinal enviado.')
os.kill(pid,signal.SIGTERM)
for _ in range(250):
    if not pidfile.exists(): print('Servidores e processamento local encerrados.');break
    time.sleep(.1)
else: raise SystemExit('Encerramento ainda em andamento; consulte .local/server.log.')
PY

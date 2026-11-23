#!/usr/bin/env bash
# Serve only on this machine. The hosted Vercel frontend uses the browser
# to call http://127.0.0.1:8765; nothing here is sent to Vercel Sandbox.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export SHORTFORGE_HOST=127.0.0.1
export SHORTFORGE_PORT=8765
export SHORTFORGE_NO_BROWSER=1
export SHORTFORGE_ALLOW_TEAM_PREVIEWS=1
export SHORTFORGE_ALLOWED_ORIGINS="https://short-clips-tan.vercel.app,https://short-clips-hz47qwzcp-murilo15.vercel.app"
# Reuse unrestricted local pipeline; cloud's 2-minute test source cap does not apply.
unset SHORTFORGE_WORKER_SECRET
unset SHORTFORGE_LOCAL_CONTROLLED
echo
echo "ShortForge: CPU e RAM deste computador, sem Sandbox/Blob."
echo "API local: http://127.0.0.1:8765/api/health"
echo "Site: https://short-clips-tan.vercel.app (ou Preview desta equipe)"
echo "Mantenha este terminal aberto enquanto gera Shorts. Ctrl+C encerra."
echo
exec bash "$ROOT/iniciar.sh"

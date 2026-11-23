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
# When Tailscale is already connected, permit only this device's exact
# MagicDNS hostname through Tailscale Serve. The worker still binds loopback.
if command -v tailscale >/dev/null 2>&1; then
  TS_HOST="$(tailscale status --json 2>/dev/null | python -c '
import json,sys
try:
    name=json.load(sys.stdin).get("Self",{}).get("DNSName","").rstrip(".").lower()
    print(name)
except (OSError,ValueError,TypeError,AttributeError):
    print("")
' 2>/dev/null || true)"
  if [[ "$TS_HOST" =~ ^[a-z0-9-]+\.[a-z0-9-]+\.ts\.net$ ]]; then
    export SHORTFORGE_TAILSCALE_HOST="$TS_HOST"
  fi
fi
# Reuse unrestricted local pipeline; cloud's 2-minute test source cap does not apply.
unset SHORTFORGE_WORKER_SECRET
unset SHORTFORGE_LOCAL_CONTROLLED
echo
echo "ShortForge: CPU e RAM deste computador, sem Sandbox/Blob."
echo "API local: http://127.0.0.1:8765/api/health"
echo "Site: https://short-clips-tan.vercel.app (ou Preview desta equipe)"
if [[ -n "${SHORTFORGE_TAILSCALE_HOST:-}" ]]; then
  echo "Acesso no celular (rede privada Tailscale): https://${SHORTFORGE_TAILSCALE_HOST}"
  echo "Em outro terminal: tailscale serve 8765"
fi
echo "Mantenha este terminal aberto enquanto gera Shorts. Ctrl+C encerra."
echo
exec bash "$ROOT/iniciar.sh"

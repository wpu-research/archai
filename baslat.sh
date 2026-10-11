#!/usr/bin/env bash
# Yarın tek komut: ArchAI (yalnız 127.0.0.1) + MCP katmanı + Cloudflare hızlı tüneli.
# Çıktıda Manus'a girilecek URL ve token yazılır.
set -euo pipefail
cd "$(dirname "$0")"
LOG=./logs; mkdir -p "$LOG"
CF=${CLOUDFLARED:-$HOME/.local/bin/cloudflared}

if ! curl -s -m 2 http://127.0.0.1:8000/api/settings >/dev/null; then
  (cd ../ArchAI && nohup uv run uvicorn webapp.app:app --host 127.0.0.1 --port 8000 >"$OLDPWD/$LOG/archai.log" 2>&1 &)
  echo "ArchAI başlatılıyor…"; sleep 6
fi

fuser -k 8765/tcp 2>/dev/null || true
[ -f "$LOG/tunnel.pid" ] && kill "$(cat "$LOG/tunnel.pid")" 2>/dev/null || true
nohup "$CF" tunnel --url http://127.0.0.1:8765 >"$LOG/tunnel.log" 2>&1 &
echo $! >"$LOG/tunnel.pid"
for _ in $(seq 30); do
  URL=$(grep -ao 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG/tunnel.log" | head -1 || true)
  [ -n "$URL" ] && break; sleep 1
done
[ -n "${URL:-}" ] || { echo "tünel adresi alınamadı, $LOG/tunnel.log'a bak"; exit 1; }

ARCHAI_PUBLIC_URL="$URL" nohup uv run python server.py >"$LOG/mcp.log" 2>&1 &
sleep 4
TOKEN=$(grep '^ARCHAI_MCP_TOKEN=' .env | cut -d= -f2 | awk '{print $1}')
echo
echo "Manus → Settings → Connectors → Custom MCP → Direct configuration"
echo "  Transport : HTTP"
echo "  URL       : $URL/mcp"
echo "  Header    : Authorization = Bearer $TOKEN"
echo
echo "Test: uv run python scripts/test_client.py $URL"

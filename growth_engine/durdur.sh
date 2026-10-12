#!/usr/bin/env bash
# Tüneli ve MCP katmanını kapatır (ArchAI lokalde açık kalır).
cd "$(dirname "$0")"
[ -f logs/tunnel.pid ] && kill "$(cat logs/tunnel.pid)" 2>/dev/null && rm -f logs/tunnel.pid
fuser -k 8765/tcp 2>/dev/null
echo "tünel ve MCP kapatıldı"

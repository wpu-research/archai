"""Core API ARCHAI_TOKEN ile korunur: Growth Engine'in core'a giden HER isteği anahtar taşımalı."""
import asyncio

from growth_engine import server


class _Resp:
    status_code = 200
    content = b"ok"
    text = "<html><head></head><body></body></html>"
    headers = {"content-type": "text/plain"}


class _Client:
    seen = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def _rec(self, url, **kw):
        _Client.seen.append((url, kw.get("headers") or {}))
        return _Resp()

    get = put = post = _rec


def test_proxy_sends_core_token(monkeypatch):
    _Client.seen = []
    monkeypatch.setattr(server.httpx, "AsyncClient", _Client)
    resp = asyncio.run(server._proxy("api/projects/x"))
    assert resp.status_code == 200
    assert _Client.seen and all(h.get("Authorization") == "Bearer test-core-api-token" for _, h in _Client.seen)


def test_every_core_call_in_source_is_authenticated():
    """Bekçi: kaynakta core adresine giden her httpx çağrısı _core_auth() (ya da ondan türeyen headers) taşır."""
    import re
    from pathlib import Path
    src = Path(server.__file__).read_text()
    calls = re.findall(r"cl\.(?:get|put|post)\(\s*f\"\{ARCHAI\}.*?\)\n", src, re.S)
    assert len(calls) >= 8
    assert all("_core_auth()" in c or "headers=headers" in c for c in calls), [c for c in calls if "_core_auth()" not in c]

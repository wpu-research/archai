"""Uçtan uca test: MCP'ye token'la bağlan, araçları listele, hızlı fizibilite çağır, imzalı linki indir."""
import asyncio, json, os, sys
from pathlib import Path
import httpx, httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

for line in Path(__file__).parent.parent.joinpath(".env").read_text().splitlines():
    line = line.split("#", 1)[0].strip()
    if "=" in line:
        k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())
URL = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765") + "/mcp"

async def main():
    hdr = {"Authorization": f"Bearer {os.environ['ARCHAI_MCP_TOKEN']}"}
    async with httpx2.AsyncClient(headers=hdr, timeout=300) as hc, streamable_http_client(URL, http_client=hc) as streams:
        r, w = streams[0], streams[1]
        async with ClientSession(r, w) as s:
            await s.initialize()
            print("araçlar:", [t.name for t in (await s.list_tools()).tools])
            res = await s.call_tool("arsa_fizibilite", {"ad": "Test Arsa Kartal", "cephe_m": 25, "derinlik_m": 30,
                                                        "taks": 0.4, "kaks": 2.0, "maks_kat": 5})
            d = res.structured_content or json.loads(res.content[0].text)
            print(json.dumps({k: v for k, v in d.items() if k != "pafta_png"}, ensure_ascii=False, indent=1))
            g = httpx.get(d["gorunus_png"]); print("görünüş png:", g.status_code, g.headers.get("content-type"), len(g.content))
            pid = d["proje_id"]
            m2r = (await s.call_tool("bolge_m2_fiyati", {"ilanlar": [{"fiyat_tl": f, "m2": 100} for f in
                  (6_500_000, 7_200_000, 7_800_000, 8_100_000, 9_000_000, 25_000_000)]}))
            print(m2r.is_error if hasattr(m2r,"is_error") else "", m2r.content[0].text[:300]); m2 = m2r.structured_content or json.loads(m2r.content[0].text)
            print("bölge m²:", m2)
            for t, a in (("karlilik", {"arsa_fiyati_tl": 30_000_000}), ("kat_karsiligi", {})):
                r = await s.call_tool(t, {"proje_id": pid, "satis_m2_fiyati_tl": m2["satis_m2_fiyati_tl"], **a})
                print(t, json.dumps(r.structured_content or r.content[0].text, ensure_ascii=False))
            bad = httpx.get(d["gorunus_png"].replace("s=", "s=x")); print("bozuk imza:", bad.status_code)

asyncio.run(main())

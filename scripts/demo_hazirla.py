"""Sunum demosu için 3 projenin tüm verisini ve dosyalarını yerele toplar → demo/demo.json + demo/assets/.

Demo internetsiz çalışır: render/film/pafta/teklif yerelden, 3D görüntüleyici 127.0.0.1:8765 üzerinden.
Kullanım: uv run python scripts/demo_hazirla.py
"""
import asyncio
import json
import re
import shutil
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server as S  # noqa: E402

KOK = Path(__file__).resolve().parent.parent
OUT = KOK / "demo"
AS = OUT / "assets"
YEREL = "http://127.0.0.1:8765"
SATIS_M2 = 93651  # Manus raporu: Kartal sıfır daire bolge_m2_fiyati (20 ilan)

PROJELER = [
    {"pid": "20261012-110110-villa-cekmekoy-ornek-proje-6187", "tur": "villa", "baslik": "Villa Çekmeköy — Örnek Proje",
     "ilan": None},
    {"pid": "20261012-102742-kartal-ada-12412-parsel-28-312-d725", "tur": "arsa",
     "baslik": "Kartal — Ada 12412 / Parsel 28 (312 m²)", "arsa_tl": 23_500_000},
    {"pid": "20261012-102738-kartal-ada-10891-parsel-10-224-92e6", "tur": "arsa",
     "baslik": "Kartal — Ada 10891 / Parsel 10 (224 m²)", "arsa_tl": 15_000_000},
]


def kareler(pid: str) -> dict:
    """film.py günlüğündeki fotogerçekçi kareler (cephe, salon, yatak, kuş)."""
    for log in KOK.glob("logs/film*.log"):
        t = log.read_text()
        if pid in t or (pid.endswith("6187") and "villa" in log.name) or (pid.endswith("92e6") and log.name == "film_b.log") \
                or (pid.endswith("d725") and log.name == "film.log"):
            m = re.search(r"kareler: (\{.*\})", t)
            if m:
                return json.loads(m.group(1))
    return {}


async def indir(cl: httpx.AsyncClient, url: str, hedef: Path) -> str:
    if not hedef.exists():
        r = await cl.get(url)
        r.raise_for_status()
        hedef.write_bytes(r.content)
    return f"/demo/assets/{hedef.name}"


async def main():
    AS.mkdir(parents=True, exist_ok=True)
    kartlar = []
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as cl:
        for i, pr in enumerate(PROJELER):
            pid = pr["pid"]
            p = await S._get(pid)
            o = S._summary(p)
            k = kareler(pid)
            kisa = f"p{i}"
            gorseller = {}
            for ad in ("cephe", "salon", "yatak", "kus"):
                if k.get(ad):
                    gorseller[ad] = await indir(cl, k[ad], AS / f"{kisa}_{ad}.jpg")
            film = KOK / "logs" / f"film_{pid}.mp4"
            if film.exists():
                shutil.copy(film, AS / f"{kisa}_film.mp4")
            dosyalar = {}
            for ad, url in o["dosyalar"].items():  # imzalı linki yerel sunucuya çevir
                dosyalar[ad] = url.replace(S.PUBLIC, YEREL)
            kart = {"proje_id": pid, "tur": pr["tur"], "baslik": pr["baslik"],
                    "kat": o["kat_sayisi"], "daire": o["daire_sayisi"], "daire_tipi": o["daire_tipi"],
                    "brut_m2": o["brut_insaat_m2"], "maliyet": o["maliyet_kdv_dahil_tl"],
                    "m2_maliyet": o["maliyet_m2_kdv_dahil_tl"], "cekme": o.get("cekme_varsayimi"),
                    "gorseller": gorseller, "film": f"/demo/assets/{kisa}_film.mp4" if film.exists() else None,
                    "model_3d": S._view_link(pid).replace(S.PUBLIC, YEREL),
                    "gezinti_3d": S._view_link(pid).replace(S.PUBLIC, YEREL) +
                    ("&walk=Salon&tour=1" if pr["tur"] == "villa" else "&furnish=1&walk=salon&tour=1"),
                    "dosyalar": dosyalar}
            if pr["tur"] == "arsa":
                kr = await S.karlilik(pid, pr["arsa_tl"], SATIS_M2)
                kk = await S.kat_karsiligi(pid, SATIS_M2, 25, 15)
                kart["satin_alma"] = {"arsa_tl": kr["arsa_tl"], "getiri_pct": kr["getiri_pct"], "kar_tl": kr["kar_tl"]}
                ip = kk["istenen_pay"]
                kart["kat_karsiligi"] = {"sahip": ip["arsa_sahibi_daire"], "muteahhit": ip["muteahhit_daire"],
                                         "marj_pct": ip["muteahhit_marj_pct"], "kar_tl": ip["muteahhit_kar_tl"]}
            kartlar.append(kart)
            print(kisa, pr["baslik"], "görsel:", list(gorseller), "film:", bool(kart["film"]))
    (OUT / "demo.json").write_text(json.dumps({"satis_m2": SATIS_M2, "kartlar": kartlar}, ensure_ascii=False, indent=1))
    print("yazıldı:", OUT / "demo.json")


if __name__ == "__main__":
    asyncio.run(main())

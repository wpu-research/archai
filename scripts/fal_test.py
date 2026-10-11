"""fal.ai testi: ArchAI cephe çizgisi → fotogerçekçi cephe. Kullanım: uv run python scripts/fal_test.py <gorunus_png_url>

Görsel URL'si fal'ın erişebileceği bir adres olmalı (baslat.sh ile açılan tünel linki).
"""
import os, sys, time
from pathlib import Path
import httpx

for line in Path(__file__).parent.parent.joinpath(".env").read_text().splitlines():
    line = line.split("#", 1)[0].strip()
    if "=" in line:
        k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())
KEY, MODEL = os.environ.get("FAL_KEY"), os.environ.get("FAL_IMAGE_MODEL") or "fal-ai/flux-pro/kontext"
if not KEY:
    sys.exit(".env içinde FAL_KEY yok")
PROMPT = ("Turn this architectural elevation line drawing into a photorealistic photo of the same modern "
          "residential apartment building in Istanbul. Keep the exact window layout, floor count and proportions. "
          "Light warm plaster facade, anthracite window frames, small balconies, street level with sidewalk and trees, "
          "late afternoon sun, eye-level architectural photography, no text, no dimension lines.")

h = {"Authorization": f"Key {KEY}"}
job = httpx.post(f"https://queue.fal.run/{MODEL}", headers=h, timeout=60,
                 json={"prompt": PROMPT, "image_url": sys.argv[1]}).raise_for_status().json()
print("kuyrukta:", job.get("request_id"))
while (st := httpx.get(job["status_url"], headers=h, timeout=30).json())["status"] != "COMPLETED":
    print(st["status"]); time.sleep(3)
res = httpx.get(job["response_url"], headers=h, timeout=60).json()
url = (res.get("images") or [{}])[0].get("url")
print("sonuç:", url or res)
if url:
    out = Path(__file__).parent.parent / "logs" / "fal_cephe.jpg"
    out.write_bytes(httpx.get(url, timeout=60).content); print("kaydedildi:", out)

"""ArchAI tanıtım filmi (~38 sn): dış cephe → salon → yatak odası → kuşbakışı.

Kullanım: uv run python scripts/film.py <proje_id> <dis.png> <salon.png>
Kareler ArchAI 3D görüntüleyicisinden (cinema=1) alınır; fal kontext fotogerçekçi yapar, Kling 10 sn'lik
sahneler üretir, ffmpeg geçişlerle birleştirir. Çıktı: logs/film_<proje_id>.mp4
"""
import asyncio
import base64
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server as S  # noqa: E402  (.env, fal yardımcıları)

KOK = Path(__file__).resolve().parent.parent
VIDEO = "fal-ai/kling-video/v2.1/standard/image-to-video"
STIL = ("Warm light-beige plaster facade, anthracite window frames, small balconies, Istanbul residential street. "
        "Photorealistic architectural photography, natural light, no text, no people.")


def data_uri(p: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


async def foto(src: str, prompt: str) -> str:
    r = await S._fal(S.FAL_IMAGE, {"prompt": prompt, "image_url": src}, 150)
    return r["images"][0]["url"]


async def klip(img: str, prompt: str, ad: str, out: Path) -> Path:
    r = await S._fal(VIDEO, {"prompt": prompt, "image_url": img, "duration": "10"}, 600)
    import httpx
    async with httpx.AsyncClient(timeout=120) as cl:
        (out / f"{ad}.mp4").write_bytes((await cl.get(r["video"]["url"])).content)
    print("klip hazır:", ad, flush=True)
    return out / f"{ad}.mp4"


async def main(pid: str, dis: Path, salon: Path):
    out = KOK / "logs" / f"film_{pid}"
    out.mkdir(parents=True, exist_ok=True)
    kayit = json.loads(S.KAYIT.read_text()).get(pid, {}) if S.KAYIT.exists() else {}
    cephe = kayit.get("render_url") or (await S.render_cephe(pid))["render_url"]

    salon_f, yatak_f, kus_f = await asyncio.gather(
        foto(data_uri(salon), "Turn this empty 3D room into a photorealistic, fully furnished modern living room with an "
             "open kitchen: sofa, rug, coffee table, plants, warm wood floor, kitchen counter on the side. Keep the window "
             "position and room proportions. Bright natural daylight, interior design photography, no text."),
        foto(data_uri(salon), "Turn this empty 3D room into a photorealistic, cozy furnished modern bedroom: double bed with "
             "linen bedding, nightstands, soft lamp, wardrobe, warm wood floor. Keep the window position and room "
             "proportions. Soft morning light, interior design photography, no text."),
        foto(data_uri(dis), "Turn this 3D massing model into a photorealistic aerial photo of the same 4-storey apartment "
             "building in an Istanbul neighbourhood, keep the shape, floor count and window layout. " + STIL),
    )
    print("kareler:", json.dumps({"cephe": cephe, "salon": salon_f, "yatak": yatak_f, "kus": kus_f}), flush=True)

    klipler = await asyncio.gather(
        klip(cephe, "Slow cinematic dolly-in from the street towards the building's entrance door, gentle parallax, "
             "trees moving in the breeze, warm late-afternoon light.", "1_cephe", out),
        klip(salon_f, "Smooth slow walkthrough camera moving into the living room and panning towards the window, "
             "realistic interior, sunlight through the window.", "2_salon", out),
        klip(yatak_f, "Slow gentle camera pan across the bedroom towards the bed, soft light, calm atmosphere.",
             "3_yatak", out),
        klip(kus_f, "Slow cinematic drone orbit around the building, revealing the neighbourhood, golden hour.",
             "4_kus", out),
    )

    # 4 × 10 sn, 0,8 sn geçişlerle ≈ 37,6 sn
    girdi = sum([["-i", str(k)] for k in klipler], [])
    f = ("[v0][v1]xfade=transition=fade:duration=0.8:offset=9.2[a];"
         "[a][v2]xfade=transition=fade:duration=0.8:offset=18.4[b];"
         "[b][v3]xfade=transition=fade:duration=0.8:offset=27.6,format=yuv420p[v]")
    norm = ";".join(f"[{i}:v]scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,"
                    f"fps=24,settb=AVTB,setpts=PTS-STARTPTS[v{i}]" for i in range(4))
    hedef = KOK / "logs" / f"film_{pid}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *girdi, "-filter_complex", norm + ";" + f, "-map", "[v]",
                    "-c:v", "libx264", "-crf", "20", "-movflags", "+faststart", str(hedef)], check=True)
    S._kaydet(pid, "film_yerel", str(hedef))
    print("FİLM:", hedef, flush=True)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])))

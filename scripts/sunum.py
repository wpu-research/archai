"""Sunum videosu: [açılış kartı] + ArchAI tanıtımı + [geçiş kartı] + bugünkü demo; TR seslendirme + TR/EN altyazı + müzik.

Kullanım: uv run python scripts/sunum.py <archai_video.mp4>     Çıktı: teslim/archai_sunum_1080p.mp4
"""
import asyncio
import json
import subprocess
import sys
from pathlib import Path

import httpx

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
import server as S  # noqa: E402

T = KOK / "teslim"
SES = T / "ses"
TTS = "fal-ai/elevenlabs/tts/multilingual-v2"
SESCI = "George"
KART1, KART2 = 4.0, 5.0  # açılış ve geçiş kartı süreleri

# (bölüm, başlangıç sn [bölüm içinde], azami süre, TR, EN)
ANLATIM = [
    ("k1", .4, 3.4, "ArchAI ve Manus: markanı on kat büyüt.", "ArchAI × Manus: 10× your brand."),
    ("p1", .3, 4.0, "ArchAI. Arsadan teklife, dakikalar içinde.", "ArchAI. From land to quote, in minutes."),
    ("p1", 4.5, 9.0, "Sıfırdan başlıyoruz: parsel, imar durumu ve daire programı. ArchAI binayı kendisi kuruyor.",
     "Start from scratch: plot, zoning and unit mix. ArchAI designs the building itself."),
    ("p1", 13.8, 4.5, "Paftalar otomatik: plan, kesit, görünüş.", "Drawings are automatic: plans, sections, elevations."),
    ("p1", 18.5, 9.0, "Metraj ve maliyet kalem kalem hesaplanıyor, her değişiklikte anında güncelleniyor.",
     "Quantities and costs are computed item by item and update instantly."),
    ("p1", 27.7, 9.0, "Teklif mektubu, teknik şartname ve formüllü metraj tablosu, firma bilgisiyle hazır.",
     "Quote letter, specifications and a formula-driven bill of quantities — branded and ready."),
    ("p1", 37.0, 9.0, "Binayı her açıdan inceleyin: tel kafes, X-ray, katı ya da gerçekçi görünüm.",
     "Inspect the building from every angle: wireframe, X-ray, solid or realistic."),
    ("p1", 46.2, 9.0, "İç mekân düzenleyiciyle tek tıkla döşeyin, dekor ekleyin.",
     "Furnish and decorate with one click in the interior editor."),
    ("p1", 55.4, 9.0, "Zemin ve boya değişince metraj anında güncelleniyor. Bölme duvar yıkılır, taşıyıcı duvar korunur.",
     "Change floors and paint, quantities follow. Remove partitions — load-bearing walls stay."),
    ("p1", 64.6, 17.0, "Binanın içinde gezin: kapıları açın, odaları dolaşın. Süpürgelik, kapı kanatları, pencereler; hepsi modelde.",
     "Walk inside: open doors, tour the rooms. Skirting, door leaves, windows — all in the model."),
    ("p1", 83.0, 4.5, "Gün ışığı ve gece aydınlatması.", "Daylight and night lighting."),
    ("p1", 87.7, 13.0, "Ve tek tuşla gerçek render: Blender Cycles ile dış cephe, salon ve yatak odası.",
     "And one-click photoreal renders with Blender Cycles: facade, living room, bedroom."),
    ("p1", 101.5, 4.6, "Elinizde sadece plan resmi mi var? ArchAI onu da tanıyor.",
     "Only have a floor-plan image? ArchAI reads it too."),
    ("p1", 106.3, 4.2, "Arsadan gerçek render'a, tek akışta.", "From land to photoreal render, in one flow."),
    ("k2", .4, 4.4, "Bugün ArchAI'yi, kendi kendini pazarlayan bir satış motoruna çevirdik.",
     "Today we turned ArchAI into a self-marketing sales engine."),
    ("p2", .3, 3.9, "ArchAI Growth Console.", "ArchAI Growth Console."),
    ("p2", 4.4, 9.6, "Semti seçiyoruz. Manus, Apify ile sahibinden'den kırk arsa ve yirmi sıfır daire ilanı topluyor.",
     "Pick a district. Manus uses Apify to collect 40 plots and 20 new apartments from sahibinden."),
    ("p2", 14.2, 10.3, "Otuz bir ilan imar ve tapu kurallarıyla eleniyor. ArchAI kalan arsalar için proje, metraj, maliyet ve teklif üretiyor.",
     "31 listings are filtered out. ArchAI designs, quantifies, costs and quotes the rest."),
    ("p2", 24.7, 3.7, "Satın alırsan zarar, kat karşılığıyla kâr.", "Buying loses money; land-for-flats profits."),
    ("p2", 28.6, 13.5, "Bu bina bu sabah yoktu. Kaynak gerçek bir sahibinden ilanı. fal, ArchAI projesinden fotogerçekçi bir tanıtım filmi üretti.",
     "This building didn't exist this morning. Source: a real listing. fal turned the project into a photoreal film."),
    ("p2", 42.4, 7.4, "Manus müteahhide ve arsa sahibine teklif, sosyal medyaya gönderi hazırlıyor. Onaysız yayın yok.",
     "Manus drafts offers and social posts. Nothing goes out without approval."),
    ("p2", 50.0, 3.0, "Günler yerine dakikalar.", "Minutes instead of days."),
    ("p2", 53.1, 4.3, "Ve projenin 3D modeli.", "And the project's 3D model."),
    ("p2", 57.6, 9.2, "Müteahhit binanın içinde yürüyor, eşya ekliyor. ArchAI; Manus, Apify ve fal ile.",
     "Walk the building, add furniture. ArchAI with Manus, Apify and fal."),
]


OKUNUS = {"ArchAI": "Ark Ey Ay", "Apify": "Epifay", "Blender Cycles": "Blender Sayklıs", "X-ray": "Eks rey",
          "Growth Console": "Grouth Konsol", "fal,": "Fal,", "fal ": "Fal "}


def okunus(t: str) -> str:
    """Seslendirme için marka adlarını Türkçe okunuşla yaz (altyazı değişmez)."""
    for a, b in OKUNUS.items():
        t = t.replace(a, b)
    return t


def sure(p: Path) -> float:
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)]))


async def seslendir(i: int, tr: str, azami: float, cl: httpx.AsyncClient) -> Path:
    out = SES / f"{i:02d}.mp3"
    if out.exists() and sure(out) <= azami:  # önceki çalıştırmadan hazır
        return out
    for hiz in (1.0, 1.1, 1.2):
        r = await S._fal(TTS, {"text": okunus(tr), "voice": SESCI, "language_code": "tr", "speed": hiz, "stability": .55,
                               "similarity_boost": .8}, 180)
        out.write_bytes((await cl.get(r["audio"]["url"])).content)
        if sure(out) <= azami:
            break
    print(f"{i:02d} {sure(out):.1f}/{azami} sn hız {hiz}", flush=True)
    return out


def ts(x):
    return f"{int(x // 3600)}:{int(x % 3600 // 60):02d}:{x % 60:05.2f}"


async def main(archai: Path):
    SES.mkdir(parents=True, exist_ok=True)
    p1 = sure(archai)
    p2v = T / "_p2_temiz.mp4"
    if not p2v.exists():  # bugünkü demo, altyazısız 1080p
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(T / "kareler.txt"),
                        "-vf", "fps=30,scale=1920:1080:flags=lanczos,format=yuv420p", "-c:v", "libx264", "-crf", "18",
                        str(p2v)], check=True, cwd=T)
    p2 = sure(p2v)
    bas = {"k1": 0.0, "p1": KART1, "k2": KART1 + p1, "p2": KART1 + p1 + KART2}
    toplam = bas["p2"] + p2

    async with httpx.AsyncClient(timeout=120) as cl:
        sesler = await asyncio.gather(*[seslendir(i, a[3], a[2], cl) for i, a in enumerate(ANLATIM)])

    # altyazı (anlatım süresi boyunca)
    ust = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Alt,DejaVu Sans,38,&H00FFFFFF,&H00FFFFFF,&H00000000,&H9E0B1624,1,0,0,0,100,100,0,0,3,13,0,2,140,140,70,1
Style: Ust,DejaVu Sans,38,&H00FFFFFF,&H00FFFFFF,&H00000000,&H9E0B1624,1,0,0,0,100,100,0,0,3,13,0,2,140,140,255,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    olay, giris = [], []
    for (bol, of, azami, tr, en), ses in zip(ANLATIM, sesler):
        t = bas[bol] + of
        d = sure(ses)
        giris.append((ses, t))
        if bol.startswith("k"):
            continue  # kartlarda yazı zaten ekranda
        stil = "Ust" if bol == "p1" else "Alt"  # ArchAI videosunun kendi etiketleri sol altta
        olay.append(f"Dialogue: 0,{ts(t)},{ts(t + max(d, 1.5) + .3)},{stil},,0,0,0,,{{\\fad(150,200)}}{tr}"
                    f"\\N{{\\fs26\\b0\\c&HD8E9F3&}}{en}")
    (T / "sunum.ass").write_text(ust + "\n".join(olay) + "\n")

    # kartlar
    kartlar = []
    for ad, sn, ust_y, alt_y in (("k1", KART1, "ArchAI × Manus", "10× Your Brand · Slush'D Istanbul 2026"),
                                 ("k2", KART2, "Bugün yaptığımız", "ArchAI Growth Engine · Manus × Apify × fal")):
        png = T / f"_{ad}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x050b14:s=1920x1080:d=1", "-vf",
                        f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='{ust_y}':fontsize=110:"
                        f"fontcolor=0x3ee8ff:x=(w-tw)/2:y=(h/2)-120,"
                        f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:text='{alt_y}':fontsize=44:"
                        f"fontcolor=0xd9ecf7:x=(w-tw)/2:y=(h/2)+40", "-frames:v", "1", str(png)], check=True)
        kartlar.append((png, sn))

    # video: kart1 + p1 + kart2 + p2 → altyazı
    v_in = ["-loop", "1", "-t", str(KART1), "-i", str(kartlar[0][0]), "-i", str(archai),
            "-loop", "1", "-t", str(KART2), "-i", str(kartlar[1][0]), "-i", str(p2v)]
    norm = lambda i: f"[{i}:v]scale=1920:1080,fps=30,format=yuv420p,setsar=1[v{i}]"
    vf = ";".join(norm(i) for i in range(4)) + ";[v0][v1][v2][v3]concat=n=4:v=1:a=0[vc];[vc]ass=sunum.ass[v]"

    # ses: p1 kendi müziği (kart1+p1), fal müziği (kart2+p2) kısık; üstüne anlatım
    a_in = ["-i", str(archai), "-i", str(T / "muzik.mp3")] + sum([["-i", str(s)] for s, _ in giris], [])
    n0 = 4
    af = [f"[{n0}:a]adelay={int(KART1 * 1000)}|{int(KART1 * 1000)},volume=0.22,afade=t=out:st={KART1 + p1 - 2}:d=2[b1]",
          f"[{n0 + 1}:a]atrim=0:{KART2 + p2},afade=t=in:d=1,afade=t=out:st={KART2 + p2 - 3}:d=3,volume=0.2,"
          f"adelay={int(bas['k2'] * 1000)}|{int(bas['k2'] * 1000)}[b2]"]
    for j, (_, t) in enumerate(giris):
        af.append(f"[{n0 + 2 + j}:a]adelay={int(t * 1000)}|{int(t * 1000)},volume=1.35[n{j}]")
    af.append("".join(f"[n{j}]" for j in range(len(giris))) + f"[b1][b2]amix=inputs={len(giris) + 2}:normalize=0,"
              f"atrim=0:{toplam},alimiter=limit=0.89[a]")
    hedef = T / "archai_sunum_1080p.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *v_in, *a_in, "-filter_complex", vf + ";" + ";".join(af),
                    "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "slow", "-crf", "19", "-c:a", "aac",
                    "-b:a", "192k", "-movflags", "+faststart", "-t", str(toplam), str(hedef)], check=True, cwd=T)
    print("SUNUM:", hedef, round(toplam, 1), "sn")


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]).resolve()))

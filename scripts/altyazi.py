"""teslim/sahneler.json → teslim/altyazi.ass (4K, TR + küçük EN satırı)."""
import json
from pathlib import Path

T = Path(__file__).resolve().parent.parent / "teslim"
S = {s["ad"]: s["t"] for s in json.loads((T / "sahneler.json").read_text())}

# (başlangıç sahnesi, ofset sn, süre sn, TR, EN)
SATIR = [
    ("acilis", .3, 4.2, "ArchAI — arsa ilanından satışa hazır fizibilite paketine, dakikalar içinde",
     "From a land listing to a sales-ready feasibility package — in minutes"),
    ("arama", .2, 5.5, "Semt seçiliyor · Manus, Apify ile sahibinden.com'dan 40 arsa + 20 daire ilanı topluyor",
     "Manus collects 40 land + 20 apartment listings from sahibinden.com via Apify"),
    ("arama", 6.0, 5.5, "31 ilan imar ve tapu kurallarıyla elendi · bölge fiyatı 93.651 TL/m²",
     "31 listings filtered out by zoning and title rules · local price 93,651 TL/m²"),
    ("arama", 11.8, 6.0, "ArchAI her arsa için avan proje, 94 kalem metraj, maliyet ve teklif üretiyor",
     "ArchAI generates concept design, 94-item bill of quantities, cost and quote per plot"),
    ("sonuc", -3.5, 6.0, "Satın alırsan zarar, kat karşılığıyla kâr — ArchAI doğru modeli ve paylaşımı hesaplıyor",
     "Buying loses money; land-for-flats is profitable — ArchAI finds the right model and split"),
    ("film", .4, 6.0, "Bu bina bu sabah yoktu · kaynak: gerçek bir sahibinden ilanı",
     "This building didn't exist this morning · source: a real sahibinden listing"),
    ("film", 6.6, 6.2, "fal, ArchAI projesinden fotogerçekçi tanıtım filmi üretti",
     "fal turned the ArchAI project into a photorealistic promo film"),
    ("kampanya", .3, 6.5, "Manus müteahhide ve arsa sahibine teklif, Instagram · LinkedIn · TikTok gönderisi hazırlıyor",
     "Manus drafts offers for developer and landowner, plus Instagram · LinkedIn · TikTok posts"),
    ("kampanya", 6.9, 2.6, "Onay olmadan hiçbir şey yayınlanmaz", "Nothing is published without approval"),
    ("rapor", .3, 8.5, "İşlem raporu · 40 ilan → 8 fizibilite → kampanya · öncesi 3–5 gün, sonrası dakikalar",
     "Process report · 40 listings → 8 feasibilities → campaign · 3–5 days → minutes"),
    ("model", .2, 4.2, "Projenin 3D modeli", "The project's 3D model"),
    ("yuru", .2, 9.0, "Müteahhit binanın içinde yürüyor, eşya ekleyebiliyor · ArchAI × Manus × Apify × fal",
     "Walk through the building, add furniture · ArchAI × Manus × Apify × fal"),
]


def ts(x):
    x = max(0, x)
    return f"{int(x // 3600)}:{int(x % 3600 // 60):02d}:{x % 60:05.2f}"


ust = """[Script Info]
ScriptType: v4.00+
PlayResX: 3840
PlayResY: 2160
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: TR,DejaVu Sans,76,&H00FFFFFF,&H00FFFFFF,&H00000000,&H9E0B1624,1,0,0,0,100,100,0,0,3,26,0,2,200,200,150,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
olay = []
toplam = S["toplam"]
for sahne, of, sure, tr, en in SATIR:
    bas = S[sahne] + of
    son = min(bas + sure, toplam - .1)
    olay.append(f"Dialogue: 0,{ts(bas)},{ts(son)},TR,,0,0,0,,{{\\fad(250,250)}}{tr}\\N{{\\fs50\\b0\\c&HD8E9F3&}}{en}")
(T / "altyazi.ass").write_text(ust + "\n".join(olay) + "\n")
print(len(olay), "satır, toplam", toplam, "sn")

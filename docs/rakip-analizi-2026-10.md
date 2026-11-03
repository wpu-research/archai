# ArchAI — Rakip Haritası (2026-10-12)

4 paralel web taraması (kütle/plan · çizim/metraj/maliyet · render/iç mekân/video · uçtan uca/ilan/Türkiye).
Fiyat ve fon rakamlarının çoğu üçüncü taraf kaynaklı ve çelişkili — pitch'te kullanmadan önce resmi sayfadan teyit et.

Pipeline kısaltmaları: **İ** ilan/parsel girişi · **K** imar/kütle/fizibilite · **P** kat planı · **Ç** çizim (DXF/PDF/BIM) ·
**R** plan tanıma (DXF/raster) · **M** metraj · **$** maliyet · **Ş** şartname · **T** teklif · **3D** gezinti/render/iç mekân · **V** video

## 1. Kim neyi kapsıyor

| Ürün | Bölge | İ | K | P | Ç | R | M | $ | Ş | T | 3D | V | Not |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **ArchAI** | TR | ◐ (Growth Engine) | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | Tek uçtan uca zincir |
| Higharc | ABD | | | ● | ● | ◐ | ● | ● | | ◐ | ● | | Müstakil konut müteahhidi; $95M Seri C (06/2026) |
| Autodesk Forma | Global | | ● | ◐ | ◐ | | | | | ◐ (Bid beta) | | | Revit/AEC Collection'a dahil; AU2026'da ajan |
| TestFit | ABD | | ● | ◐ | | | ◐ | ● | | | ◐ | | $8–20k/yıl |
| ARCHITEChTURES | ES (**TL fiyat!**) | | ● | ● | ◐ (IFC/DXF) | | | ● | | | ● | | Pro ₺1.426/ay — TR'ye yerelleşiyor olabilir |
| ArkDesign.ai | ABD | | ● | ● | | | | ◐ | | | | | Çok katlı konut, unit mix; $199/ay+ |
| Spacio / Finch / Snaptrude | NO / SE / IN-US | | ● | ● | ● | | | | | | ◐ | | Yönetmelik + BIM |
| Maket / Drafted | CA / ABD | | | ● | ◐ | | | | | | ● | | Drafted $16M seed (05/2026), tek kat |
| Blueprints AI | ABD | | | ◐ | ● | ● | | | | | | | Fotoğraf/PDF → ruhsata hazır set; $3.2–8.5k/ay; TC Disrupt bugün |
| Swapp / Glyph | IL / ABD | | | | ● | | | | | | | | BIM modeli şart |
| Togal / Beam / Kreo / STACK | ABD / UK | | | | | ● | ● | ◐ | | | | | PDF → metraj (ABD/UK pozları) |
| Buildxact / Handoff | AU / ABD | | | | | ◐ | ● | ● | | ● | | | Tadilat/konut yüklenicisi teklifi |
| Deltek Specpoint | ABD | | | | | | | | ● | | | | MasterSpec formatı |
| Chaos Veras/Enscape, D5 | Global | | | | | | | | | | ● | ● | Render + image-to-video, ajan |
| Coohom / Homestyler | CN | | | | | ◐ | ◐ | ● | | ◐ | ● | | İç mekân + kural tabanlı teklif; Manycore HKEX IPO (04/2026) |
| Algoma / TheHandover.ai / Acres | ABD | ◐ | ● | | ◐ | | | ● | | | | | Adres → 60 sn fizibilite; Claude tabanlı ajan hattı |
| **Kolayimar** | TR | ◐ | ● | | | | | ◐ | | | ◐ | ● (drone) | 81 il TKGM, kat karşılığı, ücretsiz |
| **İmarX** | TR | | ● | | ◐ | ● | | ● | ● | | ● | | En benzer TR ürünü; plan üretimi yok |
| **yapıyo.tr / ArsaBil / Evveko** | TR | | ● | | | | | ◐ | | ◐ (pazaryeri) | | | Kentsel dönüşüm, kat karşılığı |
| **Emlak360.pro** | TR | ● (XML) | ◐ | | | | | ◐ | | | ◐ (staging) | ● | Growth Engine'e en yakın |
| **Oska / AMP Hakediş** | TR | | | | | | ◐ (elle) | ● | ◐ | ◐ | | | Poz/hakediş altyapısı, AI yok |
| Emlakjet + Endeksa (iLab) | TR | ● | ◐ (değerleme) | | | | | | | | | | 02/2026 birleşti — ortak ya da tehdit |

● tam · ◐ kısmen · boş = yok

## 2. Ana sonuçlar

1. **Uçtan uca zinciri kuran kimse yok — ne global ne Türkiye'de.** Pazar dilimlere bölünmüş (kütle · plan · CD seti · metraj · maliyet · şartname · render). En yakın bütünleşik örnek Higharc, o da ABD müstakil konutla sınırlı.
2. **Türk imar mevzuatı (TAKS/KAKS, çekme, Planlı Alanlar İmar Yönetmeliği, emsal harici) için otomatik kat planı üreten ticari ürün yok.** Yerel kural seti hendektir — DBF Japonya'da, ArkDesign NYC'de, Spacio Norveç'te aynı stratejiyle yaşıyor.
3. **Türk ürünlerinin hiçbirinde plan üretimi ve otomatik metraj yok.** Kolayimar/yapıyo/ArsaBil imar + kat karşılığı, İmarX DXF + maliyet + şartname, Oska/AMP poz + hakediş yapıyor.
4. **İlan URL'sinden başlayan rakip yok.** Herkes adres/parsel bekliyor → Growth Engine'in "sahibinden ilanı → fizibilite → teklif → kampanya" zinciri boş alan.
5. **Tek başına farklılaştırmayan şeyler:** plan tanıma (Kreo, Planner 5D API, Trimble satıyor), AI render (Veras/D5/LookX ucuz), "AI ajan" (D5, Forma, Homestyler ekledi). Fark: bunların **poz bazlı metraja, TL maliyete ve imzalanabilir teklife** bağlanması.
6. **Tasarım↔maliyet bağı nadir:** yalnız Coohom, Higharc, IKEA Kreativ. Görsel AI araçlarının hiçbirinde metraj yok.

## 3. Tehditler

| Tehdit | Ufuk | Neden |
|---|---|---|
| **Kolayimar** | Kısa | 81 il veri + kat karşılığı + 3D video ücretsiz; plan + maliyet eklerse doğrudan rakip |
| **ARCHITEChTURES** | Kısa | TL fiyatla kütle + birim + maliyet; Türk mevzuatına uyum ve Ş/T çıktılarıyla geçilmeli |
| **Emlakjet+Endeksa (iLab)** | Orta | İlan + değerleme ellerinde; Growth Engine fikrini platforma gömebilir |
| **Autodesk Forma** | Orta | Revit lisansına dahil, ajan + Bid; mimarlık ofisi segmentine bedava giriş |
| **Blueprints AI** | Uzun | Görselden ruhsata hazır set; TR'ye gelirse çizim adımında güçlü |

## 4. Açıklar ve öneriler

- **Konumlandırma:** "Türk imar mevzuatına uygun — parselden/ilandan ruhsata hazır ön projeye, metraja ve teklife, dakikalar içinde." Hedef: müteahhit/geliştirici, kat karşılığı modeli (rakiplerin hiçbiri hedeflemiyor).
- **ÇŞB birim fiyat pozlarına eşleme + Oska/AMP formatına export** → Oska/AMP rakip değil, akış sonrası entegrasyon. Oska–Nemetschek/Allplan bağı dağıtım kanalı olabilir.
- **İmar verisi parçalı** (yapıyo bile İstanbul'da 22 ilçe) → "imar durumu belgesini yükle, AI okusun" yedek yolu.
- **Yerel maliyet kataloğu** (Koçtaş/Bauhaus/bayi, Higharc–US LBM modeli) → iç mekân seçimlerini gerçek TL'ye bağla.
- **Mimar/mühendis onay akışı** — Blueprints AI dahil herkes lisanslı imza şartı koyuyor; yasal sorumluluk için gerekli.
- **Video:** gerçek 3D modelden üretildiği için geometrisi tutarlı ("halüsinasyon yok") — HeyGen/Invideo 2D fotoğraf pan/zoom'una karşı satış mesajı.
- **Ders:** Archistar (→belediye), Cove (→hizmet), Parafin (→otel), Hypar (→ofis) pivot etti, Delve kapandı. Generatif kütle tek başına satmıyor; çıktıya (teklif/ruhsat seti) bağlanmalı.

## 5. Fiyat bantları (referans)

- Fizibilite: TestFit $8–20k/yıl · ArkDesign $199/ay+ · ARCHITEChTURES ₺1.426–8.507/ay
- Plan: Maket $20–100/ay · Snaptrude $60–100/ay
- CD seti: Blueprints AI $3.2–8.5k/ay
- Metraj: Kreo ~$35/kullanıcı/ay · Ediphi ~$3.6k/yıl
- Render: $15–40/ay · iç mekân editörü $5–70/ay · staging $1–30/görsel
- TR: Kolayimar/ArsaBil/yapıyo ücretsiz hesap (beklenti çıpası "bedava")

## 6. Yatırım emsalleri (2025–26)

Higharc $95M Seri C · Manycore (Coohom) HKEX IPO · Luma $900M · Krea $47M · Motif ~$46M · Attentive/Beam $30.5M Seri B ·
Collov $23M A · xBuild $19M A · Drafted $16M seed · Qbiq $16M A · Buildcheck $12M A · Rayon €10M A · Primepoint $10M seed ·
Provision $7M seed · Quotr $4M seed · Algoma $2.3M seed · CONIX.AI $1.3M pre-seed.

## 7. Doğrulanamayanlar

Kolayimar/İmarX/Emlak360 sahip ve fiyatları · Forma'nın "Revit'e ücretsiz" iddiası ve ABD fiyatı · Togal fon/fiyatı · Kreo fiyatı ·
ARCHITEChTURES TL fiyatının bölgesel gösterim mi bilinçli hamle mi olduğu · Arkio/Prescient/Delve güncel durumu ·
Hypar/PlanFinder/Laiout/Qbiq/Rayon/Spacio/Giraffe/DBF fiyatları · Exayard, Plainly, Kaizen/Archie, Cosmo, Mega Metraj, Gülhan, Hakedişçi (aramada çıkmadı).

## Seçili kaynaklar

- Higharc Seri C — siliconangle.com/2026/07/01/homebuilding-ai-startup-higharc-bags-90m-series-c-funding/
- Blueprints AI — techcrunch.com/2026/10/12/this-ai-startup-says-it-can-generate-permit-ready-blueprints-in-minutes/
- Forma AU2026 — architosh.com/2026/09/au2026-autodesk-expands-forma-and-leverages-ai/
- Forma Building Design — blogs.autodesk.com/forma (07.04.2026)
- ARCHITEChTURES fiyat — architechtures.com/en/pricing
- TestFit fiyat — testfit.io/pricing
- Chaos Veras 3.0 — chaos.com/press
- Manycore IPO — etf.etnet.com.hk (kod 00068)
- Kolayimar — kolayimar.com · İmarX — imarx.com.tr/asistan · yapıyo — yapiyo.tr · ArsaBil — arsabil.com · Emlak360 — emlak360.pro
- Evveko — webrazzi.com/2026/05/07/…evveko/
- Emlakjet+Endeksa — onlinemarketplaces.com/articles/endeksa-merger-…
- Algoma — pulse2.com/algoma-2-3-million-seed-…
- Oska — oska.com.tr

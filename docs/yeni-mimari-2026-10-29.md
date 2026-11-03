# ArchAI — Yeni Mimari ve Ek Özellikler (2026-10-29)

Kaynak: el yazısı not (29 Ekim 2026) + mevcut kod (`archai/`, 9,5 bin satır) + `docs/konsey-raporu-2026-09-30.md`.
Durum: **tasarım önerisi**, kod değişmedi. Onay sonrası fazlar halinde uygulanır.

## 1. Notun özeti

Merkezde **Claude (mimar ajanı)**; etrafında bir **uzman konseyi** (mimar / statik / elektrik-tesisat) tartışıyor.
Girdiler: İstanbul Bakırköy **e-İmar** verisi, parsel (**dikdörtgen olmayabilir!!!**), serbest metin ("binaya özellikleri yaz → prompt'a çevir").
Çıktılar: **AutoCAD kat planı (DXF)**, kesit, render, foto, video, 3D (Nvidia GPU makinede), **hologram / elle döndürme**.
Kurallar: TAKS/kat m², mutfak-banyo merkezi, cephe sağlama (elle 3D düzeltme), **statik hesap olmadan olmaz**, **elektrik ve boru hattı**, asansör.
Know-how: **Google Earth → hafriyat**. Maliyet: **insaathesabi.com**.

## 2. Mevcut durum → not eşlemesi

| Not maddesi | Repoda | Durum |
|---|---|---|
| e-İmar'dan çek | `imar_doc.py` (PDF/görsel → TAKS, KAKS, çekme; kanıt metniyle) | **Yarı**: belge okuma var, e-İmar'dan otomatik çekme yok |
| TAKS / kat m² | `generate.py`, `imar.py` | Var |
| Parsel dikdörtgen değil | `parcel.py` (çokgen → en büyük eksen hizalı dikdörtgen) | **Kısmi**: bina hâlâ dikdörtgen; eğik/yamuk parselde alan israfı |
| Mutfak/banyo merkezi | `apartment.py` çekirdek (ıslak hacim sınıfı `quantities.room_wet`) | Kural var, **merkezi şaft** açık kural değil |
| DXF kat planı, kesit | `drawings.py` (vaziyet, kat, A-A kesit, ön görünüş) | Var |
| Render, video, 3D | Blender köprüsü, `customer_video.py`, `model.glb`, Three.js | Var (GPU kuyruğu yerelde) |
| Cephe sağlama + elle 3D | `webapp/static/interior.js` (iç mekân düzenleyici) | **Yok**: yalnız iç mekân, cephe/kütle düzenleme yok |
| Mimar + mühendis çalışması | `approval.py` (insan onayı), `design_agent.py` (tek ajan) | **Konsey yok**; ajanlar arası tartışma yok |
| Statik hesap | maliyette kolon/kiriş kalemi **yok** (konsey raporu #5) | **Boşluk (en kritik)** |
| Elektrik / boru hattı | maliyette götürü m² | **Boşluk**: güzergâh/şaft üretilmiyor |
| Asansör | kuyu planda var; maliyette kalem var; kuyu "oda" gibi fiyatlanıyor (rapor #2) | Düzeltilmeli |
| Google Earth / hafriyat | `HAF-*` kalemi var, hacim eğimsiz tahmin | **Yok**: arazi kotu/eğim yok |
| insaathesabi.com | `poz.py`, `prices_default.json` (örnek fiyatlar) | Entegrasyon yok |
| Prompt'a çevir | `design_agent.py` yalnız iç mekân | **Yok**: bina özelliği metni → program/imar girdisi |
| Hologram / elle döndür | Three.js orbit var | Hologram ekranı: yalnız çıktı hedefi (GLB) |

## 3. Yeni mimari

```
                    ┌──────────────── GİRDİ KATMANI ────────────────┐
 serbest metin ───► │ Brief Ajanı: metin → program JSON (şemalı)   │
 e-İmar / PDF ────► │ İmar Adaptörü: parsel, TAKS/KAKS, çekme, kat  │
 Google Earth ────► │ Arazi Adaptörü: kot/eğim → hafriyat hacmi     │
 DXF / resim ─────► │ mevcut dxf_import / plan_image                │
                    └───────────────────┬───────────────────────────┘
                                        ▼
                    ┌────────── MİMAR AJANI (Claude, orkestratör) ───┐
                    │ sahip olduğu tek şey: PROJE MODELİ (eleman     │
                    │ listesi — mevcut tek kaynak, değişmez)         │
                    │ araçlar: generate, parcel.fit, avan, quantities│
                    └───────┬──────────┬──────────┬─────────────────┘
                            ▼          ▼          ▼
                      STATİK       ELEKTRİK/    İMAR/MEVZUAT
                      AJANI        TESİSAT      DENETÇİSİ
                      (kolon-      AJANI        (TAKS/KAKS/çekme/
                      kiriş-temel, (şaft, pano, yangın/otopark/
                      yük)         boru hattı)  sığınak kontrol)
                            └──────────┴──────────┘
                                        ▼
                    KONSEY TUR DÖNGÜSÜ: öneri → itiraz → revize
                    (en çok N tur; çözülmeyen itiraz → insana sorulur)
                                        ▼
                    ┌────────────── ÇIKTI KATMANI ──────────────────┐
                    │ DXF/PDF paftalar · kesit · metraj+maliyet     │
                    │ (insaathesabi) · şartname · teklif             │
                    │ 3D GLB → GPU makine: render / foto / video     │
                    │ hologram / elle döndür görüntüleyici           │
                    └───────────────────────────────────────────────┘
```

Temel ilkeler (mevcut koddan korunur):
1. **Geometri modelden gelir, LLM'den değil.** Ajanlar eleman listesine *öneri yaması* (patch) üretir; yamayı deterministik kod uygular ve doğrular (`plan_vision.py` ve `design_agent.py` ile aynı desen: şemaya zorlanmış JSON, katalogdan süzme, rıza/anahtar yoksa çağrı yok).
2. **Her ajanın çıktısı şemalı ve kanıtlı**: itiraz = {kural, ölçülen değer, sınır, önerilen düzeltme}. Serbest metin tartışma yok → tekrarlanabilir.
3. **İnsan onayı kalır**: `approval.py` parmak izi mantığı konsey kararına da bağlanır; statik/elektrik çıktıları "avan, imzasız" damgası taşır.
4. **Konsey bir kalite kapısıdır, süs değil**: ajan itirazı olmadan "kabul" yazamaz; itiraz kodu (örn. `STAT-KOLON-AKS`) testlerle sabitlenir.

### 3.1 Konsey — rol ve sözleşme

| Ajan | Girdi | Üretir | Doğrulama (deterministik) |
|---|---|---|---|
| Mimar (orkestratör) | brief, imar, arazi | program, kat planı yaması | `layout_check`, imar özeti |
| Statik | eleman listesi, kat sayısı | kolon aksı + kiriş + radye/temel boyutu (avan, ön boyutlandırma), betonarme kalemleri | kolon izdüşümü duvar/mahal/asansör ile çakışmıyor; açıklık ≤ eşik |
| Elektrik/Tesisat | mahal listesi, ıslak hacimler | dikey şaft, pano, kolon hattı + yatay boru güzergâhı (şematik) | ıslak hacimler şafta ≤ L m; şaft kat boyunca hizalı |
| İmar/Mevzuat | imar özeti, parsel | TAKS/KAKS/çekme/otopark/sığınak itirazları | `imar.py` + yeni kurallar |

Tur: Mimar öneri → üç denetçi paralel itiraz → Mimar yamayı uygular → en çok 3 tur. Kalan itirazlar rapora "açık madde" olarak yazılır (gizlenmez).

### 3.2 Parsel ve cephe

- **Eğik/yamuk parsel**: bugünkü "tek dikdörtgen" yerine **L / yamuk kütle** (yapılaşma alanını 1–3 dikdörtgene ayırıp çekirdeği bağlama). İlk faz: ön cepheye paralel + bir kanat (L). Hedef: dikdörtgenin kullanamadığı alanın ≥ %60'ını geri kazanmak (ölçü: yapılaşma alanı kullanım oranı).
- **Cephe sağlama**: cephe kuralları (pencere/duvar oranı, çıkma, kat yüksekliği, güneş yönü) bir doğrulayıcı olarak; **3D'de elle düzeltme** = mevcut `interior.js` düzenleyicisinin duvar/pencere seçip taşıyan "cephe modu". Düzeltilen cephe elemanlara geri yazılır, metraj ve çizimler yenilenir.

### 3.3 Arazi ve hafriyat (Google Earth know-how)

- Girdi: parsel köşe koordinatları (WGS84; `parcel.to_metric` zaten çevirir) → **kot ızgarası**.
- Kaynak seçenekleri (karar bekliyor, bkz. §6): (a) Google Earth Engine / Maps Elevation API (anahtar+kota), (b) açık veri: Copernicus GLO-30 / SRTM (30 m, ücretsiz, **parsel ölçeğinde kaba**), (c) kullanıcı Google Earth'ten kot yükler (KML/CSV).
- Hesap: temel/bodrum tabanı kotu − arazi yüzeyi → **kazı hacmi m³**, `HAF-*` kalemini besler; sonucun yanına **belirsizlik aralığı** yazılır (30 m veri ±birkaç metre verir; kesin hafriyat için topoğrafik harita/zemin etüdü şart — rapora yazılır).

### 3.4 Maliyet (insaathesabi.com)

İlk sürümde **web scraping yok**: site kullanım şartları/API durumu bilinmiyor. Öneri: `poz.py` üzerinden fiyat sağlayıcı arayüzü (`prices_default.json` ← firma listesi ← ÇŞİDB ← ileride insaathesabi API/anlaşma). Sorulacak: resmi API/ortaklık var mı?

### 3.5 GPU ve çıktılar

- Nvidia GPU makine: mevcut Blender/Cycles kuyruğu (`/real`, `ARCHAI_BLENDER`) **uzaktaki GPU worker**'a taşınır: ArchAI sunucusu GLB + iş JSON'u gönderir, worker render/video/foto döner. Güvenlik: worker'a yalnız imzalı/tokenlı HTTP; Blender köprüsünün auth'suz `exec_python`'u asla ağa açılmaz (konsey raporu #11).
- Hologram: ayrı üretim yok; hedef = **GLB + turntable video + elle döndür web görüntüleyici**. Gerçek holografik ekran (Looking Glass vb.) quilt/görüntü beslemesi ileri faz.

## 4. Ek özellik öncelikleri

| # | Özellik | Değer | Efor | Not |
|---|---|---|---|---|
| P0 | Statik ön boyutlandırma + betonarme kalemleri | Teklif güvenilirliği (rapor #5) | M | "Statik olmadan olmaz" notuyla doğrudan |
| P0 | Konsey iskeleti (rol şeması, tur döngüsü, itiraz kodları) | Mimarinin omurgası | M | Önce kural tabanlı denetçiler, LLM sonra |
| P1 | Brief → program ("prompt'a çevir") | Girdi sürtünmesi | S | `design_agent`/`imar_doc` desenini kopyalar |
| P1 | Elektrik/tesisat şaft + güzergâh | Notta çift ünlem | M | Şematik, avan |
| P1 | Asansör kuyusunu "oda" fiyatlamadan çıkar | Hata düzeltme (rapor #2) | S | `role:"common"` filtresi |
| P1 | L/yamuk kütle (düzensiz parsel) | Notta üç ünlem | L | En riskli geometri işi |
| P2 | Arazi kotu → hafriyat | Know-how | M | Veri kaynağı kararı gerekli |
| P2 | 3D cephe düzenleme modu | Elle düzeltme | M | `interior.js` üstüne |
| P2 | e-İmar otomatik çekme | Girdi sürtünmesi | ? | Resmî API var mı? Yoksa `imar_doc` PDF yolu kalır |
| P3 | Uzak GPU worker | Ölçek | M | |
| P3 | Hologram ekran çıktısı | Vitrin | S | |

## 5. Riskler

1. **Sorumluluk**: statik/elektrik çıktıları ruhsat belgesi değildir; her paftada avan notu + insan imzası (mevcut `notice.py`/`approval.py`). "Statik hesap yapıldı" izlenimi verilmemeli — dil: "ön boyutlandırma".
2. **Konsey gösteriye dönüşme riski**: ajan tartışması ölçülebilir bir hatayı yakalamıyorsa maliyet katar. Her denetçi için "yakaladığı hata sınıfı" testi yazılır (örn. kolon asansör kuyusuna düşerse STAT itirazı).
3. **Geometri doğruluğu**: L/yamuk kütle plan şemalarını (dikdörtgen çekirdek varsayımı) bozabilir; önce `parcel.py` testlerine karşı genişletilir.
4. **Veri kaynağı/lisans**: Google Earth/Maps verisi kullanım şartları, e-İmar erişimi, insaathesabi.com içeriği — hukuki teyit.
5. **Konsey raporundaki açık güvenlik/doğruluk borçları** (kimlik doğrulamasız ağ, xss, çekme ölçümü aksa göre, hızlı mod alan eksikliği) yeni özelliklerden **önce** kapanmalı; aksi halde yeni çıktılar da yanlış-ama-sessiz olur. README'ye göre bir kısmı kapandı (token, loopback, formül kaçışı) — kalanların güncel durumu tarama gerektirir.

## 6. Beyin fırtınası sonuçları (2026-10-29)

### 6.1 Kitle ve kapsam kararları
- **Kitle:** hem mimar hem müteahhit; yamuk parsel, tek cümleden bina ve maliyet doğruluğunun üçü de önemli. Ağırlık **mimar için plan üretimi**.
- **Kapsam:** genel (konut, villa, ticari, karma); ağırlıklı pazar **İstanbul kentsel dönüşüm**.
- İki kitle = aynı motor, iki ekran: müteahhit "ne çıkar / kaça mal olur / kâr eder mi", mimar "iyi başlangıç + kolay düzeltme".
- **Ürün ilkesi:** mimar kara kutuya güvenmez. Plan üretimi "bitmiş proje" değil, düzenlenebilir başlangıç olmalı.

### 6.2 Mimar tarafı: plan üretimi önerileri (değer sırasıyla)
1. **Konuşarak revizyon:** "salonu güneye al", "mutfağı 2 m² büyüt"; ajan eleman listesine yama uygular, `layout_check` ve imar kontrolü anında çalışır, fark gösterilir.
2. **Çoklu alternatif + puanlama:** aynı program için 4–6 yerleşim; net/brüt oranı, koridor payı, ıslak hacim kümeleme, gün ışığı gibi ölçülebilir puanlar.
3. **Çözücü tabanlı yerleşim:** poligon + program + kısıtlar → yerleşim. Yamuk parselin gerçek çözümü; ürünün teknik hendeği. Büyük Ar-Ge.
4. **Profesyonel DXF kalitesi:** katman standardı (mimarın şablonu yüklenebilir), blok kütüphanesi, ölçülendirme, aks balonu, mahal etiketi, kartuş.
5. **Çift yönlü akış:** mimar AutoCAD'de düzeltip DXF'i geri yükler, sistem metraj/maliyet/imar kontrolünü yeniden hesaplar (`dxf_import.py` yolun yarısı).
6. **Eskizden plana:** el çizimi fotoğrafı → düzenlenebilir plan (`plan_image.py` + Claude görsel okuması).
7. **Mevzuat denetçisi:** otopark, sığınak, yangın merdiveni, asansör zorunluluğu, engelli erişimi, minimum oda ölçüleri; üretimden bağımsız, yüklenen DXF'i de denetler.
8. **Cephe ve kesit:** dört cephe, birden çok kesit, cephe ritmi seçenekleri.

### 6.3 Genel kapsamın mimariye etkisi
- Şablon yerine **çözücü çekirdek**: *"bu poligonun içine bu programı bu kurallarla yerleştir."*
- **Tipoloji paketleri** eklenti gibi: varsayılan program + kural seti + maliyet kalemleri (apartman, villa, ofis, dükkân/karma, otel…). Yeni tip = veri yazmak, kod değil.
- **IFC çıktısı** gündeme gelir: Revit/ArchiCAD'e akan açık format (DXF yetmeyebilir).
- Tuzak: her şeyi "biraz" yapan araç ilk tercih olmaz. **Mimari genel, pazara tek tipolojiyle giriş** (İstanbul konut/kentsel dönüşüm), ikinci tipolojiyle genelliği kanıtla.

### 6.4 Yürütme yolu (A/B) ve öneri
- **A. Önce çözücü:** sağlam temel, ilk görünür sonuç 2–3 hafta sonra.
- **B. Önce mimar iş akışı:** DXF kalitesi, konuşarak revizyon, mevzuat denetçisini mevcut üretici üzerinde yap; çözücü ayrı kolda ilerler, hazır olunca üreticinin yerini alır. **Öneri: B**, çünkü mimar geri bildirimi gelmeden çözücüyü kör yazmak riskli.
- Karar henüz kesinleşmedi (bkz. §9).

### 6.5 Müteahhit/arsa sahibi tarafı: ek fikirler
Arsa fizibilitesi / kâr analizi · kat karşılığı (arsa payı) hesaplayıcı · senaryo karşılaştırma (3 alternatif yan yana) · duyarlılık analizi (fiyat kaydırıcıları) · nakit akışı / hakediş takvimi · satış değeri tahmini (veri/lisans riski) · çevre bağlamı (uydu üstüne kütle, gölge/güneş) · paylaşılabilir proje linki · deprem/zemin sınıfı uyarısı (AFAD) girdisi.

## 7. Kentsel dönüşüm (İstanbul ağırlıklı)

> Uyarı: 6306 sayılı Kanun, oy çoğunlukları, hibe/kredi desteği ve imar bonusu ayrıntıları **hatırdan yazıldı**; sayısal değerler kodlanmadan önce güncel mevzuatla teyit edilmeli.

**Fark:** yeni yapıda boş arsa ve tek sahip vardır; dönüşümde mevcut bina, çok sayıda malik ve farklı arsa payları vardır. Soru "ne çıkar?" değil, **"herkes bugünkünden ne alır ve ikna olur mu?"** Zorluk geometriden çok insan ve hukuktur.

| # | Özellik | Not |
|---|---|---|
| 1 | **Hak sahipleri daire dağıtımı** | malik / arsa payı / mevcut m² → yeni daireler; kat-cephe-manzara değer katsayıları, kura simülasyonu, müteahhit payı. Dönüşümdeki uzlaşma tıkanıklığının merkezi |
| 2 | **Mevcut ↔ yeni karşılaştırma** | malik başına kişisel çıktı ("85 m² dairen → 3. katta 98 m²") + 3D; ikna aracı |
| 3 | **Dönüşüm fizibilitesi** | yıkım/moloz, kira yardımı süresi ve tutarı, hibe/kredi, müteahhit payı, takvim; mevcut maliyet motoruna kalem ekleme |
| 4 | **Uzlaşma takibi** | evet/hayır/kararsız, gereken çoğunluğa kalan; sade panel (hukuki süreci yönetmez) |
| 5 | **Parsel birleştirme / ada ölçeği** | birleşen parseller çoğunlukla düzensiz → çözücü bu pazarda zorunlu; yeni parsel alanı/emsal/çekme etkisi |
| 6 | **Mevcut durum modelleme** | eski proje çoğu zaman yok: fotoğraf/eskiz/ölçüden taslak, eski ↔ yeni 3D |
| 7 | **Risk raporu entegrasyonu** | riskli yapı tespiti lisanslı kuruluş işidir; **biz yapmayız**, sonucu girdi alıp raporda gösteririz |
| 8 | **Sade Türkçe çıktı** | malikler mühendis değil: "TAKS/KAKS" yerine "kaç m² alırsınız" |

**Önerilen sıra:** (1)+(2) → (3) → (5) çözücüyle birlikte → uzlaşma paneli ve mevcut durum modelleme.

**Riskler**
- **Hukuk/sorumluluk:** yanlış hak hesabı gerçek zarar verir. Çıktılar "ön hesap; hukukçu/noter teyidi gerekir" damgası taşımalı (mevcut `notice.py` / `approval.py` deseni).
- **KVKK:** malik adı, TC, tapu bilgisi kişisel veridir. Ya hiç tutulmaz (anonim/etiketli girdi) ya da bilinçli ve güvenli tutulur; mevcut yerel/anahtarsız çalışma düzeni bu veriyle ağa açılmaya uygun değil.
- **Veri:** TKGM tapu/e-İmar entegrasyonu zor; ilk sürümde elle giriş.

## 8. Ek özellik havuzu ve öncelik tablosu

Beyin fırtınasında çıkan 23 ek özellik. Değer = kullanıcıya etkisi, Efor: S (günler) / M (1–3 hafta) / L (ay+). Faz, §6.4'teki **B yolu** varsayımıyla: Faz 1 mevcut üretici üzerinde hızlı kazanç, Faz 2 çözücü ve konsey, Faz 3 genişleme. Tablo §4'teki P0–P3 listesini tamamlar, yerini almaz.

### 8.1 Türkiye'ye özgü / resmî süreç

| # | Özellik | Kitle | Değer | Efor | Bağımlılık / not | Faz |
|---|---|---|---|---|---|---|
| 1 | **Kat irtifakı / kat mülkiyeti tabloları** (bağımsız bölüm, brüt/net, arsa payı, ortak alan) | mimar, dönüşüm | Yüksek | S | Mevcut plan + mahal verisi; #7'nin değer katsayısıyla arsa payı | 1 |
| 2 | **Ruhsat dosyası otomasyonu** (evrak listesi, sıralı pafta paketi, alan cetvelleri) | mimar | Yüksek | M | `drawings.py`; belediyeye göre şablon farkı | 2 |
| 3 | **Yönetmelik asistanı** (imar yönetmeliği, plan notu, otopark, yangın; kaynaklı cevap) | mimar | Yüksek | M | Kaynak metinler + RAG; mevzuat denetçisi ve konsey ajanları ortak kullanır | 2 |
| 4 | **Enerji kimlik belgesi ön hesabı (BEP-TR)** | mimar, müteahhit | Orta | M | Yalıtım/pencere kalemleri var; "ön hesap" damgası | 3 |
| 5 | **Yapı kayıt / iskân durumu notları** (eski yapı yasal durumu) | dönüşüm | Orta | S | Yalnız not/kontrol listesi; hukuki teyit şart | 3 |

### 8.2 Tasarım kalitesi / analiz

| # | Özellik | Kitle | Değer | Efor | Bağımlılık / not | Faz |
|---|---|---|---|---|---|---|
| 6 | **Güneş ve gölge analizi** (yıl boyu, daire başı gün ışığı, komşu etkisi) | mimar, müteahhit | Yüksek | M | 3D model + enlem/boylam; komşu yükseklik verisi kaba olur | 2 |
| 7 | **Rüzgâr + görüş analizi → daire değer katsayısı** | dönüşüm, müteahhit | Yüksek | M | #6'yı kullanır; hak dağılımının (§7-1) adalet girdisi | 2 |
| 8 | **Yangın ve kaçış analizi** (mesafe, merdiven genişliği, tahliye) | mimar | Orta | M | Mevzuat denetçisinin ileri hali | 2 |
| 9 | **Erişilebilirlik denetimi** (rampa, asansör ölçüsü, engelli WC, koridor) | mimar | Orta | S | Kural tabanlı; `layout_check.py` genişletmesi | 1 |
| 10 | **Akustik ve havalandırma uyarıları** (yalıtımlı duvar, ıslak hacim şaftı) | mimar | Düşük–Orta | S | Elektrik/tesisat ajanıyla örtüşür | 3 |

### 8.3 Şantiye ve uygulama

| # | Özellik | Kitle | Değer | Efor | Bağımlılık / not | Faz |
|---|---|---|---|---|---|---|
| 11 | **İş programı (Gantt) + hakediş / nakit akışı** | müteahhit | Yüksek | M | Metraj kalemleri → süre/sıra kuralları | 2 |
| 12 | **Metraj → tedarik listesi** (fire payı, tedarikçi karşılaştırma) | müteahhit | Yüksek | S–M | `costing.py`, fiyat sağlayıcı arayüzü (§3.4) | 1 |
| 13 | **Şantiye ilerleme takibi** (fotoğraftan kat/ilerleme, plan sapması) | müteahhit | Yüksek (uzun vade) | L | Görsel model + kalibrasyon; erken faz değil | 3 |
| 14 | **4D/5D BIM mantığı** (zaman+maliyet 3D'ye bağlı, şantiye animasyonu) | müteahhit | Orta | L | #11 + GLB; IFC ile birlikte düşünülür | 3 |

### 8.4 Müşteri ve satış

| # | Özellik | Kitle | Değer | Efor | Bağımlılık / not | Faz |
|---|---|---|---|---|---|---|
| 15 | **AR ile arsada görüntüleme** (telefonda arsa üstünde bina) | müteahhit, dönüşüm | Yüksek (gösteri) | M | GLB + WebXR; konum hassasiyeti sınırlı | 3 |
| 16 | **Daire seçim ve satış portalı** (kat/cephe/daire, fiyat, 3D gezinti) | müteahhit | Yüksek | M–L | #7 değer katsayısı, 3D görüntüleyici, `growth_engine/` | 3 |
| 17 | **Kişiselleştirilmiş malik sunumu** (kendi yeni dairesi, PDF/video) | dönüşüm | Yüksek | S–M | §7-1/§7-2; `customer_video.py` | 1–2 |
| 18 | **Ses ile komut** (konuşarak revizyonun sesli hali) | mimar | Orta | S | Konuşarak revizyon (§6.2-1) hazır olmalı; STT eklenir | 3 |
| 19 | **Benzer proje bankası** (aynı bölgede emsal projeler) | mimar | Orta | M | Veri toplama/lisans; kendi proje arşivinden başlar | 3 |

### 8.5 Altyapı ve iş modeli

| # | Özellik | Kitle | Değer | Efor | Bağımlılık / not | Faz |
|---|---|---|---|---|---|---|
| 20 | **Çok kullanıcılı işbirliği** (mimar + müteahhit + mühendis, yorum, geçmiş) | hepsi | Yüksek | L | Kimlik/yetki; mevcut yerel/anahtarsız model değişir; KVKK | 2–3 |
| 21 | **Proje versiyon karşılaştırma** (plan/metraj/maliyet farkı) | mimar, müteahhit | Yüksek | S–M | `approval.py` parmak izi, konuşarak revizyonun fark gösterimi | 1 |
| 22 | **AutoCAD / Revit / Rhino eklentisi ve API** | mimar | Yüksek (uzun vade) | L | Çift yönlü akış (§6.2-5); IFC | 3 |
| 23 | **Beyaz etiket** (firma logosu, kendi fiyat listesi) | müteahhit | Orta | S | Teklif ve video firma kartı zaten var | 1 |

### 8.6 Faz özeti

**Faz 1: hızlı kazanç (mevcut üretici üzerinde, B yolu)**
- Önceden planlı: DXF kalitesi, konuşarak revizyon, mevzuat denetçisi (§6.2).
- Bu tablodan: **#1** kat irtifakı, **#9** erişilebilirlik, **#12** tedarik listesi, **#21** versiyon karşılaştırma, **#23** beyaz etiket, **#17** malik sunumunun ilk hali.

**Faz 2: çözücü ve konsey ağırlıklı**
- Çözücü tabanlı yerleşim, konsey iskeleti, statik ön boyutlandırma (§3, §4).
- Bu tablodan: **#3** yönetmelik asistanı, **#2** ruhsat dosyası, **#6/#7** güneş ve değer katsayısı, **#8** yangın analizi, **#11** iş programı, #20'nin ilk sürümü.
- Kentsel dönüşümde hak dağılımı (#7 ile birleşir) ve parsel birleştirme (§7).

**Faz 3: genişleme**
- **#4, #5, #10, #13, #14, #15, #16, #18, #19, #22** ve uzak GPU worker, hologram.

### 8.7 Bağımlılık zinciri (neyin neyi açtığı)

- **Çözücü** → yamuk parsel, parsel birleştirme (§7-5), tipoloji paketleri.
- **Konuşarak revizyon** → #18 ses ile komut, #21 versiyon karşılaştırma, çift yönlü akış.
- **Yönetmelik asistanı (#3)** → mevzuat denetçisi, #8 yangın, #9 erişilebilirlik, konsey İmar ajanı.
- **Güneş/görüş (#6, #7)** → daire değer katsayısı → kat irtifakı arsa payı (#1) ve kentsel dönüşüm hak dağılımı (§7-1) → #16 satış portalı.
- **Maliyet motoru + fiyat sağlayıcı** → #12 tedarik, #11 iş programı/hakediş, kentsel dönüşüm fizibilitesi (§7-3).

### 8.8 Dikkat
- #4, #5, #8, #9 ve #2 mevzuat ve sorumluluk içerir; hepsi "ön kontrol / avan, yetkili teyidi gerekir" damgasıyla (mevcut `notice.py` deseni) ve kaynaklı kural setiyle yapılmalı.
- #13, #19, #20 ve #22 yeni veri/altyapı ve KVKK gerektirdiği için erken fazlara alınmadı.
- Verilen eforlar tahmindir; Faz 1 işlerinin gerçek kapsamı `archai/` kodu üzerinde ayrıca doğrulanmalıdır.

## 9. Karar bekleyen sorular

**Önceden açık olanlar**

1. İlk fazda hangisi: **konsey iskeleti + statik** mı, yoksa **düzensiz parsel** mı?
2. Arazi kotu kaynağı: Google API (anahtar var mı?), açık veri (kaba), yoksa kullanıcı yüklemesi mi?
3. insaathesabi.com: resmî erişim/ortaklık var mı?
4. Konsey ajanları: yalnız Claude mu (rol promptları), yoksa denetçiler önce kural tabanlı, LLM opsiyonel mi? (Önerim: kural tabanlı önce.)
5. GPU makine: aynı ağda mı, hangi kart/VRAM? Remote worker mı yoksa ArchAI doğrudan o makinede mi çalışacak?
6. Hologram: gerçek holografik ekran donanımı var mı, yoksa 3D görüntüleyici yeterli mi?

**Beyin fırtınasında eklenenler**
7. Yürütme yolu: **A (önce çözücü)** mı, **B (önce mimar iş akışı)** mı? Öneri B.
8. Hedef mimar profili: küçük ofis/serbest mi, büyük ofis mi? Çizim aracı AutoCAD mı, Revit/ArchiCAD de var mı (IFC gerekir mi)?
9. Gerçek proje DXF'leri ve gerçek bir mimardan geri bildirim alınabilir mi?
10. Kentsel dönüşümde birincil kullanıcı: müteahhit mi, mimar mı, belediye/bina yönetimi mi? Tek bina mı, ada/parsel birleştirmeli mi, riskli alan bazlı mı?
11. Hak dağılımı için (isimsiz) gerçek bir malik listesi/dağılım tablosu örnek alınabilir mi?

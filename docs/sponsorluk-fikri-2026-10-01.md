# ArchAI — Malzeme Sponsorluğu + Teklif Toplama (fikir notu, 2026-10-01)

Durum: **fikir / taslak**. Kod yok, henüz kimseyle görüşülmedi. Aşağıdaki marka adları yalnızca
"hangi sektör" örneğidir; hiçbiriyle anlaşma ya da görüşme yoktur.

## 1. Fikir tek cümlede

ArchAI zaten projeyi **kalem kalem metrajlıyor** (iç sıva+boya, dış cephe, mantolama, PVC pencere,
kapı, zemin…). Her kalem bir **sponsor yuvası** ve aynı anda bir **teklif isteği (RFQ)** olabilir:
malzeme üreticisi/bayisi o kalemde ürününü öne çıkarır, kullanıcı da o kalemin metrajıyla tek
tıkla birden çok firmadan teklif ister, gelen fiyat maliyet tablosuna işler.

İki ayrı şey, birlikte güçlü:

| | Sponsorluk | Teklif al (RFQ) |
|---|---|---|
| Kim ister | Marka / üretici | Proje sahibi / müteahhit |
| Ne sağlar | Görünürlük, ürün seçimi, lead | Gerçek fiyat, rekabet, zaman kazancı |
| ArchAI'ye ne katar | Gelir | Doğru birim fiyat (bugün `prices_default.json` **örnek** liste) |
| Risk | Tarafsızlık algısı | Spam / veri paylaşımı |

Birleşince: sponsor = katalogda "öne çıkan" ve RFQ listesinde ilk sıra; ama **teklif verebilen herkes
listede** (sponsor olmayan da), yoksa araç reklam panosuna döner ve güveni biter.

## 2. Bugünkü koda oturduğu yerler

- `archai/data/prices_default.json` — kalem kodları var: `SIV-01` iç sıva+alçı+boya, `SIV-02` dış cephe
  sıva+boya, `YAL-01` mantolama, `PEN-01` PVC/alüminyum+ısıcam (6.500 ₺/m²), `KAP-01`, `ZEM-01`, `TAV-01`,
  `SUP-01`, `ASN-01`, `TES-01/02` …
- `archai/costing.py` — varyant, override, kalem kapatma, ek kalem zaten var → **gelen teklif = override**.
- `webapp/static/interior.js` kataloğu (`wall_paint`: kırık beyaz, saf beyaz, bej, açık gri, adaçayı, gök,
  terakota, antrasit; zemin dokuları) → sponsor boya **renk kartelası / ürün kodu** buraya girer, 3D'de görünür.
- Tasarım ajanı: şu an maliyete yalnız zemin (ZEM-01) yansıyor, **duvar boyası varyantsız**. Sponsor boya için
  boyayı sıvadan ayırmak şart (aşağıda §4).
- `teklif.docx` ve `teknik_sartname.docx` — sponsor/tedarikçi ibaresi ve "veya eşdeğeri" burada çıkar.
- Müşteri videosu: firma kartı var → "Malzeme ortağı" kartı eklenebilir.

## 3. Kalem → sektör eşlemesi (kimden ne istenir)

| Kalem (kod) | Sponsor / teklif sektörü | Teklifte istenen | Not |
|---|---|---|---|
| İç boya (SIV-01'den ayrılacak) | Boya üreticileri, bayiler | m² duvar+tavan, kat sayısı, astar+2 kat, renk | Renk kartelası 3D'ye girer |
| İç sıva / alçı | Alçı, sıva üreticileri | m², makine/el sıva | |
| Dış cephe boya + sıva (SIV-02) | Dış cephe boya, sıva | m² net dış duvar, iskele dahil mi | |
| Mantolama (YAL-01) | EPS/XPS/taş yünü, yapıştırıcı-sıva sistemi | m², kalınlık (TS 825 bölgesine göre) | Sistem satışı: levha+yapıştırıcı+dübel+sıva |
| Dış cephe kaplama (yeni kalem) | Kompozit, seramik, taş, ahşap cephe, kaplama tuğla | m², detay | Ayrı kalem açılmalı |
| PVC / alüminyum doğrama (PEN-01) | Profil üreticileri + imalatçı bayiler | Pencere listesi (en×boy×adet, açılım), cam tipi | Metrajda pencere ölçüleri var → hazır liste |
| Kapı (KAP-01) | Çelik kapı, iç kapı, kasa | Adet + ölçü + tip | |
| Zemin kaplama (ZEM-01), seramik | Seramik, parke, laminat | m², fire %10 | |
| Vitrifiye / armatür | Banyo-mutfak armatürü | Mahal listesinden adet | Mahal listesi var |
| Elektrik (priz-anahtar), aydınlatma | Elektrik malzemesi | Mahal başı nokta | Şu an götürü |
| Tesisat boru / kombi / ısıtma | Boru, kombi, radyatör/yerden ısıtma | m² | Şu an götürü |
| Asansör (ASN-01) | Asansör firmaları | Durak sayısı | Yüksek bilet, tek lead değerli |
| Kaba yapı: hazır beton, demir, tuğla/gazbeton | Beton santrali, demir, duvar malzemesi | m³ / ton / m² | Sponsorluktan çok RFQ; fiyat sürekli oynar |
| Çatı, su yalıtımı | Membran, kiremit, çatı sistemi | m² | |
| Çevre: peyzaj, havuz | Havuz, taş kaplama, peyzaj | m² | |
| Mobilya / mutfak dolabı | Mobilya, mutfak imalatçısı | Mahal ölçüsü | Tasarım ajanıyla doğal bağ |
| **Hizmet:** iskele, hafriyat, işçilik | Taşeron | Kalem + m² | RFQ'ya taşeron da eklenebilir |

## 4. Önce yapılması gereken: kalemleri parçalamak

> **Durum (2026-10-01): yapıldı** (`feat/kalem-bolme`). Katalog 30 → 94 kaleme çıktı; iç/dış boya, sıva, alçı, mantolama katmanları,
> pencere doğraması / ısıcam, iç / çelik / dış kapı, beton / donatı / kalıp ayrıldı. Sponsor yuvası için ürün-spesifikasyon alanları (marka/model/garanti) henüz yok.

Sponsorluk ürün düzeyinde olacağı için bugünkü birleşik kalemler bölünmeli:

- `SIV-01` → iç sıva · alçı · **iç boya** (ayrı varyantlı)
- `SIV-02` → dış sıva · **dış boya** · (mantolama zaten ayrı)
- `PEN-01` → profil malzemesi **PVC / alüminyum** varyantı + cam tipi (çift cam / ısıcam / low-e) ayrı
- Dış cephe kaplama kalemi ekle
- Her kalemde **spesifikasyon alanları**: marka/model, sınıf, garanti — şartnameye düşsün

Bu bölme sponsor olmasa da maliyet doğruluğunu artırır (README'de bilinen kısıt: duvar boyası maliyeti
değiştirmiyor).

## 5. Akış (kullanıcı gözüyle)

1. Proje üretilir → metraj + maliyet ekranı.
2. Kalemin yanında **"Teklif al"** düğmesi; üstte toplu **"Seçili kalemlerden teklif topla"**.
3. Kalem seçilir (ör. PEN-01, SIV-02, YAL-01). Kapsam ayarı: şehir/ilçe, istenen termin, marka tercihi
   (serbest / sponsor ürünleri / belirli markalar), "eşdeğeri kabul".
4. ArchAI **RFQ paketi** üretir: kalem metrajı (Excel/PDF), kısa şartname, termin, şehir. **Müşteri adı,
   telefon, adres, parsel bilgisi gitmez** (anonim "ArchAI Proje #id").
5. Gönderim: ilk faz e-posta / WhatsApp linki / PDF indir; sonra satıcı portalı.
6. Teklif girişi: ilk faz kullanıcı elle girer (veya satıcı portal linkinden girer).
7. **Karşılaştırma tablosu**: birim fiyat, toplam, KDV dahil mi, termin, ödeme, geçerlilik, garanti,
   marka/ürün, sponsor etiketi.
8. "Bunu seç" → `costing` override olarak işlenir, maliyet güncellenir, teklif.docx'te kalem
   "tedarikçi teklifi — firma, tarih, geçerlilik" notuyla çıkar.
9. Sponsor yuvası: kalemin yanında **"Önerilen malzeme: <marka> · Sponsorlu"** kartı; seçince ürün
   kodu şartnameye ve 3D renk/doku seçimine geçer.

## 6. Veri modeli (taslak)

- `Supplier`: ad, sektör(ler), il/ilçe servis alanı, iletişim, doğrulama durumu, ETK izni, güvenilirlik puanı
- `Product`: supplier, kalem_kodu, marka, model/SKU, birim, liste fiyatı, geçerlilik tarihi, özellikler,
  doku/renk (3D için), teknik föy linki
- `Sponsorship`: supplier, kapsam (kalem kodları), bölge, başlangıç-bitiş, seviye, münhasırlık, fiyat, durum
- `RFQ`: proje_id, kalem listesi + metraj anlık görüntüsü, kapsam ayarları, gönderilen supplier'lar, durum
- `Quote`: rfq, supplier, kalem bazında birim fiyat, KDV, termin, geçerlilik, ek dosya, durum (açık/seçildi/reddedildi)
- Önemli: **metraj anlık görüntüsü RFQ'ya donar**; proje sonra değişirse eski teklif "eski metrajla verildi" etiketi alır.

## 7. Gelir modeli seçenekleri

1. **Kategori sponsorluğu**: kalem grubu × bölge × dönem (ör. "İstanbul Avrupa — iç boya — Q1"), münhasır ya da
   en çok N marka. Standart: "Sponsorlu" etiketi şart.
2. **Lead / RFQ başı ücret**: teklif isteği satıcıya düşünce; kalite filtreli (min. metraj eşiği).
3. **Katalog listeleme**: ürün kartı + renk/doku + teknik föy, yıllık.
4. **Satış komisyonu**: yalnız sipariş ArchAI üzerinden verilirse (ileri faz).
5. **Ürün karşılığı sponsorluk**: erken fazda para yerine ürün/örnek + vitrin projesi + referans.
6. **Veri/rapor**: anonim, toplulaştırılmış talep raporu ("bu ay X ilde PVC doğrama talebi") — hassas, hukuki
   görüş şart.

## 8. Sponsora ne sunarız (pitch malzemesi)

- Karar anında görünürlük: kullanıcı malzemeyi **seçerken** (avan aşamasında), katalog gezerken değil.
- Metraja bağlı, nitelikli talep: "120 m² dış cephe, İzmir, 6 hafta" gibi somut lead.
- 3D'de kendi renk/dokusuyla müşteri videosunda görünme.
- Şartnamede ürün kodu (not: kamu işi değil, özel proje; yine de "veya eşdeğeri" ibaresi).
- Raporlama: kaç RFQ, kaç teklif, seçilme oranı.

## 9. Riskler ve karşı önlemler

| Risk | Önlem |
|---|---|
| Tarafsızlık kaybı ("ArchAI hep X boyayı öneriyor") | Sponsorlu etiketi zorunlu; sponsor olmayan teklifler de listelenir; sıralama kuralı açık yazılı |
| Kişisel veri / KVKK | RFQ anonim; müşteri iletişimi kullanıcı onayı olmadan paylaşılmaz; aydınlatma metni. **Hukuki görüş al.** |
| Ticari elektronik ileti (ETK) | Satıcıya toplu mail atılmaz; satıcı kendi iznini verir / opt-in |
| Reklam mevzuatı | Sponsorlu içerik net işaretlenmeli; karşılaştırmalı reklam kuralları. **Hukuki görüş al.** |
| Eski / yanlış fiyat | Teklifte geçerlilik tarihi zorunlu, süresi geçen teklif otomatik gri |
| Teklifin metrajı yanlış çıkarsa satıcıya yanlış talep | Avan uyarısı RFQ'da da: "yaklaşık metraj, ±%X, kesin ölçü sonrası teyit" |
| Spam / sahte talep | Min. metraj eşiği, hesap doğrulama, günlük RFQ limiti |
| Satıcı tarafı boş kalır (yumurta-tavuk) | İlk faz elle: 3 kategori × bölge başına 3–5 firma ile başla; teklifi sen topla |
| Satıcının fiyatı ArchAI'yi baypas edip doğrudan müşteriyle anlaşması | Bu zaten olabilir; değeri lead'de ve karşılaştırmada tut, komisyona fazla güvenme |
| Mimar/mühendis imza sorumluluğu | Çıktı hâlâ avan; ürün seçimi "öneri", statik/tesisat projesi imzalı mühendise ait |

## 10. Fazlar

- **Faz 0 — doğrulama (kod yok, 1–2 hafta):** 3 kategori seç (öneri: **boya, PVC doğrama, mantolama** —
  metrajı net, fiyat etkisi büyük, rakip çok). Her birinden 3–5 firmayla konuş: sponsorluk ve lead'e para
  verir mi, ürün karşılığı mı, hangi bilgi lazım? Çıktı: fiyat/paket taslağı.
- **Faz 1 — RFQ paketi (küçük kod):** kalem seç → Excel/PDF + mailto/WhatsApp linki; teklif elle girişi;
  karşılaştırma tablosu; `costing` override. Sponsor ürünü yok, sadece teklif toplama. Kalem bölme (§4) burada.
- **Faz 2 — Sponsor yuvaları:** katalog + "Sponsorlu" kartı + 3D renk/doku + şartname ürün kodu + teklifte
  "malzeme ortağı". Admin ekranı (sponsorluk yönetimi).
- **Faz 3 — Satıcı portalı:** satıcı girişi, RFQ'ları görür, kalem bazlı teklif girer, istatistik, bildirim.
- **Faz 4 — Sipariş / komisyon / bölgesel fiyat endeksi**, mimar-müteahhit ağı.

## 11. Açık sorular (cevaplanınca plan netleşir)

1. Hedef kullanıcı kim: **bireysel arsa sahibi**, **küçük müteahhit** ya da **mimar ofisi**? RFQ davranışı farklı;
   müteahhit en çok teklif isteyen, arsa sahibi en çok sponsorlu "öneriye" güvenen.
2. İlk sponsor hangi segmentten: ulusal marka mı, bölgesel üretici/bayi mi? (Bölgesel daha kolay ve hızlı.)
3. ArchAI tek makine / yerel mi kalacak, yoksa barındırılan servis mi? Satıcı portalı için barındırma şart.
4. Para almadan başlayıp **ürün karşılığı vitrin projesi** ile referans mı toplanacak?
5. Teklifler kimde kalır: kullanıcıya özel mi, yoksa ArchAI toplulaştırılmış fiyat endeksi mi üretecek?
6. Hukuki yapı: şahıs / şirket? Sponsorluk faturası için ticari yapı gerekir.
7. Tezgâh / ArchAI isim ve marka ayrımı: sponsor satışı ArchAI adıyla mı, ayrı bir marka altında mı?

## 12. Hemen sonraki adımlar

1. `prices_default.json` kalem bölme taslağı çıkar (iç boya / dış boya / PVC profil+cam / cephe kaplama).
2. Faz 0 görüşme listesi: 3 kategori × 3–5 firma, tek sayfalık sponsor teklifi.
3. RFQ paketi için örnek çıktı üret (mevcut test projesinin PEN-01 + SIV-02 + YAL-01 metrajı) ve bir
   gerçek bayiye göster — "bu paketi alsan teklif verebilir misin?" testi.
4. Hukuki ön görüş: KVKK, ETK, sponsorlu içerik etiketi.

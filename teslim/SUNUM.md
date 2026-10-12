# ArchAI Growth Engine — Sunum Metni

**Hazırlık:** Laptopta ArchAI (8000) ve sunucu (8765) açık olsun. Tarayıcıda iki sekme:
1. `http://127.0.0.1:8765/demo` (yenilenmiş, arama başlatılmamış)
2. Yedek: `teslim/archai_demo.mp4` (canlı demo takılırsa bunu oynat)

Kriterler (her biri %20): sorun ve değer · çalışan demo · araç koordinasyonu · yarın yayına alınabilirlik · sunum.

---

## Ön eleme — 2 dakika (+1 dk soru)

**0:00 – 0:20 · Sorun** *(ekranda: demo açılışı, villa kartı)*
> "İstanbul'da bir müteahhit satılık bir arsa gördüğünde, mimardan avan proje ve maliyet tahmini almak için **3 ile 5 gün** bekliyor. Bu yüzden fırsatların çoğu kaçıyor ya da yanlış hesapla alınıyor.
> ArchAI, imar bilgisinden dakikalar içinde avan proje, metraj, maliyet ve teklif üreten mimarlık motorumuz. Bugün onu **kendi kendini pazarlayan bir satış motoruna** çevirdik."

**0:20 – 0:55 · Canlı akış** *(Kartal seç → YENİ ARAMA BAŞLAT; akışı göster)*
> "Semti seçiyorum. **Manus** işi devralıyor: **Apify** ile sahibinden'den 40 arsa ve 20 sıfır daire ilanı topluyor, 31'ini imar ve tapu kurallarıyla eliyor.
> Kalan adaylar için **ArchAI** proje çiziyor: kat planı, 94 kalemlik metraj, maliyet, teklif. Bölge satış fiyatını da ilanlardan çıkarıyor: metrekaresi 93.651 lira.
> Ve kritik bulgu: bu arsaların **hepsi satın alınırsa zarar ediyor**. Doğru model kat karşılığı. ArchAI paylaşımı da hesaplıyor."

**0:55 – 1:25 · Sonuç = öncesi/sonrası** *(Ada 12412 kartı → ▶ Tanıtım filmi, 8–10 sn oynat)*
> "Bu bina **bu sabah yoktu**. Kaynak gerçek bir sahibinden ilanı, linki burada. ArchAI projeyi çizdi, **fal** cepheyi ve iç mekânları fotogerçekçi yaptı, 38 saniyelik tanıtım filmini üretti."
*(filmi kapat → ⌂ 3D Model → YÜRÜ → birkaç adım)*
> "Müteahhit binanın içinde yürüyebiliyor, eşya ekleyebiliyor."

**1:25 – 1:45 · Kampanya** *(✉ Kampanya → Instagram önizlemesi)*
> "Manus her arsa için müteahhide ve arsa sahibine ayrı WhatsApp teklifi, Instagram, LinkedIn ve TikTok gönderisi hazırlıyor. Hiçbiri onaysız gönderilmiyor."

**1:45 – 2:00 · Kapanış** *(📄 İşlem raporu → ölçüm tablosu)*
> "Arsa başına 3–5 gün yerine dakikalar. Arsa başına maliyet: birkaç dolar. ArchAI, Manus, Apify ve fal ile **yarın yayına alınabilir**. Teşekkürler."

---

## Final — 3 dakika (+1 dk soru)

Ön eleme akışına ek olarak:
- **0:55'ten sonra +30 sn:** Kartın **Satın alma / Kat karşılığı** kutularını göster: "312 m² arsa satın alınırsa getiri %-32. Kat karşılığında arsa sahibine 1 daire, müteahhide 3 daire; müteahhit marjı %16."
- **Kapanıştan önce +30 sn:** İşlem raporundaki 8 arsalık tablo: "Manus 40 ilanı tarayıp 8 projeyi uçtan uca çıkardı; her satırın arkasında pafta, teklif ve metraj dosyası var." **Teklif** veya **Paftalar** butonuna tıkla, gerçek dosya açılsın.

---

## Olası sorular — kısa cevaplar

- **"Bu canlı mı?"** — "Akış, bu sabahki gerçek Manus çalışmasının kaydı: 48 dakikalık işi 30 saniyede oynatıyoruz. Rakamlar, ilanlar, render'lar ve dosyalar gerçek. Canlı konsolumuz da var, Manus görevini API'den başlatıyor." (`/console`)
- **"Rakamlar ne kadar güvenilir?"** — "Avan / ön fizibilite: taşıyıcı sistem ve vergi hariç, birim fiyatlar örnek. Amaç müteahhide 'bu arsaya bakmaya değer mi' kararını dakikalar içinde verdirmek. Kesin teklif için mimar yine gerekli."
- **"İmar bilgisi nereden?"** — "İlandan: imar durumu, emsal, gabari. TAKS ve çekme ilanlarda yok; varsayım yapıp her kartta açıkça yazıyoruz, belediyeden teyit gerekir."
- **"Kişisel veri?"** — "Telefon ve satıcı bilgisi hiç toplanmıyor (`extractPhoneNumbers:false`)."
- **"İş modeli?"** — "Müteahhit başına aylık abonelik ya da arsa başına fizibilite paketi. Maliyetimiz arsa başına birkaç dolar."
- **"Neden Manus?"** — "Çok adımlı işi o yönetiyor: ilan topluyor, eliyor, ArchAI'yi çağırıyor, kat karşılığına göre sıralıyor, kampanyayı yazıyor. Biz yalnız ArchAI'yi MCP ile bağladık."

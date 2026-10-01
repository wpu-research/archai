# ArchAI — Üç Modelli Konsey Raporu (2026-09-30)

Katılımcılar: Opus 5.5, Fable 5.1, Sonnet 5.5. Depo: `main` @ `7ea4fb5`.
Yöntem: 1. tur bağımsız salt-okunur inceleme; 2. tur her modelin **diğer ikisinin tekil iddialarını** kodla yeniden üretmeye çalışması (kendi bulgusunu kendisi onaylamadı).

## Puanlar
| Model | 1. tur | 2. tur | Not |
|---|---|---|---|
| Sonnet 5.5 | 6,5 | 6,5 | "Yerel araç olarak iyi, internete açılırsa güvensiz" |
| Opus 5.5 | 5,5 | 5,0 | Doğrulanan maliyet/imar hataları teklifi güvenilmez yapıyor |
| Fable 5.1 | 6,5 | 4,0 | "Yanlış ama sessiz" sınıfı hatalar; çekirdek mimari sanıldığından sağlam |

Ortak karar: **teknik çekirdek (tek eleman modeli, metraj, DXF/resim ortak hattı, avan notu) sağlam; müşteriye giden teklif ve ağa açık kullanım için henüz güvenilir değil.**

## Üç modelin de doğruladığı bulgular
1. **Ağ + XSS.** Sunucu 0.0.0.0:8000'de, kimlik doğrulama yok. Proje adı, DXF/vision mahal adı ve `extra_items.name` kaçışsız `innerHTML`'e giriyor (`esc()` yok). LAN'dan biri `<img onerror>` adlı proje açarsa arşiv listesinde çalışır.
2. **Girdi doğrulaması yok.** `floors=0`, `taks=0`, bozuk DXF/PNG, `/adjust` içinde tip hataları → 500. `profit_pct` negatifken **−19 ile −36 M TL** teklif üretiliyor. Hatalı yüklemeler yetim klasör bırakıyor.
3. **Resim ölçeği çözünürlüğe bağlı.** Aynı plan 2× büyütülünce ölçek 46,2 → 30,5 px/m (doğrusu 92,4), mahal 17 → 7, alan 258 → 151 m². Kapı-medyanı tahmini S0=45 sabitine kilitli.
4. **Duvar sınıflama / maliyet.** 0,20 m iç çekirdek duvarları `min_thickness:0.2` kuralıyla DIŞ duvar kalemlerine (DUV-01, YAL-01, SIV-02) giriyor: 22×30 örnekte 991,3 m² (dış 568,2 + çekirdek 423,1). Etki: quote'un **%7–10'u** (≈1,5–2,1 M TL / 21,9 M). Senaryo ölçümü (Fable): quick 450/3 %9,0; arazi 30×40 %7,4; apartman %7,0; villa %2,5; cabin ve DXF 2+1'de 0.
5. **Taşıyıcı sistem/temel/kolon/kiriş/kazı/asansör/merdiven kalemi fiyat listesinde yok**, teklif "anahtar teslim" diyor. B4'teki şişme bunu kısmen maskeliyor: toplam makul görünüp kalemler yanlış (2. turda üç model de "hepsinin kaçırdığı" diye ekledi).
6. **Hızlı mod alanı sessizce eksik.** `generate.py` `fp=min(fp, 2*net/0.82+CORE_W*11)`: 5000 m²/10 kat → 2743 (−%45); 600 m²/2 kat/1+1 → −%37; 2100 m²/5 kat → −%55. Uyarı yok, `kaks ok`.
7. **Çekme dış yüze göre değil aksa göre.** Rapor 5,1/3,1; dış yüz 4,975/2,975 (yasal 5,0/3,0 altında). `checks.setbacks` içinde `ok` alanı hiç yok — yani sorun "yanlış ok" değil, kontrol yok (Sonnet düzeltmesi).
8. **DXF birim sezgisi.** `$INSUNITS=0`, LWPOLYLINE ile çizilmiş mm plan → `outline_area=80 003 600`. INSERT (blok) içindeki duvarlar okunmuyor. Bozuk DXF → 500.
9. **Excel formül enjeksiyonu.** `=HYPERLINK(...)` adlı mahal/ek kalem → hücre `data_type='f'` (üç model de yeniden üretti).
10. **Test hijyeni.** Fikstür `.gitignore`'da (temiz klonda görüntü testleri atlanır); testler gerçek `out/projects`'e yazıyor (201 klasör, 1,3 GB) ve izlenen `references/test_plan_2+1.dxf`'i değiştiriyor; `truth` kısmen kendi kendini doğruluyor.
11. **Blender kuyruğu.** Zaman aşımı yok, kuyruk/JOBS sınırsız ve bellek içi, yükleme boyutu dosya yazıldıktan sonra kontrol ediliyor; köprü tek bağlantıyla bloklanıyor ve kimliksiz `exec`.

## 2. turda ortaya çıkan yeni bulgular
- Asansör kuyusu ve merdiven mahalleri "oda" gibi fiyatlanıyor (zemin/şap/tavan/sıva; yalnız kuyu ≈171 bin TL). `role:"common"` filtresi yok (Opus, Fable).
- Tek bozuk `project.json` tüm arşivi (`GET /api/projects`) 500'e düşürüyor (Fable).
- Yükleme sırası: `meta` doğrulaması dosya yazıldıktan sonra → 422'de müşteri planı `out/projects/<id>/plan.*` içinde kalıyor ve kimliksiz `/files` ile okunabiliyor (Opus).
- DXF/resimde tek çizgi duvarlar `default_thickness=0.2` alıp aynı dış duvar tuzağına düşüyor (Sonnet).
- DXF/resimde boyut sınırı yok; 4000 çizgili 0,5 MB DXF `_pair_walls` O(n²) ile 5,6 s (Fable).
- `/adjust` uç noktası `_run` kullanmıyor → her tip hatası 500 (Opus).
- Teklif şablonu (süre formülü, %20/30/30/20 ödeme, yetkili mahkeme) firma taahhüdü gibi basılıyor, düzenlenemiyor.

## Çürütülen / daraltılan iddialar
| İddia | Sonuç |
|---|---|
| Opus: `project._vision` boş mahalde `levels[0]` IndexError | **Çürütüldü** (Fable, Sonnet): list-comprehension boşta değerlendirilmiyor; asıl durum: 0 mahalle görsel yine API'ye gidiyor |
| Sonnet: vision çağrısında zaman aşımı yok | **Yanlış** (Opus, Fable): SDK 1.9 varsayılan okuma zaman aşımı 600 s + 2 yeniden deneme |
| Metraj aks uzunluğu köşe örtüşmesini iki kez sayar | **Küçük**: T birleşimlerinde ~%1–2,3 |
| Fable: çekirdek duvar sızıntısı KRİTİK | **YÜKSEK'e indirildi** (kendi ölçümüyle): DXF/villa/cabin'de etki yok ya da küçük |
| pid=`..` ile "out/ altına yazma" | **Orta-düşük**: yazılan tek dosya adı `interior.json`, içerik şemaya süzülüyor (Fable: GET de çalışıyor) |
| Merdiven `steps//2` | **Doğru ama düşük**: fiyat kalemi olmadığından maliyet etkisi 0; 3D/pafta eksikliği |
| İç sıva açıklık düşmüyor | **Doğru**: %8 (Fable) – %11,5 (Sonnet, Opus) fazla |
| Sonnet: 200 m²/2 kat hata mesajı parseli suçluyor | **Tartışmalı**: Sonnet'e göre mesaj doğru (derinlik 2 m), Opus'a göre yanıltıcı |

Sayısal farklar: 6000 px görselde süre 31 s (Opus) – 386 s (Fable), bellek 0,95–1,44 GB. Modeller aynı anda çalıştığı için makine yükü ölçümleri etkilemiş olabilir; ortak sonuç: piksel sınırı yok ve iş istek thread'inde.

## Konsey öncelik sırası (sentez)
**P0 — hemen (güvenlik + sessiz para hataları)**
1. Varsayılan `127.0.0.1`; (LAN gerekiyorsa token + Origin/Host kontrolü). Şu an 0.0.0.0'da açık.
2. Tüm `innerHTML` girdilerini kaçışla + CSP; vision `label` için 40 karakter / beyaz liste; `/` yasak.
3. `pid` için `re.fullmatch(r"\d{8}-\d{6}-[a-z0-9-]+")` + `resolve()` kök kontrolü; tek `_pdir(pid)` yardımcısı.
4. Pydantic şemaları (`parcel`, `zoning`, `quick`, `adjust`): aralık/tip/`0≤pct≤100`, hatalar 422; `/adjust` dahil tüm uçlar `_run` altında; hatada klasör temizliği; upload boyutu yazmadan önce.
5. Excel hücre temizleme (`=+-@` ile başlayanın önüne `'`).

**P1 — teklif doğruluğu**
6. Duvara `exterior` bayrağı yaz; fiyat kurallarını kalınlık yerine buna bağla (DXF/resim tek çizgileri dahil); regresyon testi: iç duvar dış kalemlerde 0 m².
7. Ortak alanlara (kat holü, merdiven, kuyu) `role:"common"` filtresi; iç sıvadan açıklık düş.
8. Taşıyıcı sistem, temel, kazı, asansör, merdiven: ya kalem ekle ya teklifte açıkça "hariç" yaz ve "anahtar teslim" ifadesini kaldır.
9. Hızlı mod: alan sapması %3'ü geçerse uyarı ya da 422; emsal kullanım yüzdesini raporla.
10. Çekmeyi dış yüzden hesapla, `ok` bayrağı ekle, yukarı yuvarla.

**P2 — dayanıklılık ve güven**
11. Resim ölçeği: girdiyi ~900–1200 px uzun kenara normalize et veya çok ölçekli S0 taraması; piksel sınırı (4096); iş arka plan kuyruğunda.
12. DXF: birim sezgisi tüm varlıklara bak, INSERT bloklarını aç, bozuk dosya → 422.
13. Vision: açık onay bayrağı (`available()` klasör varlığı yetmesin), açık `timeout`, sonuçta "yapay zekâ okuması" işareti.
14. Testler: `ARCHAI_OUT` + `tmp_path`; fikstürü sentetik üret; `references/*.dxf` değişmesin; `list_projects` bozuk kayda dayanıklı.
15. Blender kuyruğu: `proc.wait(timeout)`, JOBS üst sınırı, kalıcı durum; köprüye token.

## Modellerin bakış farkı
- **Opus**: güvenlik + "eksik kalem" (taşıyıcı sistem) önde; teklif hukuki doğruluğuna vurgu.
- **Fable**: "sessizce yanlış sayı" sınıfını en ağır sayıyor (puan 4); kendi kritik bulgusunu dürüstçe daraltıyor.
- **Sonnet**: en iyimser (6,5); B1'i para etkisi kolay kanıtlandığı için 1 numaraya koyuyor; kendi iddialarından ikisini savunup ölçümü güncelledi, Opus'un iki iddiasını çürüttü.

## Konseyin kendi yan etkisi
İnceleme sırasında testler ve TestClient denemeleri `out/projects` altına çok sayıda klasör yazdı (`out/` gitignore'da, izlenen dosya değişmedi — `git status` temiz).

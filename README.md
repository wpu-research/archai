# ArchAI

Arazi ve imar bilgisi (ya da sadece m²) veya mevcut bir DXF plandan:
**plan → teknik çizimler → metraj → maliyet / fiyat ayarlama → teknik şartname → teklif → 3D / AI video.**

```
uv sync
uv run uvicorn webapp.app:app --port 8000     # → http://localhost:8000
uv run pytest -q
```

## Girdiler

| Mod | Girdi | Ne olur |
|---|---|---|
| **Arazi** | parsel cephe × derinlik, TAKS, KAKS, çekmeler, maks. kat, daire tipi | kütle imar sınırına göre boyutlanır, kat planı otomatik yerleşir |
| **Hızlı teklif** | toplam m², kat sayısı, daire tipi | aynı üretici sanal bir parselle çalışır — teklif gerçek metraja dayanır |
| **DXF plan** | katmanlı DXF (DUVAR, PENCERE, KAPI, MAHAL, ops. KONTUR) | çift çizgi duvarlar, açıklıklar ve mahaller okunur, katlar tekrarlanır |
| **Resim plan** | PNG/JPG: CAD ekran görüntüsü, pafta çıktısı, tarama | duvar (çift/tek çizgi, renkli, taralı), kapı, pencere, mahal ve ölçek resimden bulunur; onay görseli (`tanima_onay.png`) üretilir. Anthropic kimliği varsa Claude mahal adlarını ve mobilyayı da okur |

## Çıktılar (proje başına `out/projects/<id>/`)

- `cizimler/` — vaziyet, zemin ve normal kat planı, A-A kesiti, ön görünüş: ayrı **DXF** + tek **PDF (A3)**
- `metraj_maliyet.xlsx` — formüllü maliyet (Excel'de birim fiyat değişince toplamlar güncellenir), metraj, mahal listesi
- `teknik_sartname.docx` — kalem kalem malzeme / uygulama / ölçü-ödeme
- `teklif.docx` — müşteriye teklif mektubu (kapsam, bedel, m² fiyatı, ödeme planı, süre, hariçler)
- `3d/` — Blender önizleme, colormap (AI video kontrol görüntüsü), `model.glb`

## 3D: gezinti, gerçekçi render, iç mekân düzenleyici

- **◉ YÜRÜ** — birinci şahıs gezinti (WASD + fare / dokunmatik), duvar çarpışması, Q/E kat; `?walk=x,y,yön` paylaşım linki
- **◈ GERÇEKÇİ** — HDRI ortam ışığı, gölgeli güneş, GTAO, PBR zemin dokuları, sıva duvar, pencere/kapı kasaları
- **✎ DÜZENLE** — zemin kaplaması (tıkla → odaya tıkla / bu kat / tüm katlar, kaplama metrajı), duvar boyası,
  nesne yerleştirme (vitrifiye, mutfak, yatak, gardırop parametrik; salon mobilyası Poly Haven), taşı/döndür/sil,
  **ÖRNEK DÖŞE**; düzen proje başına `interior.json`'a kaydedilir
- Varlıklar CC0 (Poly Haven), repoda değil: `uv run python scripts/fetch_assets.py` (~29 MB)

## Müşteri videosu

Proje ekranında **🎬 MÜŞTERİ VİDEOSU** → seçenekler (kısa ≈30 sn / standart 60–90 sn, 720p/1080p, Cycles, müzik, altyazı) →
ilerleme çubuğu → oynatıcı + mp4 indirme. Video proje verisinden otomatik kurulur: dış orbit, kat kat açılış, görünüm modları,
kapı bitişikliğinden üretilen duvardan geçmeyen yürüyüş, gün-gece, (isteğe bağlı) Cycles görüntüleri, pafta / metraj / maliyet /
teklif kartları (yalnız proje sayıları), firma kartı (ayarlarda firma bilgisi/`out/logo.png` varsa; yoksa atlanır), avan notu,
Türkçe altyazı, sentezli müzik, kapak karesi ve `.srt`. API: `POST /api/projects/{id}/video`, `GET /api/video-jobs/{jid}`,
`POST …/cancel`, `GET …/download`. Komut satırı: `python scripts/musteri_videosu.py <proje_id> --short`.

Gerekenler: `ffmpeg`, Playwright'lı bir Python (`pip install playwright && playwright install chromium`; sunucu venv'inde yoksa PATH'teki
`python3` ya da `ARCHAI_VIDEO_PYTHON` kullanılır), iç mekân modelleri/HDRI için `scripts/fetch_assets.py`, Cycles için Blender, hızlı çekim
için GPU (ANGLE-GL; yoksa SwiftShader yedeği çok yavaştır ve uyarı verir). Ortam: `ARCHAI_VIDEO_CONCURRENCY` (1), `ARCHAI_VIDEO_MAX_QUEUE` (4),
`ARCHAI_VIDEO_TIMEOUT` (3600 sn), `ARCHAI_VIDEO_KEEP_PER_PROJECT` (3), `ARCHAI_VIDEO_MAX_GB` (8), `ARCHAI_VIDEO_MIN_FREE_GB` (3).

## Resimden plan tanıma

`archai/plan_image.py` (yalnız numpy + PIL): çizgi maskesi → çift çizgi eşleştirme (eş seçiminde örtüşme önce),
kalın/renkli kontur, tek çizgi duvar (uçları duvara dayanan) → mobilya ayıklama (duvar dibi paralel çizgi;
ham çizimde küçük kapalı kutuya bakan kısa parça) → dış kabuğa bağlı bileşen → kapı boşlukları → pencere
(boşlukta paralel doğrama çizgileri ya da taralı duvarda taramanın kesildiği yer) → mahal (boş alan doldurma).
Ölçek: verilen `px_per_m` > `grid_m` > kapı boşluğu medyanı ≈ 0,95 m (ızgara varsa birimi bu tahminle seçilir).
Pafta ekleri (ölçü zinciri, aks, ölçek çubuğu) taralı dış duvarların sınır kutusuna kırpılarak atılır.

Doğruluk (`archai/plan_eval.py`, testlerde bekçi eşikleri): 3 daireli CAD ekran görüntüsünde ölçek ipucusuz
%0,1 içinde, duvar isabet/kapsam %98/%98, kapı 15/18; ArchAI'nin kendi 1/100 villa paftasında ölçek %1,
duvar %94/%99, mahal 10/10, pencere 11/11.

**Hibrit okuma** (`archai/plan_vision.py`): tanınan mahaller numaralanıp Claude'a (claude-opus-5-5,
yapılandırılmış JSON çıktı) gönderilir; mahal adı ve mobilya sembolleri (tür, kutu, duvara dayanan yüz) döner,
mobilya parametrik kataloğa yerleşir. Geometri hiçbir zaman görüntü modelinden alınmaz. Kimlik yoksa
(`ANTHROPIC_API_KEY` veya `ant auth login`) atlanır; tanıma geometriyle devam eder.

## Modüller

| | |
|---|---|
| `archai/generate.py` | arazi + imar + program → eleman listesi (TAKS/KAKS/çekme/kat kontrolü, çekirdekli 1–2 daireli kat, geniş / dar-derin yerleşim) |
| `archai/dxf_import.py` | DXF → eleman listesi |
| `archai/quantities.py` | eleman listesinden analitik metraj (aks uzunluğu, net duvar, açıklık, mahal) |
| `archai/costing.py` | birim fiyat × metraj; varyant, override, kalem kapatma, ek kalem, genel gider / kâr / KDV, yaklaşık m² yöntemi |
| `archai/data/prices_default.json` | **ÖRNEK** birim fiyat listesi — güncel ÇŞİDB birim fiyatları veya firma listesiyle değiştirilmeli |
| `archai/spec.py`, `archai/reports.py` | şartname, Excel, teklif |
| `archai/drawings.py` | DXF/PDF teknik çizimler |
| `archai/project.py` | uçtan uca akış |
| `webapp/` | FastAPI + tek sayfa arayüz |
| `blender_addon/`, `mcp_server/` | Blender köprüsü ve MCP araçları (ajan modelleme, colormap, GLB) |

Blender 4.5 LTS: `~/Applications/blender-4.5.14-linux-x64/` (başka yer için `ARCHAI_BLENDER`).

## Güvenlik ve çalıştırma

| Ortam değişkeni | Anlamı |
|---|---|
| `ARCHAI_TOKEN` | Erişim anahtarı. Ayarlıysa **her istek** (arayüz ve statik dosyalar dahil) anahtar ister: `Authorization: Bearer …`, `X-ArchAI-Token: …`, `?token=…` ya da `archai_token` çerezi. `?token=` ile gelinince HttpOnly + SameSite=Strict çerez yazılır, sonraki istekler onu kullanır. **Ayarlı değilse yalnız bu makineden (127.0.0.1 / ::1) erişilir**, uzak istemciler 403 alır. |
| `ARCHAI_OUT` | Çıktı kökü (varsayılan `out/`): projeler `ARCHAI_OUT/projects/`, ayarlar `ARCHAI_OUT/settings.json`. Testler geçici dizin kullanır. |
| `ARCHAI_ALLOWED_HOSTS` | Virgüllü ek `Host` adları (ör. `ofis-pc.local,archai.lan`). Loopback adları ve IP adresleri her zaman kabul edilir; diğer adlar 400 alır (DNS rebinding koruması). |
| `ARCHAI_BLENDER` | Blender yürütülebilir dosyası (Cycles render kuyruğu). |
| `ARCHAI_RENDER_TIMEOUT` | Tek render işinin süre sınırı, sn (varsayılan 1800); aşılırsa süreç öldürülür, iş `error` olur. |

Yerel kullanım (varsayılan, anahtar gerekmez):

```bash
uv run uvicorn webapp.app:app --port 8000            # http://localhost:8000
```

Yerel ağdan (LAN) erişim — anahtar zorunlu:

```bash
ARCHAI_TOKEN=$(openssl rand -hex 16) uv run uvicorn webapp.app:app --host 0.0.0.0 --port 8000
# diğer cihazda: http://192.168.1.20:8000/?token=<ANAHTAR>   (ilk açılıştan sonra çerez yeterli)
```

- Durum değiştiren isteklerde (POST/PUT/DELETE) `Origin` başlığı varsa `Host` ile aynı olmalı (çapraz site istekleri 403).
  Ters vekil (reverse proxy) arkasında `Host` başlığını koruyun.
- Yükleme sınırları: DXF / resim plan **25 MB** (413); Cycles sahnesi (`/real`) **300 MB**; render kuyruğu en çok
  **8** bekleyen iş (dolunca 429); bir işte en çok 200 ışık. `meta` / `job` JSON'u şemaya uymazsa 422.
- Proje kimlikleri `YYYYMMDD-HHMMSS-ad-xxxx` biçimindedir; başka biçimdeki klasörler (elle kopyalanmış eski kayıtlar)
  API'den açılmaz. Bozuk `project.json` arşiv listesinde atlanır.
- Hata yanıtları Türkçe ve tek satırdır; beklenmeyen hatalar ayrıntı sızdırmadan `500 iç hata` döner (ayrıntı sunucu logunda).
- Excel çıktısında `= + - @` ile başlayan metinler formül olarak yorumlanmasın diye başına `'` konur.

## Sınırlar — bilinmesi gerekenler

- Tüm çıktılar **avan proje** seviyesindedir (paftalar, teklif, şartname, Excel bunu yazar): statik, tesisat ve
  ruhsat projeleri yetkili mimar/mühendis imzası gerektirir.
- Resim plan: kapı açılış yönü okunmaz; kasası olmayan geçişler (duvar çizilmemiş açıklık) kapı sayılmaz;
  PDF önce resim olarak dışa aktarılmalı; mahal adı ve mobilya için Claude görsel okuması gerekir.

- Üretilen plan **şematik ön tasarımdır** (avan seviyesi); ruhsat projesi değildir, mimar kontrolü ve imzası gerekir.
  Emsal hesabı yaklaşıktır (emsal dışı alanlar ayrıştırılmıyor). Parsel şimdilik dikdörtgen.
- Kat planı kural tabanlı: kat başına 1–2 daire, tek çekirdek; ısıtma, statik, tesisat projesi üretilmez.
- Birim fiyatlar örnektir. Mekanik/elektrik tesisatı m² başına götürü.
- DXF içe aktarma katman kurallarına dayanır; DWG önce DXF'e çevrilmelidir. Eğik/eğrisel duvarlar yaklaşık.
- Blender köprüsü localhost'ta auth'suz `exec_python` çalıştırır — yalnız yerel kullanım. Web uygulaması için
  bkz. **Güvenlik ve çalıştırma** (`ARCHAI_TOKEN` olmadan yalnız loopback).
- Üçüncü taraf referans görseller (Instagram karesi) repoda tutulmaz; `.gitignore`da.

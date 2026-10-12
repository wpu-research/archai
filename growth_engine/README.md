# ArchAI Growth Engine

**ISTANBUL Ignited by Slush'D — Manus "10× Your Brand" hackathon · 12 Ekim 2026**

ArchAI (bu deponun kökü) imar bilgisinden avan proje, metraj, maliyet ve teklif üreten mimarlık motorumuz.
Hackathon'da onu **kendi kendini pazarlayan bir satış motoruna** çevirdik: Manus satılık arsaları bulur,
ArchAI her arsayı projelendirir, fal görselleri ve tanıtım filmini üretir, Manus müteahhide ve arsa sahibine
kampanyayı hazırlar.

> **Zaman çizelgesi (commit geçmişinde görülebilir):** 11 Ekim akşamı (23:17–00:03) hazırlık — notlar ve MCP katmanının
> ilk hâli (fizibilite, kârlılık, kat karşılığı araçları). 12 Ekim'de (09:24'ten itibaren) geri kalan her şey: Apify
> entegrasyonu, Growth Console, Manus API, 3D görüntüleyici, fal render/film hattı, demo ve teslim videoları.
> `git log --since=2026-10-11 --oneline` ya da GitHub'da [commit listesi](https://github.com/wpu-research/archai-growth-engine/commits/main).
> ArchAI motoru mevcut üründür; bugün ona yapılan değişiklikler aynı daldaki ArchAI commit'leridir.

## Akış

```
Manus (orkestrasyon, MCP connector'ları, API)
  ├─ Apify  clearpath/sahibinden-real-estate → 40 arsa + 20 sıfır daire ilanı (telefon/satıcı verisi alınmaz)
  ├─ ArchAI MCP (server.py, Cloudflare Tunnel + Bearer token)
  │    arsa_fizibilite · hizli_fizibilite · bolge_m2_fiyati · karlilik · kat_karsiligi
  │    render_cephe · tanitim_videosu (fal) · proje_ozet
  ├─ fal    FLUX Kontext (fotogerçekçi cephe/iç mekân) · Kling 2.1 (tanıtım filmi)
  └─ çıktı  arsa başına kampanya sayfası, WhatsApp taslakları (müteahhit + arsa sahibi), sosyal medya gönderileri
```

Kartal sonucu: 40 ilan → 31 elendi → 9 aday → 8 uygun proje. Sekizinin de **satın alma** senaryosu zararda;
ArchAI doğru modeli (**kat karşılığı**) ve paylaşımı hesapladı. Arsa başına süre: 3–5 gün → dakikalar.

## Dosyalar

| Dosya | Ne yapar |
|---|---|
| `server.py` | ArchAI'yi Manus'a açan uzak MCP sunucusu. Araçlar, imzalı dosya linkleri (`/f`), cephe kırpma (`/g`), salt-okunur imzalı 3D görüntüleyici (`/v/<proje>`), fal render/video. ArchAI yalnız `127.0.0.1`'de kalır. |
| `console.py`, `console.html` | **Growth Console**: Manus API ile görev başlatır, canlı akışı ve kampanya kartlarını gösterir (yalnız yerel). |
| `demo.html`, `scripts/demo_hazirla.py` | Sunum demosu: gerçek çalışmanın verisiyle (ilanlar, projeler, render, film) internetsiz oynatılan akış, işlem raporu, sosyal medya önizlemeleri. |
| `scripts/film.py` | ArchAI 3D modelinden kareler → fal Kontext → Kling → ~38 sn tanıtım filmi (dış cephe → salon → yatak odası → drone). |
| `scripts/sunum.py`, `kayit4k.py`, `altyazi.py` | Teslim videoları: GPU'lu 4K ekran kaydı, TR seslendirme (ElevenLabs), TR/EN altyazı, müzik. |
| `prompts/` | Manus talimatı (test edilmiş Apify girdileri, eleme kuralları, kampanya adımları). |
| `teslim/` | Sunum metni, TR/EN açıklama, ekran görüntüleri. |

## Çalıştırma

```bash
cp .env.example .env          # ARCHAI_MCP_TOKEN (≥24 karakter), FAL_KEY, APIFY_TOKEN, MANUS_API_KEY
uv sync
./baslat.sh                   # ArchAI (127.0.0.1:8000) + MCP (127.0.0.1:8765) + Cloudflare tüneli
                              # çıktıdaki URL + Bearer token → Manus › Connectors › Custom MCP (HTTP)
uv run python scripts/test_client.py <tünel-url>   # uçtan uca test
```

- Konsol: `http://127.0.0.1:8765/console` · Demo: `http://127.0.0.1:8765/demo` (önce `scripts/demo_hazirla.py`)
- Durdurma: `./durdur.sh`

## Güvenlik

- ArchAI tünele açılmaz; yalnız bu ince katman açılır. `/mcp` Bearer token ister.
- Dosya ve 3D linkleri HMAC imzalıdır; 3D görüntüleyici dışarıdan salt-okunurdur (yazma 403), yalnız yerelde düzenlenebilir.
- Konsol ve demo tünelden açılmaz (Manus API anahtarı kredi harcatır).
- Rakamlar avan / ön fizibilitedir; imar ve çekme mesafeleri belediyeden teyit edilmelidir.

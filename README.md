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

## Sınırlar — bilinmesi gerekenler

- Üretilen plan **şematik ön tasarımdır** (avan seviyesi); ruhsat projesi değildir, mimar kontrolü ve imzası gerekir.
  Emsal hesabı yaklaşıktır (emsal dışı alanlar ayrıştırılmıyor). Parsel şimdilik dikdörtgen.
- Kat planı kural tabanlı: kat başına 1–2 daire, tek çekirdek; ısıtma, statik, tesisat projesi üretilmez.
- Birim fiyatlar örnektir. Mekanik/elektrik tesisatı m² başına götürü.
- DXF içe aktarma katman kurallarına dayanır; DWG önce DXF'e çevrilmelidir. Eğik/eğrisel duvarlar yaklaşık.
- Köprü localhost'ta auth'suz `exec_python` çalıştırır; web uygulamasında kimlik doğrulama yok — yalnız yerel kullanım.
- `references/villa_ref.png` üçüncü taraf içeriğidir; repo paylaşılmadan çıkarılmalı.

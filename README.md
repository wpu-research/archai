# ArchAI — prototip

LLM ajanı → Blender'da mimari model → kamera yolu → **colormap** (malzeme segmentasyon) videosu →
AI video modeli (Higgsfield / Seedance / Kling). Instagram'daki "GPT-6 Astra + Revit/3ds Max + Higgsfield"
iş akışının açık, kendi kontrolümüzdeki versiyonu.

```
ajan (Claude Code / MCP istemcisi)
  └─ mcp_server/server.py          MCP araçları (stdio)
       └─ TCP 127.0.0.1:9876
            └─ blender_addon/archai_bridge.py   Blender içinde (headless veya GUI)
```

## Kurulum

- Blender 4.5 LTS: `~/Applications/blender-4.5.14-linux-x64/` (başka yer için `ARCHAI_BLENDER`)
- `uv sync`
- Claude Code bu klasörde açılınca `.mcp.json`'daki `archai-blender` sunucusunu onayla.

Köprü ayakta değilse ilk araç çağrısında headless Blender otomatik başlar.
Modeli canlı izlemek için GUI'de: Blender → Edit → Preferences → Add-ons → Install from Disk →
`blender_addon/archai_bridge.py` (headless süreci önce `shutdown_blender` ile kapat, port aynı).

## Smoke test

```
uv run python scripts/demo_villa.py          # 2 kare: colormap + preview
uv run python scripts/demo_villa.py --full   # + 96 kare colormap.mp4 + video paketi
```

Çıktılar `out/` altında; video paketi `out/jobs/<ad>/` (colormap.mp4, ilk kare, prompt.txt, job.json).

## Araçlar

| Araç | İş |
|---|---|
| `build` | duvar (+pencere/kapı açıklıkları), döşeme/çatı/havuz poligonu, kutu, kolon, ağaç, merdiven |
| `exec_python` | serbest bpy — yeni objeyi `tag_object(obj, "wall")` ile etiketle |
| `scene_info` | obje/tag özeti, sınır kutusu, palet |
| `camera_path` | orbit / flythrough (Catmull-Rom) / dolly |
| `render` | `colormap` (Workbench, düz renk, AA/dither kapalı), `preview` (EEVEE), `preview_cycles` |
| `prepare_video_job` | renk→malzeme lejantlı prompt + kontrol videosu paketi |

Her obje bir semantik **tag** taşır (wall, glass, wood, water…). Colormap'te tag'in paletteki düz
rengi, preview'da kaba PBR malzemesi kullanılır.

## Bilinen sınırlar

- Video modeli adımı henüz **elle**: paket hazır, API entegrasyonu yok (sağlayıcı seçilmedi).
- Köprü localhost'ta auth'suz `exec_python` çalıştırır — yalnız yerel geliştirme için.
- Eğri/organik geometri `exec_python` ile yapılmalı; `build` kutu tabanlı.

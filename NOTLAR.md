# Hackaton_ArchAI — Manus "10X Your Brand" (12 Ekim 2026)

## Etkinlik
- ISTANBUL Ignited by Slush'D — Day 0 (12 Ekim): Startup Day & Hackathon. Ana etkinlik 13–14 Ekim, Haliç.
- 08:30 orada ol · 09:00 check-in kapanır · 09:30 hacking · 12:30 öğle.
- Toplu taşıma (otopark yok, Dotshub vale ~850 TL).
- Krediler check-in sonrası: Manus, Apify, fal.ai. Manus ve FAL etkinliğin teknoloji partneri.
- **Yer: DotsHub — Yıldız, Çırağan Cd. No:44, Beşiktaş** (sunum odaları DotsHub + Feriye binaları). Etkinlik: https://luma.com/6rsu5afk
- 15:00 teslim kilitlenir → geliştirme süresi ~5,5 saat.
- Ön eleme: 2 dk sunum+demo, 1 dk soru (jüri başına 7–8 takım, 1 finalist). Final (ilk 6): 3 dk + 1 dk soru.
- Kriterler (her biri %20, 1–5 puan): sorun ve değer (öncesi/sonrası) · hackathon sırasında yapılan iş + çalışan demo · Manus ve araç koordinasyonu · yarın yayına alınabilirlik · sunum.
- Ödüller: Manus Pro 3/2/1 ay. Herkese 50 $ fal.ai kredisi.
- Önceden yazılmış kod kuralı yazılı değil → check-in'de sor. Kriter "hackathon sırasında yapılan"ı puanlıyor: ArchAI = mevcut marka, gün içinde yapılan = pazarlama ve satış iş akışı.
- İletişim: info@istanbulignitedbyslushd.com

## Fikir
Arsa ilanından 10 dakikada müteahhit fizibilite paketi.
Apify (arsa ilanları) → ArchAI hızlı teklif (plan, metraj, maliyet, teklif) → fal.ai (colormap'ten render/video) → Manus (filtrele, paketle, kişisel mesaj).

## Bağımlılık
- Motor: `~/Desktop/Urunler/ArchAI` (FastAPI, `uv run uvicorn webapp.app:app --port 8000`).
- Bu klasörde yalnız hackathon katmanı durur; ArchAI kodu kopyalanmaz.

## Riskler
- ArchAI ağa açılırsa kimliksiz + XSS (konsey raporu P0) → token şart.
- Teklif rakamları "avan / ön fizibilite" diye sunulacak (dış duvar şişmesi %7–10, taşıyıcı sistem kalemi yok).

## Manus bağlantıları (Ayarlar → Connectors → Custom MCP → Direct configuration, transport HTTP)
| Ad | URL | Header |
|---|---|---|
| Apify | `https://mcp.apify.com` | Apify girişi / token |
| fal | `https://mcp.fal.ai/mcp` | `Authorization: Bearer <FAL_KEY>` (OAuth için `https://mcp.fal.ai/mcp-relay`) |
| ArchAI | bu klasördeki MCP + Cloudflare Tunnel (yazılacak) | `Authorization: Bearer <token>` |

- ArchAI'nin mevcut `mcp_server/server.py`'si (Blender, `exec_python` içeriyor) ASLA dışarı açılmayacak.
- Bilgi: 10.000 Manus kredisi + fal ve Apify kredileri check-in sonrası.

# Hackaton_ArchAI — Manus "10X Your Brand" (12 Ekim 2026)

## Etkinlik
- ISTANBUL Ignited by Slush'D — Day 0 (12 Ekim): Startup Day & Hackathon. Ana etkinlik 13–14 Ekim, Haliç.
- 08:30 orada ol · 09:00 check-in kapanır · 09:30 hacking · 12:30 öğle.
- Toplu taşıma (otopark yok, Dotshub vale ~850 TL).
- Krediler check-in sonrası: Manus, Apify, fal.ai. Manus ve FAL etkinliğin teknoloji partneri.
- Site jüri, kriter, ödül, sunum süresi ya da önceden yazılmış kod kuralı vermiyor → check-in'de sor.
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

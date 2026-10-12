# Hackaton_ArchAI — Manus "10X Your Brand" (12 Ekim 2026)

## Etkinlik
- ISTANBUL Ignited by Slush'D — Day 0 (12 Ekim): Startup Day & Hackathon. Ana etkinlik 13–14 Ekim, Haliç.
- 08:30 orada ol · 09:00 check-in kapanır · 09:30 hacking · 12:30 öğle.
- Toplu taşıma (otopark yok, Dotshub vale ~850 TL).
- Krediler check-in sonrası: Manus, Apify, fal.ai. Manus ve FAL etkinliğin teknoloji partneri.
- **Yer: DotsHub — Yıldız, Çırağan Cd. No:44, Beşiktaş** (sunum odaları DotsHub + Feriye binaları). Etkinlik: https://luma.com/6rsu5afk
- 15:00 teslim kilitlenir → geliştirme süresi ~5,5 saat.
- Ön eleme: 2 dk sunum+demo, 1 dk soru (jüri başına 7–8 takım, 1 finalist). Final (ilk 6): 3 dk + 1 dk soru.
- **Açılış slaytları (12 Ekim):** Brief "10× Your Brand": kampanya / landing / marka sistemi, içerik motoru veya otomatik iş akışı,
  canlı demoda öncesi/sonrası. Konumlandırma: **ArchAI'nin pazarlama ve satış motoru** (pazarlamayı otomatikleştir).
  Jüri: ön eleme 15:15–16:00 (2 dk + 1 dk soru) · final ilk 6, 16:00–16:30 (3 dk + 1 dk) · 16:30 değerlendirme, 16:45 ödüller.
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

## Hazır olan (11 Ekim gecesi)
- `server.py`: ArchAI için uzak MCP. Araçlar: `hizli_fizibilite`, `arsa_fizibilite`, `proje_ozet`.
  Dönen özet: daire sayısı, brüt m², KDV dahil maliyet ve m² fiyatı, imzalı dosya linkleri (teklif, metraj, şartname, pafta PDF),
  `gorunus_png` (antetsiz, kırpılmış cephe → fal görüntüden görüntüye).
- `./baslat.sh`: ArchAI + MCP + Cloudflare hızlı tüneli; Manus'a girilecek URL ve token'ı yazar. `./durdur.sh` kapatır.
- `scripts/test_client.py [URL]`: uçtan uca test. Tünel üzerinden geçti; tokensız istek 401, bozuk imza 404.
- Tünel adresi her başlatmada değişir → Manus'taki connector URL'sini güncelle.

## Yarın (09:30–15:00)
1. 09:30–10:00 Kredileri al. Manus'a Apify, fal ve ArchAI connector'larını ekle, üçünün de araç listesini gördüğünü doğrula.
2. 10:00–11:30 Manus akışı: Apify'dan İstanbul satılık arsa ilanları → en uygun 3–5 ilan → `arsa_fizibilite`
   → fal ile `gorunus_png`'den fotogerçekçi cephe → müteahhit için tek sayfalık fizibilite + kişisel mesaj.
3. 11:30–12:30 Bir ilanla tam çalışan örnek. Firma bilgisini gir (paftalarda şu an "Örnek Yapı İnşaat" yazıyor).
4. 13:00–14:15 Kalite: çıktı sayfası/landing (Manus), ekran kaydı.
5. 14:15–15:00 2 dakikalık sunum + yedek video. 15:00'te teslim kilitlenir.

## Sunum (2 dk)
- 0:00 Sorun: müteahhit bir arsaya bakmak için mimardan avan ve maliyet bekliyor (günler).
- 0:20 ArchAI tek cümle: m²/imar → plan, metraj, maliyet, teklif.
- 0:35 Canlı/kayıt demo: Manus'a "Kartal'da 5 kat imarlı arsaları bul, fizibilite çıkar" → paket.
- 1:30 Öncesi/sonrası: günler → dakikalar; ilan başına maliyet; yarın yayına alınabilir.
- 1:50 Kapanış + "avan / ön fizibilite" notu.

## Teslim (15:00'te kilitlenir)
- Luma'da teslimin ne olduğu ve nereye yapılacağı yazmıyor; check-in sonrası gelecek "hackathon guide"da olacak. Sabah ilk iş oku.
- Hazır tutulacak teslim paketi:
  1. Manus görev paylaşım/replay linki (akışın Manus'ta çalıştığının kanıtı — "Manus kullanımı" kriteri)
  2. Çıktı linki: Manus'un yayınladığı arsa/fizibilite sayfası
  3. 60–90 sn demo videosu (canlı demo bozulursa da bu oynatılır)
  4. Kısa açıklama (TR + EN): sorun, ne yapıldı, öncesi/sonrası, kullanılan araçlar
  5. 2–3 ekran görüntüsü, takım/proje adı
- Teslimi 14:30'da yap, 15:00'i bekleme. 15:00'ten sonra yalnız sunum çalışılır.

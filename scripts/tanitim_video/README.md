# Tanıtım videosu üretim hattı (ÖRNEK / elle ayarlı)

> **Not:** Bu klasör, ArchAI'nin kendi tanıtım videosunu tek bir projeye (sabit kapı koordinatı, sabit yürüyüş anahtarları,
> sabit proje adı) göre elle ayarlayarak üreten ESKİ hattır; olduğu gibi korunur ve çalışmaya devam eder.
> **Herhangi bir projeden tek tıkla müşteri videosu** için genel hat artık `archai/video/` paketindedir
> (`archai/customer_video.py`, arayüzde "Müşteri Videosu" düğmesi, `POST /api/projects/{pid}/video`,
> komut satırı: `python scripts/musteri_videosu.py <proje_id>`). Buradaki betikler o hattın ilk örnekleridir.

ArchAI'nin tanıtım videosunu sıfırdan bir projeden üretir. Çıktılar (mp4, kareler) git'e girmez; `out/promo/` altında oluşur.

- `ARCHAI_PROMO_DIR`: çalışma klasörü (varsayılan `out/promo`)
- `ARCHAI_URL`: çalışan sunucu (varsayılan `http://localhost:8070`)

Gereken: Playwright (Chromium, GPU WebGL için `--use-gl=angle --use-angle=gl`), ffmpeg, LibreOffice (belge görüntüleri), Blender (Cycles).

| Betik | Görev |
|---|---|
| `prepare_hero.py` | Sıfırdan "Tanıtım" projesini oluşturur, `hero_id` yazar |
| `ui_scene.py` | Arayüz sahneleri; sahte imleç zaman çizelgesiyle kayıt |
| `motion.py` | 3D sahneler (intro, orbit, modes, floors, walk, daynight); sanal saatle 24 fps kare kare |
| `cycles_jobs.py` | Cycles still'leri `/api/projects/{id}/real` üzerinden |
| `music.py` | Müzik sentezi (numpy) |
| `compose.py` | Altyazı, geçişler, zaman çizelgesi, ffmpeg kodlama |
| `gpu_test.py` | GPU WebGL denetimi |

Not: SwiftShader ~45 sn/kare, NVIDIA/ANGLE ~0,45 sn/kare.

"""Müşteri videosu — genel giriş noktası.

Herhangi bir projeden (arsa, DXF, resim planı, apartman, villa…) tanıtım videosu üretir. Ayrıntılar `archai/video/`:
facts (veri) → walk (kapı bitişikliğinden yürüyüş yolu) → plan (sahne/altyazı zaman çizelgesi) → capture_worker
(Playwright + GPU WebGL, sanal saat) → compose (kartlar, altyazı, ffmpeg) → mp4.

    from archai.customer_video import generate, VideoSettings
    generate(proje_klasoru, is_klasoru, VideoSettings(profile="short"), "http://127.0.0.1:8000")
"""
from archai.video.pipeline import generate  # noqa: F401
from archai.video.plan import build_plan  # noqa: F401
from archai.video.settings import VideoSettings  # noqa: F401
from archai.video.walk import plan_walk  # noqa: F401

__all__ = ["generate", "build_plan", "plan_walk", "VideoSettings"]

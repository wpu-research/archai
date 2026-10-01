"""Müşteri videosu ayarları (pydantic ile doğrulanır; API gövdesi ve CLI aynı şemayı kullanır)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

PROFILES = ("short", "standard")
RESOLUTIONS = {"720p": (1280, 720), "1080p": (1920, 1080)}


class VideoSettings(BaseModel):
    """Üretim seçenekleri. Bilinmeyen alan reddedilir; tüm alanlar katı tiptir."""
    model_config = ConfigDict(strict=True, extra="forbid")

    profile: Literal["short", "standard"] = "standard"      # short ≈ 30 sn, standard ≈ 60–90 sn
    cycles: bool = False                                     # Blender Cycles still'leri (yavaş; varsayılan kapalı)
    cycles_quality: Literal["fast", "good"] = "fast"        # fast = still (1920 px, 256 örnek), good = HQ (2560 px, 512)
    resolution: Literal["720p", "1080p"] = "1080p"
    music: bool = True
    subtitles: bool = True                                   # Türkçe altyazılar (videoya gömülür; ayrıca .srt yazılır)
    night: bool = True                                       # gün-gece sahnesi
    furnish: bool = True                                     # iç mekân boşsa otomatik döşe (kayıt DEĞİŞMEZ)

    @property
    def size(self):
        return RESOLUTIONS[self.resolution]

    @property
    def short(self):
        return self.profile == "short"

"""Müşteri videosu hattı: proje verisinden sahne planı → Playwright/WebGL çekimi → montaj → mp4.

Saf planlama katmanı (facts, walk, plan) tarayıcı ve ffmpeg gerektirmez; çekim (capture_worker) ve montaj
(compose, pipeline) ağır bağımlılıkları yalnızca çalışırken yükler.
"""

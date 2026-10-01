"""Komut satırından müşteri videosu:  python scripts/musteri_videosu.py <proje_id> [--short] [--720p] [--cycles] [--no-music]

Çalışan bir ArchAI sunucusu gerekir (varsayılan http://127.0.0.1:8000, ARCHAI_URL ile değişir). Çıktı: out/projects/<id>/video/cli-*/
"""
import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from archai.video import pipeline  # noqa: E402
from archai.video.settings import VideoSettings  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pid")
    ap.add_argument("--short", action="store_true")
    ap.add_argument("--720p", dest="p720", action="store_true")
    ap.add_argument("--cycles", action="store_true")
    ap.add_argument("--good", action="store_true", help="Cycles yüksek kalite")
    ap.add_argument("--no-music", action="store_true")
    a = ap.parse_args()
    out = Path(os.environ.get("ARCHAI_OUT") or ROOT / "out")
    pdir = out / "projects" / a.pid
    jd = pdir / "video" / f"cli-{time.strftime('%H%M%S')}"
    jd.mkdir(parents=True)
    st = VideoSettings(profile="short" if a.short else "standard", resolution="720p" if a.p720 else "1080p", cycles=a.cycles,
                       cycles_quality="good" if a.good else "fast", music=not a.no_music)
    res = pipeline.generate(pdir, jd, st, os.environ.get("ARCHAI_URL", "http://127.0.0.1:8000"), out)
    print(jd / res["file"])


if __name__ == "__main__":
    main()

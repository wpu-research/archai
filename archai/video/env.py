"""Sistem bağımlılıklarının denetimi: ffmpeg, Playwright'lı Python, Blender (Cycles için)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

_cache = {}


def _can_import_playwright(py):
    try:
        r = subprocess.run([py, "-c", "import playwright.sync_api"], capture_output=True, timeout=30)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def playwright_python():
    """Playwright içe aktarabilen Python: ARCHAI_VIDEO_PYTHON → bu süreç → PATH'teki python3/python. Yoksa None."""
    if "py" in _cache:
        return _cache["py"]
    cands = [os.environ.get("ARCHAI_VIDEO_PYTHON"), sys.executable]
    for name in ("python3", "python"):         # PATH'teki TÜM adaylar (uv/venv python'u ilkini kapatabilir)
        for d in os.environ.get("PATH", "").split(os.pathsep):
            p = os.path.join(d, name)
            if d and os.path.isfile(p) and os.access(p, os.X_OK):
                cands.append(p)
    found = None
    seen = set()
    for c in (x for x in cands if x):
        key = c
        if key in seen:
            continue
        seen.add(key)
        if _can_import_playwright(c):
            found = c
            break
    _cache["py"] = found
    return found


def blender_path():
    p = os.environ.get("ARCHAI_BLENDER") or str(Path.home() / "Applications/blender-4.5.14-linux-x64/blender")
    return p if Path(p).is_file() else shutil.which("blender")


def check():
    """{ffmpeg, playwright, blender, ok, missing:[...]} — UI ve API bu bilgiyle seçenekleri kapatır."""
    ff = shutil.which("ffmpeg")
    py = playwright_python()
    bl = blender_path()
    missing = []
    if not ff:
        missing.append("ffmpeg")
    if not py:
        missing.append("playwright (pip install playwright && playwright install chromium)")
    return {"ffmpeg": bool(ff), "playwright": bool(py), "blender": bool(bl), "ok": not missing, "missing": missing}


def free_gb(path):
    return shutil.disk_usage(path).free / 1e9

"""Eski biçimli proje klasörlerini (ör. `hizli`, `kadikoy`) geçerli kimlik biçimine taşır.

    uv run python scripts/migrate_projects.py            # neler taşınacağını gösterir
    uv run python scripts/migrate_projects.py --apply    # taşır

Geçerli kimlik: `YYYYMMDD-HHMMSS-<ad>` (webapp.app.PID_RE). Zaman damgası klasörün değişiklik zamanından
gelir; ad, eski ada göre temizlenir. Klasör içindeki *.json dosyalarında geçen eski mutlak yollar da
yeni yolla değiştirilir. `ARCHAI_OUT` ortam değişkeni çıktı kökünü belirler (varsayılan `out/`).
`project.json`/`elements.json` içermeyen klasörler atlanır.
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PID_RE = re.compile(r"\d{8}-\d{6}-[a-z0-9-]{1,60}")
TR = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.translate(TR).lower()).strip("-")
    return s[:60] or "proje"


def plan(projects):
    taken = {p.name for p in projects.iterdir() if p.is_dir()}
    out = []
    for d in sorted(p for p in projects.iterdir() if p.is_dir() and not PID_RE.fullmatch(p.name)):
        if not ((d / "project.json").exists() or (d / "elements.json").exists()):
            out.append((d, None, "atlandı: project.json/elements.json yok"))
            continue
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(d.stat().st_mtime))
        new, n = f"{stamp}-{slug(d.name)}", 1
        while new in taken:
            n += 1
            new = f"{stamp}-{slug(d.name)[:56]}-{n}"
        taken.add(new)
        out.append((d, projects / new, "taşınacak"))
    return out


def rewrite_paths(d_new, old_abs, new_abs):
    n = 0
    for f in d_new.rglob("*.json"):
        try:
            t = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if old_abs in t:
            f.write_text(t.replace(old_abs, new_abs), encoding="utf-8")
            n += 1
    return n


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="taşımayı gerçekten yap (yoksa yalnız listeler)")
    ap.add_argument("--out", help="çıktı kökü (varsayılan ARCHAI_OUT ya da ./out)")
    a = ap.parse_args(argv)
    out = Path(a.out or os.environ.get("ARCHAI_OUT") or ROOT / "out")
    projects = out / "projects"
    if not projects.is_dir():
        print(f"{projects} yok", file=sys.stderr)
        return 1
    items = plan(projects)
    if not items:
        print("taşınacak eski klasör yok")
        return 0
    for old, new, why in items:
        print(f"{old.name:32s} → {new.name if new else '—':48s} {why}")
        if a.apply and new:
            old_abs, new_abs = str(old.resolve()), str((projects / new.name).resolve())
            old.rename(new)
            changed = rewrite_paths(new, old_abs, new_abs)
            print(f"    taşındı; {changed} json dosyasında yol güncellendi")
    if not a.apply:
        print("\n(önizleme — taşımak için --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

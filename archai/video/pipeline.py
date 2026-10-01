"""Müşteri videosu hattı (tek iş): proje klasörü + ayarlar → mp4.

CLI (kuyruk bunu alt süreç olarak başlatır; iptal/zaman aşımında süreç grubu öldürülür):
    python -m archai.video.pipeline --project-dir P --job-dir J --settings '{...}' --base http://127.0.0.1:8000

stdout protokolü: `ARCHAI_VIDEO_PROGRESS <aşama> <yüzde> <mesaj>` · `ARCHAI_VIDEO_WARN <mesaj>` · `ARCHAI_VIDEO_RESULT <json>`.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import zlib
from pathlib import Path

from . import cards, compose, env, facts as F, music, plan as P, walk as W
from .settings import VideoSettings

MIN_FREE_GB = float(os.environ.get("ARCHAI_VIDEO_MIN_FREE_GB", 3))
STAGES = {  # aşama adı → (başlangıç %, bitiş %)
    "plan": (0, 4), "hazirlik": (4, 10), "cekim": (10, 66), "cycles": (46, 72), "muzik": (72, 74), "montaj": (74, 97), "bitis": (97, 100),
}
_child = {"p": None}


def emit(stage, pct, msg=""):
    print(f"ARCHAI_VIDEO_PROGRESS {stage} {pct:.1f} {msg}", flush=True)


def warn(msg):
    print(f"ARCHAI_VIDEO_WARN {msg}", flush=True)


def _on_term(signum, frame):
    p = _child["p"]
    if p and p.poll() is None:
        p.kill()
    sys.exit(143)


def run_worker(py, mode, manifest, log, on_line=None):
    """capture_worker alt sürecini çalıştırır; satırlar log dosyasına ve on_line'a gider. Dönen: çıkış kodu."""
    worker = Path(__file__).with_name("capture_worker.py")
    proc = subprocess.Popen([py, str(worker), mode, str(manifest)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    _child["p"] = proc
    try:
        for line in proc.stdout:
            log.write(line)
            log.flush()
            if on_line:
                on_line(line.rstrip("\n"))
        return proc.wait()
    finally:
        if proc.poll() is None:
            proc.kill()
        _child["p"] = None


def stage_pct(stage, frac):
    a, b = STAGES[stage]
    return a + (b - a) * max(0.0, min(1.0, frac))


def generate(pdir, jdir, st: VideoSettings, base_url, out_root=None):
    pdir, jdir = Path(pdir), Path(jdir)
    work = jdir / "work"
    work.mkdir(parents=True, exist_ok=True)
    log = open(jdir / "pipeline.log", "a", encoding="utf-8")
    warnings = []

    def W_(msg):
        warnings.append(msg)
        warn(msg)

    chk = env.check()
    if not chk["ok"]:
        raise RuntimeError("eksik sistem bağımlılığı: " + ", ".join(chk["missing"]))
    py = env.playwright_python()
    if st.cycles and not chk["blender"]:
        W_("Blender bulunamadı: Cycles kareleri atlandı")
        st = st.model_copy(update={"cycles": False})
    if env.free_gb(jdir) < MIN_FREE_GB:
        raise RuntimeError(f"disk alanı yetersiz (en az {MIN_FREE_GB:g} GB boş yer gerekir)")

    emit("plan", 0, "Proje okunuyor")
    f = F.load_facts(pdir, out_root)
    if not f.has_building and not f.site:
        raise RuntimeError("projede gösterilecek geometri yok")
    manifest_base = {"pid": f.pid, "name": f.name, "base": base_url, "fps": P.FPS, "workdir": str(work), "size": list(st.size),
                     "floors": f.floors}

    # ---- hazırlık: iç mekân boşsa tarayıcıda otomatik döşe (proje kaydı değişmez)
    interior = None
    if st.furnish and f.has_building and f.floors and not (f.interior.get("objects")):
        emit("hazirlik", STAGES["hazirlik"][0], "İç mekân döşeniyor")
        mp = work / "prep.json"
        mp.write_text(json.dumps({**manifest_base, "scenes": []}), encoding="utf-8")
        code = run_worker(py, "prep", mp, log, on_line=lambda ln: ln.startswith("WARN ") and W_(ln[5:]))
        auto = work / "interior_auto.json"
        if code == 0 and auto.is_file():
            interior = F.read_json(auto, {})
            f.interior = interior or {}
        else:
            W_("iç mekân otomatik döşenemedi: boş odalarla devam ediliyor")
    emit("hazirlik", STAGES["hazirlik"][1], "")

    # ---- yürüyüş + plan
    wk = None
    if f.has_building and f.floors:
        wk = W.plan_walk(f, budget_s=P.D["walk"][0 if st.short else 1] - 3.0)
        if wk is None:
            W_("yürüyüş yolu bulunamadı (kapı/oda geometrisi yetersiz): gezinti sahnesi atlandı")
        elif wk.notes:
            for n in wk.notes:
                W_(n)
    plan = P.build_plan(f, st, wk)
    for w_ in plan.warnings:
        warnings.append(w_)
    manifest = P.capture_manifest(plan, f, st, wk, f.pid, base_url, work)
    mp = work / "capture.json"
    mp.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    emit("plan", STAGES["plan"][1], f"{len(plan.scenes)} sahne, {plan.total:.0f} sn")

    # ---- çekim
    live = bool(manifest["scenes"])
    renderer = None
    cap_info = {}
    if live:
        cy_on = bool(manifest["cycles"]["shots"])
        wcap = (10, 46) if cy_on else (10, 70)

        def on_line(ln):
            nonlocal renderer
            if ln.startswith("PROGRESS capture"):
                fr = float(ln.split()[2])
                emit("cekim", wcap[0] + (wcap[1] - wcap[0]) * fr, "Sahneler çekiliyor")
            elif ln.startswith("PROGRESS cycles"):
                parts = ln.split(maxsplit=3)
                emit("cycles", 46 + 26 * float(parts[2]), parts[3] if len(parts) > 3 else "Cycles render")
            elif ln.startswith("RENDERER"):
                renderer = ln[9:]
            elif ln.startswith("WARN"):
                W_(ln[5:])
        emit("cekim", 10, "Tarayıcı başlatılıyor")
        code = run_worker(py, "capture", mp, log, on_line)
        ci = work / "capture_info.json"
        if code != 0 or not ci.is_file():
            raise RuntimeError("sahne çekimi başarısız (alt süreç hata verdi); ayrıntı için pipeline.log")
        cap_info = F.read_json(ci, {})
        failed = [k for k, v in (cap_info.get("scenes") or {}).items() if not v.get("ok")]
        cyc = cap_info.get("cycles") or {}
        cycles_ok = [k for k, ok in cyc.items() if ok] if st.cycles else None
        if st.cycles and not cycles_ok:
            W_("Cycles kareleri alınamadı: fotogerçekçi sahneler atlandı")
        if failed or st.cycles:
            plan = P.build_plan(f, st, wk, cycles_ok=cycles_ok or [], skip=failed)
        if cap_info.get("soft"):
            W_("GPU bulunamadı: yazılım çizimi kullanıldı, hareket akıcılığı düşük (düşük kare sıklığı)")
        if not any(v.get("ok") for v in (cap_info.get("scenes") or {}).values()):
            raise RuntimeError("hiçbir 3B sahne çekilemedi (WebGL/tarayıcı sorunu); pipeline.log'a bakın")
    emit("cekim", STAGES["cekim"][1], "")

    # ---- müzik
    audio = None
    if st.music:
        emit("muzik", STAGES["muzik"][0], "Müzik sentezleniyor")
        audio = music.write_wav(work / "muzik.wav", plan.total + 0.5, seed=zlib.crc32(f.pid.encode()))
    # ---- montaj
    emit("montaj", STAGES["montaj"][0], "Kareler birleştiriliyor")
    card_data = cards.build_card_data(f)
    out_mp4 = jdir / "musteri_videosu.mp4"
    plan_d = P.plan_to_dict(plan)
    (jdir / "plan.json").write_text(json.dumps(plan_d, ensure_ascii=False), encoding="utf-8")
    compose.encode(plan, plan_d, card_data, work, out_mp4, cap_info, st.subtitles, audio,
                   progress=lambda fr: emit("montaj", stage_pct("montaj", fr), "Video kodlanıyor"))
    emit("bitis", STAGES["bitis"][0], "Kapak ve altyazı")
    comp = compose.Compositor(plan, card_data, work, cap_info, st.subtitles)
    comp.cover().save(jdir / "kapak.jpg", quality=92)
    compose.write_srt(plan, jdir / "altyazi.srt")
    res = {"file": out_mp4.name, "cover": "kapak.jpg", "srt": "altyazi.srt", "duration": plan.total, "frames": plan.total_frames,
           "bytes": out_mp4.stat().st_size, "size": list(st.size), "renderer": renderer, "soft": bool(cap_info.get("soft")),
           "warnings": warnings, "scenes": [{"id": s.id, "kind": s.kind, "start": s.start, "dur": s.dur} for s in plan.scenes],
           "walk": ({"rooms": wk.visited, "duration": round(wk.duration, 2)} if wk else None)}
    (jdir / "result.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    if not os.environ.get("ARCHAI_VIDEO_KEEP"):
        shutil.rmtree(work, ignore_errors=True)
    log.close()
    print("ARCHAI_VIDEO_RESULT " + json.dumps(res, ensure_ascii=False), flush=True)
    emit("bitis", 100, "Hazır")
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-dir", required=True)
    ap.add_argument("--job-dir", required=True)
    ap.add_argument("--settings", default="{}")
    ap.add_argument("--base", required=True)
    ap.add_argument("--out-root")
    a = ap.parse_args(argv)
    signal.signal(signal.SIGTERM, _on_term)
    st = VideoSettings.model_validate_json(a.settings)
    try:
        generate(a.project_dir, a.job_dir, st, a.base, a.out_root)
    except SystemExit:
        raise
    except Exception as ex:  # noqa: BLE001
        print(f"ARCHAI_VIDEO_ERROR {type(ex).__name__}: {ex}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

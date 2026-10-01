"""Müşteri videosu iş kuyruğu (render kuyruğu deseni): sınırlı eşzamanlılık, zaman aşımı, ilerleme, iptal,
kalıcı durum (status.json), alt süreç grubu temizliği ve disk sınırı.

Web katmanından bağımsızdır; `runner` enjekte edilerek testlerde ağır hat taklit edilir.
"""
from __future__ import annotations

import json
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from . import env
from .settings import VideoSettings

JID_RE = re.compile(r"vid-\d{6}-[0-9a-f]{6}")
FILES_OK = {"musteri_videosu.mp4": "video/mp4", "kapak.jpg": "image/jpeg", "altyazi.srt": "application/x-subrip"}
ACTIVE = ("queued", "running")
ROOT = Path(__file__).resolve().parents[2]


class JobError(Exception):
    """API'ye (kod, mesaj) olarak çevrilir."""

    def __init__(self, code, msg, extra=None):
        super().__init__(msg)
        self.code, self.msg, self.extra = code, msg, extra or {}


def _cfg():
    g = os.environ.get
    return {
        "max_concurrent": int(g("ARCHAI_VIDEO_CONCURRENCY", 1)),
        "max_queued": int(g("ARCHAI_VIDEO_MAX_QUEUE", 4)),
        "timeout": float(g("ARCHAI_VIDEO_TIMEOUT", 3600)),
        "keep_per_project": int(g("ARCHAI_VIDEO_KEEP_PER_PROJECT", 3)),
        "max_total_gb": float(g("ARCHAI_VIDEO_MAX_GB", 8)),
        "min_free_gb": float(g("ARCHAI_VIDEO_MIN_FREE_GB", 3)),
    }


def dir_size(p):
    n = 0
    for r, _, fs in os.walk(p):
        for f in fs:
            try:
                n += os.path.getsize(os.path.join(r, f))
            except OSError:
                pass
    return n


class VideoJobs:
    def __init__(self, projects_root, runner=None, max_concurrent=None, max_queued=None, timeout=None,
                 keep_per_project=None, max_total_gb=None, min_free_gb=None, check_env=True):
        c = _cfg()
        self.root = Path(projects_root)
        self.max_concurrent = c["max_concurrent"] if max_concurrent is None else max_concurrent
        self.max_queued = c["max_queued"] if max_queued is None else max_queued
        self.timeout = c["timeout"] if timeout is None else timeout
        self.keep = c["keep_per_project"] if keep_per_project is None else keep_per_project
        self.max_total_gb = c["max_total_gb"] if max_total_gb is None else max_total_gb
        self.min_free_gb = c["min_free_gb"] if min_free_gb is None else min_free_gb
        self.check_env = check_env
        self.runner = runner or self._run_subprocess
        self.jobs: dict[str, dict] = {}
        self.q: "queue.Queue[str]" = queue.Queue()
        self.lock = threading.RLock()
        self.procs: dict[str, subprocess.Popen] = {}
        self.cancel_flags: set[str] = set()
        self._recover()
        self.threads = [threading.Thread(target=self._worker, daemon=True, name=f"video-{i}") for i in range(self.max_concurrent)]
        for t in self.threads:
            t.start()

    # ------------------------------------------------------------------ kalıcılık
    def _save(self, j):
        try:
            (Path(j["dir"]) / "status.json").write_text(json.dumps(j, ensure_ascii=False, default=str))
        except OSError:
            pass

    def _recover(self):
        for st in self.root.glob("*/video/*/status.json"):
            try:
                j = json.loads(st.read_text())
                if j.get("status") in ACTIVE:
                    j.update(status="error", error="sunucu yeniden başladı", message="")
                    st.write_text(json.dumps(j, ensure_ascii=False, default=str))
                    shutil.rmtree(st.parent / "work", ignore_errors=True)
            except (OSError, ValueError, AttributeError):
                continue

    def _prune_mem(self):
        done = [k for k, v in self.jobs.items() if v["status"] not in ACTIVE]
        while len(self.jobs) > 200 and done:
            self.jobs.pop(done.pop(0), None)

    # ------------------------------------------------------------------ API
    def submit(self, pid, settings: VideoSettings, base_url):
        pdir = self.root / pid
        with self.lock:
            for j in self.jobs.values():
                if j["pid"] == pid and j["status"] in ACTIVE:
                    raise JobError(409, "bu proje için video zaten üretiliyor", {"job": self.public(j)})
            waiting = sum(1 for j in self.jobs.values() if j["status"] == "queued")
            if waiting >= self.max_queued:
                raise JobError(429, f"video kuyruğu dolu (en fazla {self.max_queued} bekleyen iş); biraz sonra tekrar deneyin")
            if self.check_env:
                chk = env.check()
                if not chk["ok"]:
                    raise JobError(503, "video için eksik sistem bağımlılığı: " + ", ".join(chk["missing"]))
                if settings.cycles and not chk["blender"]:
                    raise JobError(422, "Cycles için Blender bulunamadı (ARCHAI_BLENDER)")
            try:
                free = shutil.disk_usage(pdir).free / 1e9
            except OSError:
                free = 1e9
            if free < self.min_free_gb:
                raise JobError(507, f"disk alanı yetersiz (en az {self.min_free_gb:g} GB boş yer gerekir, {free:.1f} GB var)")
            jid = f"vid-{datetime.now():%H%M%S}-{uuid.uuid4().hex[:6]}"
            jd = pdir / "video" / jid
            jd.mkdir(parents=True)
            j = {"id": jid, "pid": pid, "dir": str(jd), "status": "queued", "stage": "kuyruk", "percent": 0.0, "message": "sırada",
                 "settings": settings.model_dump(), "base": base_url, "created": time.time(), "warnings": [], "error": None,
                 "queued_ahead": self.q.qsize() + sum(1 for x in self.jobs.values() if x["status"] == "running")}
            self.jobs[jid] = j
            self._save(j)
            self._prune_mem()
            self.q.put(jid)
            return self.public(j)

    def get(self, jid):
        if not JID_RE.fullmatch(jid or ""):
            return None
        with self.lock:
            j = self.jobs.get(jid)
            if j:
                return self.public(j)
        for st in self.root.glob(f"*/video/{jid}/status.json"):
            try:
                return self.public(json.loads(st.read_text()))
            except (OSError, ValueError):
                raise JobError(422, "iş kaydı bozuk")
        return None

    def job_dir(self, jid):
        """Diskteki iş klasörü (kimlik doğrulanır); yoksa None."""
        if not JID_RE.fullmatch(jid or ""):
            return None
        for st in self.root.glob(f"*/video/{jid}/status.json"):
            return st.parent
        return None

    def list_done(self, pid):
        out = []
        for st in sorted((self.root / pid / "video").glob("*/status.json"), reverse=True):
            try:
                j = json.loads(st.read_text())
                if j.get("status") == "done":
                    out.append(self.public(j))
            except (OSError, ValueError, AttributeError):
                continue
        return out

    def cancel(self, jid):
        with self.lock:
            j = self.jobs.get(jid)
            if j is None:
                return None
            if j["status"] == "queued":
                j.update(status="cancelled", message="iptal edildi")
                self._save(j)
            elif j["status"] == "running":
                self.cancel_flags.add(jid)
                self._kill(jid)
            return self.public(j)

    @staticmethod
    def public(j):
        base = f"/api/video-jobs/{j['id']}"
        out = {k: v for k, v in j.items() if k not in ("dir", "base")}
        if j.get("status") == "done":
            out.update(download=f"{base}/download", video=f"{base}/file/musteri_videosu.mp4",
                       cover=f"{base}/file/kapak.jpg", srt=f"{base}/file/altyazi.srt")
        return out

    # ------------------------------------------------------------------ yürütme
    def _kill(self, jid):
        p = self.procs.get(jid)
        if p and p.poll() is None:
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                pass

            def hard(p=p):
                time.sleep(4)
                if p.poll() is None:
                    try:
                        os.killpg(os.getpgid(p.pid), signal.SIGKILL)
                    except (ProcessLookupError, PermissionError, OSError):
                        pass
            threading.Thread(target=hard, daemon=True).start()

    def update(self, j, **kw):
        """İlerleme güncellemesi (yüzde yalnız ileri gider, durum dosyası seyrek yazılır)."""
        with self.lock:
            if "percent" in kw:
                kw["percent"] = round(max(j.get("percent", 0.0), min(100.0, float(kw["percent"]))), 1)
            changed = any(j.get(k) != v for k, v in kw.items())
            j.update(kw)
            now = time.time()
            if changed and (now - j.get("_saved", 0) > 1.5 or "status" in kw):
                j["_saved"] = now
                self._save(j)

    def _worker(self):
        while True:
            jid = self.q.get()
            with self.lock:
                j = self.jobs.get(jid)
                if j is None or j["status"] != "queued":
                    continue
                j.update(status="running", started=time.time(), stage="plan", message="başlıyor")
                self._save(j)
            try:
                self.runner(j, self)
                with self.lock:
                    if jid in self.cancel_flags:
                        j.update(status="cancelled", message="iptal edildi")
                    elif j["status"] == "running":
                        j["status"] = "done" if (Path(j["dir"]) / "musteri_videosu.mp4").is_file() else "error"
                        if j["status"] == "error" and not j.get("error"):
                            j["error"] = "video dosyası oluşmadı"
                        if j["status"] == "done":
                            j.update(percent=100.0, message="hazır")
            except Exception as ex:  # noqa: BLE001 — iş durumu kullanıcıya dönmeli
                with self.lock:
                    j.update(status="cancelled" if jid in self.cancel_flags else "error")
                    if j["status"] == "error":
                        j["error"] = str(ex)[:400]
            finally:
                with self.lock:
                    j["elapsed"] = round(time.time() - j.get("started", time.time()), 1)
                    self.cancel_flags.discard(jid)
                    self.procs.pop(jid, None)
                    j.pop("_saved", None)
                    self._save(j)
                shutil.rmtree(Path(j["dir"]) / "work", ignore_errors=True)
                self.prune(j["pid"])

    @staticmethod
    def _cmd(j):
        return [sys.executable, "-m", "archai.video.pipeline", "--project-dir", str(Path(j["dir"]).parents[1]),
                "--job-dir", j["dir"], "--settings", json.dumps(j["settings"]), "--base", j["base"]]

    def _run_subprocess(self, j, jobs):
        """Hattı ayrı süreç grubunda çalıştırır; stdout protokolünü ilerlemeye çevirir."""
        cmd = self._cmd(j)
        logf = open(Path(j["dir"]) / "runner.log", "w", encoding="utf-8")
        proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
                                start_new_session=True, env={**os.environ, "PYTHONUNBUFFERED": "1"})
        self.procs[j["id"]] = proc
        timer = threading.Timer(self.timeout, lambda: (j.__setitem__("timed_out", True), self._kill(j["id"])))
        timer.daemon = True
        timer.start()
        err = None
        try:
            for line in proc.stdout:
                logf.write(line)
                line = line.rstrip("\n")
                if line.startswith("ARCHAI_VIDEO_PROGRESS "):
                    parts = line.split(maxsplit=3)
                    try:
                        self.update(j, stage=parts[1], percent=float(parts[2]), message=parts[3] if len(parts) > 3 else "")
                    except (ValueError, IndexError):
                        pass
                elif line.startswith("ARCHAI_VIDEO_WARN "):
                    with self.lock:
                        j["warnings"] = (j["warnings"] + [line[18:]])[-10:]
                elif line.startswith("ARCHAI_VIDEO_ERROR "):
                    err = line[19:]
                elif line.startswith("ARCHAI_VIDEO_RESULT "):
                    try:
                        j["result"] = json.loads(line[20:])
                    except ValueError:
                        pass
            code = proc.wait()
        finally:
            timer.cancel()
            if proc.poll() is None:
                proc.kill()
            try:                                   # artakalan torunları (Chromium vb.) da temizle
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass
            logf.close()
        if j.pop("timed_out", False):
            raise RuntimeError(f"zaman aşımı: video {int(self.timeout)} sn içinde bitmedi")
        if j["id"] in self.cancel_flags:
            return
        if code != 0:
            raise RuntimeError(err or f"video hattı çıkış kodu {code}; log: runner.log")

    # ------------------------------------------------------------------ disk sınırı
    def prune(self, pid):
        """Projede son N bitmiş videoyu tut; toplam boyut sınırı aşılırsa en eskileri sil."""
        try:
            done = sorted([p.parent for p in (self.root / pid / "video").glob("*/status.json") if self._is_finished(p)],
                          key=lambda d: d.stat().st_mtime, reverse=True)
            for d in done[self.keep:]:
                shutil.rmtree(d, ignore_errors=True)
            allv = sorted([p.parent for p in self.root.glob("*/video/*/status.json") if self._is_finished(p)], key=lambda d: d.stat().st_mtime)
            total = sum(dir_size(d) for d in allv)
            while allv and total > self.max_total_gb * 1e9:
                d = allv.pop(0)
                total -= dir_size(d)
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass

    @staticmethod
    def _is_finished(status_path):
        try:
            return json.loads(status_path.read_text()).get("status") in ("done", "error", "cancelled")
        except (OSError, ValueError):
            return False

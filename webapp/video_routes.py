"""Müşteri videosu uç noktaları (app.py'ye yalnız `include_router` ile bağlanır).

    POST /api/projects/{pid}/video          → iş oluşturur (VideoSettings ile doğrulanır)
    GET  /api/projects/{pid}/video          → bu projenin hazır videoları
    GET  /api/video-jobs/{jid}              → aşama + yüzde
    POST /api/video-jobs/{jid}/cancel       → iptal
    GET  /api/video-jobs/{jid}/download     → mp4 (indirme)
    GET  /api/video-jobs/{jid}/file/{ad}    → mp4 / kapak.jpg / altyazi.srt (oynatıcı için, Range destekli)
    GET  /api/video-capabilities            → sistem bağımlılıkları + sınırlar

Erişim koruması (Host / token / Origin) app.py'deki ortak middleware'den gelir; proje kimliği `_pdir` ile, iş kimliği
JID_RE ile doğrulanır; dosyalar yalnız beyaz listedeki adlarla ve kimlikli işten sunulur.
"""
from __future__ import annotations

import re
import threading
import unicodedata

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from archai.video import env
from archai.video.jobs import FILES_OK, JobError, VideoJobs
from archai.video.settings import VideoSettings

router = APIRouter()
_jobs: VideoJobs | None = None
_lock = threading.Lock()


def _app():
    """webapp.app'e tembel erişim (döngüsel içe aktarmayı önler)."""
    import webapp.app as A
    return A


def get_jobs():
    global _jobs
    with _lock:
        if _jobs is None:
            _jobs = VideoJobs(_app().PROJECTS)
        return _jobs


def _base_url(request: Request):
    """İş sürecinin bağlanacağı adres: aynı makinede, isteğin geldiği port (ARCHAI_VIDEO_BASE ile değiştirilebilir)."""
    import os
    fixed = os.environ.get("ARCHAI_VIDEO_BASE")
    if fixed:
        return fixed.rstrip("/")
    host = request.headers.get("host", "")
    port = None
    m = re.search(r":(\d{1,5})$", host)
    if m and 0 < int(m.group(1)) < 65536:
        port = int(m.group(1))
    if port is None:
        # Ters vekil arkasında Host portsuz gelir (Railway): sunucunun gerçekten dinlediği port kullanılır.
        srv = request.scope.get("server")
        env = os.environ.get("PORT", "")
        if srv and srv[1]:
            port = int(srv[1])
        elif env.isdigit() and 0 < int(env) < 65536:
            port = int(env)
        else:
            port = request.url.port or (443 if request.url.scheme == "https" else 80)
    return f"http://127.0.0.1:{port}"


def _raise(e: JobError):
    if e.extra:
        return JSONResponse({"detail": e.msg, **e.extra}, status_code=e.code)
    raise HTTPException(e.code, e.msg)


def _slug(name):
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()[:40] or "proje"


@router.get("/api/video-capabilities")
def capabilities():
    from archai.video.jobs import _cfg
    chk = env.check()
    c = _cfg()
    return {**chk, "max_queued": c["max_queued"], "max_concurrent": c["max_concurrent"], "timeout": c["timeout"],
            "defaults": VideoSettings().model_dump(), "profiles": {"short": "≈ 30 sn", "standard": "≈ 60–90 sn"}}


@router.post("/api/projects/{pid}/video", status_code=202)
def create_video(pid: str, request: Request, settings: VideoSettings | None = None):
    A = _app()
    A._pdir(pid, "project.json")
    try:
        return get_jobs().submit(pid, settings or VideoSettings(), _base_url(request))
    except JobError as e:
        return _raise(e)


@router.get("/api/projects/{pid}/video")
def list_videos(pid: str):
    A = _app()
    A._pdir(pid)
    return get_jobs().list_done(pid)


@router.get("/api/video-jobs/{jid}")
def video_status(jid: str):
    try:
        j = get_jobs().get(jid)
    except JobError as e:
        return _raise(e)
    if j is None:
        raise HTTPException(404, "iş bulunamadı")
    return j


@router.post("/api/video-jobs/{jid}/cancel")
def video_cancel(jid: str):
    jobs = get_jobs()
    if jobs.get(jid) is None:
        raise HTTPException(404, "iş bulunamadı")
    j = jobs.cancel(jid)
    if j is None:                      # bellekte yok → zaten bitmiş (diskten)
        raise HTTPException(409, "iş zaten bitmiş")
    return j


def _file(jid, name, attachment=False):
    jobs = get_jobs()
    j = jobs.get(jid)
    if j is None:
        raise HTTPException(404, "iş bulunamadı")
    if j["status"] != "done":
        raise HTTPException(409, "video henüz hazır değil")
    if name not in FILES_OK:
        raise HTTPException(404)
    d = jobs.job_dir(jid)
    f = (d / name).resolve() if d else None
    if f is None or not f.is_relative_to(d.resolve()) or not f.is_file():
        raise HTTPException(404, "dosya bulunamadı")
    fname = None
    if attachment:
        try:
            pname = _app()._read_json(d.parents[1] / "project.json", "proje kaydı").get("name", "proje")
        except HTTPException:
            pname = "proje"
        fname = f"{_slug(pname)}-musteri-videosu.mp4"
    return FileResponse(f, media_type=FILES_OK[name], filename=fname)


@router.get("/api/video-jobs/{jid}/download")
def video_download(jid: str):
    return _file(jid, "musteri_videosu.mp4", attachment=True)


@router.get("/api/video-jobs/{jid}/file/{name}")
def video_file(jid: str, name: str):
    return _file(jid, name)

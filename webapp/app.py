"""ArchAI web uygulaması.

    uv run uvicorn webapp.app:app --reload --port 8000
"""

import json
import re
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from archai import costing, project

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ROOT / "out" / "projects"
PROJECTS.mkdir(parents=True, exist_ok=True)
_blender_lock = threading.Lock()  # tek headless Blender süreci — render'lar sıraya girer

app = FastAPI(title="ArchAI")


class Brief(BaseModel):
    name: str = "Yeni Proje"
    parcel: dict | None = None
    zoning: dict | None = None
    program: dict | None = None
    quick: dict | None = None
    adjust: dict | None = None
    company: dict | None = None
    customer: dict | None = None
    render_3d: bool = False


def _new_id(name):
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower().translate(str.maketrans("çğıöşü", "cgiosu"))).strip("-")[:30]
    return f"{datetime.now():%Y%m%d-%H%M%S}-{slug or 'proje'}-{uuid.uuid4().hex[:4]}"


def _public(pid, result):
    """Dosya yollarını /files/... URL'lerine çevir."""
    base = PROJECTS / pid
    files = {k: f"/files/{pid}/{Path(v).resolve().relative_to(base.resolve())}" for k, v in result["files"].items()}
    pngs = sorted((base / "cizimler").glob("*.png"))
    return {**result, "id": pid, "files": files,
            "sheets": [{"name": p.stem, "png": f"/files/{pid}/cizimler/{p.name}",
                        "dxf": f"/files/{pid}/cizimler/{p.stem}.dxf"} for p in pngs]}


def _run(fn):
    try:
        return fn()
    except ValueError as ex:
        raise HTTPException(422, str(ex))


@app.post("/api/projects")
def create_project(b: Brief):
    brief = b.model_dump(exclude_none=True)
    render_3d = brief.pop("render_3d", False)
    if not brief.get("quick") and not brief.get("parcel"):
        raise HTTPException(422, "arazi (parcel+zoning) veya hızlı mod (quick) bilgisi gerekli")
    pid = _new_id(b.name)
    with _blender_lock if render_3d else _nolock():
        result, _ = _run(lambda: project.run(brief, PROJECTS / pid, render_3d=render_3d))
    return _public(pid, result)


@app.post("/api/projects/dxf")
def create_from_dxf(file: UploadFile = File(...), name: str = Form("DXF Projesi"), floors: int = Form(1),
                    floor_height: float = Form(3.0), render_3d: bool = Form(False)):
    if not file.filename.lower().endswith(".dxf"):
        raise HTTPException(422, "yalnız .dxf kabul ediliyor (DWG'yi AutoCAD/ODA ile DXF'e çevirin)")
    pid = _new_id(name)
    d = PROJECTS / pid
    d.mkdir(parents=True)
    src = d / "plan.dxf"
    with src.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    brief = {"name": name, "dxf": {"floors": floors, "floor_height": floor_height}}
    with _blender_lock if render_3d else _nolock():
        result, _ = _run(lambda: project.run_dxf(src, brief, d, render_3d=render_3d))
    return _public(pid, result)


@app.get("/api/projects")
def list_projects():
    out = []
    for p in sorted(PROJECTS.glob("*/project.json"), reverse=True)[:50]:
        r = json.loads(p.read_text())
        out.append({"id": p.parent.name, "name": r["name"], "total": r["cost"]["total"],
                    "area": r["summary"]["gross_floor_area"]})
    return out


@app.get("/api/projects/{pid}")
def get_project(pid: str):
    p = PROJECTS / pid / "project.json"
    if not p.exists() or "/" in pid:
        raise HTTPException(404)
    return _public(pid, json.loads(p.read_text()))


@app.put("/api/projects/{pid}/adjust")
def adjust(pid: str, adj: dict):
    if not (PROJECTS / pid / "project.json").exists() or "/" in pid:
        raise HTTPException(404)
    return _public(pid, project.readjust(PROJECTS / pid, adj))


@app.post("/api/projects/{pid}/render")
def render_3d(pid: str):
    d = PROJECTS / pid
    if not (d / "elements.json").exists() or "/" in pid:
        raise HTTPException(404)
    with _blender_lock:
        files = project.render(json.loads((d / "elements.json").read_text()), d / "3d")
    r = json.loads((d / "project.json").read_text())
    r["files"].update(files)
    (d / "project.json").write_text(json.dumps(r, ensure_ascii=False, indent=1, default=str))
    return _public(pid, r)


@app.get("/api/prices")
def prices():
    return costing.load_prices()


@app.get("/files/{pid}/{path:path}")
def files(pid: str, path: str):
    f = (PROJECTS / pid / path).resolve()
    if not str(f).startswith(str(PROJECTS.resolve()) + "/") or not f.is_file():
        raise HTTPException(404)
    return FileResponse(f, filename=f.name if f.suffix in (".docx", ".xlsx", ".dxf", ".pdf") else None)


class _nolock:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")

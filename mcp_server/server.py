"""ArchAI MCP sunucusu — ajanın (Claude Code vb.) Blender'ı kullanmasını sağlar.

Blender tarafında blender_addon/archai_bridge.py çalışır. Köprü ayakta değilse
ilk araç çağrısında headless Blender otomatik başlatılır.
"""

import json
import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

ROOT = Path(__file__).resolve().parent.parent
ADDON = ROOT / "blender_addon" / "archai_bridge.py"
BLENDER = os.environ.get("ARCHAI_BLENDER", str(Path.home() / "Applications/blender-4.5.14-linux-x64/blender"))
HOST, PORT = "127.0.0.1", int(os.environ.get("ARCHAI_PORT", "9876"))
OUT = Path(os.environ.get("ARCHAI_OUT", ROOT / "out"))

mcp = MCPServer("archai-blender")
_proc: subprocess.Popen | None = None


def _call(cmd: str, args: dict | None = None, timeout: float = 3600) -> Any:
    with socket.create_connection((HOST, PORT), timeout=5) as s:
        s.settimeout(timeout)
        s.sendall((json.dumps({"cmd": cmd, "args": args or {}}) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    resp = json.loads(buf)
    if not resp.get("ok"):
        raise RuntimeError(resp.get("error", "bilinmeyen hata") + "\n" + resp.get("trace", ""))
    return resp["result"]


def _ensure() -> None:
    global _proc
    try:
        _call("ping", timeout=5)
        return
    except OSError:
        pass
    OUT.mkdir(parents=True, exist_ok=True)
    log = open(OUT / "blender.log", "a")
    _proc = subprocess.Popen([BLENDER, "-b", "--factory-startup", "--python", str(ADDON), "--", "--serve"],
                             stdout=log, stderr=subprocess.STDOUT)
    for _ in range(120):
        time.sleep(0.5)
        if _proc.poll() is not None:
            raise RuntimeError(f"Blender kapandı, log: {OUT / 'blender.log'}")
        try:
            _call("ping", timeout=5)
            return
        except OSError:
            continue
    raise RuntimeError("Blender köprüsü 60 sn'de açılmadı")


def call(cmd: str, args: dict | None = None) -> Any:
    _ensure()
    return _call(cmd, args)


@mcp.tool()
def blender_status() -> dict:
    """Blender köprüsünü (gerekirse başlatıp) kontrol eder; sürüm ve açık dosyayı döndürür."""
    return call("ping")


@mcp.tool()
def reset_scene() -> str:
    """Sahnedeki her şeyi siler. Yeni bir projeye başlarken çağır."""
    return call("reset_scene")


@mcp.tool()
def build(elements: list[dict]) -> dict:
    """Mimari elemanları oluşturur. Birimler metre, Z yukarı, açılar derece.

    Her elemanda "type" zorunlu, "name" ve "tag" (semantik malzeme) önerilir.
    Geçerli tag'ler: wall, concrete, floor, roof, glass, frame, wood, stone, metal,
    water, vegetation, tree, fabric, furniture, ground, terrain, sea, hill, terracotta.

    Tipler:
      box      {origin:[x,y,z] (min köşe), size:[sx,sy,sz], rotation_z?}
      wall     {start:[x,y], end:[x,y], height=3, thickness=0.2, base_z=0,
                openings:[{offset, width, kind:"window"|"door", sill=0.9, height, leaf?}]}
               offset = start noktasından açıklığa mesafe. Pencereye cam+kasa otomatik eklenir.
      slab     {points:[[x,y],...], z (üst yüz), thickness=0.2}   — döşeme, çatı, havuz suyu, teras
      cylinder {center:[x,y,z_alt], radius, height, radius_top?} — kolon
      sphere   {center:[x,y,z], radius, scale?}
      tree     {position:[x,y], height=5, base_z=0, crown_scale?}
      stairs   {origin:[x,y,z], width, steps, rise, run, rotation_z?}

    Hatalı elemanlar atlanır ve "errors" listesinde döner; kalanlar oluşturulur.
    Büyük modelleri kat/bölüm bazında birkaç build çağrısına böl.
    """
    return call("build", {"elements": elements})


@mcp.tool()
def delete(names: list[str] | None = None, prefix: str | None = None) -> dict:
    """Obje siler: tam adlarla ve/veya bir önekle (örn. prefix="kat2_")."""
    return call("delete", {"names": names or [], "prefix": prefix})


@mcp.tool()
def scene_info(limit: int = 200) -> dict:
    """Sahne özeti: obje sayısı, tag dağılımı, sınır kutusu, obje listesi, colormap paleti."""
    return call("scene_info", {"limit": limit})


@mcp.tool()
def exec_python(code: str) -> dict:
    """Blender içinde serbest bpy kodu çalıştırır (print çıktısı döner).
    build'in yetmediği şekiller için. Oluşturduğun objeyi colormap'e dahil etmek için
    tag_object(obj, "wall") çağır — etiketsiz objeler render'da yanlış renk alır."""
    return call("exec_python", {"code": code})


@mcp.tool()
def camera_path(mode: str = "orbit", frames: int = 120, fps: int = 24, lens: float = 24,
                points: list[list[float]] | None = None, target: list[float] | None = None,
                targets: list[list[float]] | None = None, radius: float | None = None,
                height: float | None = None, degrees: float = 90, start_angle: float = -45,
                ease: bool = True) -> dict:
    """Kamera animasyonu kurar.
      orbit      — sahne merkezinde yay: radius, height, degrees, start_angle
      flythrough — points [[x,y,z],...] boyunca yumuşak (Catmull-Rom) yol; targets/target
                   verilmezse gidiş yönüne bakar. İç mekân gezintisi için göz yüksekliği ~1.6 m.
      dolly      — points[0]→points[-1], sabit target'a bakarak.
    Önce render(still=1) ve son kareyle kadrajı kontrol et."""
    args = {k: v for k, v in dict(mode=mode, frames=frames, fps=fps, lens=lens, points=points,
            target=target, targets=targets, radius=radius, height=height, degrees=degrees,
            start_angle=start_angle, ease=ease).items() if v is not None}
    return call("camera_path", args)


@mcp.tool()
def render(kind: str = "colormap", still: int | None = None, resolution: list[int] | None = None,
           samples: int = 64, out_dir: str | None = None) -> dict:
    """Render alır.
      kind: "colormap" (düz renk malzeme haritası — video modeli için kontrol videosu),
            "preview" (EEVEE, hızlı gerçekçi), "preview_cycles" (GPU path tracing, yavaş).
      still: kare numarası verilirse tek PNG döner — sonucu görmek için bu PNG'yi oku.
      Verilmezse tüm animasyon render edilip mp4'e çevrilir."""
    args = {"kind": kind, "samples": samples, "out_dir": out_dir or str(OUT),
            "resolution": resolution or [1280, 720]}
    if still is not None:
        args["still"] = still
    return call("render", args)


@mcp.tool()
def save_blend(path: str) -> dict:
    """Sahneyi .blend olarak kaydeder."""
    return call("save", {"path": path})


@mcp.tool()
def open_blend(path: str) -> dict:
    """Var olan bir .blend dosyasını açar."""
    return call("open", {"path": path})


@mcp.tool()
def prepare_video_job(name: str, style_prompt: str, materials: dict[str, str],
                      camera_note: str = "", source_dir: str | None = None) -> dict:
    """Video modeline (Higgsfield / Seedance / Kling vb.) gönderilecek paketi hazırlar.

    materials: tag → gerçek malzeme tarifi, örn. {"wall": "white lime-washed stucco",
               "wood": "weathered oak pergola beams"}. Sahnede olan tag'lerin hepsini ver.
    Çıktı klasörü: colormap.mp4 (kontrol videosu), ilk kare, prompt.txt (renk→malzeme
    lejantı dahil) ve job.json. render(kind="colormap") önceden alınmış olmalı;
    render'ı farklı out_dir'e aldıysan aynısını source_dir olarak ver."""
    info = call("scene_info", {"limit": 0})
    palette = info["palette"]
    src = Path(source_dir or OUT).expanduser() / "colormap.mp4"
    if not src.exists():
        raise RuntimeError("önce render(kind='colormap') ile animasyonu al")
    job = Path(source_dir or OUT).expanduser() / "jobs" / name
    job.mkdir(parents=True, exist_ok=True)
    (job / "colormap.mp4").write_bytes(src.read_bytes())
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-frames:v", "1",
                    str(job / "first_frame_colormap.png")], check=True)

    def hexc(rgb):
        return "#" + "".join(f"{round(c * 255):02x}" for c in rgb)

    used = [t for t in info["tags"] if t in palette]
    missing = [t for t in used if t not in materials]
    legend = "\n".join(f"- {hexc(palette[t])} ({t}): {materials.get(t, t)}" for t in used)
    prompt = (f"{style_prompt}\n\n"
              "The input video is a flat color segmentation map of an architectural scene. "
              "Keep the geometry, proportions and camera motion exactly. Replace each flat color "
              "with the material below:\n"
              f"{legend}\n- {hexc(palette['sky'])} (sky): natural sky\n"
              + (f"\nCamera: {camera_note}\n" if camera_note else ""))
    (job / "prompt.txt").write_text(prompt)
    (job / "job.json").write_text(json.dumps({"name": name, "materials": materials,
                                              "tags": info["tags"], "palette": {t: hexc(palette[t]) for t in used}},
                                             indent=2, ensure_ascii=False))
    return {"job_dir": str(job), "missing_materials": missing, "prompt": prompt}


@mcp.tool()
def shutdown_blender() -> str:
    """Headless Blender sürecini kapatır."""
    try:
        return _call("shutdown", timeout=10)
    except OSError:
        return "zaten kapalı"


if __name__ == "__main__":
    mcp.run()

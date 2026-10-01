"""Sahne planı: proje gerçeklerinden zaman çizelgesi, altyazılar ve çekim bildirimi (saf; tarayıcı yok).

`build_plan` hiçbir sayı uydurmaz: kartlardaki rakamlar `project.json` özetinden, sahneler elemanlardan türer.
Veri olmayan sahne (ör. firma kartı, yürüyüş) planda hiç yer almaz.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import facts as F
from .settings import VideoSettings

FPS = 24
TRANS = 0.3                  # sahneler arası çapraz geçiş (sn)
CAP_IN = 0.35                # altyazı, sahne başından/sonundan bu kadar içeride
SHEET_PRIORITY = ("vaziyet", "zemin", "normal", "kesit", "gorunus")
# (kısa profil, standart) süreleri — sn
D = {
    "title": (2.2, 3.5), "intro": (2.3, 2.5), "orbit": (4.6, 10.0), "modes": (3.2, 5.2), "floor_each": (0.6, 1.5),
    "walk": (10.0, 26.0), "daynight": (2.8, 6.5), "cycles_each": (2.2, 3.0), "sheets": (2.4, 4.0), "metraj": (2.6, 4.2),
    "maliyet": (3.0, 4.2), "teklif": (0.0, 3.6), "company": (2.0, 3.2), "end": (2.8, 5.0),
}


@dataclass
class Caption:
    t0: float
    t1: float
    text: str
    sub: str | None = None
    track: str = "main"           # main: alt sol altyazı, tag: sol üst oda etiketi


@dataclass
class Scene:
    id: str
    kind: str                      # title|intro|orbit|modes|floors|walk|daynight|cycles|sheets|metraj|maliyet|teklif|company|end
    dur: float
    live: bool = False             # tarayıcıdan kare dizisi gerekir
    caps: list = field(default_factory=list)
    data: dict = field(default_factory=dict)
    start: float = 0.0             # zaman çizelgesindeki başlangıç (sn)
    trans: float = 0.0             # önceki sahneyle geçiş süresi

    @property
    def frames(self):
        return max(1, int(round(self.dur * FPS)))


@dataclass
class Plan:
    scenes: list
    total: float
    size: tuple
    settings: dict
    warnings: list = field(default_factory=list)

    @property
    def total_frames(self):
        return int(round(self.total * FPS))

    def captions(self, track=None):
        """Zaman çizelgesi saniyesinde altyazılar: [(t0, t1, text, sub, track)]."""
        out = []
        for s in self.scenes:
            for c in s.caps:
                if track is None or c.track == track:
                    out.append((s.start + c.t0, s.start + c.t1, c.text, c.sub, c.track))
        return sorted(out)


def orbit_geometry(f):
    """Orbit merkezi ve yarıçapı. Bina yoksa arsa sınırından."""
    if f.has_building:
        x0, y0, x1, y1, zt = f.bounds
        dx, dy = x1 - x0, y1 - y0
        r = 0.5 * math.sqrt(dx * dx + dy * dy + zt * zt)
        cx, cy, zc = (x0 + x1) / 2, (y0 + y1) / 2, max(0.5, zt * 0.42)
        # sitedeki ağaç/havuz da kadraja girsin ama binayı küçültmesin
        R = 2.55 * r + 4
    elif f.site:
        x0, y0, x1, y1 = f.site
        dx, dy = x1 - x0, y1 - y0
        r = 0.5 * math.hypot(dx, dy)
        cx, cy, zc = (x0 + x1) / 2, (y0 + y1) / 2, 1.0
        R = 2.2 * r + 3
    else:
        cx, cy, zc, R = 0.0, 0.0, 1.0, 40.0
    return {"center": [round(cx, 3), round(cy, 3), round(zc, 3)], "radius": round(R, 2)}


def _caps(dur, text, sub=None, t0=None, t1=None, track="main"):
    a = CAP_IN if t0 is None else t0
    b = dur - CAP_IN if t1 is None else t1
    return [Caption(round(a, 3), round(b, 3), text, sub, track)] if b - a >= 0.8 else []


def sheet_pick(f, k=3):
    items = list(f.sheets)

    def pr(it):
        n = it[0].stem.lower()
        for i, key in enumerate(SHEET_PRIORITY):
            if key in n:
                return i
        return len(SHEET_PRIORITY)
    items.sort(key=pr)
    return items[:k]


def build_plan(f, st: VideoSettings, walk=None, cycles_ok=None, skip=()):
    """f: Facts, st: VideoSettings, walk: walk.WalkPlan | None.
    cycles_ok: None → Cycles istendiyse bekleniyor (planlanan çekimler); liste → başarıyla alınan çekim adları."""
    si = 0 if st.short else 1
    d = lambda k: D[k][si]
    scenes = []
    warn = []
    og = orbit_geometry(f)
    nlev = len(f.levels)
    hl = F.headline(f)

    def add(id_, kind, dur, live=False, caps=None, data=None):
        scenes.append(Scene(id_, kind, round(dur, 3), live, caps or [], data or {}))
        return scenes[-1]

    add("title", "title", d("title"), data={"headline": hl, "site": F.site_line(f)})
    if f.has_building:
        add("intro", "intro", d("intro"), True, _caps(d("intro"), "Plandan 3D modele", hl or None),
            {**og, "az": -125, "el": 24, "fov": 34})
        add("orbit", "orbit", d("orbit"), True, _caps(d("orbit"), "Binayı her açıdan inceleyin"),
            {**og, "az0": -125, "az1": -125 + (110 if st.short else 230), "el": 24, "fov": 34})
        add("modes", "modes", d("modes"), True, _caps(d("modes"), "Tel kafes · X-ray · Katı · Gerçekçi"),
            {**og, "az": -60, "el": 24, "fov": 34, "modes": ["wire", "xray", "solid", "real"]})
        if nlev >= 2:
            per = d("floor_each")
            n_show = min(nlev, 3 if st.short else 6)
            idx = sorted({max(1, round(1 + i * (nlev - 1) / max(1, n_show - 1))) for i in range(n_show)})
            names = " → ".join(f.levels[i - 1] for i in idx)
            add("floors", "floors", per * len(idx), True, _caps(per * len(idx), "Kat kat kesit", names),
                {**og, "az": -62, "el": 30, "fov": 34, "levels": idx, "each": per})
        if walk is not None and walk.duration > 2:
            wd = walk.duration
            caps = _caps(wd, "İçinde gezin", "birinci şahıs gezinti", t0=0.4, t1=min(wd - 0.4, 3.6))
            caps += [Caption(a, b, text, f"{area:g} m²".replace(".", ","), "tag") for a, b, text, area in walk.tags]
            add("walk", "walk", wd, True, caps, {"level": walk.level, "z": walk.z, "level_index": f.levels.index(walk.level) + 1,
                                                 "visited": walk.visited, "door_open": walk.door_open})
        if st.night:
            add("daynight", "daynight", d("daynight"), True, _caps(d("daynight"), "Gün ışığı ve gece aydınlatması"),
                {**og, "az0": -100, "az1": -72, "el": 22, "fov": 34, "h0": 6.5, "h1": 18.5})
        if st.cycles:
            shots = cycle_shots(f, og, walk, st)
            ok = shots if cycles_ok is None else [s for s in shots if s["name"] in cycles_ok]
            for s in ok:
                add("cy_" + s["name"], "cycles", d("cycles_each"), False,
                    _caps(d("cycles_each"), "Fotogerçekçi render", s["label"]), {"name": s["name"], "label": s["label"]})
    else:
        add("orbit", "orbit", d("orbit"), True, _caps(d("orbit"), "Arsa ve çevresi"),
            {**og, "az0": -125, "az1": -125 + (110 if st.short else 230), "el": 24, "fov": 34})
        warn.append("projede bina yok: yalnız arsa görünümü")

    if f.sheets:
        picks = sheet_pick(f)
        add("sheets", "sheets", d("sheets"), False, _caps(d("sheets"), "Paftalar otomatik hazır",
                                                          "DXF ve PDF — " + " · ".join(l for _, l in picks)),
            {"sheets": [str(p) for p, _ in picks], "labels": [l for _, l in picks]})
    summ = f.summary
    if summ and (summ.get("gross_floor_area") or summ.get("wall_length")):
        n_items = len((f.cost or {}).get("rows") or [])
        add("metraj", "metraj", d("metraj"), False, _caps(d("metraj"), "Metraj projeden otomatik çıkar",
                                                          f"{n_items} kalem" if n_items else None), {})
    if f.cost and f.cost.get("total"):
        add("maliyet", "maliyet", d("maliyet"), False, _caps(d("maliyet"), "Maliyet kalem kalem hesaplanır"), {})
        if not st.short and f.docs:
            add("teklif", "teklif", d("teklif"), False, _caps(d("teklif"), "Teklif, şartname ve Excel hazır", " · ".join(f.docs)),
                {"docs": f.docs})
    if F.has_company_card(f):
        add("company", "company", d("company"), False, [], {})
    add("end", "end", d("end"), False, [], {})

    if skip:
        scenes[:] = [s_ for s_ in scenes if s_.id not in set(skip)]
        warn.append("çekimi başarısız sahneler atlandı: " + ", ".join(sorted(set(skip))))
    # zaman çizelgesi: ardışık sahneler TRANS kadar örtüşür
    pos = 0.0
    for i, s in enumerate(scenes):
        s.trans = TRANS if i else 0.0
        pos = pos - s.trans
        s.start = round(pos, 4)
        pos += s.dur
    total = round(pos, 3)
    return Plan(scenes, total, st.size, st.model_dump(), warn)


def cycle_shots(f, og, walk, st):
    """Cycles için kadrajlar: dış cephe + (yürüyüş varsa) iki iç mekân."""
    cx, cy, zc = og["center"]
    R = og["radius"]
    a = math.radians(-125)
    e = math.radians(20)
    shots = [{"name": "dis", "label": "Dış cephe", "level": "max", "walk": None,
              "cam": {"pos": [cx + R * 0.85 * math.cos(a) * math.cos(e), cy + R * 0.85 * math.sin(a) * math.cos(e), zc + R * 0.85 * math.sin(e)],
                      "target": [cx, cy, zc], "fov": 34}}]
    nint = 1 if st.short else 2
    if walk is not None and walk.frames:
        # yürüyüşteki en uzun kalınan iki durak (oda ortası) iç mekân still'i
        stops = _dwell_points(walk)[:nint]
        for k, (x, y, yaw, label) in enumerate(stops):
            shots.append({"name": f"ic{k + 1}", "label": label or "İç mekân", "level": walk.level, "walk": [x, y, yaw]})
    return shots


def _dwell_points(walk):
    """Yürüyüşte kamera duran yerler (peş peşe aynı konum): [(x, y, yaw, oda_etiketi)] uzun kalıştan kısaya."""
    fr = walk.frames
    out = []
    i = 0
    while i < len(fr):
        j = i
        while j + 1 < len(fr) and abs(fr[j + 1][1] - fr[i][1]) < 1e-6 and abs(fr[j + 1][2] - fr[i][2]) < 1e-6:
            j += 1
        if j - i >= 12:
            mid = (i + j) // 2
            t = fr[mid][0]
            label = next((tg[2] for tg in walk.tags if tg[0] <= t <= tg[1]), None)
            out.append((j - i, fr[mid][1], fr[mid][2], fr[mid][3], label))
        i = j + 1
    out.sort(reverse=True)
    return [(x, y, yaw, label) for _, x, y, yaw, label in out]


def plan_to_dict(plan):
    import dataclasses
    return dataclasses.asdict(plan)


def plan_from_dict(d):
    """plan_to_dict'in tersi (montaj işçi süreçlerine geçiş için)."""
    scenes = []
    for s in d["scenes"]:
        caps = [Caption(**c) for c in s.get("caps", [])]
        scenes.append(Scene(**{**s, "caps": caps}))
    return Plan(scenes, d["total"], tuple(d["size"]), d.get("settings", {}), d.get("warnings", []))


def capture_manifest(plan, f, st, walk, pid, base_url, workdir):
    """capture_worker.py'nin okuyacağı bildirim: yalnız canlı sahneler + Cycles çekimleri."""
    live = []
    for s in plan.scenes:
        if not s.live:
            continue
        item = {"id": s.id, "kind": s.kind, "frames": s.frames, **s.data}
        if s.kind == "walk" and walk is not None:
            item["samples"] = [[round(a, 4), round(b, 3), round(c, 3), round(d_, 4)] for a, b, c, d_ in walk.frames]
        live.append(item)
    shots = []
    if st.cycles and f.has_building:
        shots = cycle_shots(f, orbit_geometry(f), walk, st)
    return {"pid": pid, "name": f.name, "base": base_url, "fps": FPS, "workdir": str(workdir),
            "size": list(st.size), "scenes": live, "cycles": {"shots": shots, "hq": st.cycles_quality == "good"},
            "levels": f.levels, "floors": f.floors, "furnish": st.furnish}

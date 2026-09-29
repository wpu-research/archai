"""Hibrit plan okuma: geometri plan_image'den, anlam (mahal adı, mobilya/vitrifiye) Claude'un görsel okumasından.

Akış: tanınan mahaller orijinal resmin üstüne numaralanır → Claude'a gönderilir → her numara için mahal adı ve
çizimdeki mobilya sembolleri (tür, piksel kutusu, duvara dayanan yüz) yapılandırılmış JSON olarak döner →
mahal adları eleman listesine, mobilya parametrik iç mekân kataloğuna (interior.json) yerleşir.

Anthropic kimlik bilgisi yoksa (ANTHROPIC_API_KEY / `ant auth login`) çağrı yapılmaz; tanıma geometriyle devam
eder. Model yalnız anlam verir: duvar/kapı konumları hiçbir zaman görüntü modelinden alınmaz (plan kaymaz).
"""

import base64
import io
import math
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import Polygon

from .layout_check import local_box

MODEL = "claude-opus-5-5"
MAX_SIDE = 1800        # gönderilen görselin uzun kenarı (px); koordinatlar geri ölçeklenir

ROOM_TYPES = {  # tür → mahal adı (Türkçe, belge ve 3D'de görünen)
    "salon": "Salon", "mutfak": "Mutfak", "mutfak_yemek": "Mutfak ve Yemek", "yemek": "Yemek Odası",
    "yatak_odasi": "Yatak Odası", "ebeveyn_yatak_odasi": "Ebeveyn Yatak Odası", "cocuk_odasi": "Çocuk Odası",
    "banyo": "Banyo", "wc": "WC", "hol": "Hol", "antre": "Antre", "koridor": "Koridor", "balkon": "Balkon",
    "merdiven": "Merdiven", "asansor": "Asansör", "kat_holu": "Kat Holü", "depo": "Depo", "calisma": "Çalışma Odası",
    "giyinme": "Giyinme Odası", "diger": "Mahal",
}
# çizim sembolü → katalog türü (interior.js ITEMS); sırt: kutunun duvara dayanan yüzü
FURNITURE = {
    "kanepe_3": "kanepe", "kanepe_2": "kanepe_2li", "l_koltuk": "kanepe_l", "berjer": "modern_arm_chair_01",
    "orta_sehpa": "sehpa_yuvarlak", "yan_sehpa": "sehpa_yuvarlak", "tv_unitesi": "tv_unitesi",
    "yemek_masasi": "yemek_masasi", "sandalye": "sandalye", "cift_yatak": "yatak_cift", "tek_yatak": "yatak_tek",
    "komodin": "komodin", "gardirop": "gardirop", "mutfak_tezgahi": "mutfak", "buzdolabi": "buzdolabi",
    "lavabo": "lavabo", "klozet": "klozet", "dus": "dus", "kuvet": "kuvet", "calisma_masasi": "calisma_masasi",
    "kitaplik": "kitaplik",
}
BACK_ROT = {"N": 0.0, "S": math.pi, "W": math.pi / 2, "E": -math.pi / 2}   # interior.js: sırtı hangi duvara

SCHEMA = {
    "type": "object",
    "properties": {
        "rooms": {"type": "array", "items": {
            "type": "object",
            "properties": {"id": {"type": "integer"}, "type": {"type": "string", "enum": sorted(ROOM_TYPES)},
                           "label": {"type": "string"}},
            "required": ["id", "type", "label"], "additionalProperties": False}},
        "furniture": {"type": "array", "items": {
            "type": "object",
            "properties": {"type": {"type": "string", "enum": sorted(FURNITURE)},
                           "x0": {"type": "number"}, "y0": {"type": "number"},
                           "x1": {"type": "number"}, "y1": {"type": "number"},
                           "back": {"type": "string", "enum": ["N", "S", "E", "W", "none"]}},
            "required": ["type", "x0", "y0", "x1", "y1", "back"], "additionalProperties": False}},
    },
    "required": ["rooms", "furniture"], "additionalProperties": False,
}

PROMPT = """This image is an architectural floor plan (a CAD screenshot or drawing sheet). An automatic \
geometry pass has already found the walls and rooms; each detected room is marked with a numbered red label.

1. For every numbered label, classify the room it sits in (use the room's furniture, fixtures and any text in \
the drawing as evidence) and give a short Turkish label as it would appear on the plan (e.g. "Salon", \
"Ebeveyn Yatak Odası", "Banyo"). Include every number exactly once.
2. List every furniture and sanitary-fixture symbol drawn in the plan: its type, its bounding box in pixel \
coordinates of this image (x to the right, y downward, image is {w}×{h} px), and which side of the box is \
against a wall ("N" = top edge, "S" = bottom, "W" = left, "E" = right; "none" for free-standing items such as \
round tables and dining chairs). Report each symbol once; a dining set is one table plus one entry per chair.

Only report what is actually drawn. Do not invent furniture, rooms or fixtures that are not in the image."""


def available():
    """Kimlik bilgisi var mı (API anahtarı, OAuth jetonu ya da `ant auth login` profili)."""
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    return (Path.home() / ".config" / "anthropic").exists()


def _room_labels(img, rooms, S, H, k):
    """Mahal numaralarını (1..n) mahal merkezine çiz; k: gönderim ölçeği."""
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", max(12, int(18 * k * 1.4)))
    except OSError:
        font = ImageFont.load_default()
    for i, r in enumerate(rooms, 1):
        c = Polygon(r["points"]).representative_point()      # L/U biçimli odada da içeride
        cx, cy = c.x, c.y
        x, y = cx * S * k, (H - cy * S) * k
        t = str(i)
        bb = d.textbbox((x, y), t, font=font, anchor="mm")
        d.rectangle([bb[0] - 4, bb[1] - 3, bb[2] + 4, bb[3] + 3], fill=(220, 30, 30))
        d.text((x, y), t, fill=(255, 255, 255), font=font, anchor="mm")
    return img


def ask(img_path, rooms, S, client=None, model=MODEL):
    """Claude'a numaralı planı gönder → {"rooms": [...], "furniture": [...]} (koordinatlar orijinal pikselde)."""
    import anthropic
    import json
    src = Image.open(img_path).convert("RGB")
    W, H = src.size
    k = min(1.0, MAX_SIDE / max(W, H))
    img = src.resize((round(W * k), round(H * k))) if k < 1 else src.copy()
    _room_labels(img, rooms, S, H, k)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    client = client or anthropic.Anthropic()
    resp = client.beta.messages.create(
        model=model, max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                         "data": base64.standard_b64encode(buf.getvalue()).decode()}},
            {"type": "text", "text": PROMPT.format(w=img.width, h=img.height)},
        ]}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("görsel okuma reddedildi")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("görsel okuma yanıtı yarıda kesildi")
    data = json.loads(next(b.text for b in resp.content if b.type == "text"))
    for f in data.get("furniture", []):     # gönderim ölçeğinden orijinal piksele
        for key in ("x0", "y0", "x1", "y1"):
            f[key] = f[key] / k
    return data


def _params(kind, w, d):
    """Çizim kutusundan parametrik ölçü (w: duvar boyunca, d: derinlik; metre)."""
    r = lambda v: round(v, 2)
    if kind in ("kanepe", "kanepe_2li"):
        return {"w": r(max(1.4, w))}
    if kind == "gardirop":
        return {"w": r(max(0.8, w))}
    if kind in ("yatak_cift", "yatak_tek"):
        return {"w": r(max(0.8, w - 0.16)), "d": r(max(1.8, d))}
    if kind == "mutfak":
        return {"w": r(max(0.6, w)), "d": r(min(0.75, max(0.55, d)))}
    if kind == "dus":
        return {"w": r(max(0.7, w)), "d": r(max(0.7, d))}
    if kind == "yemek_masasi":
        return {"w": r(max(0.8, max(w, d))), "d": r(max(0.6, min(w, d)))}
    if kind == "sehpa_yuvarlak":
        return {"d": r(max(0.4, min(w, d)))}
    return {}


def furniture_objects(items, level, S, H):
    """Görsel okuma kutuları → iç mekân nesneleri (interior.json). Kutu çizimdeki dış hattır; nesne sırt yüzüne
    yaslanır, yanlamasına ortalanır (archai/apartment.py ile aynı kural)."""
    objs = []
    for f in items:
        kind = FURNITURE.get(f["type"])
        if not kind:
            continue
        x0, x1 = sorted((f["x0"], f["x1"]))
        y0, y1 = sorted((f["y0"], f["y1"]))
        back = f.get("back", "none")
        rot = BACK_ROT.get(back, 0.0)
        along_x = back in ("N", "S", "none")
        w = ((x1 - x0) if along_x else (y1 - y0)) / S
        dep = ((y1 - y0) if along_x else (x1 - x0)) / S
        params = _params(kind, w, dep)
        if kind == "yemek_masasi" and (y1 - y0) > (x1 - x0):
            rot = math.pi / 2                       # uzun kenar planın y ekseni boyunca
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if back in BACK_ROT:
            b = -local_box({"kind": kind, **params})[1]            # yerel −z = sırt derinliği
            fx, fy = math.sin(rot), -math.cos(rot)                  # plan önü
            if abs(fx) > 0.5:
                cx = (x0 if fx > 0 else x1) + fx * b * S
            else:
                cy = (y1 if fy > 0 else y0) - fy * b * S
        objs.append({"id": f"v{len(objs):03d}", "kind": kind, "level": level, "x": round(cx / S, 3),
                     "y": round((H - cy) / S, 3), "rot": round(rot, 4), "h": 0.0, **params})
    tables = [o for o in objs if o["kind"] == "yemek_masasi"]
    for o in objs:  # sandalye en yakın masaya döner (90° katına)
        if o["kind"] != "sandalye" or not tables:
            continue
        t = min(tables, key=lambda t: math.dist((t["x"], t["y"]), (o["x"], o["y"])))
        if math.dist((t["x"], t["y"]), (o["x"], o["y"])) > 2.0:
            continue
        a = math.atan2(t["x"] - o["x"], -(t["y"] - o["y"]))      # plan önü (sin r, −cos r) masaya
        o["rot"] = round(round(a / (math.pi / 2)) * (math.pi / 2), 4)
    return objs


def apply(elements, data):
    """Mahal adlarını eleman listesine yaz. Numaralama = ilk kattaki mahal sırası; üst katlar aynı sırayla
    tekrarlanır. Aynı ad birden çok mahalde geçerse hepsi numaralanır (Banyo 1, Banyo 2)."""
    rooms = [e for e in elements if e["type"] == "room"]
    if not rooms:
        return elements
    first = [e for e in rooms if e["level"] == rooms[0]["level"]]
    by_id = {r["id"]: r for r in data.get("rooms", [])}
    names = []
    for i in range(1, len(first) + 1):
        v = by_id.get(i)
        names.append(((v.get("label") or ROOM_TYPES.get(v.get("type"), "Mahal")).strip() or "Mahal") if v else f"Mahal {i}")
    total = {n: names.count(n) for n in names}
    seen = {}
    for i, n in enumerate(names):
        if total[n] > 1:
            seen[n] = seen.get(n, 0) + 1
            names[i] = f"{n} {seen[n]}"
    per_level = {}
    for e in rooms:
        j = per_level.get(e["level"], 0)
        per_level[e["level"]] = j + 1
        if j < len(names):
            e["name"] = f"{e['level']}/{names[j]}"
    return elements

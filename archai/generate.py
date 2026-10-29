"""Arazi + imar + ihtiyaç programı → şematik (avan) konut projesi.

Üretilen plan ön tasarımdır: kütle imar sınırlarına göre boyutlandırılır, kat planı kural
tabanlı yerleşimle çıkarılır. Ruhsat projesi değildir; mimar kontrolü ve düzeltmesi gerekir.

Koordinatlar: x sokak cephesi boyunca, y parsel derinliği (y=0 ön/sokak), metre.
"""

import math
from dataclasses import dataclass

EXT_T, CORE_T, INT_T = 0.25, 0.20, 0.10

# daire tipi → yaklaşık hedef net alan (m²) ve yatak odası sayısı
UNIT_TYPES = {"1+1": (55, 1), "2+1": (90, 2), "3+1": (125, 3), "4+1": (165, 4)}
CORE_W = 5.0          # çekirdek genişliği (merdiven 2.6 + asansör/şaft)
STAIR_DEPTH = 5.6     # merdiven + asansör bölgesi derinliği (arka)
HALL_BAND = 1.3       # daire içi hol bandı


@dataclass
class Rect:
    x0: float
    y0: float
    x1: float
    y1: float
    name: str
    kind: str = "room"   # room | core | void
    mod: int = 0         # çekirdek modülü (kat başına birden çok merdiven evi olduğunda)

    @property
    def w(self):
        return self.x1 - self.x0

    @property
    def d(self):
        return self.y1 - self.y0


def _r(v, step=0.05):
    return round(round(v / step) * step, 3)


def _ceil05(v):
    return round(math.ceil(v / 0.05 - 1e-6) * 0.05, 3)


def _floor05(v):
    return round(math.floor(v / 0.05 + 1e-6) * 0.05, 3)


def _ti(v):
    return f"{v:,.0f}".replace(",", ".")


def _floor3(v):
    return math.floor(v * 1000 + 1e-6) / 1000


def setback_checks(parcel_w, parcel_d, bbox, zoning):
    """Çekmeler bina DIŞ YÜZÜNDEN ölçülür. bbox = (x0, y0, x1, y1) dış yüz sınır kutusu (parsel koordinatı).
    Dönen: (düz sayılar {front, side_left, side_right, rear} — aşağı yuvarlanmış 3 hane, ayrıntı, genel ok)."""
    x0, y0, x1, y1 = bbox
    flat = {"front": _floor3(y0), "side_left": _floor3(x0), "side_right": _floor3(parcel_w - x1),
            "rear": _floor3(parcel_d - y1)}
    lim = {"front": zoning.get("front", 5), "side_left": zoning.get("side", 3), "side_right": zoning.get("side", 3),
           "rear": zoning.get("rear", 3)}
    detail = {k: {"value": v, "limit": lim[k], "ok": v >= lim[k] - 1e-6} for k, v in flat.items()}
    return flat, detail, all(d["ok"] for d in detail.values())


SETBACK_TR = {"front": "ön", "side_left": "sol yan", "side_right": "sağ yan", "rear": "arka"}


def setback_warnings(detail):
    return [f"{SETBACK_TR[k]} bahçe çekmesi {d['value']:.3f} m < {d['limit']:g} m (dış yüzden)"
            for k, d in detail.items() if not d["ok"]]


def emsal_disi_m2(zoning, gross):
    """Emsale girmeyen ortak alan (m²): `emsal_disi_m2` verilmişse o (brüt alanı aşamaz), yoksa eski `emsal_disi_pct` (% brüt)."""
    m2 = zoning.get("emsal_disi_m2")
    if m2:
        return min(float(m2), gross)
    return gross * (zoning.get("emsal_disi_pct", 0) or 0) / 100


def module_cap(unit_type):
    """Tek çekirdek + 2 daire modülünün hedef brüt oturumu (m²)."""
    ut = "2+1" if unit_type in (None, "auto") else unit_type
    return 2 * UNIT_TYPES[ut][0] / 0.82 + CORE_W * 11


def _module_search(fp, bw, bd, n_bed, target_net, min_modules=1):
    """Kat başına n çekirdek modülü (her biri 2 daire) × derinlik taraması: istenen oturumu (fp) tutturan ve daire
    net alanını hedefe en yakın veren (n, brüt genişlik, brüt derinlik). Uygun yoksa None."""
    best = None
    for n in range(min_modules, 13):
        d = 10.0
        while d <= min(15.0, bd) + 1e-9:
            w = min(fp / d, bw)                      # yapılaşma genişliğine sığmazsa alan eksik kalır (cezalı)
            aw, ad = _floor05(w - EXT_T) - 0.05, _floor05(d - EXT_T)   # 5 cm: çekme yuvarlaması payı
            uw = (aw - n * CORE_W) / (2 * n)
            unet = uw * ad * 0.88
            if uw >= 3.0 and unet * 1.3 >= target_net and unit_layout(uw, ad, n_bed):
                score = 3 * (1 - w * d / fp) + abs(unet - target_net) / target_net + 0.03 * n
                if best is None or score < best[0] - 1e-9:
                    best = (score, n, w, d)
            d += 0.25
    return None if best is None else best[1:]


# ------------------------------------------------------------------ kat başına 3–4 daire, tek çekirdek
# Biçim referansı archai/apartment.py: çekirdek ortada (U merdiven + asansör), iki ön daire çekirdeğin iki yanında
# (aynalı), arkada bir (3 daire, T kütle) veya iki (4 daire, dikdörtgen) daire. Kat holü H biçimli: ön bant (bina
# girişi, merdiven ve asansör kapıları), merdiven ile asansör arasındaki şerit, arka bant (daire girişleri).
CORE3_W = 6.2                       # merdiven 2,8 + hol şeridi 1,4 + asansör/şaft 2,0
STAIR_W, STRIP_W = 2.8, 1.4
HOL_W, KD = 1.2, 2.6                # daire holü genişliği; ön dairede mutfak/banyo sırası derinliği
H1_MIN, HB_MIN, YE_MAX, NECK_MIN = 1.6, 1.4, 11.0, 1.8
UNIT_GROSS = {"1+1": 70, "2+1": 100, "3+1": 145, "4+1": 190}   # hedef brüt m²/daire (ortak alan payı dahil)
MULTI_TYPES = ["1+1", "2+1", "3+1"]  # 3–4 daireli yerleşimde desteklenen tipler


def _fr(a, b, step):
    n = int(round((b - a) / step))
    return [round(a + i * step, 3) for i in range(n + 1)]


def units_for(fp, unit_type, upf):
    """Kat başına daire kararı: 3/4 → tek çekirdekli çok daireli yerleşim; None → 1–2 daire / çok modül yolu.
    'auto': kat brüt alanı / hedef daire brüt alanı ≈ daire sayısı (2,5–4,5 arası 3 veya 4)."""
    if upf in (3, 4):
        return upf
    if upf != "auto":
        return None
    ut = "2+1" if unit_type in (None, "auto") else unit_type
    if ut not in MULTI_TYPES:
        return None
    n = fp / UNIT_GROSS[ut]
    return (3 if n < 3.5 else 4) if 2.5 <= n < 4.5 else None


def _multi_types(wanted, fp, n):
    if wanted in (None, "auto"):
        best = min(MULTI_TYPES, key=lambda t: abs(UNIT_GROSS[t] - fp / n))
        return MULTI_TYPES[:MULTI_TYPES.index(best) + 1][::-1]
    if wanted not in MULTI_TYPES:
        return MULTI_TYPES[::-1]
    return MULTI_TYPES[:MULTI_TYPES.index(wanted) + 1][::-1]


def _core_end(yf):
    """Çekirdeğin (kat holü arka bandı dahil) bittiği y: ön daire derinliği, en çok 11 m; aşarsa arka daireye
    ≥ 1,8 m'lik bir 'boyun' kalır (çekirdeğin arkasında banyo/depo)."""
    return yf if yf <= YE_MAX + 1e-9 else _r(min(YE_MAX, yf - NECK_MIN))


def _front_dims(w, d, n):
    """Ön (köşe) daire: önde salon (tam genişlik), arkasında mutfak | banyo sırası, sonra yatak odaları; hol çekirdek
    yanında. Dönen (uygun mu, salon derinliği, yatak odası derinliği)."""
    bd = min(3.8, max(2.9, (d - KD - 4.4) / n))
    sd = d - KD - n * bd
    ok = (3.4 - 1e-6 <= sd <= 5.6 + 1e-6 and 5.8 - 1e-6 <= w <= 11.0 + 1e-6 and (w - .2) * (sd - .2) >= 17
          and (w - HOL_W - .2) * (bd - .2) >= 9.2)
    return ok, sd, bd


def _rear4_dims(w, dr, de, n):
    """Arka (köşe) daire, 4'lü yerleşim: arkada salon, yan cepheye dizili yatak odaları; hol ve (banyo + mutfak)
    şeridi çekirdeğin arkasında. dr: dış bölüm derinliği, de: iç şerit derinliği."""
    bd = min(3.8, max(2.8, (dr - 4.2) / n))
    sd = dr - n * bd
    ok = (3.2 - 1e-6 <= sd <= 5.6 + 1e-6 and (w - .2) * (sd - .2) >= 17 and (w - .2) * (bd - .2) >= 9.2
          and 2.6 - 1e-6 <= de - 2.4 <= 7.4 + 1e-6)   # iç şerit: banyo 2,4 + mutfak ≤ 4,4 + depo ≤ 3,0
    return ok, sd, bd


def _center_dims(wr, dr3, n, neck):
    """Arka orta daire, 3'lü yerleşim: arkada tam genişlik salon; üstünde sol sütun mutfak (+banyo), orta hol,
    sağ sütun yatak odaları; boyun varsa banyo/depo çekirdeğin hemen arkasında."""
    cw = wr / 2 - HOL_W / 2
    sd3 = min(5.0, max(3.6, dr3 - max(3.2 * n, 2.6 if neck else 4.6)))
    du = dr3 - sd3
    bd = du / n
    kit = du - (0 if neck else 2.2)
    e = 1e-6
    ok = (2.9 - e <= bd <= 5.0 + e and kit >= 2.4 - e and 2.6 - e <= cw <= 5.5 + e and (cw - .2) * (bd - .2) >= 9.2
          and (wr - .2) * (sd3 - .2) >= 17)
    return ok, sd3, bd


def _multi_search(n, fp, bw, bd_max, n_bed, target):
    """Kat başına n (3|4) daire için geometri: brüt oturumu (dış yüz) fp'yi aşmadan tutturan, daireleri dengeleyen
    ve daire brütünü hedefe yaklaştıran (Wf ön daire genişliği, Yf ön daire derinliği, arka ölçüler). Yoksa None."""
    best = None
    for Wf in _fr(5.8, 11.0, 0.1):
        W = _r(2 * Wf + CORE3_W)
        if W + EXT_T + 0.05 > bw + 1e-9:
            break
        for Yf in _fr(8.6, 20.0, 0.1):
            ok, sd, bdep = _front_dims(Wf, Yf, n_bed)
            if not ok:
                continue
            Ye = _core_end(Yf)
            Af = Wf * Yf
            cands = []
            if n == 4:
                D = _floor05(fp / (W + EXT_T) - EXT_T)
                if D + EXT_T + 0.05 > bd_max + 1e-9:
                    D = _floor05(bd_max - EXT_T - 0.05)
                dr = round(D - Yf, 3)
                if dr <= 0 or not _rear4_dims(Wf, dr, D - Ye, n_bed)[0]:
                    continue
                gross = (W + EXT_T) * (D + EXT_T)
                ar = Wf * dr + CORE3_W / 2 * (D - Ye)
                cands.append((gross, ar, {"D": D}))
            else:
                front = (W + EXT_T) * (Yf + EXT_T)
                if front >= fp:
                    continue
                neck = Yf - Ye >= NECK_MIN - 1e-9
                base = max(3.2 * n_bed, 2.6 if neck else 4.6) + 4.4
                for dr3 in _fr(base - 0.6, base + 1.2, 0.2):
                    D = _r(Yf + dr3)
                    if D + EXT_T + 0.05 > bd_max + 1e-9:
                        continue
                    wr = math.floor(((fp - front) / dr3 - EXT_T) * 10 + 1e-6) / 10
                    wr = W if wr >= W - 0.2 else wr
                    # arka blok çekirdekten ya taşmalı (her yanda ≥ 0,5 m: ince duvar parçası kalmasın) ya da tam genişlik
                    if wr < CORE3_W + 1.0 or not _center_dims(wr, dr3, n_bed, neck)[0]:
                        continue
                    gross = front + (wr + EXT_T) * dr3
                    ar = wr * dr3 + CORE3_W * (Yf - Ye)
                    cands.append((gross, ar, {"D": D, "Wr": wr}))
            for gross, ar, extra in cands:
                if gross > fp * 1.0005:
                    continue
                per = gross / n
                score = (4 * (fp - gross) / fp + abs(ar - Af) / Af + 0.3 * abs(per - target) / target
                         + 0.02 * abs(sd - 4.4) + 0.02 * abs(bdep - 3.3))
                if best is None or score < best[0] - 1e-9:
                    best = (score, {"n": n, "Wf": Wf, "Yf": Yf, "Ye": Ye, "W": W, "gross": round(gross, 2), **extra})
    return None if best is None else best[1]


def multi_choice(fp, wanted, upf, bw=math.inf, bd=math.inf):
    """Kat başına 3–4 daire kararı ve geometrisi: (n, tip, geom) veya None. 'auto'da önce tahmin edilen n, sonra
    diğeri (3↔4) istenen tiple denenir (tip küçültülmez, 1–2 daire yoluna düşülür); açık 3/4'te tip küçültülebilir."""
    n0 = units_for(fp, wanted, upf)
    if not n0:
        return None
    ns = [n0] if upf in (3, 4) else [n0, 7 - n0]
    types = _multi_types(wanted, fp, n0)
    if upf not in (3, 4):
        types = types[:1]
    for t in types:
        for n in ns:
            g = _multi_search(n, fp, bw, bd, UNIT_TYPES[t][1], UNIT_GROSS[t])
            if g:
                return n, t, g
    return None


def quick_envelope(q):
    """Hızlı mod: kat başına 3–4 daire seçilecekse sanal parselin yapılaşma kutusu (brüt genişlik, derinlik; m)."""
    fp = q["gross_area"] / int(q["floors"])
    c = multi_choice(fp, q.get("unit_type", "auto"), q.get("units_per_floor", "auto"))
    if not c:
        return None
    g = c[2]
    return round(g["W"] + EXT_T + 0.05, 2), round(g["D"] + EXT_T + 0.05, 2)


def _multi_reason(n, fp, bw, bd, types):
    free = next((g for t in types if (g := _multi_search(n, fp, math.inf, math.inf, UNIT_TYPES[t][1],
                                                          UNIT_GROSS[t]))), None)
    if free:
        return (f"kat başına {n} daire için yapılaşma alanı yetmiyor: {bw:.1f} × {bd:.1f} m mevcut, en az ≈ "
                f"{free['W'] + EXT_T + 0.05:.1f} × {free['D'] + EXT_T + 0.05:.1f} m gerekir (ortada {CORE3_W:g} m "
                f"çekirdek, iki yanında birer ön daire, arkada {n - 2} daire)")
    return (f"kat başına {n} daire bu kat alanına ({fp:.0f} m²) yerleşmiyor: {n} × "
            f"{'/'.join(types)} için daire başına ≈ {fp / n:.0f} m² brüt kalıyor — kat başı daire sayısını "
            "azaltın veya kat alanını artırın")


# ------------------------------------------------------------------ kütle

def _multi_massing(fp, W, D, bw, bd, sd, fr, rr, wanted, upf, quick):
    """Kat başına 3–4 daire: tip/sayı seç, geometriyi parsele yerleştir. Uygun yoksa None."""
    c = multi_choice(fp, wanted, upf, bw, bd)
    if not c:
        return None
    n, t, g = c
    width, depth = g["W"], g["D"]
    ox = _ceil05(sd + EXT_T / 2 + max(0.0, bw - EXT_T - width) / 2)
    oy = _ceil05(fr + EXT_T / 2)
    if ox + width + EXT_T / 2 > W - sd + 1e-6 or oy + depth + EXT_T / 2 > D - rr + 1e-6:
        return None
    warnings = []
    if wanted not in ("auto", t):
        warnings.append(f"{wanted} kat başına {n} daireli yerleşimde {'bu alan-kat kombinasyonuna' if quick else 'bu parsele'} "
                        f"sığmıyor; {t} önerildi")
    per = g["gross"] / n
    if per > 1.5 * UNIT_GROSS[t]:
        warnings.append(f"daireler hedef brüt alanın çok üzerinde (≈{per:.0f} m², {t} hedefi ≈{UNIT_GROSS[t]} m²) — "
                        "daire tipini veya kat başı daire sayısını gözden geçirin")
    return {"footprint": (width, depth), "origin": (ox, oy), "unit_type": t, "layout": f"core{n}",
            "units_per_floor": n, "modules": 1, "geom": g, "warnings": warnings}


def massing(parcel, zoning, program):
    W, D = parcel["width"], parcel["depth"]
    A = W * D
    fr, sd, rr = zoning.get("front", 5), zoning.get("side", 3), zoning.get("rear", 3)
    bw, bd = W - 2 * sd, D - fr - rr
    if bw < 8 or bd < 8:
        raise ValueError(f"çekme mesafelerinden sonra yapılaşma alanı çok küçük ({bw:.1f} × {bd:.1f} m)")
    taks, kaks = zoning.get("taks", 0.4), zoning.get("kaks", 1.2)
    max_floors = zoning.get("max_floors", 5)
    ex = zoning.get("emsal_disi_pct", 0) or 0       # ortak alan emsal dışı payı, % brüt (eski girdi)
    ex_m2 = zoning.get("emsal_disi_m2") or 0         # ortak alan (merdiven/asansör/hol) emsal dışı alanı, m²
    hmax = zoning.get("max_height")                  # yençok / saçak kotu sınırı (m)
    pre_warn = []
    if hmax:
        fh = zoning.get("floor_height", 3.0)
        by_h = int(hmax / fh + 1e-6)
        if by_h < 1:
            raise ValueError(f"yençok/saçak sınırı {hmax:g} m, kat yüksekliği {fh:g} m — tek kat bile sığmıyor")
        if by_h < max_floors:
            pre_warn.append(f"yençok/saçak sınırı {hmax:g} m ve kat yüksekliği {fh:g} m ile en çok {by_h} kat yapılabilir "
                            f"(imar kat sınırı {max_floors}); kat sayısı {by_h} ile sınırlandı")
            max_floors = by_h
    upf = program.get("units_per_floor", "auto")
    quick = bool(program.get("quick_area"))
    where = "bu alan-kat kombinasyonu (sanal parsel)" if quick else "parsel bu imar koşullarında"
    wanted = program.get("unit_type", "2+1")
    target_net = UNIT_TYPES["2+1" if wanted == "auto" else wanted][0]

    max_fp = min(taks * A, bw * bd)
    total = kaks * A + ex_m2 if ex_m2 else kaks * A / (1 - ex / 100)   # emsale girmeyen alanla birlikte izin verilen brüt alan
    floors = max(1, min(max_floors, math.ceil(total / max_fp - 1e-9)))
    fp = min(max_fp, total / floors)
    warnings = list(pre_warn)
    n_multi = units_for(fp, wanted, upf)
    if n_multi:
        res = _multi_massing(fp, W, D, bw, bd, sd, fr, rr, wanted, upf, quick)
        if res:
            res["warnings"] = pre_warn + list(res.get("warnings", []))
            return {"parcel_area": A, "buildable": (bw, bd), "floors": floors, **res}
        if upf in (3, 4):
            raise ValueError(_multi_reason(n_multi, fp, bw, bd, _multi_types(wanted, fp, n_multi)))
    elif upf not in ("auto", 1, 2):
        raise ValueError(f"kat başına daire sayısı {upf} desteklenmiyor (otomatik, 1, 2, 3 veya 4)")
    # Tek çekirdek + 2 daire modülü, hedef daireden çok büyük bir oturuma bölünemez. Eskiden oturum bu modüle
    # kırpılıyordu (5000 m²/10 kat → 2743 m²). Şimdi kat başına birden çok çekirdek modülü (her biri 2 daire)
    # ve derinlik taranır; arazi modunda uygun çözüm yoksa eski kırpma korunur ve KAKS uyarısı düşer.
    cap = module_cap(wanted)
    n_mod, choice = 1, None
    if upf == "auto" and fp > cap:
        n_bed = UNIT_TYPES["2+1" if wanted == "auto" else wanted][1]
        for _ in range(4):
            choice = _module_search(fp, bw, bd, n_bed, target_net, min_modules=1 if quick else 2)
            if choice is None or choice[1] * choice[2] >= fp * 0.97 or floors >= max_floors:
                break
            # oturum yapılaşma genişliğine sığmadı: izin varsa kat ekleyip kat alanını küçült
            floors = min(max_floors, math.ceil(total / (choice[1] * choice[2]) - 1e-9))
            fp = min(max_fp, total / floors)
        if choice is None and not quick:
            fp = cap
        elif choice:
            fp = min(fp, choice[1] * choice[2])
    if choice:
        n_mod, width, depth = choice
    else:
        # derinlik 10–15 m aralığında, genişlik yapılaşma alanına sığacak şekilde
        depth = min(bd, max(10.0, min(15.0, fp / min(bw, 26))))
        width = min(bw, fp / depth)
        if width < 2 * 5.5 + CORE_W:
            width = min(bw, 2 * 5.5 + CORE_W)
            depth = min(bd, fp / width)
    # brüt ölçü → aks ölçüsü (dış duvar yarı kalınlıkları), sınırı aşmamak için aşağı yuvarla
    width, depth = _floor05(width - EXT_T), _floor05(depth - EXT_T)
    # aks başlangıcı: DIŞ YÜZ çekme çizgisinin içinde kalsın (yukarı yuvarla), karşı kenarı buna göre kırp
    ox = _ceil05(sd + EXT_T / 2 + max(0.0, bw - EXT_T - width) / 2)
    oy = _ceil05(fr + EXT_T / 2)
    width = min(width, _floor05(W - sd - EXT_T / 2 - ox))
    depth = min(depth, _floor05(D - rr - EXT_T / 2 - oy))
    if upf == "auto":
        upf = 2 * n_mod if n_mod > 1 else (2 if (width - CORE_W) / 2 >= 5.0 else 1)
    unit_w = (width - n_mod * CORE_W) / upf
    avail_net = unit_w * depth * 0.88
    order = list(UNIT_TYPES)
    candidates = order[::-1] if wanted == "auto" else order[:order.index(wanted) + 1][::-1]
    chosen, layout = None, None
    for ut in candidates:
        lay = unit_layout(unit_w, depth, UNIT_TYPES[ut][1])
        if lay and UNIT_TYPES[ut][0] <= avail_net * 1.3:
            chosen, layout = ut, lay
            break
    if chosen is None:
        raise ValueError(f"{where} daire yerleşimine yetmiyor (daire genişliği {unit_w:.1f} m)")
    if wanted not in ("auto", chosen):
        warnings.append(f"{wanted} {'bu alan-kat kombinasyonuna' if quick else 'bu parsele'} sığmıyor "
                        f"(daire {unit_w:.1f} × {depth:.1f} m); {chosen} önerildi")
    unet = unit_w * depth * 0.88
    if unet > 1.6 * UNIT_TYPES[chosen][0]:
        warnings.append(f"daireler hedef net alanın çok üzerinde (≈{unet:.0f} m², {chosen} hedefi "
                        f"{UNIT_TYPES[chosen][0]} m²) — daire tipini veya kat başı daire sayısını gözden geçirin")
    return {"parcel_area": A, "buildable": (bw, bd), "footprint": (width, depth), "origin": (ox, oy),
            "floors": floors, "unit_type": chosen, "layout": layout, "units_per_floor": upf, "modules": n_mod,
            "warnings": warnings}


# ------------------------------------------------------------------ kat planı

def _unit_rects(x0, x1, D, n_bed, mirror, tag):
    """Bir daire: ön (y küçük) gündüz, arka gece bölgesi. mirror → çekirdek solda."""
    w = x1 - x0
    day_d = _r(max(4.8, min(6.0, D * 0.45)))
    night_y0 = day_d + HALL_BAND
    rects = []

    def xs(a, b):  # birim [0,1] aralığını çekirdekten dışa doğru eşle
        if mirror:   # çekirdek solda (x0 tarafı)
            return x0 + a * w, x0 + b * w
        return x1 - b * w, x1 - a * w

    n_back = min(n_bed, int((w - BATH_W) // MIN_BED_W))
    n_front = n_bed - n_back
    # gündüz: mutfak çekirdek tarafında, (arkaya sığmayan oda), salon dış köşede
    kw = min(0.38, 2.8 / w)
    fw = MIN_BED_W / w * n_front
    kx0, kx1 = xs(0, kw)
    rects.append(Rect(_r(kx0), 0, _r(kx1), day_d, f"{tag}/Mutfak"))
    for i in range(n_front):
        fx0, fx1 = xs(kw + i * MIN_BED_W / w, kw + (i + 1) * MIN_BED_W / w)
        rects.append(Rect(_r(fx0), 0, _r(fx1), day_d, f"{tag}/Yatak Odası {n_back + i + 1}"))
    sx0, sx1 = xs(kw + fw, 1)
    rects.append(Rect(_r(sx0), 0, _r(sx1), day_d, f"{tag}/Salon"))
    rects.append(Rect(_r(x0), day_d, _r(x1), night_y0, f"{tag}/Hol"))
    # gece: banyo çekirdek tarafında, sonra yatak odaları
    bath = BATH_W / w
    parts = [("Banyo", bath)] + [(f"Yatak Odası {i + 1}", (1 - bath) / n_back) for i in range(n_back)]
    eb = 1.8 / w
    if n_bed >= 3 and parts[-1][1] - eb >= MIN_BED_W / w:  # ebeveyn banyosu: son odadan ayır
        parts[-1] = (parts[-1][0], parts[-1][1] - eb)
        parts.append(("Ebeveyn Banyo", eb))
    a = 0.0
    for name, frac in parts:
        bx0, bx1 = xs(a, a + frac)
        rects.append(Rect(_r(bx0), night_y0, _r(bx1), D, f"{tag}/{name}"))
        a += frac
    return rects


MIN_BED_W, BATH_W = 2.8, 2.2


def _unit_rects_deep(x0, x1, D, n_bed, mirror, tag):
    """Dar-derin daire: önde salon (+açık mutfak), hol çekirdek boyunca derinliğe uzanır,
    banyo ve yatak odaları dış (yan) cepheye dizilir."""
    w = x1 - x0
    day_d = _r(max(4.8, min(6.0, D * 0.38)))
    hall = 1.2
    if mirror:  # çekirdek solda
        hx0, hx1, ox0, ox1 = x0, x0 + hall, x0 + hall, x1
    else:
        hx0, hx1, ox0, ox1 = x1 - hall, x1, x0, x1 - hall
    rects = []
    if w >= 7.0:
        kw = 2.8
        kx = (x1 - kw, x1) if not mirror else (x0, x0 + kw)  # mutfak çekirdek tarafında
        sx = (x0, x1 - kw) if not mirror else (x0 + kw, x1)
        rects += [Rect(_r(kx[0]), 0, _r(kx[1]), day_d, f"{tag}/Mutfak"),
                  Rect(_r(sx[0]), 0, _r(sx[1]), day_d, f"{tag}/Salon")]
    else:
        rects.append(Rect(_r(x0), 0, _r(x1), day_d, f"{tag}/Salon + Açık Mutfak"))
    rects.append(Rect(_r(hx0), day_d, _r(hx1), D, f"{tag}/Hol"))
    rest = D - day_d
    bed_d = (rest - BATH_W) / n_bed
    y = day_d
    for name, dd in [("Banyo", BATH_W)] + [(f"Yatak Odası {i + 1}", bed_d) for i in range(n_bed)]:
        y1 = D if name.endswith(str(n_bed)) and name.startswith("Yatak") else _r(y + dd)
        rects.append(Rect(_r(ox0), _r(y), _r(ox1), y1, f"{tag}/{name}"))
        y = y1
    return rects


def unit_layout(unit_w, depth, n_bed):
    """Uygun yerleşim tipi: 'wide' (ön/arka bölge) veya 'deep' (yan cepheye dizilim); sığmazsa None."""
    n_back = min(n_bed, int((unit_w - BATH_W) // MIN_BED_W))
    n_front = n_bed - n_back
    if n_back >= 1 and n_front <= 1 and unit_w - 2.8 - n_front * MIN_BED_W >= 3.6 and depth <= 16:
        return "wide"
    day_d = max(4.8, min(6.0, depth * 0.38))
    if unit_w - 1.2 >= 3.0 and (depth - day_d - BATH_W) / n_bed >= MIN_BED_W:
        return "deep"
    return None


def _mirror(rects, W):
    return [Rect(_r(W - r.x1), r.y0, _r(W - r.x0), r.y1, r.name, r.kind, r.mod) for r in rects]


def _front_unit(w, d, n_bed, tag):
    """Sol ön daire x∈[0,w], y∈[0,d]; çekirdek sağda (x=w). Salon önde tam genişlik (ön + yan cephe), hol çekirdek
    boyunca, mutfak yan cephede salona açılır, banyo hole; yatak odaları yan cepheye dizilir."""
    _, sd, bd = _front_dims(w, d, n_bed)
    sd, hx = _r(sd), _r(w - HOL_W)
    kx = _r(hx - BATH_W)
    rs = [Rect(0, 0, w, sd, f"{tag}/Salon"), Rect(hx, sd, w, d, f"{tag}/Hol"),
          Rect(0, sd, kx, _r(sd + KD), f"{tag}/Mutfak"), Rect(kx, sd, hx, _r(sd + KD), f"{tag}/Banyo")]
    y = _r(sd + KD)
    for i in range(n_bed):
        y1 = d if i == n_bed - 1 else _r(y + bd)
        if i == n_bed - 1 and n_bed >= 3 and hx - 1.8 >= MIN_BED_W:   # ebeveyn banyosu: son odanın iç ucunda
            rs += [Rect(0, y, _r(hx - 1.8), y1, f"{tag}/Yatak Odası {i + 1}"),
                   Rect(_r(hx - 1.8), y, hx, y1, f"{tag}/Ebeveyn Banyo")]
        else:
            rs.append(Rect(0, y, hx, y1, f"{tag}/Yatak Odası {i + 1}"))
        y = y1
    return rs


def _rear4_unit(cx0, xm, yf, ye, D, n_bed, tag):
    """Sol arka daire (4'lü): dış bölüm x∈[0,cx0]×[yf,D] (arkada salon, yan cepheye yatak odaları), çekirdeğin
    arkasında x∈[cx0,xm]×[ye,D] hol + banyo + mutfak şeridi (mutfak arka cephede)."""
    _, sd, bd = _rear4_dims(cx0, D - yf, D - ye, n_bed)
    hx = _r(cx0 + HOL_W)
    ys = _r(D - sd)
    kd = min(D - ye - 2.4, 4.4)            # mutfak arka cephede; uzun şeritte banyo ile arasında depo
    rest = D - ye - 2.4 - kd
    yb = _r(ye + 2.4 + (rest if rest < 1.2 else 0))
    yk = _r(D - kd)
    rs = [Rect(0, ys, cx0, D, f"{tag}/Salon"), Rect(cx0, ye, hx, D, f"{tag}/Hol"),
          Rect(hx, ye, xm, yb, f"{tag}/Banyo"), Rect(hx, yk, xm, D, f"{tag}/Mutfak")]
    if yk - yb > 1e-6:
        rs.append(Rect(hx, yb, xm, yk, f"{tag}/Depo"))
    y = ys
    for i in range(n_bed):
        y0 = yf if i == n_bed - 1 else _r(y - bd)
        rs.append(Rect(0, y0, cx0, y, f"{tag}/Yatak Odası {i + 1}"))
        y = y0
    return rs


def _center_unit(b0, b1, cx0, cx1, yf, ye, D, n_bed, tag):
    """Arka orta daire (3'lü): arkada tam genişlik salon (arka + iki yan cephe); üstünde sol sütun mutfak (+banyo),
    ortada hol (çekirdeğin arka bandına bağlanır), sağ sütun yatak odaları. Boyun varsa banyo/depo çekirdeğe bitişik."""
    neck = yf - ye >= NECK_MIN - 1e-9
    _, sd3, bd = _center_dims(b1 - b0, D - yf, n_bed, neck)
    xm = _r((cx0 + cx1) / 2)
    hx0, hx1 = _r(xm - HOL_W / 2), _r(xm + HOL_W / 2)
    ys = _r(D - sd3)
    rs = [Rect(b0, ys, b1, D, f"{tag}/Salon"), Rect(hx0, ye, hx1, ys, f"{tag}/Hol")]
    if neck:
        rs += [Rect(cx0, ye, hx0, yf, f"{tag}/Banyo"), Rect(hx1, ye, cx1, yf, f"{tag}/Depo"),
               Rect(b0, yf, hx0, ys, f"{tag}/Mutfak")]
    else:
        rs += [Rect(b0, yf, hx0, _r(yf + 2.2), f"{tag}/Banyo"), Rect(b0, _r(yf + 2.2), hx0, ys, f"{tag}/Mutfak")]
    y = ys
    for i in range(n_bed):
        y0 = yf if i == n_bed - 1 else _r(y - bd)
        rs.append(Rect(hx1, y0, b1, y, f"{tag}/Yatak Odası {i + 1}"))
        y = y0
    return rs


def multi_plan(g, n_bed):
    """Kat başına 3 (T kütle) veya 4 (dikdörtgen) daireli tek çekirdekli kat. Dönen (rects, cores)."""
    Wf, Yf, Ye, W, D = g["Wf"], g["Yf"], g["Ye"], g["W"], g["D"]
    cx0, cx1, xm = Wf, _r(Wf + CORE3_W), _r(Wf + CORE3_W / 2)
    extra = Ye - (H1_MIN + STAIR_DEPTH + HB_MIN)
    h1 = _r(H1_MIN + extra / 2)
    yc = _r(h1 + STAIR_DEPTH)
    left = _front_unit(Wf, Yf, n_bed, "Daire 1")
    rects = left + _mirror([Rect(r.x0, r.y0, r.x1, r.y1, r.name.replace("Daire 1/", "Daire 2/")) for r in left], W)
    if g["n"] == 4:
        rl = _rear4_unit(cx0, xm, Yf, Ye, D, n_bed, "Daire 3")
        rects += rl + _mirror([Rect(r.x0, r.y0, r.x1, r.y1, r.name.replace("Daire 3/", "Daire 4/")) for r in rl], W)
    else:
        wr = g["Wr"]
        b0 = _r(xm - wr / 2)
        rects += _center_unit(b0, _r(b0 + wr), cx0, cx1, Yf, Ye, D, n_bed, "Daire 3")
    sx, lx = _r(cx0 + STAIR_W), _r(cx0 + STAIR_W + STRIP_W)
    rects += [Rect(cx0, 0, cx1, h1, "Kat Holü", "core"), Rect(sx, h1, lx, yc, "Kat Holü", "core"),
              Rect(cx0, yc, cx1, Ye, "Kat Holü", "core"),
              Rect(cx0, h1, sx, yc, "Merdiven", "core"), Rect(lx, h1, cx1, yc, "Asansör/Şaft", "core")]
    return rects, [(cx0, cx1, h1)]


def floor_plan(width, depth, n_bed, layout, upf=2, modules=1, geom=None):
    """Kat planı: `modules` adet [daire | çekirdek | daire] modülü yan yana; `geom` verilirse (kat başına 3–4 daire)
    tek çekirdekli çok daireli yerleşim. Dönen (rects, cores); cores = [(cx0, cx1, sy), ...] her çekirdek için."""
    if geom:
        return multi_plan(geom, n_bed)
    fn = _unit_rects if layout == "wide" else _unit_rects_deep
    sy = _r(depth - STAIR_DEPTH)
    if upf == 1:  # çekirdek sağ yanda, tek daire
        cx0, cx1 = _r(width - CORE_W), width
        rects = fn(0, cx0, depth, n_bed, mirror=False, tag="Daire 1")
        spans = [(cx0, cx1)]
    else:
        rects, spans = [], []
        mw = width / modules
        for k in range(modules):
            m0, m1 = _r(k * mw) if k else 0.0, (_r((k + 1) * mw) if k < modules - 1 else width)
            cx0 = _r(m0 + (m1 - m0 - CORE_W) / 2)
            cx1 = _r(cx0 + CORE_W)
            for r in fn(m0, cx0, depth, n_bed, mirror=False, tag=f"Daire {2 * k + 1}"):
                r.mod = k
                rects.append(r)
            for r in fn(cx1, m1, depth, n_bed, mirror=True, tag=f"Daire {2 * k + 2}"):
                r.mod = k
                rects.append(r)
            spans.append((cx0, cx1))
    cores = []
    for k, (cx0, cx1) in enumerate(spans):
        sfx = f" {k + 1}" if len(spans) > 1 else ""
        rects += [Rect(cx0, 0, cx1, sy, f"Kat Holü{sfx}", "core", k),
                  Rect(cx0, sy, _r(cx0 + 2.8), depth, f"Merdiven{sfx}", "core", k),
                  Rect(_r(cx0 + 2.8), sy, cx1, depth, f"Asansör/Şaft{sfx}", "core", k)]
        cores.append((cx0, cx1, sy))
    return rects, cores


def _wall_segments(rects, width, depth):
    """Hücre kenarlarından tekil duvar aksları: {(orient, coord): [(s0, s1, t), ...]}."""
    edges = {}
    for r in rects:
        core = r.kind == "core"
        unit = r.name.split("/")[0] if (r.kind == "room" and "/" in r.name) else None
        for orient, c, s0, s1 in (("h", r.y0, r.x0, r.x1), ("h", r.y1, r.x0, r.x1),
                                   ("v", r.x0, r.y0, r.y1), ("v", r.x1, r.y0, r.y1)):
            t = CORE_T if core else INT_T
            edges.setdefault((orient, round(c, 3)), []).append((round(s0, 3), round(s1, 3), t, unit,
                                                                r.name if core else None))
    lines = {}
    for key, es in edges.items():
        orient, c = key
        pts = sorted({p for s0, s1, *_ in es for p in (s0, s1)})
        pieces = []
        for a, b in zip(pts, pts[1:]):
            m = (a + b) / 2
            cov = [e for e in es if e[0] <= m <= e[1]]
            if not cov:
                continue
            names = {e[4] for e in cov}
            if len(cov) >= 2 and len(names) == 1 and None not in names:
                continue   # aynı ortak mahalin (H biçimli kat holü) parçaları arası: duvar yok
            # dış duvar: kenarın yalnız bir yanında mahal var (T kütlede iç köşeler dahil)
            sides = [_covered(rects, m, c + d) if orient == "h" else _covered(rects, c + d, m) for d in (-1e-3, 1e-3)]
            if sides[0] != sides[1]:
                t = EXT_T
            else:
                t = max(e[2] for e in cov)
                if len({e[3] for e in cov if e[3]}) > 1:
                    t = max(t, CORE_T)   # iki farklı dairenin ortak duvarı: daire ayırma duvarı
            if pieces and abs(pieces[-1][1] - a) < 1e-6 and pieces[-1][2] == t:
                pieces[-1] = (pieces[-1][0], b, t)
            else:
                pieces.append((a, b, t))
        lines[key] = pieces
    return lines


def _covered(rects, x, y):
    return any(r.x0 < x < r.x1 and r.y0 < y < r.y1 for r in rects)


def _ext_edges(r, rects):
    """Mahalin dış cepheye bakan kenar parçaları: (orient, coord, s0, s1). Komşu mahalin kapladığı kısımlar düşülür."""
    out = []
    for orient, c, s0, s1, lo in (("h", r.y0, r.x0, r.x1, True), ("h", r.y1, r.x0, r.x1, False),
                                  ("v", r.x0, r.y0, r.y1, True), ("v", r.x1, r.y0, r.y1, False)):
        ivs = [(s0, s1)]
        for q in rects:
            if q is r:
                continue
            if orient == "h" and abs((q.y1 if lo else q.y0) - c) < 1e-6:
                a, b = q.x0, q.x1
            elif orient == "v" and abs((q.x1 if lo else q.x0) - c) < 1e-6:
                a, b = q.y0, q.y1
            else:
                continue
            nxt = []
            for u, v in ivs:
                if b <= u + 1e-9 or a >= v - 1e-9:
                    nxt.append((u, v))
                    continue
                if a > u:
                    nxt.append((u, a))
                if b < v:
                    nxt.append((b, v))
            ivs = nxt
        out += [(orient, c, u, v) for u, v in ivs if v - u > 1e-6]
    return out


WIN_W = {"Salon": 3.0, "Mutfak": 1.4, "Yatak": 1.6, "Banyo": 0.6, "Ebeveyn": 0.6}


def _shared(r, q):
    """İki dikdörtgenin ortak kenarı: (orient, coord, s0, s1) veya None."""
    for orient, a, b in (("v", r.x1, q.x0), ("v", r.x0, q.x1)):
        if abs(a - b) < 1e-6:
            s0, s1 = max(r.y0, q.y0), min(r.y1, q.y1)
            if s1 - s0 > 0.05:
                return orient, a, s0, s1
    for orient, a, b in (("h", r.y1, q.y0), ("h", r.y0, q.y1)):
        if abs(a - b) < 1e-6:
            s0, s1 = max(r.x0, q.x0), min(r.x1, q.x1)
            if s1 - s0 > 0.05:
                return orient, a, s0, s1
    return None


def _door(edge, width=0.9, at="mid"):
    orient, c, s0, s1 = edge
    avail = s1 - s0 - 0.2
    if avail < 0.7:
        return None
    w = min(width, avail)
    m = (s0 + s1) / 2 if at == "mid" else (s0 + 0.1 + w / 2 if at == "start" else s1 - 0.1 - w / 2)
    return (orient, c, _r(m - w / 2), _r(m + w / 2), "door")


def _openings(rects, width, depth, cores, ground):
    """Kural tabanlı açıklıklar: (orient, coord, s0, s1, kind) listesi. cores: [(cx0, cx1, sy), ...]."""
    if isinstance(cores, tuple):
        cores = [cores]
    ops = []

    def win(orient, c, a, b, w):
        w = min(w, b - a - 0.8)
        if w >= 0.5:
            m = (a + b) / 2
            ops.append((orient, c, _r(m - w / 2), _r(m + w / 2), "window"))

    for tag in sorted({r.name.split("/")[0] for r in rects if r.kind == "room"}):
        unit = [r for r in rects if r.name.startswith(tag + "/")]
        hol = next(r for r in unit if r.name.endswith("/Hol"))
        halls = [r for r in rects if r.kind == "core" and r.name.startswith("Kat Holü") and r.mod == hol.mod]
        rooms = [r for r in unit if r is not hol]
        for r in rooms:
            short = r.name.split("/")[1]
            ww = next((v for k, v in WIN_W.items() if short.startswith(k)), 1.4)
            ext = _ext_edges(r, rects)
            ext.sort(key=lambda e: -(e[3] - e[2]))
            for e in ext[:2 if short.startswith("Salon") else 1]:
                win(*e, ww if e is ext[0] else 2.0)
            # kapı: holle ortak kenar, yoksa holle bağlantılı komşu odaya
            edge = _shared(r, hol)
            if edge is None:
                for q in rooms:
                    if q is not r and _shared(q, hol) and _shared(r, q):
                        edge = _shared(r, q)
                        break
            if edge:
                d = _door(edge, 0.8 if "Banyo" in short else 0.9)
                if d:
                    ops.append(d)
        # daire girişi: kat holü ↔ daire holü, yoksa kat holüne bakan odaya
        entry = next((e for h in halls if (e := _shared(hol, h))), None)
        if entry is None:
            entry = next((e for r in rooms for h in halls if (e := _shared(r, h))), None)
        d = _door(entry, 1.0) if entry else None
        if d:
            ops.append(d)
    for cx0, cx1, sy in cores:
        if ground:
            ops.append(("h", 0, _r((cx0 + cx1) / 2 - 0.6), _r((cx0 + cx1) / 2 + 0.6), "door"))
        else:
            win("h", 0, cx0, cx1, 1.4)
        ops.append(("h", sy, _r(cx0 + 0.5), _r(cx0 + 1.6), "door"))
    # asansör kabin kapısı: kuyunun kat holüne bakan kenarında
    for lift in (r for r in rects if r.kind == "core" and r.name.startswith("Asansör")):
        edge = next((e for h in rects if h.kind == "core" and h.name.startswith("Kat Holü") and h.mod == lift.mod
                     and (e := _shared(lift, h))), None)
        d = _door(edge, 0.9) if edge else None
        if d:
            ops.append(d)
    return ops


def _stair_elements(lvl, ox, oy, z, fh, core):
    """Kat yüksekliğine ulaşan U merdiven: ön kol (holden arkaya çıkar) + arka sahanlık + dönüş kolu (öne iner/çıkar).
    Merdiven evi iç ölçüsü ≈ 2,6 × 5,4 m; kol genişliği 1,2 m, basamak 28 cm, rıht = kat yüksekliği / 2n."""
    cx0, cx1, sy = core
    risers = max(2, int(round(fh / 0.17)))
    risers += risers % 2                        # iki eşit kol
    n, rise, run, w = risers // 2, round(fh / risers, 4), 0.28, 1.2
    # kat holü önünde ≥1,2 m serbest geçiş (kapı sy'de), arkada ≥1,2 m sahanlık
    y0 = sy + max(1.2, min(1.7, STAIR_DEPTH - 0.1 - n * run - 1.2))
    y1 = y0 + n * run                           # sahanlık başlangıcı
    land = [ox + cx0 + 0.1, oy + y1, z]
    return [
        {"type": "stairs", "name": f"{lvl}/merdiven_kol1", "tag": "stone", "level": lvl,
         "origin": [round(ox + cx0 + 0.15 + w, 3), round(oy + y0, 3), z], "width": w, "steps": n,
         "rise": rise, "run": run, "rotation_z": 90},
        {"type": "box", "name": f"{lvl}/merdiven_sahanlik", "tag": "stone", "level": lvl,
         "origin": [round(v, 3) for v in land], "size": [2.6, round(STAIR_DEPTH - 0.1 - (y1 - sy), 3), round(n * rise, 3)]},
        {"type": "stairs", "name": f"{lvl}/merdiven_kol2", "tag": "stone", "level": lvl,
         "origin": [round(ox + cx0 + 0.25 + w, 3), round(oy + y1, 3), round(z + n * rise, 3)], "width": w, "steps": n,
         "rise": rise, "run": run, "rotation_z": -90},
    ]


def _room_poly(r, lines):
    def half(orient, c, s_mid):
        for s0, s1, t in lines.get((orient, round(c, 3)), []):
            if s0 - 1e-6 <= s_mid <= s1 + 1e-6:
                return t / 2
        return INT_T / 2
    xm, ym = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
    a = r.x0 + half("v", r.x0, ym)
    b = r.x1 - half("v", r.x1, ym)
    c = r.y0 + half("h", r.y0, xm)
    d = r.y1 - half("h", r.y1, xm)
    return [[round(a, 3), round(c, 3)], [round(b, 3), round(c, 3)], [round(b, 3), round(d, 3)], [round(a, 3), round(d, 3)]]


def _tag_key(tag):
    n = tag.rsplit(" ", 1)[-1]
    return (0, int(n), tag) if n.isdigit() else (1, 0, tag)


def _outline(rects, width, depth):
    """Brüt kat konturu (dış yüzler, aks + EXT_T/2). Dikdörtgen kütlede 4 köşe; T kütlede birleşik çokgen."""
    h = EXT_T / 2
    rect = [(-h, -h), (width + h, -h), (width + h, depth + h), (-h, depth + h)]
    from shapely.geometry import box
    from shapely.ops import unary_union
    u = unary_union([box(r.x0, r.y0, r.x1, r.y1) for r in rects])
    if abs(u.area - width * depth) < 1e-3:
        return rect
    g = u.buffer(h, join_style=2).simplify(1e-4)
    pts = [(round(x, 3), round(y, 3)) for x, y in list(g.exterior.coords)[:-1]]
    if g.exterior.is_ccw is False:
        pts = pts[::-1]
    return pts


def _room_polys(rects, lines):
    """Mahal adı → (tür, iç yüz çokgeni). Aynı adlı çekirdek parçaları (H kat holü) tek mahalde birleşir:
    parçaların birleşimi − duvar gövdeleri."""
    groups = {}
    for r in rects:
        groups.setdefault(r.name, []).append(r)
    out = {}
    for name, rs in groups.items():
        if len(rs) == 1:
            out[name] = (rs[0].kind, _room_poly(rs[0], lines))
            continue
        from shapely.geometry import box
        from shapely.ops import unary_union
        area = unary_union([box(r.x0, r.y0, r.x1, r.y1) for r in rs])
        walls = unary_union([box(a, c - t / 2, b, c + t / 2) if o == "h" else box(c - t / 2, a, c + t / 2, b)
                             for (o, c), ps in lines.items() for a, b, t in ps])
        p = area.difference(walls)
        if p.geom_type != "Polygon":
            p = max(p.geoms, key=lambda g: g.area)
        p = p.simplify(1e-4)
        out[name] = (rs[0].kind, [[round(x, 3), round(y, 3)] for x, y in list(p.exterior.coords)[:-1]])
    return out


def roof_parapet(outline, z, t=EXT_T, h=0.9):
    """Çatı korkuluğu: kat konturunun her (eksene paralel) kenarı için içe doğru bir kutu.
    Önceki sürüm tek kutuyu yanlış köşeden başlatıyor ve T/L kütlelerde binanın dışına taşıyordu."""
    from shapely.geometry import Point, Polygon
    poly, out = Polygon(outline), []
    pts = [tuple(p) for p in outline]
    for i, ((x0, y0), (x1, y1)) in enumerate(zip(pts, pts[1:] + pts[:1])):
        if abs(y0 - y1) < 1e-6 and abs(x0 - x1) > 1e-6:                      # yatay kenar
            lo, hi = sorted((x0, x1)); inside_up = poly.contains(Point((lo + hi) / 2, y0 + t / 2))
            origin, size = [round(lo, 3), round(y0 if inside_up else y0 - t, 3), z], [round(hi - lo, 3), t, h]
        elif abs(x0 - x1) < 1e-6 and abs(y0 - y1) > 1e-6:                    # dikey kenar
            lo, hi = sorted((y0, y1)); inside_right = poly.contains(Point(x0 + t / 2, (lo + hi) / 2))
            origin, size = [round(x0 if inside_right else x0 - t, 3), round(lo, 3), z], [t, round(hi - lo, 3), h]
        else:
            continue                                                         # eğik kenar: atla
        out.append({"type": "box", "name": f"cati_parapet{i}", "tag": "wall", "level": "Çatı", "origin": origin, "size": size})
    return out


def generate(parcel, zoning, program):
    m = massing(parcel, zoning, program)
    width, depth = m["footprint"]
    ox, oy = m["origin"]
    fh = zoning.get("floor_height", 3.0)
    slab_t = 0.2
    n_bed = UNIT_TYPES[m["unit_type"]][1]
    rects, cores = floor_plan(width, depth, n_bed, m["layout"], m["units_per_floor"], m.get("modules", 1),
                              m.get("geom"))
    core = cores[0]
    lines = _wall_segments(rects, width, depth)
    P = lambda x, y: [round(ox + x, 3), round(oy + y, 3)]

    elements = [{"type": "slab", "name": "parsel", "tag": "terrain", "role": "site", "level": "Arsa",
                 "points": [[0, 0], [parcel["width"], 0], [parcel["width"], parcel["depth"]], [0, parcel["depth"]]],
                 "z": -0.02, "thickness": 0.3},
                {"type": "slab", "name": "giris_yolu", "tag": "stone", "role": "paving", "level": "Arsa",
                 "points": [P((core[0] + core[1]) / 2 - 1.0, -oy), P((core[0] + core[1]) / 2 + 1.0, -oy),
                            P((core[0] + core[1]) / 2 + 1.0, 0), P((core[0] + core[1]) / 2 - 1.0, 0)],
                 "z": 0.02, "thickness": 0.05}]
    outline = [P(x, y) for x, y in _outline(rects, width, depth)]
    room_polys = _room_polys(rects, lines)
    tags = sorted({r.name.split("/")[0] for r in rects if r.kind == "room"}, key=_tag_key)
    units = []
    for f in range(m["floors"]):
        lvl = f"Kat {f}" if f else "Zemin Kat"
        z = f * fh
        elements.append({"type": "slab", "name": f"{lvl}/doseme", "tag": "concrete", "role": "floor", "level": lvl,
                         "points": outline, "z": z, "thickness": slab_t})
        ops = _openings(rects, width, depth, cores, ground=(f == 0))
        wi = 0
        for (orient, c), pieces in sorted(lines.items()):
            for s0, s1, t in pieces:
                wi += 1
                mine = sorted([(a, b, k) for o, cc, a, b, k in ops if o == orient and abs(cc - c) < 1e-6
                               and a >= s0 - 1e-6 and b <= s1 + 1e-6])
                start, end = ((s0, c), (s1, c)) if orient == "h" else ((c, s0), (c, s1))
                ext = t == EXT_T   # _wall_segments dış kenara (tek yanında mahal olan) yalnız dış duvar kalınlığı verir
                elements.append({
                    "type": "wall", "name": f"{lvl}/D{wi:02d}", "tag": "wall", "level": lvl, "exterior": ext,
                    "start": P(*start), "end": P(*end), "thickness": t, "height": fh - slab_t, "base_z": z,
                    "openings": [{"offset": round(a - s0, 3), "width": round(b - a, 3), "kind": k,
                                  **({"sill": 0.9, "height": 1.4 if (b - a) < 2 else 1.6} if k == "window"
                                     else {"height": 2.1, "leaf": True})} for a, b, k in mine]})
        for name, (kind, pts) in room_polys.items():
            poly = [P(x, y) for x, y in pts]
            elements.append({"type": "room", "name": f"{lvl}/{name}", "level": lvl, "points": poly, "z": z,
                             "height": fh - slab_t, "role": "common" if kind == "core" else "room"})
        for k, c in enumerate(cores):
            for st in _stair_elements(lvl, ox, oy, z, fh, c):
                if len(cores) > 1:
                    st["name"] = st["name"].replace("/merdiven", f"/merdiven{k + 1}")
                elements.append(st)
        for tag in tags:
            units.append({"level": lvl, "unit": tag, "type": m["unit_type"]})
    elements.append({"type": "slab", "name": "cati", "tag": "roof", "role": "roof", "level": "Çatı",
                     "points": outline, "z": m["floors"] * fh, "thickness": slab_t})
    elements += roof_parapet(outline, m["floors"] * fh)

    # uygunluk kontrolü
    A = m["parcel_area"]
    from .quantities import polygon_area
    fp_gross = ((width + EXT_T) * (depth + EXT_T) if len(outline) == 4
                else polygon_area([tuple(p) for p in _outline(rects, width, depth)]))
    gross_total = fp_gross * m["floors"]
    unit_net = {}
    for r in rects:
        if r.kind == "room":
            u = r.name.split("/")[0]
            unit_net[u] = unit_net.get(u, 0) + polygon_area([tuple(p) for p in _room_poly(r, lines)])
    h = EXT_T / 2
    sb, sb_detail, sb_ok = setback_checks(parcel["width"], parcel["depth"],
                                          (ox - h, oy - h, ox + width + h, oy + depth + h), zoning)
    ex = emsal_disi_m2(zoning, gross_total)           # emsale girmeyen alan (m²)
    kaks_val = (gross_total - ex) / A                 # emsale giren brüt alan / parsel
    fh = zoning.get("floor_height", 3.0)
    checks = {
        "taks": {"value": round(fp_gross / A, 3), "limit": zoning.get("taks", 0.4), "ok": fp_gross / A <= zoning.get("taks", 0.4) + 1e-3},
        "kaks": {"value": round(kaks_val, 3), "limit": zoning.get("kaks", 1.2), "ok": kaks_val <= zoning.get("kaks", 1.2) + 1e-3},
        "floors": {"value": m["floors"], "limit": zoning.get("max_floors", 5), "ok": m["floors"] <= zoning.get("max_floors", 5)},
        "setbacks": sb, "setbacks_detail": sb_detail, "setback_ok": sb_ok,
    }
    if zoning.get("max_height"):
        hv = round(m["floors"] * fh, 2)
        checks["height"] = {"value": hv, "limit": zoning["max_height"], "ok": hv <= zoning["max_height"] + 1e-3}
    if ex:
        cap = 0.30 * gross_total                       # emsal dışı alan brüt alanın en çok %30'u
        checks["emsal_disi"] = {"value": round(ex, 2), "limit": round(cap, 2), "ok": ex <= cap + 1e-6, "unit": "m²"}
    warnings = list(m["warnings"]) + setback_warnings(sb_detail)
    extra = {}
    qa = program.get("quick_area")
    if qa:   # hızlı mod: istenen alan tutturuldu mu
        dev = (gross_total - qa) / qa * 100
        extra["area_deviation_pct"] = round(dev, 2)
        extra["virtual_parcel"] = True
        if abs(dev) > 3:
            warnings.append(f"istenen {_ti(qa)} m², üretilen {_ti(gross_total)} m² (sapma %{dev:+.1f})")
    else:    # arazi modu: emsal kullanımı
        kaks_area = zoning.get("kaks", 1.2) * A
        used = (gross_total - ex) / kaks_area * 100 if kaks_area else 0.0
        extra["kaks_used_pct"] = round(used, 1)
        if used < 85:
            warnings.append(f"KAKS kullanımı %{used:.0f} (izin verilen {_ti(kaks_area)} m², üretilen {_ti(gross_total)} m²) — "
                            "kat adedi, daire tipi veya TAKS sınırını gözden geçirin")
    from .imar import imar_summary
    report = {
        **m, "warnings": warnings, **extra, "imar_ozeti": imar_summary(zoning, A, checks), "footprint_gross": round(fp_gross, 2), "gross_total": round(gross_total, 2),
        "unit_count": len(units), "unit_net_area": {k: round(v, 2) for k, v in unit_net.items()},
        "unit_target_net": UNIT_TYPES[m["unit_type"]][0], "checks": checks,
        "note": "Şematik ön tasarım — emsal hesabı yaklaşık (emsal dışı alan yalnız girilen değerle (m²) düşülür); mimar kontrolü gerekir. "
                "Duvar metrajı aks uzunluğuyla: T/L birleşimlerinde ~%1–2 fazla sayım içerir.",
    }
    return elements, report

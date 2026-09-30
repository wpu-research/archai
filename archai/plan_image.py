"""Resim plan (PNG/JPG ekran görüntüsü, tarama) → eleman listesi.

CAD ekran görüntüsü veya taranmış kat planından duvar, kapı boşluğu ve mahal çıkarır; sonuç
DXF içe aktarımıyla aynı eleman listesidir (metraj, çizim, 3D aynen çalışır).

Yöntem (yalnız numpy + PIL):
  1. mürekkep maskesi (koyu zeminde açık çizgi veya açık zeminde koyu çizgi, renkli dahil)
  2. kapanış: çift çizgili duvarın iki yüzü arası dolar → dolu çubuk; açılış: tek çizgiler (mobilya,
     yazı, ızgara) elenir → kalın çubuklar (duvar adayları)
  3. yatay/dikey uzun çubuklar → aks parçaları; duvara bitişik paralel parçalar (kanepe sırtı, yatak
     başlığı) ve boşa sarkan parçalar budanır
  4. kollinear parçalar arası boşluk → kapı açıklığı (dxf_import ile aynı kurallar), uçlar aksa oturur
  5. duvarlar + kapı boşlukları kapatılıp boş alan doldurulur → mahaller

Ölçek önceliği: px_per_m > grid_m (arka plan ızgarası periyodu) > kapı boşluğu medyanı ≈ 0,95 m
(ızgara varsa birimi bu tahmine en yakın standart değerden seçilir).
Çözünürlük bağımsızlığı: ipucusuz ölçek, girdinin √2 basamaklarıyla yeniden örneklenmiş kopyalarında sabit işlem
ölçeğiyle (CANON_S) aranır; son tanıma ≈ CANON_S px/m'ye küçültülmüş kopyada yapılır (büyütülmez), sonuç orijinal
piksele çevrilir. Girdi ≤ MAX_PIXELS; işlem görseli ≤ WORK_SIDE (zaman/bellek sınırlı).
Pencere, mahal adı ve mobilya sembolleri bu aşamada okunmaz (raporda uyarı olarak döner).
"""

import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from .dxf_import import Piece, _merge_collinear, _snap_ends, build_elements
from .quantities import polygon_area

DOOR_M = 0.95         # kapı boşluğu medyanı varsayımı (ölçek yoksa; iç kapı 0,9–1,0 m)


# ---------------------------------------------------------------- numpy morfoloji
def _box_count(m, ry, rx):
    """Her pikselin (2ry+1)×(2rx+1) penceresindeki dolu piksel sayısı (integral görüntü)."""
    p = np.pad(m.astype(np.int32), ((ry + 1, ry), (rx + 1, rx)))
    c = p.cumsum(0).cumsum(1)
    return c[2 * ry + 1:, 2 * rx + 1:] - c[:-2 * ry - 1, 2 * rx + 1:] - c[2 * ry + 1:, :-2 * rx - 1] + c[:-2 * ry - 1, :-2 * rx - 1]


def dilate(m, ry, rx=None):
    rx = ry if rx is None else rx
    return _box_count(m, ry, rx) > 0


def erode(m, ry, rx=None):
    rx = ry if rx is None else rx
    return _box_count(m, ry, rx) == (2 * ry + 1) * (2 * rx + 1)


def ink_mask(rgb):
    """(mürekkep, nötr): zeminle belirgin kontrastlı pikseller ve bunların renksiz (beyaz/gri/siyah) olanları."""
    a = rgb.astype(np.int16)
    lum = a.mean(2)
    bg = float(np.median(lum))
    ink = a.max(2) > bg + 70 if bg < 128 else lum < bg - 70
    neutral = (a.max(2) - a.min(2)) < 60
    return ink, ink & neutral


def grid_period(rgb, ink):
    """Arka plan ızgarası periyodu (px): yalnız zemin piksellerinin sütun/satır ortalamasında düzenli tepeler; yoksa None."""
    lum = rgb.astype(np.float32).mean(2)
    if np.median(lum) >= 128:
        lum = 255 - lum          # açık zemin: ızgara çizgisi koyudur
    bgpx = ~dilate(ink, 2)
    out = []
    for ax in (0, 1):
        cnt = bgpx.sum(ax)
        prof = np.where(cnt > 10, (lum * bgpx).sum(ax) / np.maximum(cnt, 1), np.nan)
        prof = np.nan_to_num(prof - np.nanmedian(prof))
        prof = prof - np.convolve(prof, np.ones(15) / 15, "same")
        thr = max(0.8, 2.5 * float(np.median(np.abs(prof))))
        peaks = [i for i in range(2, len(prof) - 2) if prof[i] > thr and prof[i] >= prof[i - 1] and prof[i] >= prof[i + 1]]
        d = np.diff(peaks)
        if len(d) < 8:
            continue
        med = float(np.median(d))
        good = d[np.abs(d - med) <= 2]
        if med >= 6 and len(good) >= 0.6 * len(d):
            out.append(float(good.mean()))
    return float(np.mean(out)) if out else None


# ---------------------------------------------------------------- çubuk çıkarımı
def _bars(mask, min_len, max_t):
    """Yatay çubuklar: satır koşuları (≥ min_len) ardışık satırlarda birleşir → (y0, y1, x0, x1)."""
    runs_by_row = []
    for row in mask:
        x = np.flatnonzero(np.diff(np.r_[0, row.astype(np.int8), 0]))
        runs_by_row.append([(int(s), int(e) - 1) for s, e in zip(x[::2], x[1::2]) if e - s >= min_len])
    open_, done = [], []
    for y, runs in enumerate(runs_by_row):
        nxt = []
        for s, e in runs:
            hit = next((b for b in open_ if min(e, b[3]) - max(s, b[2]) >= 0.8 * min(e - s, b[3] - b[2])), None)
            if hit:
                open_.remove(hit)
                nxt.append([hit[0], y, min(hit[2], s), max(hit[3], e), hit[4] + [(s, e)]])
            else:
                nxt.append([y, y, s, e, [(s, e)]])
        done += open_
        open_ = nxt
    done += open_
    out = []
    for y0, y1, _, _, rs in done:
        t = y1 - y0 + 1
        if t > max_t:
            continue
        xs0, xs1 = sorted(r[0] for r in rs), sorted(r[1] for r in rs)
        # uçlar: satırların çoğunun ulaştığı yer (birleşim köşelerindeki taşmayı at)
        out.append((y0, y1, xs0[len(xs0) // 4], xs1[(3 * len(xs1)) // 4]))
    return out


def _pieces(bars_h, bars_v, H, S, min_t):
    """Çubuk (px) → aks parçası (metre, y yukarı). Yatay: u=(1,0), n=y; dikey: u=(0,1), n=−x."""
    ps = []
    for y0, y1, x0, x1 in bars_h:
        t = max(min_t, (y1 - y0 + 1) / S)
        ps.append(Piece(1.0, 0.0, (H - (y0 + y1 + 1) / 2) / S, x0 / S, (x1 + 1) / S, round(t, 3)))
    for x0, x1, y0, y1 in bars_v:
        t = max(min_t, (x1 - x0 + 1) / S)
        ps.append(Piece(0.0, 1.0, -((x0 + x1 + 1) / 2) / S, (H - y1 - 1) / S, (H - y0) / S, round(t, 3)))
    # birleşim düğümü (kalın çubukların kesişimi, çubuğa değen başka çizgi) kısa ve tıknazdır: at
    ps = [p for p in ps if p.s1 - p.s0 >= max(0.5, 2 * p.t) and (p.t <= 0.25 or p.s1 - p.s0 >= 1.0)]  # sembol lekesi
    for p in ps:
        p.src = "thick"   # kalın dolu kontur (renkli duvar çizgisi): mobilya filtresi dokunmaz
    return ps


def _pair(lines, t_min, t_max, wide=None):
    """Çift çizgi duvar: paralel çizgi çiftleri → (parçalar, tek kalan çizgiler).

    Eş seçiminde önce örtüşme oranı, sonra yakınlık (en yakın çizgi çoğu zaman duvarın dibindeki
    mobilya kenarıdır). Eşin aynı hattaki tüm parçaları birlikte kullanılır: yüz çizgisi komodin/kasa
    ile bölünmüş olsa da duvar sürekli çıkar. lines: (yatay?, n, s0, s1) metre.
    """
    order = sorted(range(len(lines)), key=lambda i: -(lines[i][3] - lines[i][2]))
    used, out, rest = set(), [], []
    for i in order:
        if i in used:
            continue
        hA, nA, a0, a1 = lines[i]
        best, bs = None, -1e9
        for j in order:
            if j == i or j in used:
                continue
            hB, nB, b0, b1 = lines[j]
            d = abs(nA - nB)
            if hB != hA or not (t_min <= d <= (wide[0] if wide else t_max)):
                continue
            if d > t_max and not wide[1](hA, nA, nB, max(a0, b0), min(a1, b1)):
                continue           # 0,2 m'den geniş çift yalnız arası taralı/doluysa duvar (poşe)
            ov = min(a1, b1) - max(a0, b0)
            if ov < 0.3 * min(a1 - a0, b1 - b0):
                continue
            sc = ov / (a1 - a0) - d
            if sc > bs:
                best, bs = j, sc
        used.add(i)
        if best is None:
            rest.append(lines[i])
            continue
        nB = lines[best][1]
        track = [j for j in order if j not in used and lines[j][0] == hA and abs(lines[j][1] - nB) <= 0.02
                 and min(a1, lines[j][3]) - max(a0, lines[j][2]) > 0]
        ivs = sorted((max(a0, lines[j][2]), min(a1, lines[j][3])) for j in track)
        used |= set(track)
        merged = []
        for s0, s1 in ivs:  # A sürekli: eşin kesikleri 0,4 m'den kısaysa tek duvar
            if merged and s0 - merged[-1][1] < 0.4:
                merged[-1][1] = max(merged[-1][1], s1)
            else:
                merged.append([s0, s1])
        n, t = (nA + nB) / 2, round(abs(nA - nB), 3)
        cur = a0
        for s0, s1 in merged:
            out.append(Piece(1.0, 0.0, n, s0, s1, t) if hA else Piece(0.0, 1.0, n, s0, s1, t))
            if s0 - cur >= 0.5:
                rest.append((hA, nA, cur, s0))
            cur = s1
        if a1 - cur >= 0.5:
            rest.append((hA, nA, cur, a1))
    return out, rest


def _singles(rest, walls, min_len=1.0, t=0.1, tol=0.12, clear=0.9):
    """Tek çizgiyle çizilmiş duvar (ör. merdiven evi): uzun, yakınında paralel duvar olmayan (tezgâh / dolap
    önü duvara 0,6–0,7 m paralel durur), uçları duvara ya da başka bir tek çizgi duvara değen çizgi.
    Adaylar birbirini destekleyebilir; ≥ 2 m olanın bir ucu boşta kalabilir (hole açılan merdiven evi)."""
    cand = []
    for h, n, s0, s1 in sorted(rest, key=lambda r: -(r[3] - r[2])):
        if s1 - s0 < min_len:
            continue
        p = Piece(1.0, 0.0, n, s0, s1, t) if h else Piece(0.0, 1.0, n, s0, s1, t)
        if any(abs(p.ux * q.uy - p.uy * q.ux) < 0.02 and abs(p.n - q.n) < clear
               and min(p.s1, q.s1) - max(p.s0, q.s0) > 0.5 * (p.s1 - p.s0) for q in walls + cand):
            continue
        cand.append(p)
    changed = True
    while changed:
        changed = False
        for p in list(cand):
            pool = walls + [c for c in cand if c is not p]
            touch = sum(any(abs(p.ux * q.uy - p.uy * q.ux) > 0.5 and _seg_dist(pt, q) <= q.t / 2 + tol for q in pool)
                        for _, pt in _ends(p))
            if touch < (1 if p.s1 - p.s0 >= 2.0 else 2):
                cand.remove(p)
                changed = True
    return cand


def _ends(p):
    for s in (p.s0, p.s1):
        yield s, (s * p.ux - p.n * p.uy, s * p.uy + p.n * p.ux)


def _seg_dist(pt, q):
    """Noktanın q aks parçasına uzaklığı (parça boyunca kırpılmış)."""
    s = pt[0] * q.ux + pt[1] * q.uy
    n = -pt[0] * q.uy + pt[1] * q.ux
    ds = max(q.s0 - s, 0, s - q.s1)
    return math.hypot(ds, n - q.n)


def label_free(free):
    """4-komşu bağlı bileşen etiketleme (satır koşuları + birleşim-bul) → (etiket görüntüsü, piksel sayıları)."""
    H, W = free.shape
    parent = [0]

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    lab = np.zeros((H, W), np.int32)
    prev = []
    for y in range(H):
        x = np.flatnonzero(np.diff(np.r_[0, free[y].astype(np.int8), 0]))
        cur = []
        for s0, e0 in zip(x[::2], x[1::2]):
            ids = [l for ps_, pe_, l in prev if ps_ < e0 and pe_ > s0]
            if ids:
                r = find(ids[0])
                for l in ids[1:]:
                    rl = find(l)
                    if rl != r:
                        parent[rl] = r
                l = r
            else:
                l = len(parent)
                parent.append(l)
            lab[y, s0:e0] = l
            cur.append((s0, e0, l))
        prev = cur
    roots = np.array([find(i) for i in range(len(parent))], np.int32)
    lab = roots[lab]
    return lab, np.bincount(lab.ravel(), minlength=len(parent))


def _furniture(ps, lab, sizes, H, S, small=1.6, max_gap=1.4):
    """Mobilya kenarını ele (renkli kontur kaynaklı parçalara dokunulmaz):
    - < 2,2 m ve iki yanı da küçük kapalı kutuya bakıyor (masa-sandalye, yatak içi, lavabo, tezgâh)
    - < 1,3 m ve bir yanı küçük kutu ya da çizgiyle dolu (kanepe kolu, sandalye yanı)."""
    lim = small * S * S

    def probe(p, s, sg, dense_small):
        for dd in (0.06, 0.1, 0.16, 0.24, 0.34) if dense_small else (0.12,):
            n = p.n + sg * (p.t / 2 + dd)
            x, y = s * p.ux - n * p.uy, s * p.uy + n * p.ux
            px, py = int(round(x * S)), int(round(H - y * S))
            if not (0 <= py < lab.shape[0] and 0 <= px < lab.shape[1]):
                return False
            if lab[py, px] > 0:
                return sizes[lab[py, px]] < lim
        return dense_small
    def anchored(p):
        """Kollinear devamı var (kapıyla bölünmüş duvar) ya da iki ucu da bir duvara değiyor."""
        if any(q is not p and abs(p.ux * q.uy - p.uy * q.ux) < 0.02 and abs(p.n - q.n) < 0.06
               and (0 < q.s0 - p.s1 <= max_gap or 0 < p.s0 - q.s1 <= max_gap) for q in ps):
            return True
        return all(any(q is not p and abs(p.ux * q.uy - p.uy * q.ux) > 0.5 and _seg_dist(pt, q) <= q.t / 2 + 0.12
                       for q in ps) for _, pt in _ends(p))
    keep = []
    for p in ps:
        L = p.s1 - p.s0
        if getattr(p, "src", "") == "thick" or L >= 2.6:
            keep.append(p)
            continue
        k = max(3, int(L / 0.25))
        both = one = 0
        for i in range(k):
            s = p.s0 + 0.1 + (L - 0.2) * (i + 0.5) / k
            both += probe(p, s, -1, False) and probe(p, s, 1, False)
            one += probe(p, s, -1, True) or probe(p, s, 1, True)
        if (L < 2.2 and both >= 0.6 * k) or (L < 1.3 and one >= 0.9 * k) or (one >= 0.9 * k and not anchored(p)):
            continue
        keep.append(p)
    return keep


def _hug(ps, gap=0.22):
    """Duvarın dibindeki paralel parçayı (kanepe sırtı, yatak başlığı, tezgâh kenarı) ele: daha uzun bir
    parçaya ≤ gap mesafede, boyunun ≥ %60'ı örtüşen."""
    keep = []
    for p in sorted(ps, key=lambda p: -(p.s1 - p.s0)):
        # dış (renkli kontur) duvarın dibi daha geniş: kanepe sırtı / tezgâh önü 0,3–0,45 m içeride durur
        if not any(abs(p.ux * q.uy - p.uy * q.ux) <= 0.02
                   and abs(p.n - q.n) <= (p.t + q.t) / 2 + (0.35 if getattr(q, "src", "") == "thick" else gap)
                   and min(p.s1, q.s1) - max(p.s0, q.s0) >= 0.6 * (p.s1 - p.s0) for q in keep):
            keep.append(p)
    return keep


def _prune(ps, max_gap, tol):
    """Duvara bitişik paralel parçaları (mobilya kenarı) ve boşta biten parçaları ele."""
    ps = sorted(ps, key=lambda p: -(p.s1 - p.s0))
    keep = []
    for p in ps:  # paralel komşu: daha uzun bir parçayla ≥%60 örtüşüp dibinde duran → mobilya/başlık
        hug = False
        for q in keep:
            if abs(p.ux * q.uy - p.uy * q.ux) > 0.02:
                continue
            if abs(p.n - q.n) > (p.t + q.t) / 2 + 0.22:
                continue
            ov = min(p.s1, q.s1) - max(p.s0, q.s0)
            if ov >= 0.6 * (p.s1 - p.s0):
                hug = True
                break
        if not hug:
            keep.append(p)
    def end_state(p, end, pt):
        """'touch' (bir duvara değiyor), 'gap' (kapı boşluğu kadar ileride duvar var) veya None."""
        out = -1 if end == 0 else 1
        gap = False
        for q in keep:
            if q is p:
                continue
            par = abs(p.ux * q.uy - p.uy * q.ux) < 0.02
            if par and abs(p.n - q.n) < 0.08:
                if _seg_dist(pt, q) <= tol:
                    return "touch"
            elif not par and _seg_dist(pt, q) <= q.t / 2 + tol:
                return "touch"
            if gap:
                continue
            for k in range(1, 14):
                probe = (pt[0] + p.ux * out * max_gap * k / 13, pt[1] + p.uy * out * max_gap * k / 13)
                if (par and abs(p.n - q.n) < 0.08 and _seg_dist(probe, q) < 0.05) or \
                        (not par and _seg_dist(probe, q) <= q.t / 2 + 0.03):
                    gap = True
                    break
        return "gap" if gap else None

    # iki uç da bağlı olmalı ve en az biri fiziksel temas (dolap çerçevesi gibi serbest kutular elenir).
    # Zincirleme budama gerçek duvarları da götürür: en fazla iki tur, her turda karar tüm kümeye göre.
    for _ in range(2):
        drop = [p for p in keep if (lambda st: None in st or "touch" not in st)([end_state(p, i, pt) for i, (_, pt) in enumerate(_ends(p))])]
        if not drop:
            break
        keep = [p for p in keep if p not in drop]
    return keep


def _components(ps, max_gap, tol):
    """Temas/boşluk komşuluğu grafı; dış kabuğa (en uzun parça) bağlı bileşen dışındakiler mobilya kümesidir."""
    n = len(ps)
    adj = [set() for _ in range(n)]
    for i, p in enumerate(ps):
        for end, (_, pt) in enumerate(_ends(p)):
            out = -1 if end == 0 else 1
            for j, q in enumerate(ps):
                if i == j:
                    continue
                par = abs(p.ux * q.uy - p.uy * q.ux) < 0.02
                if par and abs(p.n - q.n) >= 0.08:
                    continue
                near = _seg_dist(pt, q) <= (tol if par else q.t / 2 + tol)
                if not near:
                    for k in range(1, 14):
                        probe = (pt[0] + p.ux * out * max_gap * k / 13, pt[1] + p.uy * out * max_gap * k / 13)
                        if _seg_dist(probe, q) <= (0.05 if par else q.t / 2 + 0.03):
                            near = True
                            break
                if near:
                    adj[i].add(j)
                    adj[j].add(i)
    comp, best = [-1] * n, None
    for r in range(n):  # toplam uzunluğu en büyük bağlı bileşen = bina (antet / mobilya kümeleri değil)
        if comp[r] >= 0:
            continue
        comp[r], st, members = r, [r], [r]
        while st:
            for j in adj[st.pop()]:
                if comp[j] < 0:
                    comp[j] = r
                    st.append(j)
                    members.append(j)
        L = sum(ps[i].s1 - ps[i].s0 for i in members)
        if best is None or L > best[0]:
            best = (L, members)
    return [ps[i] for i in sorted(best[1])] if best else []


def _clip_annotations(ps, margin=0.3):
    """Pafta ekleri (ölçü zinciri, aks çizgisi, ölçek çubuğu) bina kabuğunun dışında kalır. Kabuk kutusu:
    taralı/dolu çift duvarlar (≥ 18 cm) ve 2 m'den uzun kalın konturlar. Parçalar bu kutuya kırpılır
    (ölçü çizgisiyle birleşmiş dış duvar korunur); kutu dışındaki kısa kalıntılar atılır. Kalın dış duvar
    yoksa (sade çizim) dokunulmaz."""
    ext = [p for p in ps if p.s1 - p.s0 >= 1.5 and (p.t >= 0.18 and getattr(p, "src", "") != "thick")
           or (getattr(p, "src", "") == "thick" and p.s1 - p.s0 >= 2.0)]      # yazı / ölçek çubuğu kısadır
    if len(ext) < 4:
        return ps
    xs, ys = [], []
    for p in ext:
        for _, (x, y) in _ends(p):
            xs.append(x)
            ys.append(y)
    x0, x1, y0, y1 = min(xs) - margin, max(xs) + margin, min(ys) - margin, max(ys) + margin
    out = []
    for p in ps:
        horiz = abs(p.ux) > 0.5
        n_pos = p.n if horiz else -p.n                     # yatay: y, dikey: x
        lo, hi = (y0, y1) if horiz else (x0, x1)
        if not lo <= n_pos <= hi:
            continue
        a, b = (x0, x1) if horiz else (y0, y1)
        p.s0, p.s1 = max(p.s0, a), min(p.s1, b)
        if p.s1 - p.s0 >= 0.3:
            out.append(p)
    return out


def _unify_thickness(ps):
    """Aynı hat üzerindeki parçalar (kapıyla bölünmüş duvar) aynı kalınlık ve eksende olsun → birleşebilsin."""
    groups = []
    for p in ps:
        for g in groups:
            q = g[0]
            if abs(p.ux * q.uy - p.uy * q.ux) < 0.02 and abs(p.n - q.n) < 0.06:
                g.append(p)
                break
        else:
            groups.append([p])
    for g in groups:
        L = sum(p.s1 - p.s0 for p in g)
        n = sum(p.n * (p.s1 - p.s0) for p in g) / L
        t = round(float(np.median([p.t for p in g])), 3)
        for p in g:
            p.n, p.t = n, t
    return ps


def _end_doors(walls, max_gap, min_gap=0.6):
    """Duvar ucu ile dik duvar arasındaki boşluk (0,6–max_gap) → parçayı uzat, boşluğu kapı açıklığı yap."""
    for w in walls:
        if w.s1 - w.s0 < 0.8:        # kısa parça (kasa dönüşü, sembol) kapıyla uzatılmaz
            continue
        for end in (0, 1):
            s = w.s0 if end == 0 else w.s1
            pt = (s * w.ux - w.n * w.uy, s * w.uy + w.n * w.ux)
            out = -1 if end == 0 else 1
            best = None
            for q in walls:
                if q is w or abs(w.ux * q.uy - w.uy * q.ux) < 0.2:
                    continue
                if _seg_dist(pt, q) <= q.t / 2 + 0.05:
                    best = None
                    break
                sq = pt[0] * q.ux + pt[1] * q.uy
                nq = -pt[0] * q.uy + pt[1] * q.ux
                if not (q.s0 - 0.05 <= sq <= q.s1 + 0.05):
                    continue
                dot = -w.ux * q.uy + w.uy * q.ux     # w ekseni boyunca q aksına uzaklık
                d = (q.n - nq) / dot * out
                gap = d - q.t / 2
                if min_gap <= gap <= max_gap and (best is None or d < best[0]):
                    best = (d, gap, q)
            if best is None:
                continue
            d, gap, q = best
            if end == 0:
                w.openings = [(o[0], o[1], *o[2:]) for o in w.openings]
                w.openings.append((w.s0 - gap, w.s0, "door", False))
                w.s0 -= d
            else:
                w.openings.append((w.s1, w.s1 + gap, "door", False))
                w.s1 += d
    return walls


def _classify_openings(walls, ink, S, H):
    """Açıklık türü: boşluk boyunca duvara paralel ≥ 2 sürekli çizgi (pencere doğraması/camı) → pencere;
    boş ya da yalnız kanat/yay (dik/eğri çizgi) → kapı."""
    for w in walls:
        out = []
        for a, b, kind, *rest in w.openings:
            L = b - a
            if L < 0.3:
                out.append((a, b, kind, *rest))
                continue
            hits = 0
            prev = False
            for k in range(9):          # kalınlık boyunca 9 hat: her birinde boşluk boyunca mürekkep oranı
                n = w.n + (k / 8 - 0.5) * w.t
                cov = cnt = 0
                for j in range(12):
                    sp = a + L * (0.08 + 0.84 * j / 11)
                    x, y = sp * w.ux - n * w.uy, sp * w.uy + n * w.ux
                    px, py = int(round(x * S)), int(round(H - y * S))
                    if 0 <= py < ink.shape[0] and 0 <= px < ink.shape[1]:
                        cnt += 1
                        cov += bool(ink[max(0, py - 1):py + 2, max(0, px - 1):px + 2].any())
                line = cnt and cov / cnt >= 0.85
                hits += line and not prev          # bitişik hatlar aynı çizgi sayılır
                prev = line
            out.append((a, b, "window" if hits >= 2 else "door", True, *rest[1:]))
        w.openings = out
    return walls


def _poche_windows(walls, ink, S, H, min_w=0.5):
    """Taralı/dolu (poşe) dış duvarda taramanın kesildiği ≥ 0,5 m'lik bölüm = pencere (CAD'de pencere
    boşluğu taranmaz, yalnız doğrama çizgileri kalır)."""
    for w in walls:
        if w.t < 0.18:
            continue
        L = w.s1 - w.s0
        k = max(8, int(L / 0.05))
        dens = []
        horiz = abs(w.ux) > 0.5
        c = (H - w.n * S) if horiz else (-w.n * S)            # eksen (px): yatayda satır, dikeyde sütun
        half = w.t * S / 2
        bands = [(c - half + 2, c - 0.15 * w.t * S), (c + 0.15 * w.t * S, c + half - 2)]   # orta %30 (doğrama) hariç
        for j in range(k):
            sp = w.s0 + L * (j + 0.5) / k
            a0, a1 = (sp - 0.05) * S, (sp + 0.05) * S
            vals = []
            for lo, hi in bands:
                lo, hi = int(round(lo)), int(round(hi))
                if hi <= lo:
                    continue
                if horiz:
                    patch = ink[max(0, lo):hi, max(0, int(a0)):int(a1)]
                else:
                    patch = ink[max(0, int(H - a1)):int(H - a0), max(0, lo):hi]
                if patch.size:
                    vals.append(patch.mean())
            dens.append(float(np.mean(vals)) if vals else 1.0)
        if sum(d > 0.08 for d in dens) < 0.3 * k:
            continue                    # duvar zaten taralı değil
        ops = [(o[0], o[1]) for o in w.openings]
        j = 0
        while j < k:
            if dens[j] > 0.04:
                j += 1
                continue
            e = j
            while e < k and dens[e] <= 0.04:
                e += 1
            a, b = w.s0 + L * j / k, w.s0 + L * e / k
            if b - a >= min_w and a > w.s0 + 0.1 and b < w.s1 - 0.1 and not any(x < b and y > a for x, y in ops):
                w.openings.append((a, b, "window", True))
            j = e
    return walls


# ---------------------------------------------------------------- mahaller
def _wall_polys(walls, close_openings):
    polys = []
    for w in walls:
        spans = [(w.s0, w.s1)]
        if not close_openings:
            spans = []
            cur = w.s0
            for a, b, *_ in sorted(w.openings):
                spans.append((cur, a))
                cur = b
            spans.append((cur, w.s1))
        for a, b in spans:
            if b - a < 1e-3:
                continue
            h = w.t / 2
            pts = [(a, w.n - h), (b, w.n - h), (b, w.n + h), (a, w.n + h)]
            polys.append(Polygon([(s * w.ux - n * w.uy, s * w.uy + n * w.ux) for s, n in pts]).buffer(0.01, join_style=2))
    return unary_union(polys)


def _rooms(walls, cell=0.05, min_area=1.2):
    """Kapılar kapalıyken duvar dışı serbest alan: dış bölge (kenardan dolan) atılır, kalan her bileşen mahal."""
    solid = _wall_polys(walls, close_openings=True)
    x0, y0, x1, y1 = solid.bounds
    x0, y0, x1, y1 = x0 - 0.5, y0 - 0.5, x1 + 0.5, y1 + 0.5
    W, H = int((x1 - x0) / cell) + 1, int((y1 - y0) / cell) + 1
    img = Image.new("1", (W, H), 0)
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    geoms = getattr(solid, "geoms", [solid])
    ring = lambda r: [((x - x0) / cell, (y1 - y) / cell) for x, y in r.coords]
    for g in geoms:  # duvar birleşimi: dış sınır dolu, içindeki delikler (odalar) boş
        d.polygon(ring(g.exterior), fill=1)
        for h in g.interiors:
            d.polygon(ring(h), fill=0)
    occ = dilate(np.array(img, dtype=bool), 2)          # ≤ ~20 cm kaçakları kapat
    lab = np.zeros(occ.shape, np.int32)
    n = 0
    sizes = {}
    for yy in range(H):  # 4-komşu etiketleme (tarama + yığın)
        for xx in range(W):
            if occ[yy, xx] or lab[yy, xx]:
                continue
            n += 1
            st = [(yy, xx)]
            lab[yy, xx] = n
            cnt = 0
            while st:
                cy, cx = st.pop()
                cnt += 1
                for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                    if 0 <= ny < H and 0 <= nx < W and not occ[ny, nx] and not lab[ny, nx]:
                        lab[ny, nx] = n
                        st.append((ny, nx))
            sizes[n] = cnt
    outside = lab[0, 0]
    rooms = []
    for k, cnt in sizes.items():
        if k == outside or cnt * cell * cell < min_area:
            continue
        cells = []
        for yy in np.unique(np.nonzero(lab == k)[0]):
            xs = np.flatnonzero(lab[yy] == k)
            br = np.flatnonzero(np.diff(xs) > 1)
            for a, b in zip(np.r_[0, br + 1], np.r_[br, len(xs) - 1]):
                cells.append(box(x0 + xs[a] * cell, y1 - (yy + 1) * cell, x0 + (xs[b] + 1) * cell, y1 - yy * cell))
        poly = unary_union(cells).buffer(cell * 2.6, join_style=2).buffer(-cell * 0.6, join_style=2).difference(solid).simplify(cell)
        if poly.geom_type != "Polygon":
            poly = max(poly.geoms, key=lambda g: g.area)
        rooms.append(poly)
    return solid, rooms


# ---------------------------------------------------------------- işlem görseli + ölçek
MAX_PIXELS = 60_000_000   # girdi sınırı (≈ 7750 × 7750); üstü reddedilir
CANON_S = 50.0            # işlem ölçeği (px/m): eşikler bu ölçek civarında ayarlı (test planı 46, villa paftası 44)
WORK_SIDE = (320, 2600)   # işlem görselinin uzun kenarı (px) sınırları: bellek/zaman üst sınırı
MAX_UPSCALE = 1.0         # son tanıma turunda büyütme üst sınırı
GRID_SIDE = 1000          # ızgara periyodu bu boyuttaki önizlemede aranır (büyük periyotta tepe filtresi kaçırır)
SEARCH_SIDE = (400, 2300)  # ölçek hipotezlerinin işlem görseli uzun kenarı (≈ 8–46 m pafta genişliği)


def load_image(path):
    """Resmi güvenle aç: bozuk/desteklenmeyen dosya ve aşırı büyük resim ValueError."""
    try:
        im = Image.open(path)
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError) as ex:
        raise ValueError(f"resim okunamadı: {ex}") from ex
    W, H = im.size
    if W * H > MAX_PIXELS:
        im.close()
        raise ValueError(f"resim çok büyük ({W}×{H} px = {W * H / 1e6:.0f} MP > {MAX_PIXELS / 1e6:.0f} MP); "
                         "küçültüp yeniden yükleyin")
    try:
        return im.convert("RGB")
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError) as ex:
        raise ValueError(f"resim okunamadı: {ex}") from ex


class _Work:
    """Orijinal resmin k katı ölçekli (LANCZOS) işlem kopyası ve maskeleri. Metre koordinatları k'dan bağımsızdır:
    işlem pikseli / işlem ölçeği = orijinal piksel / orijinal ölçek."""

    def __init__(self, img, k, labels=True):
        W0, H0 = img.size
        size = (max(1, round(W0 * k)), max(1, round(H0 * k)))
        im = img if size == img.size else img.resize(size, Image.LANCZOS)
        self.k = size[1] / H0
        self.rgb = np.asarray(im)
        self.H, self.W = self.rgb.shape[:2]
        self.ink, self.neutral = ink_mask(self.rgb)
        if labels:
            self.lab, self.sizes = label_free(~dilate(self.ink, 1))
            self.sizes[0] = 0


def _door_widths(walls):
    return [b - a for w in walls for a, b, k, *_ in w.openings if k == "door" and 0.5 < b - a < 1.4]


def _run(w, S, max_opening):
    """İşlem görselinde (w) S px/m ölçeğiyle duvar + açıklık çıkarımı."""
    ink, neutral, lab, sizes, H, Wimg = w.ink, w.neutral, w.lab, w.sizes, w.H, w.W
    r_thick = max(1, round(0.035 * S))
    thick = dilate(erode(ink, r_thick), r_thick)                    # ≥ ~7 cm dolu kontur (renkli duvar çizgisi)
    thin = neutral & ~dilate(thick, 1)
    min_len, max_line = round(0.3 * S), max(3, round(0.06 * S))   # ≥ 3 px: kenar yumuşatma çizgiyi kalınlaştırır
    lines = [(True, (H - (y0 + y1 + 1) / 2) / S, x0 / S, (x1 + 1) / S) for y0, y1, x0, x1 in _bars(thin, min_len, max_line)
             if x1 - x0 < 0.8 * Wimg]
    lines += [(False, -((x0 + x1 + 1) / 2) / S, (H - y1 - 1) / S, (H - y0) / S) for x0, x1, y0, y1 in _bars(thin.T, min_len, max_line)
              if y1 - y0 < 0.8 * H]                                   # pafta çerçevesi / antet çizgisi değil
    def filled(h, n1, n2, s0, s1):
        """İki çizgi arasındaki bantta mürekkep oranı (tarama / dolu poşe duvar)."""
        lo, hi = sorted((n1, n2))
        if h:
            y0, y1 = int(H - hi * S) + 2, int(H - lo * S) - 1
            band = ink[max(0, y0):max(0, y1), int(s0 * S):int(s1 * S)]
        else:
            x0, x1 = int(-hi * S) + 2, int(-lo * S) - 1
            band = ink[int(H - s1 * S):int(H - s0 * S), max(0, x0):max(0, x1)]
        return band.size > 0 and band.mean() >= 0.12
    pieces, rest = _pair(lines, 0.055, 0.2, wide=(0.4, filled))   # < 5,5 cm çift: dolap/tezgâh çerçevesi
    bh = _bars(thick, min_len, round(0.42 * S))
    bv = _bars(thick.T, min_len, round(0.42 * S))
    pieces += _pieces(bh, bv, H, S, 0.1)
    pieces = [p for p in pieces if p.s1 - p.s0 >= 0.5 or p.t > 0.12]  # kısa ince çift: sandalye, komodin
    ps = _furniture(_hug(pieces), lab, sizes, H, S)
    ps += _furniture(_singles(rest, ps), lab, sizes, H, S)
    ps = _components(_clip_annotations(ps), max_opening, 0.2)
    ps = _unify_thickness(ps)
    walls = _merge_collinear(ps, [], [], max_opening, max_opening)
    walls = _end_doors(walls, max_opening)
    return _poche_windows(_classify_openings(_snap_ends(walls), ink, S, H), ink, S, H)



def _snap_k(k):
    """İşlem katsayısını √2 basamağına oturt: 2^(n/2) ölçekli girdiler aynı işlem görseline iner; 1'e yakın
    ölçekte (0,84–1,19) resim yeniden örneklenmez (ince çizgili ekran görüntüsünde örnekleme sapma yaratır)."""
    return 2 ** (round(2 * math.log2(k)) / 2)


def _fit_k(img, k):
    """İşlem görselinin uzun kenarı WORK_SIDE içinde kalsın."""
    L = max(img.size)
    return min(max(k, WORK_SIDE[0] / L), WORK_SIDE[1] / L)


def _work(img, prev, k):
    """k katı işlem görseli (küçültme önizlemeden: hızlı) → (_Work, gerçek işlem/orijinal oranı)."""
    if k <= prev.k:
        w = _Work(prev.img, k / prev.k)
        return w, w.k * prev.k
    w = _Work(img, k)
    return w, w.k


def _estimate_scale(img, prev, max_opening):
    """İpucusuz ölçek: işlem ölçeği CANON_S sabit tutulup girdi √2 basamaklarıyla küçültülür/büyütülür (her basamak
    bir ölçek hipotezi h = CANON_S / k). Her hipotezde kapı boşlukları bulunur; medyanı ≈ DOOR_M olan (kendisiyle
    tutarlı, est ≈ h) ve çok kapı veren hipotez seçilir. Çözünürlükten bağımsızdır: 2× girdi, 1× girdinin bir basamak
    aşağısıyla aynı işlem görselini görür. → (S orijinal px/m, kapı sayısı) ya da (None, 0)."""
    best = None
    L = max(img.size)
    for j in range(-6, 13):
        k = 2 ** (-j / 2)
        if not (SEARCH_SIDE[0] <= L * k <= SEARCH_SIDE[1]):
            continue
        w, kt = _work(img, prev, k)
        h = CANON_S / k
        ws = _door_widths(_run(w, h * kt, max_opening))
        if len(ws) < 2:
            continue
        est = h * float(np.median(ws)) / DOOR_M
        # tutarlılık × kapı sayısı; küçük işlem görselinde (≤ 800 px) yazı/sembol boşlukları sahte kapı üretir
        score = len(ws) * math.exp(-(math.log(est / h) / 0.25) ** 2) * min(1.0, max(w.W, w.H) / 800) ** 2
        if best is None or score > best[0]:
            best = (score, est, len(ws))
    return (best[1], best[2]) if best else (None, 0)


# ---------------------------------------------------------------- ana akış
def recognize(path, px_per_m=None, grid_m=None, floors=1, floor_height=3.0, max_opening=1.4, add_roof=True):
    """Resim plan → (elements, report). report["overlay"] için overlay() kullanılabilir.

    Tanıma çözünürlükten bağımsız bir işlem görselinde yapılır (ölçek ≈ CANON_S px/m, uzun kenar ≤ WORK_SIDE);
    metre koordinatları ve report["px_per_m"] orijinal resme göredir (overlay orijinal pikselle çizer)."""
    img = load_image(path)
    warnings = []
    kp = min(1.0, WORK_SIDE[1] / max(img.size))
    prev = SimpleNamespace(k=kp, img=img if kp == 1 else img.resize((max(1, round(img.width * kp)),
                                                                     max(1, round(img.height * kp))), Image.LANCZOS))
    pw = _Work(prev.img, min(1.0, GRID_SIDE / max(prev.img.size)), labels=False)   # ızgara tepeleri ≈ 10–40 px
    period = grid_period(pw.rgb, pw.ink)
    period = period / (pw.k * prev.k) if period else None  # orijinal piksel
    if px_per_m:
        S, method = float(px_per_m), "verilen ölçek"
    elif grid_m and period:
        S, method = period / grid_m, f"ızgara {period:.1f} px = {grid_m} m"
    else:  # ölçek yok: hipotez taraması (kapı genişliği medyanı ≈ 0,95 m); ızgara varsa ona oturt
        if grid_m:
            warnings.append("Izgara bulunamadı; grid_m kullanılamadı, ölçek kapı genişliğinden tahmin edildi")
        S, n = _estimate_scale(img, prev, max_opening)
        if S:
            method = f"kapı genişliği medyanı ≈ {DOOR_M} m ({n} kapı)"
            if period:  # ızgara birimi bilinmiyor: kapı tahminine en yakın standart birim (±%25)
                opts = [(abs(period / g - S) / S, g) for g in (0.1, 0.2, 0.25, 0.5, 1.0)]
                err, g = min(opts)
                if err <= 0.25:
                    S, method = period / g, f"ızgara {period:.1f} px = {g} m (kapı genişliğiyle seçildi)"
            warnings.append(f"Ölçek tahmin edildi ({method}); bilinen bir ölçüyle doğrulayın")
        else:
            S, method = CANON_S, "varsayılan (ölçek bulunamadı)"
            warnings.append(f"Ölçek bulunamadı; {CANON_S:g} px/m varsayıldı — px_per_m veya grid_m verin")
    w, kt = _work(img, prev, _fit_k(img, min(MAX_UPSCALE, _snap_k(CANON_S / S))))
    walls = _run(w, S * kt, max_opening)
    if not walls:
        raise ValueError("resimde duvar bulunamadı (plan çizimi değil ya da ölçek çok yanlış; px_per_m verin)")
    solid, room_polys = _rooms(walls)
    rooms = [{"points": [[round(x, 3), round(y, 3)] for x, y in list(p.exterior.coords)[:-1]], "name": f"Mahal {i + 1}"}
             for i, p in enumerate(sorted(room_polys, key=lambda p: (-round(p.centroid.y, 0), p.centroid.x)))]
    env = unary_union([solid] + room_polys).buffer(0.05, join_style=2).buffer(-0.05, join_style=2)
    if env.geom_type != "Polygon":
        env = max(env.geoms, key=lambda g: g.area)
    outline = [[round(x, 3), round(y, 3)] for x, y in list(Polygon(env.exterior).simplify(0.05).exterior.coords)[:-1]]
    nwin = sum(1 for w in walls for o in w.openings if o[2] == "window")
    warnings += [f"{nwin} pencere çizim sembolünden tanındı" if nwin else
                 "Çizimde pencere sembolü bulunamadı; gerekirse 3D'de/DXF'te eklenmeli",
                 "Kapı boşlukları boşluk kuralıyla bulundu; kanat yönü bilinmiyor"]
    elements = build_elements(walls, rooms, outline, floors, floor_height, add_roof=add_roof)
    report = {"source": "image", "px_per_m": round(S, 3), "scale_method": method, "grid_px": period,
              "walls": len(walls), "openings": sum(len(w.openings) for w in walls), "windows": nwin,
              "rooms": len(rooms), "floors": floors,
              "outline_area": round(polygon_area([tuple(p) for p in outline]), 2), "warnings": warnings}
    return elements, report


def overlay(path, elements, report, out_path):
    """Onay görseli: tanınan duvar (sarı), kapı (kırmızı), pencere (camgöbeği), mahal (mavi) orijinalin üstünde."""
    from PIL import ImageDraw
    im = Image.open(path).convert("RGB")
    H, S = im.height, report["px_per_m"]
    d = ImageDraw.Draw(im, "RGBA")
    P = lambda x, y: (x * S, H - y * S)
    for r in (e for e in elements if e["type"] == "room" and e.get("z", 0) == 0):
        d.polygon([P(*p) for p in r["points"]], fill=(60, 140, 255, 45), outline=(60, 140, 255, 200))
    for w in (e for e in elements if e["type"] == "wall" and e.get("base_z", 0) == 0):
        (x0, y0), (x1, y1) = w["start"], w["end"]
        L = math.dist(w["start"], w["end"]) or 1
        ux, uy = (x1 - x0) / L, (y1 - y0) / L
        nx, ny = -uy * w["thickness"] / 2, ux * w["thickness"] / 2
        d.polygon([P(x0 + nx, y0 + ny), P(x1 + nx, y1 + ny), P(x1 - nx, y1 - ny), P(x0 - nx, y0 - ny)], fill=(255, 200, 0, 110))
        for o in w["openings"]:
            a, b = o["offset"], o["offset"] + o["width"]
            col = (30, 200, 255, 255) if o["kind"] == "window" else (255, 30, 30, 255)
            d.line([P(x0 + ux * a, y0 + uy * a), P(x0 + ux * b, y0 + uy * b)], fill=col, width=4)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    im.save(out_path)
    return out_path

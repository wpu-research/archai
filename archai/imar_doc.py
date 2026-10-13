"""İmar durum belgesi okuma: PDF / görsel → arazi modu girdileri (TAKS, KAKS, çekmeler, kat, yençok, ada/parsel).

İki yol:
  metin  : e-imar / belediye çıktısı gibi metin katmanlı PDF → pypdf ile metin → kural tabanlı ayrıştırma
           (`parse_text`). Çevrimdışı, hiçbir yere gönderilmez.
  görsel : taranmış PDF veya fotoğraf → Claude (yalnız kullanıcı onayıyla, `consent=True`) yapılandırılmış alanlar.

Her alan için belgedeki kanıt (eşleşen metin parçası) döner; kullanıcı formu doldurmadan önce görür.
Okunan değerler ÖNERİDİR: imar müdürlüğünden teyit edilmeli (plan notları, özel hükümler, kot alınacak nokta
burada yorumlanmaz). İmar durum belgesi parsel cephesi/derinliği vermez — yalnız alan; cephe ve derinlik kullanıcıdan.
"""

import base64
import io
import json
import re

MAX_PAGES = 12
MODEL = "claude-opus-5-5"

# --------------------------------------------------------------------------- metin

_NUM = r"(\d{1,3}(?:[.,]\d{1,3})?)"


def _f(s):
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _norm(text):
    t = text.replace(" ", " ").replace("İ", "I").replace("ı", "i")
    t = re.sub(r"[ \t]+", " ", t)
    return t


def _find(rx, text, flags=re.I):
    m = re.search(rx, text, flags)
    return (m, text[max(0, m.start() - 10):m.end() + 10].strip().replace("\n", " ")) if m else (None, None)


RULES = {
    "taks": [r"\bTAKS\b\s*[:=]?\s*" + _NUM],
    "kaks": [r"\b(?:KAKS|EMSAL)\b\s*(?:\([^)]{0,12}\))?\s*[:=]?\s*" + _NUM, r"\bE\s*=\s*" + _NUM],
    "max_height": [r"\b(?:H\s*max|Hmaks|yen[cç]ok|sa[cç]ak kotu|bina y[uü]ksekli[gğ]i)\b\s*[:=]?\s*" + _NUM + r"\s*m?"],
    "max_floors": [r"\b(?:kat adedi|kat say[iı]s[iı]|kat\s*ad\.?)\s*[:=]?\s*(\d{1,2})\b",
                   r"\b(\d{1,2})\s*kat\b(?!\s*(?:alan|kar[sş]))"],
    "front": [r"\b[oö]n\s*(?:bah[cç]e)?\s*(?:mesafesi|[cç]ekme(?:\s*mesafesi)?)?\s*[:=]?\s*" + _NUM + r"\s*m"],
    "side": [r"\byan\s*(?:bah[cç]e)?\s*(?:mesafesi|[cç]ekme(?:\s*mesafesi)?)?\s*[:=]?\s*" + _NUM + r"\s*m"],
    "rear": [r"\barka\s*(?:bah[cç]e)?\s*(?:mesafesi|[cç]ekme(?:\s*mesafesi)?)?\s*[:=]?\s*" + _NUM + r"\s*m"],
    "parcel_area": [r"\b(?:parsel alan[iı]|y[uü]z[oö]l[cç][uü]m[uü]|tapu alan[iı])\s*(?:\(m2?²?\))?\s*[:=]?\s*"
                    r"(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*m"],
    "ada": [r"\bada\s*(?:no)?\s*[:=]?\s*(\d{1,6})\b"],
    "parsel": [r"\bparsel\s*(?:no)?\s*[:=]?\s*(\d{1,6})\b"],
    "pafta": [r"\bpafta\s*(?:no)?\s*[:=]?\s*([0-9A-Z][0-9A-Z\-./]{0,15})"],
}
NIZAM_RX = r"\b(ayr[iı]k|bitişik|bitisik|blok|ikiz)\s*nizam"
NOTATION_RX = r"\b(A|B|BL|İK|IK)\s*[-–]\s*(\d{1,2})\b"     # A-4: ayrık nizam 4 kat
LOC_RX = {"il": r"\b[iIİ]l\s*[:=]\s*([A-ZÇĞIİÖŞÜa-zçğıöşü]{2,20})", "ilce": r"\b[iIİ]l[cç]e\s*[:=]\s*([A-ZÇĞIİÖŞÜa-zçğıöşü]{2,25})",
          "mahalle": r"\b(?:[Mm]ahalle(?:si)?|[Mm]ah\.?)\s*[:=]\s*([A-ZÇĞIİÖŞÜa-zçğıöşü0-9 .]{2,40}?)(?:\s{2,}|\n|$)"}
LIMITS = {"taks": (0.05, 1.0), "kaks": (0.05, 10.0), "max_height": (2.5, 200.0), "max_floors": (1, 60),
          "front": (0, 30), "side": (0, 30), "rear": (0, 30), "parcel_area": (20, 1_000_000)}


def _area(s):
    s = s.strip()
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?", s):
        return float(s.replace(".", "").replace(",", "."))
    return _f(s)


def parse_text(text):
    """Belge metninden alanlar. Dönen: {"values": {...}, "evidence": {...}, "site": {...}, "nizam": str|None}."""
    t = _norm(text)
    values, evidence = {}, {}
    for key, rxs in RULES.items():
        for rx in rxs:
            m, ev = _find(rx, t)
            if not m:
                continue
            raw = m.group(1)
            v = _area(raw) if key == "parcel_area" else raw.strip() if key in ("ada", "parsel", "pafta") else _f(raw)
            if v is None:
                continue
            if key in LIMITS:
                lo, hi = LIMITS[key]
                if not lo <= v <= hi:
                    continue
                if key == "max_floors":
                    v = int(v)
            values[key], evidence[key] = v, ev
            break
    nizam = None
    m, ev = _find(NIZAM_RX, t)
    if m:
        w = m.group(1).lower()
        nizam = "ayrık" if w.startswith("ayr") else "bitişik" if w.startswith("bit") else w
        evidence["nizam"] = ev
    m, ev = _find(NOTATION_RX, t, 0)
    if m:
        code, kat = m.group(1), int(m.group(2))
        nizam = nizam or {"A": "ayrık", "B": "bitişik", "BL": "blok"}.get(code, "ikiz")
        if "max_floors" not in values and 1 <= kat <= 60:
            values["max_floors"], evidence["max_floors"] = kat, ev
        evidence.setdefault("nizam", ev)
    site = {}
    for k in ("ada", "parsel", "pafta"):
        if k in values:
            site[k] = str(values.pop(k))
    for k, rx in LOC_RX.items():
        m, _ = _find(rx, text, 0)
        if m:
            site[k] = m.group(1).strip()
    return {"values": values, "evidence": evidence, "site": site, "nizam": nizam}


def pdf_text(data):
    from pypdf import PdfReader
    r = PdfReader(io.BytesIO(data))
    if r.is_encrypted:
        try:
            r.decrypt("")
        except Exception:  # noqa: BLE001
            raise ValueError("PDF parola korumalı")
    return "\n".join((p.extract_text() or "") for p in r.pages[:MAX_PAGES])


# --------------------------------------------------------------------------- Claude (görsel / taranmış)

FIELDS = ("taks", "kaks", "max_height", "max_floors", "front", "side", "rear", "parcel_area")
SCHEMA = {
    "type": "object",
    "properties": {
        **{k: {"type": ["number", "null"]} for k in FIELDS},
        "nizam": {"type": ["string", "null"], "enum": ["ayrık", "bitişik", "blok", "ikiz", None]},
        "il": {"type": ["string", "null"]}, "ilce": {"type": ["string", "null"]},
        "mahalle": {"type": ["string", "null"]}, "pafta": {"type": ["string", "null"]},
        "ada": {"type": ["string", "null"]}, "parsel": {"type": ["string", "null"]},
        "evidence": {"type": "array", "items": {"type": "object", "properties": {
            "field": {"type": "string"}, "text": {"type": "string"}},
            "required": ["field", "text"], "additionalProperties": False}},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": [*FIELDS, "nizam", "il", "ilce", "mahalle", "pafta", "ada", "parsel", "evidence", "notes"],
    "additionalProperties": False,
}
PROMPT = """This is a Turkish zoning status document (imar durum belgesi) or an excerpt of a zoning plan note. \
Extract only values that are explicitly written in the document:
- taks (TAKS, footprint ratio), kaks (KAKS or Emsal / E), max_height (Hmax / yençok / saçak kotu, metres),
  max_floors (kat adedi; "A-4" means ayrık nizam 4 floors), front / side / rear (ön / yan / arka bahçe or çekme
  mesafesi, metres), parcel_area (parsel alanı / yüzölçümü, m²), nizam, il, ilçe, mahalle, pafta, ada, parsel.
Use null for anything not written. Do not infer values from general regulations (e.g. the Planlı Alanlar \
İmar Yönetmeliği defaults) — only what this document states.
For every non-null value add an evidence item quoting the exact text it came from.
In notes, list (in Turkish, short) special provisions that could change the buildable envelope: plan notes, \
kot alınacak nokta, bodrum/çatı katı hükümleri, terk, yol genişliği, otopark or sığınak conditions."""


def available():
    from . import plan_vision
    return plan_vision.available()


def ask_claude(data, media_type, client=None, model=MODEL):
    import anthropic
    if media_type == "application/pdf":
        block = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                "data": base64.standard_b64encode(data).decode()}}
    else:
        from PIL import Image
        img = Image.open(io.BytesIO(data)).convert("RGB")
        k = min(1.0, 2000 / max(img.size))
        if k < 1:
            img = img.resize((round(img.width * k), round(img.height * k)))
        buf = io.BytesIO()
        img.save(buf, "PNG")
        block = {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                             "data": base64.standard_b64encode(buf.getvalue()).decode()}}
    client = client or anthropic.Anthropic(timeout=90.0, max_retries=1)
    resp = client.beta.messages.create(
        model=model, max_tokens=8000,
        betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": [block, {"type": "text", "text": PROMPT}]}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("belge okuma reddedildi")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("belge okuma yanıtı yarıda kesildi")
    d = json.loads(next(b.text for b in resp.content if b.type == "text"))
    values = {}
    for k in FIELDS:
        v = d.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            lo, hi = LIMITS[k]
            if lo <= v <= hi:
                values[k] = int(v) if k == "max_floors" else float(v)
    ev = {}
    for e in d.get("evidence") or []:
        if e.get("field") and e.get("text"):
            ev.setdefault(e["field"], str(e["text"])[:200])
    site = {k: str(d[k]).strip()[:40] for k in ("il", "ilce", "mahalle", "pafta", "ada", "parsel") if d.get(k)}
    return {"values": values, "evidence": ev, "site": site, "nizam": d.get("nizam"),
            "notes": [str(n)[:300] for n in (d.get("notes") or [])][:12]}


# --------------------------------------------------------------------------- birleşik

IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def read(filename, data, consent=False, client=None):
    """Belgeyi oku → {"values", "evidence", "site", "nizam", "notes", "method", "warnings", "zoning", "missing"}."""
    name = str(filename or "").lower()
    ext = name[name.rfind("."):] if "." in name else ""
    warnings, res, method = [], None, None
    if ext == ".pdf":
        try:
            text = pdf_text(data)
        except ValueError:
            raise
        except Exception:  # noqa: BLE001 — bozuk PDF
            raise ValueError("PDF okunamadı (bozuk olabilir)")
        if len(text.strip()) >= 40:
            res, method = parse_text(text), "metin"
        mt = "application/pdf"
    elif ext in IMAGE_TYPES:
        mt = IMAGE_TYPES[ext]
    elif ext in (".txt",):
        res, method, mt = parse_text(data.decode("utf-8", "replace")), "metin", None
    else:
        raise ValueError("desteklenen biçimler: .pdf, .png, .jpg, .webp, .txt")
    weak = res is None or len(res["values"]) < 3
    if weak and mt:
        if consent is not True and client is None:
            warnings.append("Belge metin katmanı içermiyor veya az alan okundu. Taranmış belge için Claude okuması "
                            "gerekir: onay kutusunu işaretleyip tekrar yükleyin (belge Anthropic'e gönderilir).")
        elif client is None and not available():
            warnings.append("Claude okuması onaylandı ama Anthropic kimlik bilgisi yok (ANTHROPIC_API_KEY).")
        else:
            try:
                res, method = ask_claude(data, mt, client=client), "claude"
                warnings.append("Değerler yapay zekâ okumasıdır — belgeyle karşılaştırın.")
            except Exception as ex:  # noqa: BLE001
                warnings.append(f"Claude okuması başarısız: {ex}")
    res = res or {"values": {}, "evidence": {}, "site": {}, "nizam": None}
    res.setdefault("notes", [])
    v = res["values"]
    zoning = {k: v[k] for k in ("taks", "kaks", "front", "side", "rear", "max_floors", "max_height") if k in v}
    if res.get("nizam") == "bitişik":
        zoning["side"] = 0.0
        warnings.append("Bitişik nizam: yan çekme 0 alındı (ArchAI iki yanda simetrik çekme varsayar; köşe parsel ve "
                        "kalkan duvar koşullarını kontrol edin).")
    missing = [k for k in ("taks", "kaks", "front", "side", "rear", "max_floors") if k not in zoning]
    if missing:
        warnings.append("Belgede bulunamadı: " + ", ".join(missing) + " — formda elle girin.")
    if "parcel_area" in v:
        warnings.append(f"Parsel alanı {v['parcel_area']:g} m²: imar belgesi cephe/derinlik vermez; "
                        "formdaki cephe × derinlik bu alana uymalı.")
    warnings.append("Okunan değerler öneridir; imar müdürlüğünden ve plan notlarından teyit edin.")
    return {**res, "method": method or "yok", "zoning": zoning, "missing": missing, "warnings": warnings}

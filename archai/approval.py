"""Mimar / mühendis onayı: avan belgelerin yetkili kişi tarafından incelendiğinin kaydı.

Onay iki şeyi bağlar:
  parmak izi  — projenin içeriği (metraj satırları + maliyet + brif): `fingerprint()`. Proje değişirse (fiyat ayarı,
                poz, iç mekân varyantı…) parmak izi değişir, onay kendiliğinden GEÇERSİZ olur ve belgeler yeniden
                "TASLAK" damgasıyla üretilir.
  dosya özeti — onay anında üretilen belgelerin SHA-256 özetleri. Dosya sonradan elle değiştirilirse `status()`
                "DEĞİŞTİRİLMİŞ" der.

Bu kayıt avan seviyede iç inceleme beyanıdır; e-imza, ruhsat projesi imzası veya yapı denetim onayı DEĞİLDİR.
Uygulamada kimlik doğrulaması yoktur: onaylayanın beyan ettiği ad / unvan / oda sicil no kaydedilir.
"""

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

FILE = "onay.json"
CERT = "onay_tutanagi.docx"
TITLES = ("Mimar", "İnşaat Mühendisi", "Makine Mühendisi", "Elektrik Mühendisi", "Harita Mühendisi", "Jeoloji Mühendisi",
          "Şehir Plancısı", "İç Mimar", "Diğer")
CHAMBERS = ("TMMOB Mimarlar Odası", "TMMOB İnşaat Mühendisleri Odası", "TMMOB Makina Mühendisleri Odası",
            "TMMOB Elektrik Mühendisleri Odası", "TMMOB Harita ve Kadastro Mühendisleri Odası",
            "TMMOB Jeoloji Mühendisleri Odası", "TMMOB Şehir Plancıları Odası", "TMMOB İçmimarlar Odası", "Diğer")
DOC_KEYS = ("teklif_docx", "metraj_maliyet_xlsx", "sartname_docx", "kesif_xlsx", "kesif_csv", "cizim_pdf")
STATEMENT = ("Bu projenin avan seviyedeki çizim, metraj, maliyet, teknik şartname ve teklif belgelerini inceledim. "
             "Belgeler avan (ön tasarım) niteliğindedir; ruhsat ve uygulama projeleri ayrıca hazırlanıp imzalanacaktır.")
_TXT = re.compile(r"^[^\x00-\x1f<>]{1,120}$")


def fingerprint(qres, cost, brief):
    """Proje içeriğinin parmak izi (dosya yollarından ve zamandan bağımsız)."""
    b = {k: v for k, v in (brief or {}).items() if k not in ("render_3d",)}
    blob = json.dumps({"lines": qres["lines"], "cost": cost, "brief": b}, sort_keys=True, ensure_ascii=False,
                      default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


class QuantitiesMismatchError(RuntimeError):
    """Belge/onay işlemi için metraj ve kayıtlı maliyet yeniden eşleştirilmelidir."""


def quantities_fp(qres):
    """Sadece metraj (miktar satırları) parmak izi — fiyat/brif değişse de geometri değişmediğini doğrular."""
    blob = json.dumps({"lines": qres["lines"]}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def code(fp):
    return f"{fp[:4]}-{fp[4:8]}-{fp[8:12]}".upper()


def load(out):
    try:
        d = json.loads((Path(out) / FILE).read_text())
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def stamp_for(out, fp):
    """Belgelere basılacak onay bilgisi: kayıt var ve parmak izi tutuyorsa onay sözlüğü, yoksa None (TASLAK)."""
    d = load(out)
    if d and d.get("status") == "onaylandi" and d.get("fingerprint") == fp:
        return {**d["signer"], "date": d["date"], "code": code(fp)}
    return None


def stamp_text(onay):
    if not onay:
        return "TASLAK — MİMAR / MÜHENDİS ONAYI BEKLİYOR"
    return (f"AVAN İNCELEME ONAYI: {onay['name']}, {onay['title']}, {onay['chamber']} sicil {onay['reg_no']} · "
            f"{onay['date'][:10]} · doğrulama {onay['code']}")


def validate_signer(s):
    if not isinstance(s, dict):
        raise ValueError("onaylayan bilgisi eksik")
    out = {}
    for k, label in (("name", "ad soyad"), ("title", "unvan"), ("chamber", "meslek odası"), ("reg_no", "oda sicil no")):
        v = str(s.get(k) or "").strip()
        if not v or not _TXT.match(v):
            raise ValueError(f"{label} gerekli (en çok 120 karakter)")
        out[k] = v
    if len(out["name"].split()) < 2:
        raise ValueError("ad soyad tam yazılmalı")
    if out["title"] not in TITLES:
        raise ValueError(f"unvan şunlardan biri olmalı: {', '.join(TITLES)}")
    if out["chamber"] not in CHAMBERS:
        raise ValueError(f"meslek odası şunlardan biri olmalı: {', '.join(CHAMBERS)}")
    if not re.fullmatch(r"[0-9A-Za-z./\-]{1,20}", out["reg_no"]):
        raise ValueError("oda sicil no yalnız harf, rakam, nokta, eğik çizgi veya tire içerebilir (en çok 20)")
    note = str(s.get("note") or "").strip()
    if len(note) > 1000 or (note and re.search(r"[\x00-\x08\x0b-\x1f]", note)):
        raise ValueError("not en çok 1000 karakter olmalı")
    out["note"] = note
    if s.get("statement") is not True:
        raise ValueError("inceleme beyanı onaylanmalı")
    return out


def _sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _doc_hashes(files):
    return {k: {"file": Path(files[k]).name, "sha256": _sha(files[k])} for k in DOC_KEYS
            if files.get(k) and Path(files[k]).is_file()}


def approve(out, signer, regenerate):
    """Onayla: kayıt → belgeleri onay damgasıyla yeniden üret (`regenerate(out)` → project result) → dosya özetleri
    → onay tutanağı. Dönen: güncel proje sonucu.

    Onaydan önce, metraj (quantities) parmak izini project.json'dakilerle karşılaştır.
    Geometri değişmişse (quantities_fp uyuşmuyorsa) onayı REDDER — hata onay kaydı
    yazılmadan yakalanır. Normal onay kayıtlı fiyatı korur (katalog fiyatı değişimi
    onayı bozmaz, sadece geometri değişikliği engellenir).
    """
    from . import quantities as Q
    out = Path(out)
    signer = validate_signer(signer)
    result = json.loads((out / "project.json").read_text())
    elements = json.loads((out / "elements.json").read_text())
    q = Q.compute(elements)

    # Metraj parmak izi kontrolü: project.json'daki quantities_fp (maliyet hesaplandığı
    # andaki geometri) ile güncel elemanlardan hesaplananı karşılaştır.
    # Uyuşmuyorsa → elemanlar maliyetten sonra değişmiş → onayı engelle.
    stored_qfp = result.get("quantities_fp")
    current_qfp = quantities_fp(q)
    if stored_qfp is None:
        raise QuantitiesMismatchError(
            "Eski projede metraj referansı yok. Onaylamadan önce `refinalize` ile "
            "metraj, maliyet ve çizimleri yeniden üretin; güncel fiyatları kontrol edin."
        )
    if stored_qfp != current_qfp:
        raise QuantitiesMismatchError(
            "Proje elemanları (metraj) onaydan önce değişmiş. "
            "Onaylamadan önce `readjust` (fiyat değişimi) ya da "
            "`refinalize` (geometri/eleman değişimi) ile maliyeti yeniden hesaplayın."
        )

    fp = current_fp(out, result)
    rec = {"status": "onaylandi", "signer": {k: signer[k] for k in ("name", "title", "chamber", "reg_no")},
           "note": signer["note"], "statement": STATEMENT, "date": datetime.now().isoformat(timespec="seconds"),
           "fingerprint": fp, "quantities_fp": current_qfp, "history": (load(out) or {}).get("history", [])}
    # Kayıt, belgeler damgalanabilsin diye yeniden üretimden ÖNCE yazılır. Üretim yarıda kalırsa belge özeti
    # olmayan bir "onaylandi" kaydı kalmasın: önceki kayıt ve belgeler bayt bayt geri konur (yeniden üretmek
    # önceki onayın SHA-256 özetlerini tutturmaz).
    prev = (out / FILE).read_bytes() if (out / FILE).is_file() else None
    keep = [out / "project.json"] + [Path(result["files"][k]) for k in DOC_KEYS if (result.get("files") or {}).get(k)]
    snapshot = {p: p.read_bytes() for p in keep if p.is_file()}
    (out / FILE).write_text(json.dumps(rec, ensure_ascii=False, indent=1))
    try:
        result = regenerate(out)
        if current_fp(out, result) != fp:      # belgeler yeniden üretilirken içerik değişmemeli
            raise RuntimeError("onay sırasında proje değişti")
        rec["documents"] = _doc_hashes(result["files"])
        rec["history"].append({"event": "onay", "date": rec["date"], "by": rec["signer"]["name"], "code": code(fp)})
        (out / FILE).write_text(json.dumps(rec, ensure_ascii=False, indent=1))
    except BaseException:
        if prev is None:
            (out / FILE).unlink(missing_ok=True)
        else:
            (out / FILE).write_bytes(prev)
        for p, data in snapshot.items():
            p.write_bytes(data)
        raise
    write_certificate(out / CERT, result["name"], rec)
    result["files"]["onay_tutanagi_docx"] = str(out / CERT)
    (out / "project.json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str))
    return result


def revoke(out, regenerate, reason=""):
    out = Path(out)
    d = load(out)
    if not d or d.get("status") != "onaylandi":
        raise ValueError("geri alınacak onay yok")
    # redocument metrajı doğrulamadan kayıt değişirse işlem yarım kalır ve
    # yeniden geri alma denemesi de reddedilir. Önce aynı önkoşulu kontrol et.
    from . import quantities as Q
    result = json.loads((out / "project.json").read_text())
    q = Q.compute(json.loads((out / "elements.json").read_text()))
    if result.get("quantities_fp") != quantities_fp(q):
        raise QuantitiesMismatchError(
            "Metraj referansı eksik veya değişmiş. Belgeleri yenileyerek onayı geri "
            "almadan önce `refinalize` ile çıktıları yeniden üretin."
        )
    d["history"].append({"event": "geri alındı", "date": datetime.now().isoformat(timespec="seconds"),
                         "by": d["signer"]["name"], "reason": str(reason)[:300]})
    d["status"] = "geri_alindi"
    (out / FILE).write_text(json.dumps(d, ensure_ascii=False, indent=1))
    result = regenerate(out)
    (out / CERT).unlink(missing_ok=True)
    result["files"].pop("onay_tutanagi_docx", None)
    (out / "project.json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str))
    return result


def current_fp(out, result=None):
    from . import quantities as Q
    out = Path(out)
    result = result or json.loads((out / "project.json").read_text())
    q = Q.compute(json.loads((out / "elements.json").read_text()))
    return fingerprint(q, result["cost"], result["brief"])


def status(out):
    """{"status": taslak | onaylandi | gecersiz | degistirilmis | geri_alindi, ...}"""
    out = Path(out)
    d = load(out)
    if not d:
        return {"status": "taslak", "text": stamp_text(None), "titles": TITLES, "chambers": CHAMBERS,
                "statement": STATEMENT, "history": []}
    base = {k: d.get(k) for k in ("signer", "note", "date", "history", "statement")}
    base.update(titles=TITLES, chambers=CHAMBERS)
    if d.get("status") != "onaylandi":
        return {**base, "status": d.get("status", "taslak"), "text": stamp_text(None)}
    result = json.loads((out / "project.json").read_text())

    # 1. Geometri (metraj) değişikliği: quantities_fp ile kontrol et.
    stored_qfp = d.get("quantities_fp")
    if stored_qfp is not None:
        from . import quantities as Q
        q = Q.compute(json.loads((out / "elements.json").read_text()))
        current_qfp = quantities_fp(q)
        if stored_qfp != current_qfp:
            return {**base, "status": "gecersiz", "text": "ONAY GEÇERSİZ — proje metrajı onaydan sonra değişti; yeniden onay gerekir"}

    # Kayıtlı maliyet veya brif değişirse, belgeler aynı kalsa da onay geçersizdir.
    # Dış fiyat kataloğu burada okunmaz; katalog değişimi kayıtlı fiyatı etkilemez.
    if current_fp(out, result) != d.get("fingerprint"):
        return {**base, "status": "gecersiz", "text": "ONAY GEÇERSİZ — proje onaydan sonra değişti; yeniden onay gerekir"}

    # 3. Tam parmak izi de aynı -> belge bütünlük kontrolü
    onay = {**d["signer"], "date": d["date"], "code": code(d["fingerprint"])}
    docs, changed = [], False
    for k, v in (d.get("documents") or {}).items():
        # Arşivlenmiş teklif paketindeki aynı adlı belge canlı dosyanın yerini tutamaz.
        # Belgeler kökte, çizim PDF'i ise cizimler/ altındadır.
        p = out / "cizimler" / v["file"] if k == "cizim_pdf" else out / v["file"]
        ok = p.is_file() and _sha(p) == v["sha256"]
        changed |= not ok
        docs.append({"key": k, "file": v["file"], "sha256": v["sha256"], "ok": ok})
    st = "degistirilmis" if changed else "onaylandi"
    return {**base, "status": st, "code": onay["code"], "documents": docs,
            "text": ("BELGE DEĞİŞTİRİLMİŞ — onaydan sonra en az bir dosya elle değiştirildi" if changed
                     else stamp_text(onay))}


def write_certificate(path, project_name, rec):
    from docx.shared import Pt

    from . import reports as R
    d = R._doc()
    R._header_footer(d.sections[0], "AVAN İNCELEME ONAY TUTANAĞI", f"Doğrulama: {code(rec['fingerprint'])}",
                     stamp=stamp_text({**rec["signer"], "date": rec["date"], "code": code(rec["fingerprint"])}))
    R._para(d, "AVAN İNCELEME ONAY TUTANAĞI", bold=True, size=13)
    R._kv_table(d, [("Proje", project_name), ("Onaylayan", rec["signer"]["name"]), ("Unvan", rec["signer"]["title"]),
                    ("Meslek odası / sicil", f"{rec['signer']['chamber']} / {rec['signer']['reg_no']}"),
                    ("Tarih", rec["date"].replace("T", " ")), ("Doğrulama kodu", code(rec["fingerprint"])),
                    ("Proje parmak izi (SHA-256)", rec["fingerprint"])])
    R._para(d, "")
    R._para(d, "Beyan", bold=True)
    R._para(d, rec["statement"])
    if rec.get("note"):
        R._para(d, "Not", bold=True)
        R._para(d, rec["note"])
    R._para(d, "Onaylanan belgeler", bold=True)
    R._table(d, [("Belge", "Dosya", "SHA-256")] + [(k, v["file"], v["sha256"]) for k, v in rec["documents"].items()],
             (3.2, 4.2, 9.4), size=7.5)
    R._para(d, "")
    R._para(d, "Bu tutanak avan seviyede iç inceleme kaydıdır; e-imza, ruhsat projesi imzası veya yapı denetim onayı "
               "yerine geçmez. Dosyaların bütünlüğü yukarıdaki SHA-256 özetleriyle doğrulanabilir.", italic=True, size=8)
    for p in d.paragraphs:
        for r in p.runs:
            r.font.size = r.font.size or Pt(10)
    d.save(path)
    return path

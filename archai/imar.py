"""İmar özeti: girilen imar değerleri ile üretilen projenin yan yana karşılaştırması (tek tablo, tüm çıktılar aynısını kullanır)."""
from .notice import IMAR_NOTE


def imar_summary(zoning, parcel_area, checks):
    """checks: generate raporundaki kontroller. Dönüş: {"rows": [...], "note": IMAR_NOTE}. Satır: etiket, girilen sınır, hesaplanan, birim, durum."""
    rows = []

    def add(key, label, limit, value, unit, ok):
        rows.append({"key": key, "label": label, "limit": limit, "value": value, "unit": unit, "ok": bool(ok)})

    for key, label, unit in (("taks", "TAKS (taban alanı katsayısı)", ""), ("kaks", "KAKS / emsal", ""),
                             ("floors", "Kat adedi", "kat"), ("height", "Yençok / saçak kotu", "m")):
        c = checks.get(key)
        if c:
            add(key, label, c["limit"], c["value"], unit, c["ok"])
    if zoning.get("emsal_disi_pct"):
        add("emsal_disi", "Emsal dışı ortak alan payı", zoning["emsal_disi_pct"], zoning["emsal_disi_pct"], "%",
            zoning["emsal_disi_pct"] <= 30)
    for key, label in (("front", "Ön çekme"), ("side_left", "Sol yan çekme"), ("side_right", "Sağ yan çekme"),
                       ("rear", "Arka çekme")):
        d = (checks.get("setbacks_detail") or {}).get(key)
        if isinstance(d, dict) and "limit" in d and "value" in d:
            add(key, label, d["limit"], d["value"], "m", d.get("ok", True))
    return {"rows": rows, "note": IMAR_NOTE, "parcel_area": round(parcel_area, 1)}

"""Kayıtlı maliyetten basit fizibilite; piyasa fiyatı tahmini veya vergi hesabı değildir."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from . import approval, quantities


def _number(value, label, *, positive=False):
    if isinstance(value, bool):
        raise ValueError(f"{label}: sayısal değer gerekli")
    try:
        n = Decimal(str(value))
    except InvalidOperation as ex:
        raise ValueError(f"{label}: sayısal değer gerekli") from ex
    if not n.is_finite() or n < 0 or n > Decimal('1e15') or (positive and n < Decimal('0.01')):
        raise ValueError(f"{label}: sonlu, {'en az 0,01' if positive else 'negatif olmayan'} ve en fazla 10^15 değer gerekli")
    return n


def compute(record, elements, *, arsa_bedeli_tl, satis_m2_fiyati_tl, satilabilir_alan_m2, ek_gider_pct=0):
    q = quantities.compute(elements)
    if record.get("quantities_fp") != approval.quantities_fp(q):
        raise approval.QuantitiesMismatchError(
            "Metraj referansı eksik veya değişmiş. ONAY sekmesinden metraj ve belgeleri yenileyin.")
    arsa = _number(arsa_bedeli_tl, "Arsa bedeli")
    fiyat = _number(satis_m2_fiyati_tl, "Satış m² fiyatı", positive=True)
    alan = _number(satilabilir_alan_m2, "Satılabilir alan", positive=True)
    if fiyat > Decimal('1e9') or alan > Decimal('1e8'):
        raise ValueError("Satış m² fiyatı en fazla 10^9, satılabilir alan en fazla 10^8 olabilir")
    ek_pct = _number(ek_gider_pct, "Ek gider yüzdesi")
    if ek_pct > 100:
        raise ValueError("Ek gider yüzdesi en fazla 100 olabilir")
    insaat = _number(record["cost"]["total"], "Kayıtlı inşaat bedeli", positive=True)
    ek = insaat * ek_pct / 100
    gider = insaat + arsa + ek
    gelir = alan * fiyat
    kar = gelir - gider
    money = lambda n: float(n.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    return {
        "varsayimlar": {"arsa_bedeli_tl": money(arsa), "satis_m2_fiyati_tl": money(fiyat),
                        "satilabilir_alan_m2": money(alan), "ek_gider_pct": money(ek_pct)},
        "sonuc": {"insaat_bedeli_tl": money(insaat), "ek_gider_tl": money(ek),
                  "toplam_gider_tl": money(gider), "satis_geliri_tl": money(gelir),
                  "tahmini_kar_tl": money(kar), "kar_marji_pct": money(kar / gelir * 100),
                  "maliyet_getirisi_pct": money(kar / gider * 100),
                  "basabas_m2_fiyati_tl": money(gider / alan)},
        "kaynak": {"proje_parmak_izi": approval.fingerprint(q, record["cost"], record["brief"]),
                   "metraj_parmak_izi": record["quantities_fp"], "maliyet_alani": "cost.total"},
        "uyarilar": [
            "Avan fizibilite; yatırım tavsiyesi veya ekspertiz değildir.",
            "İnşaat bedeli kayıtlı teklif toplamıdır; KDV, yüklenici kârı ve genel gider ayarlarını içerir. Canlı katalog okunmaz.",
            "Satılabilir alan ve KDV dahil satış m² fiyatı kullanıcı varsayımıdır; brüt inşaat alanı otomatik olarak satış alanı sayılmaz.",
            "Ek gider yalnız inşaat bedeli üzerinden hesaplanır. Arsa bedeli ayrıca eklenir; mevcut maliyet kalemlerini tekrar eklemeyin.",
            "Sonuç net muhasebe kârı değildir. Gelir/kurumlar vergisi, KDV mahsuplaşması, enflasyon ve nakit akışının zaman değeri hesaplanmaz; finansman, tapu ve pazarlama giderleri ayrıca varsayılmalıdır.",
        ],
    }

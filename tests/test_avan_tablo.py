"""Avan alan cetveli (11903) — alan-sadık model."""
import pytest

from archai import avan_tablo as T

STRIP = [(0, 0), (31.8, 0), (31.8, 11.9), (0, 11.9)]


@pytest.fixture(scope="module")
def model():
    return T.build(STRIP, T.TABLO_11903, front=0.5, side=0, rear=0.5)


def test_kat_alanlari_tabloyla_eslesir(model):
    els, rep = model
    a = rep["avan_tablo"]["model_kat_alanlari"]
    t = T.TABLO_11903
    for k in range(1, 7):
        assert a[f"Kat {k}"] == pytest.approx(t["normal"]["alan"], abs=0.1)
    assert a["Zemin Kat"] == pytest.approx(t["zemin"]["alan"], abs=0.1)
    assert a["1. Bodrum"] == pytest.approx(t["bodrum"]["alan"], abs=0.1)
    assert a["Çatı Katı"] == pytest.approx(t["cati_kati"]["alan"], abs=0.1)
    assert rep["gross_total"] == pytest.approx(t["toplam_insaat"], abs=0.5)


def test_bolumler_ve_katlar(model):
    els, rep = model
    assert rep["floors"] == 7 and rep["unit_count"] == 24
    daire = {e["name"].split("/")[1] for e in els if e["type"] == "room" and e["name"].split("/")[1].startswith("Daire")}
    isy = {(e["level"], e["name"].split("/")[1]) for e in els if e["type"] == "room" and "İşyeri" in e["name"]}
    assert len(isy) == 6 and len(daire) == 4
    levels = {e["level"] for e in els}
    assert {"1. Bodrum", "Zemin Kat", "Kat 1", "Kat 6", "Çatı Katı"} <= levels


def test_kotlar(model):
    els, rep = model
    z = {e["level"]: e["z"] for e in els if e["type"] == "slab" and e["role"] == "floor"}
    assert z["1. Bodrum"] == pytest.approx(-2.5)
    assert z["Kat 6"] + rep["avan_tablo"]["kat_yuksekligi"] == pytest.approx(19.0, abs=0.01)   # saçak
    roofs = sorted(e["z"] for e in els if e["type"] == "slab" and e["role"] == "roof")
    assert roofs[-1] == pytest.approx(21.2, abs=0.01)                                            # mahya


def test_tum_acikliklar_duvara_islenir(model):
    els, _ = model
    for lvl in ("Zemin Kat", "1. Bodrum"):
        ext = [e for e in els if e["type"] == "wall" and e["level"] == lvl and e.get("exterior")]
        assert all(e["openings"] for e in ext if e["start"][1] == e["end"][1])      # ön ve arka cephede açıklık var
        assert sum(1 for e in ext for o in e["openings"] if o["kind"] == "door") >= 2


def test_sigmayan_alan_hata_verir():
    with pytest.raises(ValueError, match="sığmıyor|dikdörtgen"):
        T.build([(0, 0), (10, 0), (10, 10), (0, 10)], T.TABLO_11903, 0.5, 0, 0.5)

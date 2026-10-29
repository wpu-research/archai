"""Kat irtifakı tablosu, statik ön boyutlandırma ve versiyon karşılaştırma (archai/kat_irtifaki.py, statik.py, compare.py)."""
import pytest
from fastapi.testclient import TestClient

from archai import kat_irtifaki, statik
from archai.generate import generate
from webapp.app import app

c = TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
PARCEL = {"width": 24.0, "depth": 38.5}
ZON = {"taks": 0.25, "kaks": 2.0, "front": 5.0, "side": 3.0, "rear": 3.0, "max_floors": 3, "floor_height": 3.1}


@pytest.fixture(scope="module")
def plan():
    return generate(PARCEL, ZON, {"unit_type": "2+1", "units_per_floor": "auto"})


def test_kat_irtifaki_arsa_payi_toplami_payda(plan):
    els, rep = plan
    res = kat_irtifaki.compute(els, rep["parcel_area"])
    assert res["ozet"]["bolum_sayisi"] == rep["unit_count"] == 6 and res["ozet"]["konut"] == 6
    assert sum(b["arsa_payi"] for b in res["bolumler"]) == res["payda"] == 1000
    assert res["ozet"]["brut_toplam"] == pytest.approx(rep["gross_total"], abs=0.5)    # tüm brüt bölümlere dağılır
    assert all(b["net"] < b["toplam_brut"] for b in res["bolumler"])
    assert [b["no"] for b in res["bolumler"]] == list(range(1, 7))


def test_kat_irtifaki_bodrum_ortak_alan_ayrilir():
    """Bodrumda işyeri + sığınak: sığınak/teknik/otopark bağımsız bölüm dışı ortak alan sayılır, işyerlerine pay olarak eklenir."""
    from archai import avan_tablo as T
    els, rep = T.build([(0, 0), (31.8, 0), (31.8, 11.9), (0, 11.9)], T.TABLO_11903, 0.5, 0, 0.5)
    res = kat_irtifaki.compute(els, rep["parcel_area"])
    assert res["ozet"]["konut"] == 24 and res["ozet"]["isyeri"] == 6
    assert res["ortak_alan_toplam"] if "ortak_alan_toplam" in res else res["ozet"]["ortak_alan_toplam"] > 100
    assert sum(b["arsa_payi"] for b in res["bolumler"]) == 1000
    bod = [b for b in res["bolumler"] if b["kat"] == "1. Bodrum"]
    assert len(bod) == 2 and all(b["ortak_pay"] > 0 for b in bod)
    assert all(b["toplam_brut"] < 80 for b in bod)             # sığınak payı bodrum dükkânlarına yüklenmedi


def test_statik_on_boyutlandirma(plan):
    els, rep = plan
    s = statik.compute(els, rep)
    assert s["kolon_sayisi"] >= 8 and s["kolon_kesiti"]["b"] >= 0.30 and s["kolon_kesiti"]["h"] >= 0.50
    assert s["kiris"]["h"] >= 0.40 and s["doseme"]["uygun"] and s["radye"]["uygun"]
    assert s["miktar"]["beton_m3"] > 0 and s["miktar"]["donati_ton"] > 0 and "değildir" in s["not"]
    assert any("deprem" in w for w in s["uyarilar"])
    # emniyet gerilmesi düşükse uyarı
    low = statik.compute(els, rep, sigma_em=20)
    assert not low["radye"]["uygun"] and any("temel gerilmesi" in w for w in low["uyarilar"])
    assert set(statik.adjust_for(s)) == {"KOL-01", "DON-02", "KAL-02"}


def _new(name, **extra):
    r = c.post("/api/projects", json={"name": name, "parcel": PARCEL, "zoning": ZON,
                                      "program": {"unit_type": "2+1", "units_per_floor": "auto", **extra}})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_uclar_ve_karsilastirma():
    a = _new("karsilastir a")
    b = _new("karsilastir b", cikma={"ust_kat": 1.5, "cati_geri": 1.0})
    ki = c.get(f"/api/projects/{a}/kat-irtifaki").json()
    assert ki["ozet"]["bolum_sayisi"] == 6 and c.get(ki["dosya"]).status_code == 200
    st = c.get(f"/api/projects/{a}/statik").json()
    assert st["kolon_sayisi"] > 0 and {k["kod"] for k in st["kiyas"]} == {"KOL-01", "DON-02", "KAL-02"}
    assert c.get(st["dosya"]).status_code == 200
    assert c.get(f"/api/projects/{a}/statik?sigma=5").status_code == 422
    cmp = c.get(f"/api/projects/{a}/karsilastir/{b}").json()
    assert cmp["a"]["id"] == a and cmp["b"]["id"] == b
    assert any(g["anahtar"] == "program.cikma.ust_kat" and g["b"] == 1.5 for g in cmp["girdiler"])
    gross = next(x for x in cmp["rapor"] if x["anahtar"] == "gross_total")
    assert gross["fark"] > 0 and gross["yuzde"] > 10
    assert cmp["kalemler"] and cmp["kalemler"][0]["fark"] != 0
    assert c.get(f"/api/projects/{a}/karsilastir/20200101-000000-yok-abcd").status_code == 404


def test_statik_uygula_maliyeti_gunceller():
    pid = _new("statik uygula")
    before = c.get(f"/api/projects/{pid}").json()["cost"]
    r = c.post(f"/api/projects/{pid}/statik/uygula")
    assert r.status_code == 200, r.text
    after = c.get(f"/api/projects/{pid}").json()
    q = {x["code"]: x["quantity"] for x in after["cost"]["rows"]}
    assert q["KOL-01"] == r.json()["uygulanan"]["KOL-01"] and q["KOL-01"] != {x["code"]: x["quantity"] for x in before["rows"]}["KOL-01"]
    assert after["brief"]["adjust"]["qty_overrides"]["KOL-01"] == q["KOL-01"]


def test_capraz_dogrulama_imar_ve_catı_dairesi():
    from archai import avan_tablo as T, capraz
    els, rep = T.build([(0, 0), (31.8, 0), (31.8, 11.9), (0, 11.9)], T.TABLO_11903, 0.5, 0, 0.5)
    proj = {"report": rep, "cost": {}, "brief": {"tablo": True}}
    k = {x["kod"]: x for x in capraz.compute(proj, els)["kontroller"]}
    assert k["CATI-GERI"]["durum"] == "uygun" and k["CATI-ASANSOR"]["durum"] == "uygun" and k["KUR-ASANSOR"]["durum"] == "uygun"
    assert k["CATI-DONUSUM"]["durum"] == "uyari" and "1.14" in k["CATI-DONUSUM"]["aciklama"]       # dönüşüm parselinde çatı dairesi yok
    assert k["TUT-BOLUM"]["durum"] == "uygun" and k["TUT-ARSA-PAYI"]["durum"] == "uygun"
    assert k["KUR-OTOPARK"]["durum"] == "ihlal"                                                      # tabloda otopark 0
    # çatı dairesi geri çekmesi yoksa ihlal
    from copy import deepcopy
    bad = deepcopy(els)
    for e in bad:
        if e.get("name") == "cati_kati":
            xs = [p[0] for p in e["points"]]
            e["points"] = [[min(xs) - 40, p[1]] if p[0] == min(xs) else p for p in e["points"]]
    kb = {x["kod"]: x for x in capraz.compute(proj, bad)["kontroller"]}
    assert kb["CATI-GERI"]["durum"] == "ihlal"


def test_capraz_endpoint_cekme_ihlali():
    pid = _new("capraz", cikma={"ust_kat": 1.5, "cati_geri": 1.0})
    d = c.get(f"/api/projects/{pid}/capraz-dogrulama").json()
    k = {x["kod"]: x for x in d["kontroller"]}
    assert k["IMAR-CEKME-SIDE_LEFT"]["durum"] == "ihlal" and k["TUT-ALAN-METRAJ"]["durum"] == "uygun"
    assert d["ozet"]["ihlal"] >= 3 and "AVAN" in d["damga"]


def test_odeme_plani():
    pid = _new("odeme")
    d = c.get(f"/api/projects/{pid}/odeme-plani").json()
    assert d["sure_ay"] >= 6 and d["tablo"][0]["ay"] == 0 and d["tablo"][-1]["not"] == "teminat iadesi"
    assert d["odenen_toplam"] == pytest.approx(d["toplam_kdv_dahil"], abs=5)            # toplam ödeme = sözleşme bedeli (KDV dahil)
    assert d["tablo"][-2]["is_orani"] == 100.0
    is_ = [r["is_orani"] for r in d["tablo"][1:-1]]
    assert is_ == sorted(is_)
    assert c.get(d["dosya"]).status_code == 200
    d2 = c.get(f"/api/projects/{pid}/odeme-plani?ay=24&avans=20&teminat=0").json()
    assert d2["sure_ay"] == 24 and d2["tablo"][0]["net_odeme"] > d["tablo"][0]["net_odeme"]
    assert c.get(f"/api/projects/{pid}/odeme-plani?ay=1").status_code == 422


def test_cephe_duzeltme():
    pid = _new("cephe")
    d = c.get(f"/api/projects/{pid}/cephe").json()
    assert d["duvarlar"] and {w["yon"] for w in d["duvarlar"]} >= {"on", "arka", "sol", "sag"}
    w = next(x for x in d["duvarlar"] if x["kat"] == "Kat 1" and x["yon"] == "on" and x["acikliklar"])
    o = w["acikliklar"][0]
    before = c.get(f"/api/projects/{pid}").json()["summary"]["window_area"]
    # geçerli değişiklik: pencereyi genişlet (tüm normal katlara)
    r = c.put(f"/api/projects/{pid}/cephe", json={"islemler": [{"duvar": w["duvar"], "islem": "degistir", "index": o["index"],
                                                              "width": min(o["width"] + 0.4, 3.4), "ayni_katlar": True}]})
    assert r.status_code == 200 and r.json()["uygulanan"] >= 2, r.text
    after = c.get(f"/api/projects/{pid}").json()["summary"]["window_area"]
    assert after > before
    # geçersiz: duvar dışına taşan, çakışan, bilinmeyen duvar
    bad = [{"duvar": w["duvar"], "islem": "degistir", "index": o["index"], "offset": w["uzunluk"] - 0.2},
           {"duvar": w["duvar"], "islem": "ekle", "kind": "window", "offset": o["offset"], "width": 1.0},
           {"duvar": "Kat 9/D99", "islem": "sil", "index": 0}]
    for b in bad:
        assert c.put(f"/api/projects/{pid}/cephe", json={"islemler": [b]}).status_code == 422, b
    # ekle + sil ve yedek dosyası
    n0 = len(next(x for x in c.get(f"/api/projects/{pid}/cephe").json()["duvarlar"] if x["duvar"] == w["duvar"])["acikliklar"])
    r = c.put(f"/api/projects/{pid}/cephe", json={"islemler": [{"duvar": w["duvar"], "islem": "sil", "index": 0}]})
    assert r.status_code == 200
    n1 = len(next(x for x in c.get(f"/api/projects/{pid}/cephe").json()["duvarlar"] if x["duvar"] == w["duvar"])["acikliklar"])
    assert n1 == n0 - 1
    from webapp.app import PROJECTS
    assert (PROJECTS / pid / "elements.onceki.json").is_file()


def test_refinalize_istekleri_korur():
    from archai import project
    from webapp.app import PROJECTS
    pid = _new("istek korur")
    f = PROJECTS / pid / "project.json"
    import json as _j
    j = _j.loads(f.read_text())
    j["istekler"] = [{"metin": "x", "modellendi": False}]
    f.write_text(_j.dumps(j, ensure_ascii=False))
    out = project.refinalize(PROJECTS / pid)
    assert out["istekler"] == [{"metin": "x", "modellendi": False}] and out["cost"]["total"] > 0


def test_sponsor_teklifte_gorunur(monkeypatch):
    from docx import Document
    from archai import catalog, project
    from webapp.app import PROJECTS
    r = c.put("/api/sponsorlar", json={"sponsorlar": [{"ad": "Örnek Mutfak A.Ş.", "kategoriler": ["mutfak", "yanlış"], "web": "https://example.com"}]})
    assert r.status_code == 200 and r.json()["sponsorlar"][0]["kategoriler"] == ["mutfak"]
    assert c.put("/api/sponsorlar", json={"sponsorlar": [{"ad": "X", "web": "ftp://x"}]}).status_code == 422
    pid = _new("sponsorlu")
    f = PROJECTS / pid / "project.json"
    import json as _j
    j = _j.loads(f.read_text())
    j["brief"]["adjust"] = {"catalog": {"SER-01": {"supplier": "örnek mutfak a.ş.", "sku": "M-1", "name": "Tezgâh seti", "unit_price": 100.0,
                                                    "material": 100.0, "labor": 0, "waste_pct": 0, "url": ""}}}
    f.write_text(_j.dumps(j, ensure_ascii=False))
    assert c.get(f"/api/projects/{pid}/sponsorlar").json()["sponsorlar"][0]["urunler"][0]["kod"] == "SER-01"
    project.redocument(PROJECTS / pid)
    text = "\n".join(p.text for p in Document(PROJECTS / pid / "teklif.docx").paragraphs)
    assert "SPONSOR / ÖNERİLEN MARKALAR" in text and "4. TEKLİF ŞARTLARI" in text
    c.put("/api/sponsorlar", json={"sponsorlar": []})

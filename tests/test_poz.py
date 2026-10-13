"""Poz eşlemesi: lisanslı liste okuma, eşleme durumları, fiyat aktarımı, keşif özeti."""

import csv

import pytest
from openpyxl import Workbook, load_workbook

from archai import costing, poz, project


def test_parse_num_tr_and_en():
    assert poz.parse_num("1.234,56") == 1234.56
    assert poz.parse_num("1,234.56") == 1234.56
    assert poz.parse_num("950,00 TL") == 950.0
    assert poz.parse_num("₺ 3.800") == 3800.0
    assert poz.parse_num(12) == 12.0
    assert poz.parse_num("—") is None and poz.parse_num(None) is None and poz.parse_num(True) is None


def test_norm_unit_and_poz():
    assert poz.norm_unit("M2") == "m²" and poz.norm_unit("m3") == "m³" and poz.norm_unit("Ad.") == "adet"
    assert poz.norm_unit("Ton") == "ton" and poz.norm_unit("mtül") == "m"
    assert poz.norm_poz(" 15.150.1006 ") == "15.150.1006"
    assert poz.norm_poz("=cmd()") is None and poz.norm_poz("") is None and poz.norm_poz("abc") is None


CSV = """AMP Yazılım çıktısı;;;
2026 ÇŞB İnşaat Birim Fiyatları;;;
Sıra No;Poz No;Tanımı;Birimi;Birim Fiyatı
1;15.150.1006;Beton santralinde üretilen C 30/37 hazır beton dökülmesi (pompa ile);m3;3.950,25
2;15.160.1003;Ø 8- Ø 12 mm nervürlü beton çelik çubuğu;Ton;32.100,00
3;15.180.1003;Plywood ile düz yüzeyli betonarme kalıbı yapılması;m2;710,40
4;15.275.1101;Kireç ve çimento karışımı harç ile iç sıva yapılması;m2;241,10
5;15.999.9999;Fiyatı olmayan satır;m2;
"""


@pytest.fixture
def lst(tmp_path):
    p = tmp_path / "liste.csv"
    p.write_text(CSV, encoding="cp1254")
    return poz.read_price_list(p)


def test_read_csv_finds_header_and_skips(lst):
    assert lst["count"] == 4 and lst["skipped"] == 1
    b = lst["items"]["15.150.1006"]
    assert b["birim"] == "m³" and b["fiyat"] == 3950.25 and "C 30/37" in b["tanim"]
    assert lst["items"]["15.160.1003"]["birim"] == "ton"


def test_read_xlsx(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.append(["Başlık"])
    ws.append(["Poz No", "Tanımı", "Birimi", "Birim Fiyat (TL)"])
    ws.append(["15.150.1006", "C30/37 hazır beton", "m³", 3900.5])
    p = tmp_path / "l.xlsx"
    wb.save(p)
    r = poz.read_price_list(p)
    assert r["items"]["15.150.1006"]["fiyat"] == 3900.5


def test_read_rejects_unknown_and_empty(tmp_path):
    p = tmp_path / "x.pdf"
    p.write_bytes(b"%PDF")
    with pytest.raises(ValueError, match="desteklenen"):
        poz.read_price_list(p)
    q = tmp_path / "e.csv"
    q.write_text("a;b\n1;2\n")
    with pytest.raises(ValueError, match="poz satırı bulunamadı"):
        poz.read_price_list(q)


def test_match_statuses_and_overrides(lst):
    prices = costing.load_prices()
    rows = {r["code"]: r for r in poz.match(prices, lst)}
    assert rows["BET-01"]["durum"] == "eslesti" and rows["BET-01"]["liste_fiyat"] == 3950.25
    assert rows["BET-01"]["kaynak"] == "öneri" and rows["BET-01"]["dogrulandi"] is False
    assert rows["KAL-01"]["durum"] == "eslesti"
    assert rows["DON-02"]["durum"] == "listede_yok"            # 15.160.1004 listede yok
    assert rows["GEN-01"]["durum"] == "poz_yok"
    # iç sıva için aday: listede benzer tanım + aynı birim
    assert rows["SIV-01"]["adaylar"] and rows["SIV-01"]["adaylar"][0]["poz"] == "15.275.1101"
    ov = poz.overrides(rows.values())
    assert ov["BET-01"] == 3950.25 and "DON-02" not in ov and "GEN-01" not in ov


def test_unit_mismatch_not_applied(lst):
    lst["items"]["15.150.1006"]["birim"] = "m²"
    rows = {r["code"]: r for r in poz.match(costing.load_prices(), lst)}
    assert rows["BET-01"]["durum"] == "birim_uyusmaz"
    assert "BET-01" not in poz.overrides(rows.values())


def test_project_poz_overrides_map(lst):
    adj = {"poz": {"SIV-01": "15.275.1101", "BET-01": "15.150.1006"}}
    rows = {r["code"]: r for r in poz.match(costing.load_prices(), lst, adjust=adj)}
    assert rows["SIV-01"]["durum"] == "eslesti" and rows["SIV-01"]["kaynak"] == "proje"
    with pytest.raises(ValueError, match="geçersiz poz"):
        costing.validate_adjust({"poz": {"SIV-01": "=HYPERLINK()"}})


def test_no_list_status():
    rows = {r["code"]: r for r in poz.match(costing.load_prices(), None)}
    assert rows["BET-01"]["durum"] == "liste_yok" and rows["GEN-01"]["durum"] == "poz_yok"


def test_project_writes_kesif_and_poz_column(tmp_path):
    brief = {"name": "Poz Test", "quick": {"gross_area": 600, "floors": 4, "unit_type": "2+1"},
             "adjust": {"poz": {"SIV-01": "15.275.1101"}}}
    result, _ = project.run(brief, tmp_path)
    assert result["files"]["kesif_xlsx"].endswith("kesif_ozeti.xlsx")
    ws = load_workbook(result["files"]["kesif_xlsx"]).active
    data = {ws.cell(r, 8).value: (ws.cell(r, 2).value, ws.cell(r, 9).value) for r in range(6, ws.max_row)}
    assert data["BET-01"] == ("15.150.1006", "öneri — doğrulanmadı")
    assert data["SIV-01"] == ("15.275.1101", "proje")
    assert data["GEN-01"] == (None, "özel kalem (poz yok)")
    with open(result["files"]["kesif_csv"], encoding="utf-8-sig") as f:
        rows = list(csv.reader(f, delimiter=";"))
    assert rows[0][:3] == ["Sıra No", "Poz No", "İmalatın Cinsi"]
    assert any(r[1] == "15.150.1006" and "," in r[4] for r in rows[1:])
    # birim fiyat cetvelinde Poz No sütunu artık poz numarası (yoksa ArchAI kodu)
    bf = load_workbook(result["files"]["metraj_maliyet_xlsx"])["Birim Fiyat Cetveli"]
    col = [bf.cell(r, 2).value for r in range(6, bf.max_row)]
    assert "15.150.1006" in col and "GEN-01" in col


def test_approx_classes_2026():
    c = costing.load_prices()["approx_unit_costs"]
    assert c["IV-A"] == 26450 and c["V-E"] == 103500 and next(k for k in c if not k.startswith("_")) == "III-B"

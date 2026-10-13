"""İmar durum belgesi okuma: metin ayrıştırma, PDF metin katmanı, Claude yolu (sahte istemci)."""

import json
from types import SimpleNamespace

import matplotlib
import pytest

from archai import imar_doc as I

matplotlib.use("Agg")

SAMPLE = """T.C. KADIKÖY BELEDİYESİ İMAR VE ŞEHİRCİLİK MÜDÜRLÜĞÜ
İMAR DURUM BELGESİ
İl: İstanbul   İlçe: Kadıköy   Mahalle: Fenerbahçe
Pafta: F22-C-14   Ada: 1234   Parsel: 56
Parsel Alanı: 1.250,40 m²
Yapılaşma Koşulları: A-5 (Ayrık nizam 5 kat)
TAKS: 0,35   KAKS (Emsal): 1,75
Hmax: 15,50 m
Ön bahçe mesafesi: 5 m  Yan bahçe mesafesi: 3,5 m  Arka bahçe mesafesi: 4 m
"""


def test_parse_sample():
    r = I.parse_text(SAMPLE)
    assert r["values"] == {"taks": 0.35, "kaks": 1.75, "max_height": 15.5, "max_floors": 5, "front": 5.0,
                           "side": 3.5, "rear": 4.0, "parcel_area": 1250.4}
    assert r["site"] == {"ada": "1234", "parsel": "56", "pafta": "F22-C-14", "il": "İstanbul", "ilce": "Kadıköy",
                         "mahalle": "Fenerbahçe"}
    assert r["nizam"] == "ayrık" and "0,35" in r["evidence"]["taks"]


def test_notation_and_emsal_variants():
    r = I.parse_text("Yapılaşma: B-3   E=1.20   TAKS=0.60")
    assert r["values"]["max_floors"] == 3 and r["values"]["kaks"] == 1.2 and r["nizam"] == "bitişik"


def test_out_of_range_rejected():
    assert "taks" not in I.parse_text("TAKS: 4,5")["values"]


def test_read_bitisik_sets_side_zero_and_reports_missing():
    r = I.read("b.txt", "Bitişik nizam, TAKS: 0,60 Kat adedi: 4".encode())
    assert r["zoning"]["side"] == 0.0 and "kaks" in r["missing"] and r["method"] == "metin"


def test_pdf_text_layer(tmp_path):
    import matplotlib.pyplot as plt
    matplotlib.rcParams["pdf.fonttype"] = 42
    fig = plt.figure()
    for i, line in enumerate(SAMPLE.splitlines()):
        fig.text(0.05, 0.95 - i * 0.07, line, fontsize=7)
    p = tmp_path / "imar.pdf"
    fig.savefig(p)
    plt.close(fig)
    r = I.read("imar.pdf", p.read_bytes())
    assert r["method"] == "metin" and r["zoning"]["kaks"] == 1.75 and r["site"]["parsel"] == "56"


class _FakeClient:
    def __init__(self, payload):
        self.payload, self.calls = payload, []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(stop_reason="end_turn",
                               content=[SimpleNamespace(type="text", text=json.dumps(self.payload))])


def test_scanned_image_goes_to_claude_only_with_client():
    from PIL import Image
    import io
    buf = io.BytesIO()
    Image.new("RGB", (3000, 1000), "white").save(buf, "PNG")
    payload = {"taks": 0.4, "kaks": 1.2, "max_height": None, "max_floors": 4, "front": 5, "side": 3, "rear": 3,
               "parcel_area": 900, "nizam": "ayrık", "il": "İzmir", "ilce": None, "mahalle": None, "pafta": None,
               "ada": "10", "parsel": "2", "evidence": [{"field": "taks", "text": "TAKS 0.40"}],
               "notes": ["Kot bahçe ortalamasından alınacak"]}
    fc = _FakeClient(payload)
    r = I.read("tarama.png", buf.getvalue(), client=fc)
    assert r["method"] == "claude" and r["zoning"]["max_floors"] == 4 and r["site"]["il"] == "İzmir"
    assert r["notes"] == ["Kot bahçe ortalamasından alınacak"] and r["evidence"]["taks"] == "TAKS 0.40"
    blk = fc.calls[0]["messages"][0]["content"][0]
    assert blk["type"] == "image"
    # onaysız, istemcisiz: çağrı yok
    r2 = I.read("tarama.png", buf.getvalue())
    assert r2["method"] == "yok" and r2["zoning"] == {}


def test_unsupported():
    with pytest.raises(ValueError, match="desteklenen"):
        I.read("x.doc", b"..")

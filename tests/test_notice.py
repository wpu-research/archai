"""Avan notu: her çıktı (paftalar, teklif, şartname, Excel) kapsam sınırını açıkça söylemeli."""

import ezdxf
from docx import Document
from openpyxl import load_workbook

from archai import project
from archai.notice import AVAN_NOTE, AVAN_SHORT


def _docx_text(p):
    d = Document(p)
    body = "\n".join(x.text for x in d.paragraphs)
    cells = "\n".join(c.text for t in d.tables for r in t.rows for c in r.cells)
    foot = "\n".join(q.text for s in d.sections for q in s.footer.paragraphs)
    return body + cells, foot


def test_avan_note_in_all_outputs(tmp_path):
    res, _ = project.run_apartment(tmp_path)
    f = res["files"]
    for key in ("teklif_docx", "sartname_docx"):
        text, foot = _docx_text(f[key])
        assert AVAN_NOTE in text, key
        assert AVAN_SHORT in foot, key
    wb = load_workbook(f["metraj_maliyet_xlsx"])
    for ws in wb.worksheets:
        assert AVAN_NOTE in (ws["A4"].value or ""), ws.title
    dxfs = [v for k, v in f.items() if k.startswith("cizim_") and str(v).endswith(".dxf")]
    assert dxfs
    for p in dxfs:
        texts = [e.dxf.text for e in ezdxf.readfile(p).modelspace().query("TEXT")]
        assert AVAN_SHORT in texts, p

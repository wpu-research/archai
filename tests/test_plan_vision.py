"""Hibrit okuma: Claude çağrısı sahte istemciyle taklit edilir (kimlik bilgisi gerekmez). Sahte yanıt, elle
ölçülmüş referansın (archai/apartment.py) mobilya kutularıdır: yerleştirme mantığı referansla karşılaştırılır."""

import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from archai import apartment as A
from archai import plan_vision as pv

PLAN = "tests/data/plan_3daire.jpg"
KIND2TYPE = {"kanepe": "kanepe_3", "kanepe_2li": "kanepe_2", "sehpa_yuvarlak": "orta_sehpa",
             "yemek_masasi": "yemek_masasi", "sandalye": "sandalye", "mutfak": "mutfak_tezgahi",
             "yatak_cift": "cift_yatak", "yatak_tek": "tek_yatak", "komodin": "komodin", "gardirop": "gardirop",
             "lavabo": "lavabo", "klozet": "klozet", "dus": "dus"}
ROT2BACK = {0.0: "N", round(math.pi, 4): "S", round(math.pi / 2, 4): "W", round(-math.pi / 2, 4): "E"}


def _vision_answer(n_rooms):
    items = []
    for kind, x0, y0, x1, y1, rot, _ in A.WEST_ITEMS + A.SOUTH_ITEMS:
        back = "none" if kind in ("yemek_masasi", "sehpa_yuvarlak", "sandalye") else ROT2BACK[round(rot, 4)]
        items.append({"type": KIND2TYPE[kind], "x0": x0, "y0": y0, "x1": x1, "y1": y1, "back": back})
    rooms = [{"id": i, "type": "banyo" if i % 5 == 0 else "yatak_odasi", "label": "Banyo" if i % 5 == 0 else "Yatak Odası"}
             for i in range(1, n_rooms + 1)]
    return {"rooms": rooms, "furniture": items}


class FakeClient:
    """client.beta.messages.create(...) → yapılandırılmış JSON metin bloğu. İstek parametreleri kaydedilir."""

    def __init__(self, answer):
        self.answer, self.calls = answer, []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(stop_reason="end_turn",
                               content=[SimpleNamespace(type="text", text=json.dumps(self.answer))])


def test_furniture_placement_matches_reference():
    """Çizim kutusu + duvara dayanan yüz → nesne konumu, elle kurulan referansla ≤ 12 cm uyuşur."""
    S, H = A.S, 737
    ref = [A._place(*it) for it in A.WEST_ITEMS + A.SOUTH_ITEMS]
    got = pv.furniture_objects(_vision_answer(0)["furniture"], "Normal Kat", S, H)
    assert len(got) == len(ref)
    to_img = lambda o: ((o["x"] - A.OX) * S + A.PX0, A.PY0 - (o["y"] - A.OY) * S)   # referans metre → px
    bad = []
    for r, g in zip(ref, got):
        rx, ry = to_img(r)
        gx, gy = g["x"] * S, (H - g["y"] * S)
        d = math.hypot(rx - gx, ry - gy) / S
        if g["kind"] != r["kind"] or d > 0.12 or abs((g["rot"] - r["rot"] + math.pi) % (2 * math.pi) - math.pi) > 1e-3:
            bad.append((r["kind"], round(d, 3), r["rot"], g["rot"]))
    assert not bad, bad


@pytest.mark.skipif(not Path(PLAN).exists(), reason="test planı görseli yerelde yok")
def test_hybrid_image_project(tmp_path):
    from archai import project, plan_image
    els, rep = plan_image.recognize(PLAN)
    n = sum(1 for e in els if e["type"] == "room")
    fake = FakeClient(_vision_answer(n))
    design = project._vision(PLAN, els, rep, client=fake)
    req = fake.calls[0]
    assert req["model"] == "claude-opus-5-5" and req["fallbacks"] == "default"
    assert req["output_config"]["format"]["type"] == "json_schema"
    assert req["messages"][0]["content"][0]["type"] == "image"
    names = [e["name"].split("/")[1] for e in els if e["type"] == "room"]
    assert "Banyo 1" in names and "Yatak Odası 1" in names and len(set(names)) == len(names)
    assert rep["vision"] == "claude" and len(design["objects"]) == len(A.WEST_ITEMS) + len(A.SOUTH_ITEMS)


def test_vision_off_without_credentials(monkeypatch, tmp_path):
    from archai import project
    monkeypatch.setattr(pv, "available", lambda: False)
    rep = {"warnings": []}
    assert project._vision("x.png", [], rep) is None and rep["vision"] == "kapalı"

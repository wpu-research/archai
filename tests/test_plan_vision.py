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
    assert project.VISION_UNVERIFIED in rep["warnings"]


def _no_call(*a, **k):
    raise AssertionError("onaysız/gereksiz Anthropic çağrısı")


ROOM = {"type": "room", "name": "Zemin/Mahal 1", "level": "Zemin", "z": 0, "points": [[0, 0], [4, 0], [4, 3], [0, 3]]}


def test_vision_requires_consent(monkeypatch):
    """Sözleşme değişikliği (konsey #7): eskiden kimlik varsa varsayılan 'auto' planı sessizce gönderiyordu.
    Artık yalnız mode is True (kullanıcı onayı) ya da testte sahte client verilirse çağrı yapılır."""
    from archai import project
    monkeypatch.setattr(pv, "available", lambda: True)
    monkeypatch.setattr(pv, "ask", _no_call)
    for mode in (False, "auto", "true", 1, None):
        rep = {"warnings": [], "px_per_m": 50}
        assert project._vision("x.png", [dict(ROOM)], rep, mode) is None
        assert rep["vision"] == "kapalı (onay verilmedi)"
        assert any("onay kutusunu" in w for w in rep["warnings"])


def test_vision_consent_without_credentials(monkeypatch):
    from archai import project
    monkeypatch.setattr(pv, "available", lambda: False)
    monkeypatch.setattr(pv, "ask", _no_call)
    rep = {"warnings": [], "px_per_m": 50}
    assert project._vision("x.png", [dict(ROOM)], rep, True) is None and rep["vision"] == "kapalı (kimlik yok)"


def test_vision_skipped_without_rooms():
    from archai import project
    fake = FakeClient({"rooms": [], "furniture": []})
    rep = {"warnings": [], "px_per_m": 50}
    assert project._vision("x.png", [], rep, True, client=fake) is None
    assert fake.calls == [] and rep["vision"] == "kapalı (mahal yok)"


def test_run_image_passes_only_bool_true(monkeypatch, tmp_path):
    from archai import plan_image, project
    seen = []

    def spy(img, els, rep, mode, client=None):
        seen.append(mode)
        raise RuntimeError("dur")
    monkeypatch.setattr(plan_image, "recognize", lambda *a, **k: ([dict(ROOM)], {"warnings": [], "px_per_m": 50}))
    monkeypatch.setattr(project, "_vision", spy)
    for val, want in (({}, False), ({"vision": "true"}, False), ({"vision": 1}, False), ({"vision": True}, True)):
        with pytest.raises(RuntimeError):
            project.run_image("x.png", {"image": val}, tmp_path)
        assert seen[-1] is want


def test_available_needs_real_credentials(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert not pv.available()
    (tmp_path / ".config" / "anthropic").mkdir(parents=True)
    assert not pv.available()                                   # boş dizin kimlik değil
    (tmp_path / ".config" / "anthropic" / "profile.json").write_text("{}")
    assert pv.available()
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "yok")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert pv.available()


def test_client_timeout(monkeypatch, tmp_path):
    import anthropic
    from PIL import Image
    made = {}

    class Boom(Exception):
        pass

    def fake_ctor(**kw):
        made.update(kw)
        raise Boom()
    monkeypatch.setattr(anthropic, "Anthropic", fake_ctor)
    img = tmp_path / "p.png"
    Image.new("RGB", (200, 150), "white").save(img)
    with pytest.raises(Boom):
        pv.ask(img, [ROOM], 20.0)
    assert made == {"timeout": 90.0, "max_retries": 1}


def test_labels_sanitized():
    evil = "Salon/<img src=x onerror=alert(1)>" + "A" * 483
    assert len(evil) == 517
    els = [dict(ROOM), {**ROOM, "name": "Zemin/Mahal 2"}, {**ROOM, "name": "Zemin/Mahal 3"}, {**ROOM, "name": "Zemin/Mahal 4"}]
    pv.apply(els, {"rooms": [{"id": 1, "type": "salon", "label": evil}, {"id": 2, "type": "banyo", "label": "\x00\u202e\n "},
                             {"id": 3, "type": "wc", "label": "WC"}, {"id": 4, "type": "wc", "label": "W\u0007C"}]})
    names = [e["name"].split("/", 1)[1] for e in els]
    assert len(names[0]) <= pv.LABEL_MAX and not any(c in names[0] for c in "<>/\\\"'`&")
    assert names[0].startswith("Salon img src=x onerror=alert(1)")
    assert names[1] == "Banyo"                                  # boş kaldı → tür adı
    assert names[2:] == ["WC 1", "WC 2"]                        # tekrar eden ad numaralanır

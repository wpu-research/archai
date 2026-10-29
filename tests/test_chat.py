"""Sohbet asistanı: onay/kimlik denetimi, araç döngüsü, yeniden üretim, fiyat ve künye (sahte Claude istemcisi)."""
import json
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

from archai import chat
from webapp.app import app

c = TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))


def use(id_, name, **inp):
    return NS(type="tool_use", id=id_, name=name, input=inp)


def text(t):
    return NS(type="text", text=t)


class Fake:
    """Sıralı yanıtlar; her çağrının argümanlarını (mesaj listesinin kopyasıyla) kaydeder."""

    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kw):
        self.calls.append({**kw, "messages": list(kw["messages"])})
        content, stop = self.responses.pop(0)
        return NS(content=content, stop_reason=stop)


def say(*blocks, stop="end_turn"):
    return (list(blocks), stop)


@pytest.fixture
def project_id():
    r = c.post("/api/projects", json={"name": "sohbet", "quick": {"gross_area": 450, "floors": 3, "unit_type": "2+1"}})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def ask(pid, fake, monkeypatch, msg="merhaba", **kw):
    monkeypatch.setattr(chat, "make_client", lambda: fake)
    monkeypatch.setattr(chat, "available", lambda: True)
    return c.post(f"/api/projects/{pid}/chat", json={"message": msg, "consent": True, **kw})


def test_onay_ve_kimlik_olmadan_cagri_yok(project_id, monkeypatch):
    fake = Fake(say(text("yok")))
    monkeypatch.setattr(chat, "make_client", lambda: fake)
    monkeypatch.setattr(chat, "available", lambda: True)
    assert c.post(f"/api/projects/{project_id}/chat", json={"message": "x"}).status_code == 422
    monkeypatch.setattr(chat, "available", lambda: False)
    assert c.post(f"/api/projects/{project_id}/chat", json={"message": "x", "consent": True}).status_code == 422
    assert fake.calls == []
    assert c.post("/api/projects/20200101-000000-yok-abcd/chat", json={"message": "x", "consent": True}).status_code == 404


def test_arac_dongusu_ve_istek_bicimi(project_id, monkeypatch):
    fake = Fake(say(use("t1", "proje_ozeti")), say(text("3 katlı, 450 m².")))
    r = ask(project_id, fake, monkeypatch, "özet ver", history=[{"role": "user", "content": "selam"},
                                                               {"role": "assistant", "content": "merhaba"}])
    assert r.status_code == 200, r.text
    assert r.json()["reply"] == "3 katlı, 450 m²." and r.json()["actions"] == [{"tool": "proje_ozeti", "ok": True}]
    first, second = fake.calls
    assert first["model"] == "claude-opus-5-5" and first["fallbacks"] == "default"
    assert {t["name"] for t in first["tools"]} >= {"proje_ozeti", "projeyi_yeniden_uret", "fiyat_ayarla", "kunye_guncelle"}
    assert [m["role"] for m in first["messages"]] == ["user", "assistant", "user"]
    last = second["messages"][-1]
    assert last["role"] == "user" and last["content"][0]["type"] == "tool_result"
    out = json.loads(last["content"][0]["content"])
    assert out["id"] == project_id and out["uretilen"]["floors"] == 3


def test_yeniden_uret_yeni_proje_acar_eskisi_kalir(project_id, monkeypatch):
    new_quick = {"quick": {"gross_area": 900, "floors": 4, "unit_type": "2+1"}}
    fake = Fake(say(use("t1", "projeyi_yeniden_uret", degisiklikler=new_quick)), say(text("yeni proje hazır")))
    r = ask(project_id, fake, monkeypatch, "900 m², 4 kat yap")
    assert r.status_code == 200, r.text
    new = r.json()["new_project"]
    assert new and new != project_id
    assert c.get(f"/api/projects/{project_id}").status_code == 200           # eski proje bozulmadı
    p = c.get(f"/api/projects/{new}").json()
    assert p["name"].endswith("(v2)") and p["report"]["floors"] == 4


def test_fiyat_ve_kunye(project_id, monkeypatch):
    before = c.get(f"/api/projects/{project_id}").json()["cost"]["total"]
    fake = Fake(say(use("a", "maliyet_kalemleri", limit=3)), say(use("b", "fiyat_ayarla", ayar={"vat_pct": 10})),
                say(use("c", "kunye_guncelle", kunye={"owner": "Test Müteahhit", "company": {"name": "ABC İnşaat"}})),
                say(text("tamam")))
    r = ask(project_id, fake, monkeypatch, "kdv 10, firma ABC")
    assert r.status_code == 200 and r.json()["updated"] is True, r.text
    rows = json.loads(fake.calls[1]["messages"][-1]["content"][0]["content"])["kalemler"]
    assert len(rows) == 3 and rows[0]["tutar"] >= rows[1]["tutar"] and rows[0]["kod"]
    p = c.get(f"/api/projects/{project_id}").json()
    assert p["cost"]["vat_pct"] == 10 and p["cost"]["total"] != before
    assert p["brief"]["owner"] == "Test Müteahhit" and p["brief"]["company"]["name"] == "ABC İnşaat"


def test_arac_hatasi_modele_doner(project_id, monkeypatch):
    bad = {"quick": {"gross_area": 5, "floors": 3, "unit_type": "2+1"}}
    fake = Fake(say(use("t1", "projeyi_yeniden_uret", degisiklikler=bad)), say(text("alan çok küçük, daha büyük girin")))
    r = ask(project_id, fake, monkeypatch, "5 m² yap")
    assert r.status_code == 200 and r.json()["new_project"] is None
    assert r.json()["actions"][0]["ok"] is False
    res = fake.calls[1]["messages"][-1]["content"][0]
    assert res["is_error"] is True and "hata" in json.loads(res["content"])


def test_ret_ve_tur_siniri(project_id, monkeypatch):
    r = ask(project_id, Fake(say(stop="refusal")), monkeypatch)
    assert r.status_code == 200 and "yanıtlayamadım" in r.json()["reply"]
    loop = Fake(*[say(use(f"t{i}", "proje_ozeti")) for i in range(chat.MAX_TURNS + 2)])
    r = ask(project_id, loop, monkeypatch)
    assert r.status_code == 200 and "durdurdum" in r.json()["reply"] and len(loop.calls) == chat.MAX_TURNS


def test_gecmis_temizlenir():
    h = [{"role": "assistant", "content": "ilk"}, {"role": "user", "content": "a"}, {"role": "user", "content": "b"},
         {"role": "system", "content": "x"}, {"role": "assistant", "content": ""}, {"role": "assistant", "content": "c"}]
    out = chat._clean_history(h)
    assert [m["role"] for m in out] == ["user", "assistant"] and out[0]["content"] == "a\nb"


# ---------------------------------------------------------------- yeni-proje modu (açık proje yok)

def ask_new(fake, monkeypatch, msg="merhaba", **kw):
    monkeypatch.setattr(chat, "make_client", lambda: fake)
    monkeypatch.setattr(chat, "available", lambda: True)
    return c.post("/api/chat", json={"message": msg, "consent": True, **kw})


def test_yeni_mod_onay_ve_kimlik(monkeypatch):
    fake = Fake(say(text("x")))
    monkeypatch.setattr(chat, "make_client", lambda: fake)
    monkeypatch.setattr(chat, "available", lambda: True)
    assert c.post("/api/chat", json={"message": "x"}).status_code == 422
    monkeypatch.setattr(chat, "available", lambda: False)
    assert c.post("/api/chat", json={"message": "x", "consent": True}).status_code == 422
    assert fake.calls == []


def test_yeni_mod_proje_uretir_ve_istekleri_kaydeder(monkeypatch):
    brief = {"name": "Sohbetle proje", "quick": {"gross_area": 600, "floors": 3, "unit_type": "2+1"}}
    ist = [{"metin": "bahçede havuz", "modellendi": False}, {"metin": "3 katlı", "modellendi": True}]
    fake = Fake(say(use("t1", "projeyi_uret", brief=brief, istekler=ist)), say(text("proje hazır")))
    r = ask_new(fake, monkeypatch, "600 m², 3 kat, havuz da olsun", form={"pw": "30", "taks": "0.4"})
    assert r.status_code == 200, r.text
    pid = r.json()["new_project"]
    assert pid and r.json()["actions"] == [{"tool": "projeyi_uret", "ok": True}]
    first = fake.calls[0]
    assert [t["name"] for t in first["tools"]] == ["projeyi_uret"]                   # yeni modda yalnız üretim aracı
    assert "AÇIK BİR PROJE YOK" in first["system"] and '"taks": "0.4"' in first["system"]
    p = c.get(f"/api/projects/{pid}").json()
    assert p["name"] == "Sohbetle proje" and p["istekler"] == ist
    assert any("havuz" in w and "modellenmedi" in w for w in p["report"]["warnings"])
    assert not any("3 katlı" in w for w in p["report"]["warnings"])


def test_yeni_mod_yuklenen_cokgen(monkeypatch):
    poly = [[0, 0], [32, 0], [29, 26], [2, 23]]
    brief = {"name": "Yamuk sohbet", "parcel": {"yuklenen_cokgen": True},
             "zoning": {"taks": 0.43, "kaks": 3.0, "front": 3, "side": 3.5, "rear": 3.5, "max_floors": 7, "floor_height": 2.75},
             "program": {"unit_type": "1+1", "units_per_floor": 4}}
    fake = Fake(say(use("t1", "projeyi_uret", brief=brief)), say(text("tamam")))
    r = ask_new(fake, monkeypatch, "yüklediğim parsele 7 kat", parsel={"polygon": poly})
    assert r.status_code == 200, r.text
    assert "Kullanıcı parsel DXF'i yükledi: 4 köşe" in fake.calls[0]["system"]
    p = c.get(f"/api/projects/{r.json()['new_project']}").json()
    assert p["report"]["parcel_geom"]["front_edge"] is not None and p["report"]["parcel_area"] > 600
    # DXF yüklenmeden çokgen istenirse araç hatası modele döner
    fake2 = Fake(say(use("t1", "projeyi_uret", brief=brief)), say(text("DXF yükleyin")))
    r2 = ask_new(fake2, monkeypatch, "yamuk parsel")
    assert r2.json()["new_project"] is None and r2.json()["actions"][0]["ok"] is False


def test_yeniden_uretimde_istekler_tasinir(project_id, monkeypatch):
    brief = {"name": "istekli", "quick": {"gross_area": 450, "floors": 3, "unit_type": "2+1"}}
    ist = [{"metin": "çatıda teras bahçe", "modellendi": False}]
    r = ask_new(Fake(say(use("t1", "projeyi_uret", brief=brief, istekler=ist)), say(text("ok"))), monkeypatch)
    pid = r.json()["new_project"]
    new_quick = {"quick": {"gross_area": 900, "floors": 4, "unit_type": "2+1"}}
    r2 = ask(pid, Fake(say(use("t2", "projeyi_yeniden_uret", degisiklikler=new_quick)), say(text("ok"))), monkeypatch)
    p2 = c.get(f"/api/projects/{r2.json()['new_project']}").json()
    assert p2["istekler"] == ist and any("teras" in w for w in p2["report"]["warnings"])

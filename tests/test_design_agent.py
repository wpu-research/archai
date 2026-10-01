"""Tasarım ajanı: sağlayıcılar (kural / claude / http), şema süzmesi, API ve güvenlik."""

import base64
import io
import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from archai import design_agent as DA
from archai import plan_vision
from webapp import design_routes
from webapp.app import PROJECTS, app

ROOT = Path(__file__).resolve().parents[1]
LOCAL = dict(base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
c = TestClient(app, **LOCAL)


def png(color=(230, 225, 215), size=(120, 90), fmt="PNG"):
    b = io.BytesIO()
    Image.new("RGB", size, color).save(b, fmt)
    return b.getvalue()


def photo(color=(230, 225, 215)):
    return DA.clean_photo(png(color))


def key(v):
    return (v["title"], v["floor"], v["wall_paint"], v["furniture_style"], v["decor"], tuple(v["palette"]))


@pytest.fixture(scope="module")
def pid():
    r = c.post("/api/projects", json={"name": "tasarim test", "quick": {"gross_area": 300, "floors": 2, "unit_type": "2+1"}})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def post_design(pid, files=(), **data):
    fl = [("photos", (f"f{i}.png", b, "image/png")) for i, b in enumerate(files)]
    return c.post(f"/api/projects/{pid}/designs", files=fl or None, data=data)


# ------------------------------------------------------------------ katalog eşleşmesi
def test_catalog_matches_viewer():
    js = (ROOT / "webapp/static/interior.js").read_text()
    floors = set(re.findall(r"\{id: '([a-z0-9_]+)', name: '[^']+', tile:", js))
    paints = set(re.findall(r"\{id: '([a-z_]+)', name: '[^']+', c: 0x", js))
    assert floors == set(DA.FLOORS) and paints == set(DA.PAINTS)
    items = set(re.findall(r"\{id: '([A-Za-z0-9_]+)', name:", js))
    assert {k for g in DA.SWAP_GROUPS.values() for k in g} <= items


# ------------------------------------------------------------------ kural sağlayıcı
@pytest.mark.parametrize("n", [3, 4, 5])
def test_kural_deterministic_and_bounds(n):
    ph = [photo((200, 170, 140))]
    a, wa = DA.generate(DA.KuralProvider(), "Sıcak ve modern bir salon, ekonomik olsun", ph, n)
    b, wb = DA.generate(DA.KuralProvider(), "Sıcak ve modern bir salon, ekonomik olsun", ph, n)
    assert len(a) == n and [key(v) for v in a] == [key(v) for v in b] and a[0]["preview"] == b[0]["preview"]
    assert len({v["furniture_style"] for v in a}) == n          # alternatifler birbirinden farklı yönde
    assert [v["id"] for v in a] == [f"v{i}" for i in range(1, n + 1)]
    for v in a:
        assert v["floor"] in DA.FLOORS and v["wall_paint"] in DA.PAINTS and v["patch"]["floors"]["wet"] in DA.FLOORS
        Image.open(io.BytesIO(v["preview"])).verify()


def test_kural_clamps_n_and_needs_no_input():
    assert len(DA.generate(DA.KuralProvider(), "", [], 99)[0]) == 5
    assert len(DA.generate(DA.KuralProvider(), "", [], 1)[0]) == 3


def test_kural_reads_turkish_keywords():
    vs, _ = DA.generate(DA.KuralProvider(), "Skandinav tarzı, kırık beyaz duvar, mermer zemin olsun. Bütçe dostu. Kitaplık ve TV ünitesi", [], 4)
    assert vs[0]["furniture_style"] == "skandinav"
    assert vs[0]["wall_paint"] == "kirik_beyaz" and vs[0]["floor"] == "marble_tiles"
    assert "Kitaplık" in vs[0]["summary"]
    eko, _ = DA.generate(DA.KuralProvider(), "modern ekonomik", [], 3)
    lux, _ = DA.generate(DA.KuralProvider(), "modern lüks premium", [], 3)
    assert eko[0]["floor"] == "laminate_floor_02" and lux[0]["floor"] == "marble_tiles"
    # büyük harf / İ / ı normalleşmesi
    assert DA.parse_brief("SICAK İÇ MEKÂN")["styles"].get("sicak") == 1


def test_kural_photo_palette_drives_style_and_paint():
    dark, _ = DA.generate(DA.KuralProvider(), "", [photo((40, 42, 46))], 3)
    assert dark[0]["furniture_style"] == "endustriyel"
    green, _ = DA.generate(DA.KuralProvider(), "", [photo((120, 160, 110))], 3)
    assert green[0]["furniture_style"] == "dogal"
    warm_wall, _ = DA.generate(DA.KuralProvider(), "modern", [photo((228, 213, 191))], 3)
    assert warm_wall[0]["wall_paint"] in ("kirik_beyaz", "saf_beyaz", "acik_gri")
    assert any(h in warm_wall[0]["palette"] for h in [DA._hex((228, 213, 191))]) or len(warm_wall[0]["palette"]) >= 4


def test_clean_photo_rejects_bad_files():
    for bad in (b"", b"not an image", b"GIF89a" + b"\0" * 20, png(size=(4, 4))):
        with pytest.raises(DA.PhotoError):
            DA.clean_photo(bad)
    big = DA.clean_photo(png(size=(3000, 2000)))
    assert max(Image.open(io.BytesIO(big)).size) <= DA.PHOTO_SIDE


# ------------------------------------------------------------------ şema süzmesi
def test_sanitize_variant_filters_everything():
    v = DA.sanitize_variant({
        "id": "../../etc/passwd", "title": "<script>alert(1)</script>Güzel\x00 Oda" + "x" * 200,
        "summary": "özet‮", "palette": ["#AABBCC", "red", "javascript:1", "112233", 5, None, "#fff"] + ["#000000"] * 9,
        "floor": "../x", "wall_paint": "neon", "furniture_style": "baroque", "decor": "yes",
        "patch": {"floors": {"dry": "marble_tiles", "wet": "nope"}, "sql": "drop", "paint": "bej"},
        "extra": {"a": 1}})
    assert v["id"] == "v1" and set(v) == {"id", "title", "summary", "palette", "floor", "wall_paint", "furniture_style",
                                          "decor", "preview", "patch"}
    assert "<" not in v["title"] and len(v["title"]) <= DA.TITLE_MAX and "\x00" not in v["title"]
    assert v["palette"][:2] == ["#aabbcc", "#112233"] and len(v["palette"]) <= 6
    assert v["floor"] == "marble_tiles" and v["wall_paint"] == "bej" and v["furniture_style"] == "modern" and v["decor"] is False
    assert v["patch"] == {"floors": {"dry": "marble_tiles", "wet": DA.DEFAULT_WET}, "paint": "bej",
                          "furniture_style": "modern", "decor": False}
    assert DA.sanitize_variant("x") is None and DA.sanitize_variant({"nothing": 1}) is None and DA.sanitize_variant(None) is None


def test_preview_validation():
    good = base64.b64encode(png(size=(2000, 1500))).decode()
    assert Image.open(io.BytesIO(DA._preview_bytes(good))).width <= DA.PREVIEW_OUT_SIDE      # yeniden kodlanır
    assert DA._preview_bytes("data:image/png;base64," + good)
    for bad in ("!!!", base64.b64encode(b"<html>").decode(), base64.b64encode(b"GIF89a" + b"0" * 30).decode(),
                base64.b64encode(png(size=(DA.PREVIEW_MAX_SIDE + 1, 10))).decode(), "A" * (DA.PREVIEW_MAX_BYTES * 2), 123, {}):
        assert DA._preview_bytes(bad) is None
    # SVG / script taşıyan "önizleme" asla olduğu gibi saklanmaz
    assert DA._preview_bytes(base64.b64encode(b"<svg onload=alert(1)>").decode()) is None


# ------------------------------------------------------------------ http sağlayıcı (sahte sunucu)
class Fake:
    """Sahte dış ajan: mod değişkenine göre davranır, aldığı istekleri kaydeder."""

    def __init__(self):
        self.mode, self.requests, self.other_hits = "ok", [], 0
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                outer.requests.append((dict(self.headers), json.loads(body)))
                m = outer.mode
                if m == "redirect":
                    self.send_response(302)
                    self.send_header("Location", f"http://127.0.0.1:{outer.port}/other")
                    self.end_headers()
                    return
                if m == "slow":
                    time.sleep(3)
                if m == "500":
                    self.send_response(500)
                    self.end_headers()
                    return
                if m == "huge":
                    data = b'{"variants": [], "pad": "' + b"a" * (DA.HTTP_MAX_RESPONSE + 100) + b'"}'
                elif m == "garbage":
                    data = b"<html>not json"
                elif m == "wrongshape":
                    data = json.dumps({"variants": "x"}).encode()
                elif m == "mixed":
                    data = json.dumps({"variants": [
                        {"title": "İyi", "floor": "oak_wood_planks", "wall_paint": "bej", "furniture_style": "klasik",
                         "decor": True, "palette": ["#112233"], "preview": base64.b64encode(png()).decode(), "evil": "x"},
                        "string", 5, None, {"title": ""}, {"floor": "hack", "wall_paint": "nope"},
                        {"title": "Kötü önizleme", "floor": "marble_tiles", "preview": "<svg onload=1>"},
                        {"title": "<img src=x onerror=1>XSS", "wall_paint": "gok"}] + [{"title": f"t{i}", "floor": "wood_floor"} for i in range(30)]
                    }).encode()
                else:
                    data = json.dumps({"variants": [{"title": f"Ajan {i}", "summary": "s", "floor": "marble_tiles",
                                                     "wall_paint": "adacayi", "furniture_style": "dogal", "decor": True,
                                                     "palette": ["#010203"]} for i in range(3)]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                outer.other_hits += 1
                self.send_response(200)
                self.end_headers()

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}/agent"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()


@pytest.fixture()
def fake(monkeypatch):
    f = Fake()
    monkeypatch.setenv("ARCHAI_DESIGN_AGENT_URL", f.url)
    monkeypatch.setenv("ARCHAI_DESIGN_AGENT_TIMEOUT", "1")
    yield f
    f.srv.shutdown()


def run_http(brief="oda", photos=(), n=3):
    return DA.generate(DA.HttpProvider(), brief, list(photos), n, {"levels": 1})


def test_http_contract_and_request_body(fake, monkeypatch):
    monkeypatch.setenv("ARCHAI_DESIGN_AGENT_TOKEN", "sir")
    ph = photo()
    vs, _ = run_http("Mavi bir oda", [ph], 3)
    assert [v["title"] for v in vs] == ["Ajan 0", "Ajan 1", "Ajan 2"] and vs[0]["patch"]["floors"]["dry"] == "marble_tiles"
    hdr, body = fake.requests[0]
    assert body["brief"] == "Mavi bir oda" and body["n"] == 3 and base64.b64decode(body["photos"][0]) == ph
    assert body["project"] == {"levels": 1} and hdr["Authorization"] == "Bearer sir"
    assert Image.open(io.BytesIO(vs[0]["preview"])).format == "JPEG"          # ajan önizleme vermediyse yerelde çizilir


def test_http_mixed_and_malicious_response(fake):
    fake.mode = "mixed"
    vs, warn = run_http(n=5)
    assert len(vs) == 5 and vs[0]["title"] == "İyi" and vs[0]["furniture_style"] == "klasik"
    assert all(set(v) == {"id", "title", "summary", "palette", "floor", "wall_paint", "furniture_style", "decor", "preview", "patch"}
               for v in vs)
    assert all(v["floor"] in DA.FLOORS and v["wall_paint"] in DA.PAINTS for v in vs)
    assert all("<" not in v["title"] for v in vs)
    for v in vs:
        assert Image.open(io.BytesIO(v["preview"])).format == "JPEG"          # kötü önizleme → yerel çizim


@pytest.mark.parametrize("mode", ["500", "garbage", "wrongshape", "huge", "slow", "redirect"])
def test_http_bad_responses_are_contained(fake, mode):
    fake.mode = mode
    with pytest.raises(DA.ProviderError) as ei:
        run_http()
    assert ei.value.status == 502 and "\n" not in str(ei.value) and "127.0.0.1" not in str(ei.value)
    assert fake.other_hits == 0                    # yönlendirme izlenmedi


def test_http_requires_env_url(monkeypatch):
    monkeypatch.delenv("ARCHAI_DESIGN_AGENT_URL", raising=False)
    with pytest.raises(DA.ProviderError) as ei:
        run_http()
    assert ei.value.status == 422
    for bad in ("file:///etc/passwd", "ftp://x/y", "javascript:1", "//x"):
        monkeypatch.setenv("ARCHAI_DESIGN_AGENT_URL", bad)
        with pytest.raises(DA.ProviderError):
            run_http()


# ------------------------------------------------------------------ claude sağlayıcı
class SpyClient:
    def __init__(self, reply=None):
        self.calls = 0
        self.reply = reply
        outer = self

        class Msgs:
            def create(self, **kw):
                outer.calls += 1
                outer.kw = kw
                text = type("B", (), {"type": "text", "text": json.dumps(outer.reply)})()
                return type("R", (), {"stop_reason": "end_turn", "content": [text]})()
        self.beta = type("Beta", (), {"messages": Msgs()})()


def test_claude_never_calls_without_consent_or_credentials(monkeypatch):
    spy = SpyClient({"variants": []})
    with pytest.raises(DA.ProviderError) as ei:
        DA.ClaudeProvider(consent=False, client=spy).generate("x", [photo()], 3)
    assert ei.value.status == 422 and spy.calls == 0
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(plan_vision, "available", lambda: False)
    boom = {"n": 0}

    def fail(*a, **k):
        boom["n"] += 1
        raise AssertionError("ağ çağrısı yapılmamalıydı")
    monkeypatch.setattr("anthropic.Anthropic", fail)
    with pytest.raises(DA.ProviderError) as ei:
        DA.ClaudeProvider(consent=True).generate("x", [photo()], 3)
    assert ei.value.status == 422 and boom["n"] == 0
    with pytest.raises(DA.ProviderError):                           # "true" metni ya da truthy değer onay sayılmaz
        DA.ClaudeProvider(consent="true", client=spy).generate("x", [], 3)
    assert spy.calls == 0


def test_claude_with_consent_filters_output():
    reply = {"variants": [{"title": "<b>Claude</b> 1", "summary": "ok", "floor": "oak_wood_planks", "wet_floor": "marble_tiles",
                           "wall_paint": "bej", "furniture_style": "klasik", "decor": True, "palette": ["#0a0b0c"]},
                          {"title": "Hileli", "summary": "x", "floor": "zzz", "wet_floor": "yyy", "wall_paint": "qqq",
                           "furniture_style": "www", "decor": False, "palette": ["not-a-color"]}] * 3}
    spy = SpyClient(reply)
    vs, _ = DA.generate(DA.ClaudeProvider(consent=True, client=spy), "mavi bir oda", [photo()], 4)
    assert spy.calls == 1 and len(vs) == 4
    assert vs[0]["patch"]["floors"] == {"dry": "oak_wood_planks", "wet": "marble_tiles"} and "<" not in vs[0]["title"]
    assert vs[1]["floor"] == DA.DEFAULT_FLOOR and vs[1]["wall_paint"] == DA.DEFAULT_PAINT
    content = spy.kw["messages"][0]["content"]
    assert content[0]["type"] == "image" and "<kullanici_metni>" in content[-1]["text"]
    assert spy.kw["output_config"]["format"]["type"] == "json_schema"


# ------------------------------------------------------------------ uygulama (interior.json)
ELS = [{"type": "room", "kind": "room", "name": "Zemin Kat/Daire A/Salon", "level": "Zemin Kat", "points": [[0, 0], [4, 0], [4, 4], [0, 4]]},
       {"type": "room", "kind": "room", "name": "Zemin Kat/Daire A/Banyo", "level": "Zemin Kat", "points": [[4, 0], [6, 0], [6, 2], [4, 2]]},
       {"type": "room", "kind": "common", "name": "Zemin Kat/Kat Holü", "level": "Zemin Kat", "points": [[6, 0], [8, 0], [8, 2], [6, 2]]}]


def test_apply_variant_pure():
    v = DA.sanitize_variant({"title": "t", "floor": "oak_wood_planks", "wall_paint": "adacayi", "furniture_style": "klasik",
                             "decor": False, "patch": {"floors": {"wet": "marble_tiles"}}})
    cur = {"floors": {"Zemin Kat/Kat Holü": "terrazzo_tiles"}, "paint": "bej", "demolished": ["w1"],
           "objects": [{"id": "a", "kind": "modern_arm_chair_01", "x": 1, "y": 2},
                       {"id": "b", "kind": "sandalye", "x": 1, "y": 2}, {"id": "c", "kind": "kanepe", "x": 3, "y": 3},
                       {"id": "d", "kind": "hali", "decor": True, "x": 1, "y": 1}]}
    snap = json.dumps(cur, sort_keys=True)
    out = DA.apply_variant(v, cur, ELS)
    assert json.dumps(cur, sort_keys=True) == snap                              # girdi değişmez
    assert out["floors"]["Zemin Kat/Daire A/Salon"] == "oak_wood_planks"
    assert out["floors"]["Zemin Kat/Daire A/Banyo"] == "marble_tiles"
    assert out["floors"]["Zemin Kat/Kat Holü"] == "terrazzo_tiles"             # ortak alana dokunulmaz
    assert out["paint"] == "adacayi" and out["demolished"] == ["w1"]
    kinds = {o["id"]: o["kind"] for o in out["objects"]}
    assert kinds == {"a": "mid_century_lounge_chair", "b": "dining_chair_02", "c": "kanepe"}   # klasik; dekor kapalı → silindi


# ------------------------------------------------------------------ API
def test_api_flow_select_updates_interior_and_cost(pid):
    before = c.get(f"/api/projects/{pid}").json()
    r = post_design(pid, [png((60, 60, 66))], brief="Endüstriyel loft, siyah çerçeve, beton etkisi", n="4", provider="kural")
    assert r.status_code == 200, r.text
    s = r.json()
    assert len(s["variants"]) == 4 and s["provider"] == "kural" and s["photos"] == 1 and "avan" in s["notice"].lower()
    assert s["variants"][0]["furniture_style"] == "endustriyel"
    assert all(v["cost"]["total"] and "zem_variant" in v["cost"] for v in s["variants"])
    pv = c.get(s["variants"][0]["preview"])
    assert pv.status_code == 200 and pv.headers["content-type"] == "image/jpeg" and Image.open(io.BytesIO(pv.content)).size[0] > 100
    assert c.get(f"/api/projects/{pid}/designs").json()["sets"][0]["id"] == s["id"]
    # tohumlanmış iç mekân: berjer + dekor
    c.put(f"/api/projects/{pid}/interior", json={"floors": {}, "paint": "kirik_beyaz", "objects": [
        {"id": "z1", "kind": "modern_arm_chair_01", "level": "Zemin Kat", "x": 2, "y": 2, "rot": 0, "h": 0},
        {"id": "z2", "kind": "hali", "level": "Zemin Kat", "x": 2, "y": 2, "rot": 0, "h": 0, "decor": True}]})
    sel = c.post(f"/api/projects/{pid}/designs/{s['id']}/select", json={"variant": "v2"})
    assert sel.status_code == 200, sel.text
    out = sel.json()
    v = s["variants"][1]
    inter = c.get(f"/api/projects/{pid}/interior").json()
    assert inter["paint"] == v["wall_paint"] and out["interior"] == inter
    rooms = [e for e in c.get(f"/api/projects/{pid}/elements").json() if e["type"] == "room" and e.get("kind", "room") == "room"]
    assert rooms and all(inter["floors"][r["name"]] in (v["floor"], v["patch"]["floors"]["wet"]) for r in rooms)
    assert any(inter["floors"][r["name"]] == v["floor"] for r in rooms)
    after = c.get(f"/api/projects/{pid}").json()
    assert after["brief"]["adjust"]["variants"]["ZEM-01"] == v["cost"]["zem_variant"]
    assert after["cost"]["total"] == pytest.approx(v["cost"]["total"], rel=1e-6)           # önizlenen maliyet = uygulanan
    assert out["project"]["cost"]["total"] == after["cost"]["total"] and before["id"] == after["id"]
    ids = {o["id"]: o for o in inter["objects"]}
    assert ids["z1"]["kind"] == DA.SWAP_GROUPS["berjer"][DA.STYLES[v["furniture_style"]]["swap"][0]]
    assert ("z2" in ids) == v["decor"] and out["decor"] == v["decor"]
    assert c.get(f"/api/projects/{pid}/designs").json()["sets"][0]["selected"] == "v2"
    # belgeler yeniden üretilir ve avan notu korunur
    assert c.get(after["files"]["teklif_docx"]).status_code == 200 and "avan" in out["notice"].lower()


def test_api_validation_and_security(pid):
    base = f"/api/projects/{pid}/designs"
    sets_before = len(c.get(base).json()["sets"])
    assert post_design(pid, [png()], n="2").status_code == 422
    assert post_design(pid, [png()], n="6").status_code == 422
    assert post_design(pid, [png()], n="x").status_code == 422
    assert post_design(pid, [png()], provider="evil").status_code == 422
    assert post_design(pid).status_code == 422                                   # ne foto ne metin
    assert post_design(pid, [png()] * 6, brief="x").status_code == 422           # çok fotoğraf
    assert post_design(pid, brief="x" * (DA.MAX_BRIEF + 1)).status_code == 422
    bad = post_design(pid, [b"MZ\x90\x00 not an image"], brief="x")
    assert bad.status_code == 422 and "\n" not in bad.json()["detail"]
    assert post_design(pid, [b"<svg xmlns='http://www.w3.org/2000/svg' onload='alert(1)'/>"], brief="x").status_code == 422
    assert post_design(pid, [png(size=(4, 4))], brief="x").status_code == 422
    assert post_design(pid, [png()], brief="x", provider="claude").status_code == 422        # onay yok
    assert post_design(pid, [png()], brief="x", provider="claude", claude_consent="true").status_code in (422, 502)
    assert post_design(pid, [png()], brief="x", provider="http").status_code == 422          # ortamda adres yok
    # hiçbir hata yarım set bırakmaz
    assert len(c.get(base).json()["sets"]) == sets_before
    # kimlik doğrulama
    for bad_pid in ("yok", "../x", "20260101-000000-yok-0000", "%2e%2e"):
        assert c.get(f"/api/projects/{bad_pid}/designs").status_code == 404
        assert post_design(bad_pid, brief="x").status_code in (404, 405)
    ok = post_design(pid, brief="x").json()
    for bad in ("../../../etc/passwd", "v1", "000000000000-0000", "x" * 40):
        assert c.get(f"/api/projects/{pid}/designs/{bad}/preview/v1").status_code == 404
        assert c.post(f"/api/projects/{pid}/designs/{bad}/select", json={"variant": "v1"}).status_code in (404, 405)
    for vid in ("v0", "v99", "..", "v1.jpg", "set.json", "V1"):
        assert c.get(f"/api/projects/{pid}/designs/{ok['id']}/preview/{vid}").status_code == 404
    sel = f"{base}/{ok['id']}/select"
    for body in ({"variant": "../x"}, {"variant": "v9"}, {"variant": 1}, {}, {"variant": "v1", "x": 1}):
        assert c.post(sel, json=body).status_code in (404, 422)
    assert c.post(sel, json={"variant": "v1"}).status_code == 200
    # çapraz kaynak
    assert c.post(sel, json={"variant": "v1"}, headers={"Origin": "http://evil.example"}).status_code == 403
    assert c.post(base, data={"brief": "x"}, headers={"Origin": "http://evil.example"}).status_code == 403
    assert c.post(base, data={"brief": "x"}, headers={"Host": "evil.example"}).status_code == 400


def test_api_upload_size_limit(pid, monkeypatch):
    monkeypatch.setattr(design_routes, "MAX_PHOTO_BYTES", 1000)
    noise = io.BytesIO()
    Image.frombytes("RGB", (60, 60), os.urandom(60 * 60 * 3)).save(noise, "PNG")
    assert len(noise.getvalue()) > 1000
    assert post_design(pid, [noise.getvalue()], brief="x").status_code == 413


def test_api_html_in_brief_is_stored_inert(pid):
    r = post_design(pid, brief="<script>alert(1)</script> modern <img src=x onerror=alert(2)>").json()
    assert "<" not in r["brief"] and ">" not in r["brief"]
    assert all("<" not in v["title"] + v["summary"] for v in r["variants"])


def test_api_http_provider_end_to_end(pid, fake):
    fake.mode = "mixed"
    r = post_design(pid, [png()], brief="ajan dene", n="3", provider="http")
    assert r.status_code == 200, r.text
    assert r.json()["provider"] == "http" and r.json()["variants"][0]["title"] == "İyi"
    fake.mode = "500"
    assert post_design(pid, brief="x", provider="http").status_code == 502


def test_api_no_orphans_and_pruning(pid, monkeypatch):
    d = PROJECTS / pid / "designs"
    monkeypatch.setattr(design_routes, "MAX_SETS", 3)
    for _ in range(5):
        assert post_design(pid, brief="modern").status_code == 200
        time.sleep(0.01)
    names = [p.name for p in d.iterdir() if p.is_dir()]
    assert len(names) == 3 and all((d / n / "set.json").is_file() for n in names)
    # bozuk set listeyi bozmaz
    (d / names[0] / "set.json").write_text("{bozuk")
    got = c.get(f"/api/projects/{pid}/designs")
    assert got.status_code == 200 and len(got.json()["sets"]) == 2
    assert c.post(f"/api/projects/{pid}/designs/{names[0]}/select", json={"variant": "v1"}).status_code == 422
    assert not list(d.rglob("*.tmp"))


def test_photos_are_not_persisted(pid):
    marker = png((12, 34, 56), size=(64, 64))
    post_design(pid, [marker], brief="x")
    for f in (PROJECTS / pid / "designs").rglob("*"):
        if f.is_file():
            assert f.suffix in (".json", ".jpg") and f.name != "photo.jpg"

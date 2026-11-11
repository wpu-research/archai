"""Growth Engine ↔ Core Fizibilite API entegrasyon testleri.

Testler offline çalışır: HTTP yanıtları taklit edilerek Growth Engine'in
istek ve yanıt sözleşmesi doğrulanır. .env secretleri okunmaz.
"""

import json
from unittest.mock import patch

import pytest

from growth_engine.server import _fizibilite_hesapla, karlilik, kat_karsiligi


# Test proje verisi (core fizibilite API'sinin beklediği formatta)
TEST_PROJECT_ID = "20261103-120000-abcdef"


class MockResponse:
    """httpx.Response mock'u."""
    def __init__(self, status_code, json_data, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text or json.dumps(json_data)

    def json(self):
        return self._json


class MockAsyncClient:
    """httpx.AsyncClient mock'u - belirli URL'ler için yanıt döndürür."""
    def __init__(self, responses):
        self.responses = {
            ("get", f"http://127.0.0.1:8000/api/projects/{TEST_PROJECT_ID}"): MockResponse(200, {
                "rooms": [{"name": "Kat 1/Daire 1/Hol", "area": 80},
                          {"name": "Ortak hol", "area": 20}],
                "summary": {"gross_floor_area": 1000},
            }),
            **responses,
        }
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def post(self, url, json=None, headers=None):
        self.calls.append(("post", url, json, headers))
        key = ("post", url)
        if key in self.responses:
            return self.responses[key]
        return MockResponse(404, {"detail": "Not found"})

    async def get(self, url, headers=None):
        self.calls.append(("get", url, None, headers))
        key = ("get", url)
        if key in self.responses:
            return self.responses[key]
        return MockResponse(404, {"detail": "Not found"})


# Core fizibilite API başarılı yanıtı
SUCCESS_FIZIBILITE = {
    "varsayimlar": {
        "arsa_bedeli_tl": 500000,
        "satis_m2_fiyati_tl": 25000,
        "satilabilir_alan_m2": 800,
        "ek_gider_pct": 10
    },
    "sonuc": {
        "insaat_bedeli_tl": 1000000,
        "ek_gider_tl": 100000,
        "toplam_gider_tl": 1600000,
        "satis_geliri_tl": 20000000,
        "tahmini_kar_tl": 18400000,
        "kar_marji_pct": 92.0,
        "maliyet_getirisi_pct": 1150.0,
        "basabas_m2_fiyati_tl": 2000
    },
    "kaynak": {
        "proje_parmak_izi": "a" * 64,
        "metraj_parmak_izi": "b" * 64,
        "maliyet_alani": "cost.total"
    },
    "uyarilar": ["Avan fizibilite..."]
}


def test_fizibilite_hesapla_basari():
    """Core fizibilite API başarılı yanıtını işler ve _kaynak metadata ekler."""
    responses = {
        ("post", "http://127.0.0.1:8000/api/projects/20261103-120000-abcdef/fizibilite"): MockResponse(200, SUCCESS_FIZIBILITE)
    }
    mock_client = MockAsyncClient(responses)

    with patch("httpx.AsyncClient", return_value=mock_client):
        import asyncio
        result = asyncio.run(_fizibilite_hesapla(
            proje_id=TEST_PROJECT_ID,
            arsa_bedeli_tl=500000,
            satis_m2_fiyati_tl=25000,
            ek_gider_pct=10,
        ))

    assert result["varsayimlar"]["arsa_bedeli_tl"] == 500000
    assert result["sonuc"]["satis_geliri_tl"] == 20000000
    assert "_kaynak" in result
    assert result["_kaynak"]["endpoint"] == "/api/projects/{pid}/fizibilite"
    assert result["_kaynak"]["satilabilir_alan_kaynak"] == "inferred_from_project"
    assert result["_kaynak"]["core_fingerprint"] == "a" * 64
    assert result["_kaynak"]["metraj_fingerprint"] == "b" * 64
    assert [call[0] for call in mock_client.calls] == ["get", "post"]
    assert mock_client.calls[1][2]["satilabilir_alan_m2"] == 800
    for call in mock_client.calls:
        assert call[3]["Authorization"] == "Bearer test-core-api-token"


def test_fizibilite_hesapla_explicit_alan():
    """satilabilir_alan_m2 açıkça verildiğinde _kaynak 'explicit' işaretler."""
    fiz = {**SUCCESS_FIZIBILITE, "varsayimlar": {**SUCCESS_FIZIBILITE["varsayimlar"], "satilabilir_alan_m2": 900}}
    responses = {
        ("post", "http://127.0.0.1:8000/api/projects/20261103-120000-abcdef/fizibilite"): MockResponse(200, fiz)
    }
    mock_client = MockAsyncClient(responses)

    with patch("httpx.AsyncClient", return_value=mock_client):
        import asyncio
        result = asyncio.run(_fizibilite_hesapla(
            proje_id=TEST_PROJECT_ID,
            arsa_bedeli_tl=500000,
            satis_m2_fiyati_tl=25000,
            ek_gider_pct=10,
            satilabilir_alan_m2=900,
        ))

    assert result["varsayimlar"]["satilabilir_alan_m2"] == 900
    assert result["_kaynak"]["satilabilir_alan_kaynak"] == "explicit"
    # Body'de satilabilir_alan_m2 gönderilmiş olmalı
    sent_body = mock_client.calls[0][2]
    assert sent_body["satilabilir_alan_m2"] == 900


def test_fizibilite_hesapla_401_unauthorized():
    """ARCHAI_TOKEN geçersizse 401 hatası net şekilde fırlatılır."""
    responses = {
        ("post", "http://127.0.0.1:8000/api/projects/20261103-120000-abcdef/fizibilite"): MockResponse(401, {"detail": "unauthorized"})
    }
    mock_client = MockAsyncClient(responses)

    with patch("httpx.AsyncClient", return_value=mock_client):
        import asyncio
        with pytest.raises(ValueError, match="yetkisiz"):
            asyncio.run(_fizibilite_hesapla(
                proje_id=TEST_PROJECT_ID,
                arsa_bedeli_tl=500000,
                satis_m2_fiyati_tl=25000,
                ek_gider_pct=10,
            ))


def test_fizibilite_hesapla_409_stale_quantities():
    """Metraj parmak izi değişmişse 409 hatası net şekilde fırlatılır."""
    responses = {
        ("post", "http://127.0.0.1:8000/api/projects/20261103-120000-abcdef/fizibilite"): MockResponse(409, {"detail": "Metraj referansı değişmiş. ONAY sekmesinden yenileyin."})
    }
    mock_client = MockAsyncClient(responses)

    with patch("httpx.AsyncClient", return_value=mock_client):
        import asyncio
        with pytest.raises(ValueError, match="Metraj referansı değişmiş"):
            asyncio.run(_fizibilite_hesapla(
                proje_id=TEST_PROJECT_ID,
                arsa_bedeli_tl=500000,
                satis_m2_fiyati_tl=25000,
                ek_gider_pct=10,
            ))


def test_fizibilite_hesapla_422_invalid_input():
    """Geçersiz girdilerde 422 hatası net şekilde fırlatılır."""
    responses = {
        ("post", "http://127.0.0.1:8000/api/projects/20261103-120000-abcdef/fizibilite"): MockResponse(422, {"detail": "Satılabilir alan pozitif olmalı"})
    }
    mock_client = MockAsyncClient(responses)

    with patch("httpx.AsyncClient", return_value=mock_client):
        import asyncio
        with pytest.raises(ValueError, match="Geçersiz girdi"):
            asyncio.run(_fizibilite_hesapla(
                proje_id=TEST_PROJECT_ID,
                arsa_bedeli_tl=500000,
                satis_m2_fiyati_tl=25000,
                ek_gider_pct=10,
            ))


def test_fizibilite_hesapla_gecersiz_proje_id():
    """Geçersiz proje_id formatında ValueError fırlatır."""
    import asyncio
    with pytest.raises(ValueError, match="geçersiz proje_id"):
        asyncio.run(_fizibilite_hesapla(
            proje_id="invalid-id",
            arsa_bedeli_tl=500000,
            satis_m2_fiyati_tl=25000,
            ek_gider_pct=10,
        ))


# --- karlilik aracı testleri ---

def test_karlilik_basari():
    """karlilik aracı core API'den veri çeker ve doğru formatta döner."""
    responses = {
        ("post", "http://127.0.0.1:8000/api/projects/20261103-120000-abcdef/fizibilite"): MockResponse(200, SUCCESS_FIZIBILITE),
        ("get", "http://127.0.0.1:8000/api/projects/20261103-120000-abcdef"): MockResponse(200, {"rooms": [{"name": "Kat 1/Daire 1/Hol", "area": 800}], "summary": {"gross_floor_area": 800}, "cost": {"total": 1000000}})
    }
    mock_client = MockAsyncClient(responses)

    with patch("httpx.AsyncClient", return_value=mock_client):
        import asyncio
        result = asyncio.run(karlilik(
            proje_id=TEST_PROJECT_ID,
            arsa_fiyati_tl=500000,
            satis_m2_fiyati_tl=25000,
            ek_gider_pct=10,
        ))

    assert result["proje_id"] == TEST_PROJECT_ID
    assert result["satis_geliri_tl"] == 20000000
    assert result["kar_tl"] == 18400000
    assert "_kaynak" in result
    assert result["_kaynak"]["satilabilir_alan_kaynak"] == "inferred_from_project"


def test_karlilik_explicit_alan():
    """karlilik aracında explicit satilabilir_alan_m2 parametresi çalışır."""
    fiz = {**SUCCESS_FIZIBILITE, "varsayimlar": {**SUCCESS_FIZIBILITE["varsayimlar"], "satilabilir_alan_m2": 900}}
    responses = {
        ("post", "http://127.0.0.1:8000/api/projects/20261103-120000-abcdef/fizibilite"): MockResponse(200, fiz),
        ("get", "http://127.0.0.1:8000/api/projects/20261103-120000-abcdef"): MockResponse(200, {"rooms": [{"name": "Kat 1/Daire 1/Hol", "area": 800}], "summary": {"gross_floor_area": 800}, "cost": {"total": 1000000}})
    }
    mock_client = MockAsyncClient(responses)

    with patch("httpx.AsyncClient", return_value=mock_client):
        import asyncio
        result = asyncio.run(karlilik(
            proje_id=TEST_PROJECT_ID,
            arsa_fiyati_tl=500000,
            satis_m2_fiyati_tl=25000,
            ek_gider_pct=10,
            satilabilir_alan_m2=900,
        ))

    assert result["satilabilir_brut_m2"] == 900
    assert result["_kaynak"]["satilabilir_alan_kaynak"] == "explicit"


# --- kat_karsiligi aracı testleri ---

SUCCESS_FIZIBILITE_KK = {
    "varsayimlar": {"arsa_bedeli_tl": 0, "satis_m2_fiyati_tl": 25000, "satilabilir_alan_m2": 800, "ek_gider_pct": 10},
    "sonuc": {
        "insaat_bedeli_tl": 1000000,
        "ek_gider_tl": 100000,
        "toplam_gider_tl": 1100000,
        "satis_geliri_tl": 20000000,
        "tahmini_kar_tl": 18900000,
        "kar_marji_pct": 94.5,
        "maliyet_getirisi_pct": 1718.2,
        "basabas_m2_fiyati_tl": 1375
    },
    "kaynak": {"proje_parmak_izi": "c" * 64, "metraj_parmak_izi": "d" * 64, "maliyet_alani": "cost.total"},
    "uyarilar": []
}


def _make_rooms():
    """Oda isimleri: 'Kat X/Daire Y/Mahal' formatında - _daireler buna göre sayar."""
    rooms = []
    for kat in (1, 2):
        for daire in (1, 2):
            base = f"Kat {kat}/Daire {daire}"
            rooms.append({"name": f"{base}/Hol", "area": 20})
            rooms.append({"name": f"{base}/Yatak Odası", "area": 30})
            rooms.append({"name": f"{base}/Banyo", "area": 10})
    return rooms


def test_kat_karsiligi_basari():
    """kat_karsiligi aracı core API kullanır ve paylaşım hesaplar."""
    responses = {
        ("post", "http://127.0.0.1:8000/api/projects/20261103-120000-abcdef/fizibilite"): MockResponse(200, SUCCESS_FIZIBILITE_KK),
        ("get", "http://127.0.0.1:8000/api/projects/20261103-120000-abcdef"): MockResponse(200, {
            "rooms": _make_rooms(),
            "summary": {"gross_floor_area": 800},
            "cost": {"total": 1000000}
        })
    }
    mock_client = MockAsyncClient(responses)

    with patch("httpx.AsyncClient", return_value=mock_client):
        import asyncio
        result = asyncio.run(kat_karsiligi(
            proje_id=TEST_PROJECT_ID,
            satis_m2_fiyati_tl=25000,
            arsa_sahibi_payi_pct=45,
            hedef_marj_pct=20,
            ek_gider_pct=10,
        ))

    assert result["proje_id"] == TEST_PROJECT_ID
    assert result["daire_sayisi"] == 4
    assert "istenen_pay" in result
    assert "onerilen" in result
    assert "_kaynak" in result


def test_kat_karsiligi_hedef_marj_100_hata():
    """hedef_marj_pct >= 100 olduğunda ValueError fırlatır (bölme sıfıra)."""
    responses = {
        ("post", "http://127.0.0.1:8000/api/projects/20261103-120000-abcdef/fizibilite"): MockResponse(200, SUCCESS_FIZIBILITE_KK),
        ("get", "http://127.0.0.1:8000/api/projects/20261103-120000-abcdef"): MockResponse(200, {
            "rooms": [{"name": "Kat 1/Daire 1/Hol", "area": 100}],
            "summary": {"gross_floor_area": 800}, "cost": {"total": 1000000}
        })
    }
    mock_client = MockAsyncClient(responses)

    with patch("httpx.AsyncClient", return_value=mock_client):
        import asyncio
        with pytest.raises(ValueError, match="hedef_marj_pct 0 dahil, 100 hariç"):
            asyncio.run(kat_karsiligi(
                proje_id=TEST_PROJECT_ID,
                satis_m2_fiyati_tl=25000,
                arsa_sahibi_payi_pct=45,
                hedef_marj_pct=100,  # Geçersiz
                ek_gider_pct=10,
            ))


def test_kat_karsiligi_sifir_gelir_hata():
    """Satış geliri sıfır/negatif olduğunda ValueError fırlatır."""
    fiz_zero = {**SUCCESS_FIZIBILITE_KK, "sonuc": {**SUCCESS_FIZIBILITE_KK["sonuc"], "satis_geliri_tl": 0}}
    responses = {
        ("post", "http://127.0.0.1:8000/api/projects/20261103-120000-abcdef/fizibilite"): MockResponse(200, fiz_zero),
        ("get", "http://127.0.0.1:8000/api/projects/20261103-120000-abcdef"): MockResponse(200, {
            "rooms": [{"name": "Kat 1/Daire 1/Hol", "area": 100}],
            "summary": {"gross_floor_area": 800}, "cost": {"total": 1000000}
        })
    }
    mock_client = MockAsyncClient(responses)

    with patch("httpx.AsyncClient", return_value=mock_client):
        import asyncio
        with pytest.raises(ValueError, match="Satış geliri sıfır veya negatif"):
            asyncio.run(kat_karsiligi(
                proje_id=TEST_PROJECT_ID,
                satis_m2_fiyati_tl=0,  # Sıfır fiyat
                arsa_sahibi_payi_pct=45,
                hedef_marj_pct=20,
                ek_gider_pct=10,
            ))


def test_kat_karsiligi_explicit_alan():
    """kat_karsiligi aracında explicit satilabilir_alan_m2 parametresi çalışır."""
    fiz = {**SUCCESS_FIZIBILITE_KK, "varsayimlar": {**SUCCESS_FIZIBILITE_KK["varsayimlar"], "satilabilir_alan_m2": 900}}
    responses = {
        ("post", "http://127.0.0.1:8000/api/projects/20261103-120000-abcdef/fizibilite"): MockResponse(200, fiz),
        ("get", "http://127.0.0.1:8000/api/projects/20261103-120000-abcdef"): MockResponse(200, {
            "rooms": _make_rooms(),
            "summary": {"gross_floor_area": 800}, "cost": {"total": 1000000}
        })
    }
    mock_client = MockAsyncClient(responses)

    with patch("httpx.AsyncClient", return_value=mock_client):
        import asyncio
        result = asyncio.run(kat_karsiligi(
            proje_id=TEST_PROJECT_ID,
            satis_m2_fiyati_tl=25000,
            arsa_sahibi_payi_pct=45,
            hedef_marj_pct=20,
            ek_gider_pct=10,
            satilabilir_alan_m2=900,
        ))

    # _fizibilite_hesapla'ya 900 gönderilmiş olmalı
    sent_body = mock_client.calls[0][2]
    assert sent_body["satilabilir_alan_m2"] == 900


# --- Parite testleri: mevcut imza korundu mu? ---

def test_karlilik_imza_korundu():
    """karlilik fonksiyon imzası: proje_id, arsa_fiyati_tl, satis_m2_fiyati_tl, ek_gider_pct=10, satilabilir_alan_m2=None"""
    import inspect
    sig = inspect.signature(karlilik)
    params = list(sig.parameters.keys())
    assert params == ["proje_id", "arsa_fiyati_tl", "satis_m2_fiyati_tl", "ek_gider_pct", "satilabilir_alan_m2"]
    assert sig.parameters["ek_gider_pct"].default == 10
    assert sig.parameters["satilabilir_alan_m2"].default is None


def test_kat_karsiligi_imza_korundu():
    """kat_karsiligi fonksiyon imzası: proje_id, satis_m2_fiyati_tl, arsa_sahibi_payi_pct=45, hedef_marj_pct=20, ek_gider_pct=10, satilabilir_alan_m2=None"""
    import inspect
    sig = inspect.signature(kat_karsiligi)
    params = list(sig.parameters.keys())
    assert params == ["proje_id", "satis_m2_fiyati_tl", "arsa_sahibi_payi_pct", "hedef_marj_pct", "ek_gider_pct", "satilabilir_alan_m2"]
    assert sig.parameters["arsa_sahibi_payi_pct"].default == 45
    assert sig.parameters["hedef_marj_pct"].default == 20
    assert sig.parameters["ek_gider_pct"].default == 10
    assert sig.parameters["satilabilir_alan_m2"].default is None

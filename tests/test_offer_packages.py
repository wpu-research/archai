"""Sürümlü teklif belgeleri: kaynak değişse bile önceki paketler sabit kalır."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from archai import approval, offer_packages, quantities
from webapp.app import app


@pytest.fixture
def source(tmp_path, monkeypatch):
    import webapp.app as webapp_module
    directory = tmp_path / "projects" / "20261104-120000-test"
    directory.mkdir(parents=True)
    monkeypatch.setattr(webapp_module, "PROJECTS", directory.parent)
    doc = directory / "teklif.docx"
    doc.write_bytes(b"offer v1")
    qfp = approval.quantities_fp(quantities.compute([]))
    record = {"name": "Deneme", "brief": {}, "cost": {"total": 1200},
              "quantities_fp": qfp, "files": {"teklif_docx": str(doc)}}
    (directory / "project.json").write_text(json.dumps(record))
    (directory / "elements.json").write_text("[]")
    return directory, record, doc


def test_immutable_offer_versions_and_api(source):
    directory, record, doc = source
    client = TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
    url = "/api/projects/20261104-120000-test/teklif-paketleri"
    assert client.get(url).json() == {"paketler": []}
    first = client.post(url)
    assert first.status_code == 200, first.text
    a = first.json()["paket"]
    assert a["version"] == 1 and a["approval_status"] == "taslak"
    assert a["documents"]["teklif_docx"]["url"].endswith("/v0001/teklif.docx")
    assert client.get(a["documents"]["teklif_docx"]["url"]).content == b"offer v1"
    doc.write_bytes(b"offer v2")
    second = client.post(url)
    assert second.status_code == 200, second.text
    assert second.json()["paket"]["version"] == 2
    assert (directory / "teklif_paketleri/v0001/teklif.docx").read_bytes() == b"offer v1"
    assert (directory / "teklif_paketleri/v0002/teklif.docx").read_bytes() == b"offer v2"
    listed = client.get(url).json()["paketler"]
    assert [p["version"] for p in listed] == [2, 1]
    assert client.get(listed[1]["documents"]["teklif_docx"]["url"]).content == b"offer v1"
    assert json.loads((directory / "teklif_paketleri/v0001/manifest.json").read_text())["documents"] == {
        "teklif_docx": {"file": "teklif.docx", "sha256": a["documents"]["teklif_docx"]["sha256"]}}


def test_archive_cannot_mask_missing_approved_document(source):
    directory, record, doc = source
    fp = approval.current_fp(directory)
    (directory / approval.FILE).write_text(json.dumps({
        "status": "onaylandi", "fingerprint": fp, "quantities_fp": record["quantities_fp"],
        "signer": {"name": "Test User", "title": "Mimar", "chamber": "TMMOB Mimarlar Odası", "reg_no": "1"},
        "date": "2026-11-04T00:00:00", "documents": approval._doc_hashes(record["files"])}))
    assert approval.status(directory)["status"] == "onaylandi"
    offer_packages.create(directory, record, [])
    doc.unlink()
    assert (directory / "teklif_paketleri/v0001/teklif.docx").is_file()
    assert approval.status(directory)["status"] == "degistirilmis"


def test_parallel_offer_versions_do_not_overwrite(source):
    directory, record, _ = source
    with ThreadPoolExecutor(max_workers=4) as pool:
        versions = list(pool.map(lambda _: offer_packages.create(directory, record, [])["version"], range(4)))
    assert sorted(versions) == [1, 2, 3, 4]
    assert all((directory / f"teklif_paketleri/v{v:04d}/teklif.docx").is_file() for v in versions)


def test_stale_quantities_rejected_without_writing(source):
    directory, record, _ = source
    record["quantities_fp"] = "a" * 64
    client = TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
    (directory / "project.json").write_text(json.dumps(record))
    assert client.post("/api/projects/20261104-120000-test/teklif-paketleri").status_code == 409
    assert not (directory / offer_packages.DB_NAME).exists()


def test_preexisting_version_is_never_removed(source):
    directory, record, _ = source
    existing = directory / "teklif_paketleri/v0001"
    existing.mkdir(parents=True)
    (existing / "existing.txt").write_text("keep")
    with pytest.raises(FileExistsError):
        offer_packages.create(directory, record, [])
    assert (existing / "existing.txt").read_text() == "keep"

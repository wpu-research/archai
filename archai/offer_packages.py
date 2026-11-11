"""Proje bazında sürümlü, değiştirilmeyen teklif belge anlık görüntüleri."""
import hashlib
import json
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from . import approval, quantities

DB_NAME = "teklif_paketleri.sqlite3"
DOCS = ("teklif_docx", "metraj_maliyet_xlsx", "sartname_docx", "kesif_xlsx", "kesif_csv", "cizim_pdf")


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def create(directory, record, elements):
    directory = Path(directory).resolve()
    q = quantities.compute(elements)
    if record.get("quantities_fp") != approval.quantities_fp(q):
        raise approval.QuantitiesMismatchError("Metraj referansı eksik veya değişmiş; teklif paketinden önce belgeleri yeniden üretin.")
    fp = approval.fingerprint(q, record["cost"], record["brief"])
    sources = {}
    for key in DOCS:
        filename = record.get("files", {}).get(key)
        if not filename:
            continue
        source = Path(filename)
        if not source.is_absolute():
            source = directory / source
        source = source.resolve()
        if not source.is_relative_to(directory) or not source.is_file():
            raise ValueError(f"Teklif belgesi bulunamadı veya proje dışına çıkıyor: {key}")
        sources[key] = source
    if "teklif_docx" not in sources:
        raise ValueError("Teklif belgesi bulunamadı")

    root = directory / "teklif_paketleri"
    root.mkdir(exist_ok=True)
    with closing(sqlite3.connect(directory / DB_NAME, timeout=10)) as db:
        db.execute("CREATE TABLE IF NOT EXISTS packages (version INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
        db.execute("BEGIN IMMEDIATE")
        version = db.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM packages").fetchone()[0]
        target = root / f"v{version:04d}"
        created = False
        try:
            target.mkdir()  # published versions are never overwritten
            created = True
            docs = {}
            for key, source in sources.items():
                dest = target / source.name
                shutil.copyfile(source, dest)
                if _sha(source) != _sha(dest):
                    raise ValueError(f"Belge kopyalama sırasında değişti: {key}")
                docs[key] = {"file": dest.name, "sha256": _sha(dest)}
            # A concurrently updated project must not result in a mislabeled snapshot.
            if approval.current_fp(directory) != fp:
                raise ValueError("Proje paket oluşturulurken değişti; yeniden deneyin")
            package = {"version": version, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "project_fingerprint": fp, "quantities_fingerprint": record["quantities_fp"],
                       "approval_status": approval.status(directory)["status"], "cost_total_tl": record["cost"]["total"],
                       "documents": docs}
            (target / "manifest.json").write_text(json.dumps(package, ensure_ascii=False, indent=2))
            db.execute("INSERT INTO packages VALUES (?, ?)", (version, json.dumps(package, ensure_ascii=False)))
            db.commit()
        except BaseException:
            db.rollback()
            if created:
                shutil.rmtree(target)
            raise
    return package


def list_saved(directory):
    path = Path(directory) / DB_NAME
    if not path.exists():
        return []
    with closing(sqlite3.connect(path, timeout=10)) as db:
        return [json.loads(row[0]) for row in db.execute("SELECT payload FROM packages ORDER BY version DESC")]

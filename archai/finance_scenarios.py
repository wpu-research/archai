"""Proje bazında değiştirilmeyen fizibilite anlık görüntüleri."""
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from . import approval, quantities

LIMIT = 50
DB_NAME = "fizibilite_senaryolari.sqlite3"


def save(directory, name, result):
    name = name.strip()
    if not name or len(name) > 80 or any(ord(c) < 32 for c in name):
        raise ValueError("Senaryo adı 1–80 karakter olmalı; kontrol karakteri içeremez")
    row = {"id": uuid4().hex, "ad": name,
           "kayit_zamani": datetime.now(timezone.utc).isoformat(timespec="seconds"), "hesap": result}
    # Birden fazla worker aynı projeye yazsa bile sınır ve kayıt atomiktir.
    with closing(sqlite3.connect(Path(directory) / DB_NAME, timeout=10)) as db:
        db.execute("CREATE TABLE IF NOT EXISTS scenarios (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        with db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT COUNT(*) FROM scenarios").fetchone()[0] >= LIMIT:
                raise ValueError(f"Proje başına en fazla {LIMIT} senaryo kaydedilebilir")
            db.execute("INSERT INTO scenarios VALUES (?, ?)",
                       (row["id"], json.dumps(row, ensure_ascii=False, allow_nan=False)))
    return row


def list_saved(directory, record, elements):
    path = Path(directory) / DB_NAME
    q = quantities.compute(elements)
    verified = record.get("quantities_fp") == approval.quantities_fp(q)
    current_fp = approval.fingerprint(q, record["cost"], record["brief"])
    rows = []
    if path.exists():
        with closing(sqlite3.connect(path, timeout=10)) as db:
            rows = [json.loads(row[0]) for row in db.execute("SELECT payload FROM scenarios ORDER BY rowid DESC")]
    for row in rows:
        row["guncel"] = verified and row["hesap"]["kaynak"]["proje_parmak_izi"] == current_fp
    return {"senaryolar": rows, "metraj_guncel": verified, "proje_parmak_izi": current_fp, "limit": LIMIT}

"""Test hijyeni: tüm çıktı geçici dizinlere yazılır, repodaki izlenen dosyalar değişmez.

ARCHAI_OUT, webapp.app / archai.project içe aktarılmadan ÖNCE ayarlanmalı (modül yüklenirken okunur).
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_TMP = tempfile.mkdtemp(prefix="archai_test_")
os.environ["ARCHAI_OUT"] = _TMP
os.environ.pop("ARCHAI_TOKEN", None)          # testler loopback istemci olarak çalışır
os.environ.pop("ARCHAI_ALLOWED_HOSTS", None)

ROOT = Path(__file__).resolve().parents[1]


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture(scope="session")
def ref_dir():
    """scripts/make_test_plan.py çıktısı (DXF + truth) geçici dizinde — references/ dokunulmaz."""
    d = Path(_TMP) / "references"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "make_test_plan.py")], check=True, capture_output=True,
                   env={**os.environ, "ARCHAI_REF_OUT": str(d)})
    return d


@pytest.fixture(scope="session")
def test_dxf(ref_dir):
    return ref_dir / "test_plan_2+1.dxf"

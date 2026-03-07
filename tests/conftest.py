"""Pytest session bootstrap for sandbox-friendly temporary directories."""

import os
import shutil
import tempfile
import uuid
from pathlib import Path
import pytest


_TMP_ROOT = Path(__file__).resolve().parents[1] / "codex_tmp" / "pytest_runtime"
_TMP_ROOT.mkdir(parents=True, exist_ok=True)
_TMP_CASES_ROOT = Path(__file__).resolve().parents[1] / "codex_tmp" / "tmp_cases"
_TMP_CASES_ROOT.mkdir(parents=True, exist_ok=True)

for _name in ("TMPDIR", "TEMP", "TMP"):
    os.environ[_name] = str(_TMP_ROOT)

tempfile.tempdir = str(_TMP_ROOT)


@pytest.fixture
def tmp_path():
    """Provide a writable tmp path without relying on pytest's tmpdir factory."""
    case_dir = _TMP_CASES_ROOT / f"case_{uuid.uuid4().hex}"
    case_dir.mkdir(parents=True, exist_ok=False)
    try:
        yield case_dir
    finally:
        shutil.rmtree(case_dir, ignore_errors=True)

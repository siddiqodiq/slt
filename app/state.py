"""Keadaan kecil yang harus bertahan saat restart: saklar sedekah rutin.

Disimpan sebagai satu file JSON di server (`STATE_PATH`, di-gitignore). Bukan
Notion, karena ini pengaturan, bukan catatan ibadah; bukan cache, karena server
ini tanpa Redis dan cache memori hilang tiap restart.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import Any

from .config import get_settings

log = logging.getLogger(__name__)

DEFAULT: dict[str, Any] = {
    "rutin_aktif": False,
    "rutin_sejak": None,  # tanggal ISO saat terakhir dinyalakan
    # Awal sedekah rutin yang tidak putus — boleh sebelum bot ada (riwayat itu
    # tidak dibuatkan baris Notion, hanya dihitung sebagai "berjalan N hari").
    "rutin_mulai": None,
    "pengingat_bulan": None,  # "YYYY-MM" pengingat bulanan terakhir
}


def _path() -> str:
    # STATE_PATH di env hanya untuk tes — supaya tidak membaca file asli server.
    return os.getenv("STATE_PATH") or get_settings().state_path


def load() -> dict[str, Any]:
    path = _path()
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return dict(DEFAULT)
    except (OSError, ValueError):
        log.exception("state.json tidak terbaca — memakai default")
        return dict(DEFAULT)
    return {**DEFAULT, **data}


def update(**changes: Any) -> dict[str, Any]:
    """Tulis atomik (file sementara lalu rename) supaya crash tidak merusak file."""
    data = {**load(), **changes}
    path = _path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return data

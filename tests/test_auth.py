import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from app.miniapp.auth import InitDataError, user_id_of, validate_init_data

TOKEN = "123456:TEST-TOKEN-abcdefghijklmnop"


def sign(pairs: dict) -> str:
    check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode({**pairs, "hash": digest})


def init_data(auth_date: int | None = None, user_id: int = 42) -> str:
    return sign(
        {
            "auth_date": str(auth_date or int(time.time())),
            "query_id": "AAF",
            "user": json.dumps({"id": user_id, "first_name": "Uji"}, separators=(",", ":")),
        }
    )


def test_init_data_sah():
    parsed = validate_init_data(init_data(), TOKEN)
    assert user_id_of(parsed) == 42


def test_hash_dipalsukan_ditolak():
    raw = init_data()
    palsu = raw.replace("hash=", "hash=0") [:-1]
    with pytest.raises(InitDataError):
        validate_init_data(palsu, TOKEN)


def test_user_id_diubah_tanpa_hash_baru_ditolak():
    raw = init_data(user_id=42)
    diubah = raw.replace("%2242%22", "%229999%22").replace("42", "9999", 1)
    with pytest.raises(InitDataError):
        validate_init_data(diubah, TOKEN)


def test_auth_date_kedaluwarsa_ditolak():
    lama = init_data(auth_date=int(time.time()) - 90000)
    with pytest.raises(InitDataError):
        validate_init_data(lama, TOKEN, max_age=86400)


def test_token_bot_salah_ditolak():
    with pytest.raises(InitDataError):
        validate_init_data(init_data(), "999:LAIN")


def test_init_data_kosong_ditolak():
    with pytest.raises(InitDataError):
        validate_init_data("", TOKEN)


def test_signature_diterima_baik_ikut_hash_maupun_tidak():
    """Telegram (Bot API 8.0) mengirim `signature` untuk validasi Ed25519.

    Klien lama tidak mengirimnya, dan yang mengirim tidak selalu memasukkannya
    ke data-check-string. Menolak salah satu bentuk berarti menolak sesi yang
    sah — dan gagalnya senyap: pesannya hanya "hash tidak cocok".
    """
    dasar = {
        "auth_date": str(int(time.time())),
        "query_id": "AAF",
        "user": json.dumps({"id": 42, "first_name": "Uji"}, separators=(",", ":")),
    }
    dengan_sig = {**dasar, "signature": "Ed25519_abc-123"}

    # hash dihitung tanpa signature, tapi signature tetap ikut terkirim
    check = "\n".join(f"{k}={dasar[k]}" for k in sorted(dasar))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    luar_hash = urlencode({**dengan_sig, "hash": digest})

    for raw in (sign(dasar), luar_hash, sign(dengan_sig)):
        assert user_id_of(validate_init_data(raw, TOKEN)) == 42

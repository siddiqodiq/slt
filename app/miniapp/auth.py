"""Validasi `initData` Telegram — wajib (§7).

secret = HMAC_SHA256("WebAppData", bot_token); hash dibandingkan dengan
`hmac.compare_digest`, bukan `==`. `user_id` yang dikirim klien tidak pernah
dipercaya sebelum hash-nya terbukti dan `auth_date` masih segar.
Cukup `hmac` + `hashlib` dari standard library.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


class InitDataError(ValueError):
    pass


def validate_init_data(init_data: str, bot_token: str, max_age: int = 86400) -> dict:
    if not init_data:
        raise InitDataError("initData kosong")
    if not bot_token:
        raise InitDataError("bot token belum dikonfigurasi di server")

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", "")
    if not received_hash:
        raise InitDataError("initData tanpa hash")

    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()

    # `signature` (Ed25519, Bot API 8.0) dipakai untuk validasi pihak ketiga dan
    # tidak ikut dihitung dalam HMAC. Klien lama tidak mengirimnya sama sekali,
    # jadi kedua bentuk dicoba — menolak salah satunya berarti menolak sesi yang
    # sebenarnya sah, dan gagalnya senyap: hanya "hash tidak cocok".
    candidates = [{k: v for k, v in pairs.items() if k != "signature"}]
    if "signature" in pairs:
        candidates.append(dict(pairs))

    for fields in candidates:
        dcs = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
        expected = hmac.new(secret_key, dcs.encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, received_hash):
            break
    else:
        raise InitDataError("hash initData tidak cocok")

    pairs.pop("signature", None)

    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError as exc:
        raise InitDataError("auth_date tidak valid") from exc
    age = time.time() - auth_date
    if auth_date <= 0 or age > max_age:
        raise InitDataError(f"initData kedaluwarsa ({int(age)} detik)")

    parsed: dict = dict(pairs)
    if "user" in pairs:
        try:
            parsed["user"] = json.loads(pairs["user"])
        except json.JSONDecodeError as exc:
            raise InitDataError("field user bukan JSON") from exc
    return parsed


def user_id_of(parsed: dict) -> int:
    user = parsed.get("user")
    if isinstance(user, dict) and user.get("id"):
        return int(user["id"])
    raise InitDataError("initData tidak memuat user")

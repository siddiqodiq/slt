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
    pairs.pop("signature", None)  # milik Ed25519 third-party validation, bukan bagian HMAC

    data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        raise InitDataError("hash initData tidak cocok")

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

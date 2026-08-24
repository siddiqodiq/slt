"""Lapisan cache. Redis kalau tersedia, memori proses kalau tidak.

Filesystem dyno bersifat sementara (§3), jadi tidak ada cache di disk sama sekali.
Fallback memori hanya untuk pengembangan lokal dan supaya bot tetap jalan
(dengan cache dingin) kalau add-on Redis sedang bermasalah.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from .config import get_settings

log = logging.getLogger(__name__)


class _MemoryBackend:
    def __init__(self) -> None:
        self._data: dict[str, tuple[float | None, str]] = {}

    def _alive(self, key: str) -> str | None:
        item = self._data.get(key)
        if item is None:
            return None
        expires, value = item
        if expires is not None and expires < time.time():
            self._data.pop(key, None)
            return None
        return value

    async def get(self, key: str) -> str | None:
        return self._alive(key)

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        self._data[key] = (time.time() + ttl if ttl else None, value)

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self._data.pop(key, None)

    async def delete_prefix(self, prefix: str) -> None:
        for key in [k for k in self._data if k.startswith(prefix)]:
            self._data.pop(key, None)

    async def set_if_absent(self, key: str, value: str, ttl: int | None = None) -> bool:
        if self._alive(key) is not None:
            return False
        await self.set(key, value, ttl)
        return True

    async def close(self) -> None:
        self._data.clear()


class _RedisBackend:
    def __init__(self, url: str) -> None:
        import redis.asyncio as redis  # import lokal supaya test tanpa redis tetap jalan

        kwargs: dict[str, Any] = {"decode_responses": True}
        if url.startswith("rediss://"):
            # Heroku Key-Value Store memakai sertifikat self-signed.
            kwargs["ssl_cert_reqs"] = None
        self._r = redis.from_url(url, **kwargs)

    async def get(self, key: str) -> str | None:
        return await self._r.get(key)

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        await self._r.set(key, value, ex=ttl)

    async def delete(self, *keys: str) -> None:
        if keys:
            await self._r.delete(*keys)

    async def delete_prefix(self, prefix: str) -> None:
        batch: list[str] = []
        async for key in self._r.scan_iter(match=f"{prefix}*", count=200):
            batch.append(key)
            if len(batch) >= 200:
                await self._r.delete(*batch)
                batch.clear()
        if batch:
            await self._r.delete(*batch)

    async def set_if_absent(self, key: str, value: str, ttl: int | None = None) -> bool:
        return bool(await self._r.set(key, value, ex=ttl, nx=True))

    async def close(self) -> None:
        await self._r.aclose()


class Cache:
    def __init__(self, url: str | None = None) -> None:
        url = url if url is not None else get_settings().redis_url
        self.backend: Any
        if url:
            try:
                self.backend = _RedisBackend(url)
                self.kind = "redis"
            except Exception:  # pragma: no cover - hanya saat lib/URL bermasalah
                log.exception("Redis tidak bisa diinisialisasi, jatuh ke cache memori")
                self.backend = _MemoryBackend()
                self.kind = "memory"
        else:
            self.backend = _MemoryBackend()
            self.kind = "memory"

    async def get_json(self, key: str) -> Any | None:
        raw = await self._safe("get", key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    async def set_json(self, key: str, value: Any, ttl: int | None = None) -> None:
        await self._safe("set", key, json.dumps(value, default=str), ttl)

    async def get(self, key: str) -> str | None:
        return await self._safe("get", key)

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        await self._safe("set", key, value, ttl)

    async def delete(self, *keys: str) -> None:
        await self._safe("delete", *keys)

    async def delete_prefix(self, prefix: str) -> None:
        await self._safe("delete_prefix", prefix)

    async def claim(self, key: str, ttl: int | None = None) -> bool:
        """True kalau pemanggil ini yang pertama memegang `key`.

        Dipakai agar prompt shalat tidak terkirim dua kali setelah dyno restart (§10).
        """
        result = await self._safe("set_if_absent", key, "1", ttl)
        return bool(result)

    async def close(self) -> None:
        await self._safe("close")

    async def _safe(self, method: str, *args: Any) -> Any:
        try:
            return await getattr(self.backend, method)(*args)
        except Exception:  # pragma: no cover
            log.exception("Operasi cache %s gagal", method)
            if method in {"get", "set_if_absent"}:
                # Gagal-terbuka untuk baca; gagal-tertutup untuk klaim agar tidak dobel-kirim.
                return None if method == "get" else False
            return None


_cache: Cache | None = None


def get_cache() -> Cache:
    global _cache
    if _cache is None:
        _cache = Cache()
    return _cache


def set_cache(cache: Cache) -> None:  # dipakai test
    global _cache
    _cache = cache


# --- Kunci cache -----------------------------------------------------------

def k_jadwal(kabkota: str, ym: str) -> str:
    return f"jadwal:{kabkota}:{ym}"


def k_prompt_sent(day: str, prayer: str) -> str:
    return f"prompt:{day}:{prayer}"


def k_answered(day: str, prayer: str) -> str:
    return f"resp:{day}:{prayer}"


def k_prompt_msg(day: str, prayer: str) -> str:
    return f"promptmsg:{day}:{prayer}"


def k_rows(start: str, end: str) -> str:
    return f"rows:{start}:{end}"


def k_page(day: str) -> str:
    return f"page:{day}"


ROWS_PREFIX = "rows:"

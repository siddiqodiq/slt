"""Akses Notion — satu-satunya penyimpan data permanen (§3, §8).

Semua agregasi dilakukan di aplikasi; Notion hanya menyerahkan baris mentah.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import httpx

from .cache import ROWS_PREFIX, Cache, get_cache, k_page
from .config import (
    BADIYAH_OPTIONS,
    CHECKBOX_SUNNAH,
    PRAYERS,
    QABLIYAH_OPTIONS,
    Settings,
    get_settings,
)
from .domain import sumber_merge
from .timeutil import label_hari

log = logging.getLogger(__name__)

NOTION_API = "https://api.notion.com/v1"


class NotionError(RuntimeError):
    pass


@dataclass
class DayRecord:
    """Satu baris tracker, sudah diterjemahkan dari bentuk properti Notion."""

    day: date
    page_id: str = ""
    prayers: dict[str, dict[str, str | None]] = field(default_factory=dict)
    qabliyah: list[str] = field(default_factory=list)
    badiyah: list[str] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)
    tilawah: int = 0
    catatan: str = ""
    sumber: str | None = None
    sedekah_rutin: bool = False  # sedekah otomatis harian tercatat
    sedekah_n: int = 0  # berapa kali sedekah tambahan
    sedekah_ket: str = ""  # satu baris per sedekah tambahan

    @property
    def sedekah_ada(self) -> bool:
        return self.sedekah_rutin or self.sedekah_n > 0

    def waktu(self, prayer: str) -> str | None:
        return (self.prayers.get(prayer) or {}).get("waktu")

    def cara(self, prayer: str) -> str | None:
        return (self.prayers.get(prayer) or {}).get("cara")

    @property
    def recorded_count(self) -> int:
        return sum(1 for p in PRAYERS if self.waktu(p))


class NotionClient:
    """HTTP tipis dengan throttle ~3 req/s dan penghormatan `Retry-After` (§10)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.s = settings or get_settings()
        self._lock = asyncio.Lock()
        self._last_call = 0.0
        self._client: httpx.AsyncClient | None = None

    @property
    def use_data_source(self) -> bool:
        return bool(self.s.notion_data_source_id) and self.s.notion_version >= "2025-09-03"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.s.notion_token}",
            "Notion-Version": self.s.notion_version,
            "Content-Type": "application/json",
        }

    async def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(base_url=NOTION_API, timeout=30, headers=self._headers())
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _throttle(self) -> None:
        interval = 1.0 / max(self.s.notion_rps, 0.5)
        async with self._lock:
            wait = self._last_call + interval - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()

    async def request(self, method: str, path: str, json_body: dict | None = None) -> dict:
        client = await self.client()
        for attempt in range(5):
            await self._throttle()
            try:
                resp = await client.request(method, path, json=json_body)
            except httpx.HTTPError as exc:
                if attempt == 4:
                    raise NotionError(f"koneksi Notion gagal: {exc}") from exc
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            if resp.status_code == 429:
                delay = float(resp.headers.get("Retry-After", "1"))
                log.warning("Notion rate limit, tunggu %.1fs", delay)
                await asyncio.sleep(delay)
                continue
            if resp.status_code in (409, 500, 502, 503, 504):
                await asyncio.sleep(1.0 * (attempt + 1))
                continue
            if resp.status_code == 404:
                raise NotionError(
                    "Notion 404 — halaman/database kemungkinan belum di-share ke integrasi "
                    "(§3 brief: 404 di sini berarti tidak terlihat, bukan tidak ada)."
                )
            if resp.status_code >= 400:
                raise NotionError(f"Notion {resp.status_code}: {resp.text[:400]}")
            return resp.json()
        raise NotionError("Notion tidak merespons setelah beberapa percobaan")

    # --- endpoint yang berbeda antar versi API ---------------------------

    async def query(self, body: dict) -> dict:
        if self.use_data_source:
            return await self.request("POST", f"/data_sources/{self.s.notion_data_source_id}/query", body)
        return await self.request("POST", f"/databases/{self.s.notion_database_id}/query", body)

    async def schema(self) -> dict:
        if self.use_data_source:
            return await self.request("GET", f"/data_sources/{self.s.notion_data_source_id}")
        return await self.request("GET", f"/databases/{self.s.notion_database_id}")

    def parent(self) -> dict:
        if self.use_data_source:
            return {"type": "data_source_id", "data_source_id": self.s.notion_data_source_id}
        return {"type": "database_id", "database_id": self.s.notion_database_id}

    async def create_page(self, properties: dict) -> dict:
        return await self.request("POST", "/pages", {"parent": self.parent(), "properties": properties})

    async def update_page(self, page_id: str, properties: dict) -> dict:
        return await self.request("PATCH", f"/pages/{page_id}", {"properties": properties})


# --- builder & parser properti --------------------------------------------

def p_title(text: str) -> dict:
    return {"title": [{"type": "text", "text": {"content": text}}]}


def p_rich(text: str) -> dict:
    if not text:
        return {"rich_text": []}
    return {"rich_text": [{"type": "text", "text": {"content": text[:2000]}}]}


def p_select(value: str | None) -> dict:
    return {"select": {"name": value} if value else None}


def p_multi(values: list[str]) -> dict:
    return {"multi_select": [{"name": v} for v in values]}


def p_date(day: date) -> dict:
    return {"date": {"start": day.isoformat()}}


def p_check(value: bool) -> dict:
    return {"checkbox": bool(value)}


def p_number(value: int | float | None) -> dict:
    return {"number": value}


def _read_select(prop: dict | None) -> str | None:
    if not prop:
        return None
    sel = prop.get("select") or prop.get("status")
    return sel.get("name") if sel else None


def _read_multi(prop: dict | None) -> list[str]:
    if not prop:
        return []
    return [o.get("name", "") for o in prop.get("multi_select") or []]


def _read_text(prop: dict | None) -> str:
    if not prop:
        return ""
    chunks = prop.get("rich_text") or prop.get("title") or []
    return "".join(c.get("plain_text", "") for c in chunks)


def _read_int(prop: dict | None) -> int:
    return int((prop or {}).get("number") or 0)


def _read_date(prop: dict | None) -> date | None:
    if not prop:
        return None
    value = prop.get("date")
    if not value or not value.get("start"):
        return None
    return date.fromisoformat(value["start"][:10])


class NotionRepo:
    """Operasi tingkat-domain di atas NotionClient."""

    def __init__(
        self,
        client: NotionClient | None = None,
        settings: Settings | None = None,
        cache: Cache | None = None,
    ) -> None:
        self.s = settings or get_settings()
        self.client = client or NotionClient(self.s)
        self.cache = cache or get_cache()

    # --- baca -------------------------------------------------------------

    def parse(self, page: dict) -> DayRecord | None:
        props = page.get("properties", {})
        day = _read_date(props.get(self.s.prop_date))
        if day is None:
            return None
        rec = DayRecord(day=day, page_id=page.get("id", ""))
        for prayer in PRAYERS:
            rec.prayers[prayer] = {
                "waktu": _read_select(props.get(self.s.prop_waktu(prayer))),
                "cara": _read_select(props.get(self.s.prop_cara(prayer))),
            }
        rec.qabliyah = _read_multi(props.get(self.s.prop_qabliyah))
        rec.badiyah = _read_multi(props.get(self.s.prop_badiyah))
        rec.checks = {
            name: bool((props.get(name) or {}).get("checkbox", False)) for name in CHECKBOX_SUNNAH
        }
        tilawah = (props.get(self.s.prop_tilawah) or {}).get("number")
        rec.tilawah = int(tilawah or 0)
        rec.catatan = _read_text(props.get(self.s.prop_catatan))
        rec.sumber = _read_select(props.get(self.s.prop_sumber))
        rec.sedekah_rutin = bool((props.get(self.s.prop_sedekah_rutin) or {}).get("checkbox", False))
        rec.sedekah_n = _read_int(props.get(self.s.prop_sedekah_n))
        rec.sedekah_ket = _read_text(props.get(self.s.prop_sedekah_ket))
        return rec

    async def fetch_range(self, start: date, end: date) -> list[DayRecord]:
        """Tarik seluruh baris dalam rentang, 100 per permintaan (§3)."""
        body: dict[str, Any] = {
            "filter": {
                "and": [
                    {"property": self.s.prop_date, "date": {"on_or_after": start.isoformat()}},
                    {"property": self.s.prop_date, "date": {"on_or_before": end.isoformat()}},
                ]
            },
            "sorts": [{"property": self.s.prop_date, "direction": "ascending"}],
            "page_size": 100,
        }
        records: list[DayRecord] = []
        cursor: str | None = None
        while True:
            if cursor:
                body["start_cursor"] = cursor
            data = await self.client.query(body)
            for page in data.get("results", []):
                rec = self.parse(page)
                if rec:
                    records.append(rec)
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
        return records

    async def get_day(self, day: date) -> DayRecord | None:
        body = {
            "filter": {"property": self.s.prop_date, "date": {"equals": day.isoformat()}},
            "page_size": 1,
        }
        data = await self.client.query(body)
        results = data.get("results", [])
        if not results:
            return None
        return self.parse(results[0])

    async def get_or_create(self, day: date) -> DayRecord:
        rec = await self.get_day(day)
        if rec:
            await self.cache.set(k_page(day.isoformat()), rec.page_id, ttl=7 * 86400)
            return rec
        props = {
            self.s.prop_title: p_title(label_hari(day)),
            self.s.prop_date: p_date(day),
        }
        page = await self.client.create_page(props)
        log.info("Baris Notion dibuat untuk %s", day.isoformat())
        await self._invalidate()
        created = self.parse(page) or DayRecord(day=day, page_id=page.get("id", ""))
        await self.cache.set(k_page(day.isoformat()), created.page_id, ttl=7 * 86400)
        return created

    # --- tulis ------------------------------------------------------------

    async def _update(self, rec: DayRecord, props: dict) -> None:
        await self.client.update_page(rec.page_id, props)
        await self._invalidate()

    async def _invalidate(self) -> None:
        await self.cache.delete_prefix(ROWS_PREFIX)

    async def set_prayer(
        self, day: date, prayer: str, waktu: str | None, cara: str | None, sumber: str
    ) -> DayRecord:
        rec = await self.get_or_create(day)
        props: dict[str, Any] = {}
        if waktu is not None:
            props[self.s.prop_waktu(prayer)] = p_select(waktu)
        if cara is not None:
            props[self.s.prop_cara(prayer)] = p_select(cara)
        if self.s.sumber_enabled:
            props[self.s.prop_sumber] = p_select(sumber_merge(rec.sumber, sumber))
        await self._update(rec, props)
        if waktu is not None:
            rec.prayers.setdefault(prayer, {})["waktu"] = waktu
        if cara is not None:
            rec.prayers.setdefault(prayer, {})["cara"] = cara
        return rec

    async def clear_prayer(self, day: date, prayer: str) -> None:
        rec = await self.get_or_create(day)
        await self._update(
            rec,
            {
                self.s.prop_waktu(prayer): p_select(None),
                self.s.prop_cara(prayer): p_select(None),
            },
        )
        rec.prayers[prayer] = {"waktu": None, "cara": None}

    async def toggle_check(self, day: date, name: str) -> bool:
        rec = await self.get_or_create(day)
        new_value = not rec.checks.get(name, False)
        await self._update(rec, {name: p_check(new_value)})
        rec.checks[name] = new_value
        return new_value

    async def toggle_multi(self, day: date, prop: str, value: str) -> list[str]:
        rec = await self.get_or_create(day)
        current = list(rec.qabliyah if prop == self.s.prop_qabliyah else rec.badiyah)
        if value in current:
            current.remove(value)
        else:
            current.append(value)
        options = QABLIYAH_OPTIONS if prop == self.s.prop_qabliyah else BADIYAH_OPTIONS
        current.sort(key=lambda v: options.index(v) if v in options else 99)
        await self._update(rec, {prop: p_multi(current)})
        if prop == self.s.prop_qabliyah:
            rec.qabliyah = current
        else:
            rec.badiyah = current
        return current

    async def add_tilawah(self, day: date, pages: int) -> int:
        """Menambah, bukan menimpa (§6)."""
        rec = await self.get_or_create(day)
        total = max(0, rec.tilawah + pages)
        await self._update(rec, {self.s.prop_tilawah: p_number(total)})
        rec.tilawah = total
        return total

    async def set_tilawah(self, day: date, pages: int) -> int:
        rec = await self.get_or_create(day)
        total = max(0, pages)
        await self._update(rec, {self.s.prop_tilawah: p_number(total)})
        rec.tilawah = total
        return total

    async def append_catatan(self, day: date, text: str) -> str:
        rec = await self.get_or_create(day)
        merged = f"{rec.catatan}\n{text}".strip() if rec.catatan else text
        await self._update(rec, {self.s.prop_catatan: p_rich(merged)})
        rec.catatan = merged
        return merged

    # --- sedekah ---------------------------------------------------------

    async def set_sedekah_rutin(self, day: date, value: bool = True) -> DayRecord:
        rec = await self.get_or_create(day)
        await self._update(rec, {self.s.prop_sedekah_rutin: p_check(value)})
        rec.sedekah_rutin = value
        return rec

    async def add_sedekah(self, day: date, baris: str) -> DayRecord:
        """Tambah satu sedekah: kali +1, keterangan satu baris baru."""
        rec = await self.get_or_create(day)
        n = rec.sedekah_n + 1
        ket = f"{rec.sedekah_ket}\n{baris}".strip() if rec.sedekah_ket else baris
        await self._update(rec, {
            self.s.prop_sedekah_n: p_number(n),
            self.s.prop_sedekah_ket: p_rich(ket),
        })
        rec.sedekah_n, rec.sedekah_ket = n, ket
        return rec

    async def undo_sedekah(self, day: date, n_saat_itu: int) -> DayRecord | None:
        """Batalkan sedekah terakhir — hanya kalau belum ada yang ditambahkan sesudahnya."""
        rec = await self.get_day(day)
        if rec is None or rec.sedekah_n != n_saat_itu or n_saat_itu < 1:
            return None
        ket = "\n".join(rec.sedekah_ket.splitlines()[:-1])
        n = rec.sedekah_n - 1
        await self._update(rec, {
            self.s.prop_sedekah_n: p_number(n or None),
            self.s.prop_sedekah_ket: p_rich(ket),
        })
        rec.sedekah_n, rec.sedekah_ket = n, ket
        return rec

    async def mark_sumber(self, day: date, sumber: str) -> None:
        if not self.s.sumber_enabled:
            return
        rec = await self.get_or_create(day)
        await self._update(rec, {self.s.prop_sumber: p_select(sumber_merge(rec.sumber, sumber))})

    # --- pemeriksaan skema saat boot (§10) --------------------------------

    async def validate_schema(self) -> list[str]:
        """Kembalikan daftar masalah skema; kosong artinya aman."""
        data = await self.client.schema()
        props: dict[str, dict] = data.get("properties", {})
        issues: list[str] = []

        def expect(name: str, kind: str) -> None:
            prop = props.get(name)
            if prop is None:
                issues.append(f"properti '{name}' tidak ditemukan")
            elif prop.get("type") != kind:
                issues.append(f"properti '{name}' bertipe {prop.get('type')}, diharapkan {kind}")

        expect(self.s.prop_title, "title")
        expect(self.s.prop_date, "date")
        for prayer in PRAYERS:
            expect(self.s.prop_waktu(prayer), "select")
            expect(self.s.prop_cara(prayer), "select")
        expect(self.s.prop_qabliyah, "multi_select")
        expect(self.s.prop_badiyah, "multi_select")
        for name in CHECKBOX_SUNNAH:
            expect(name, "checkbox")
        expect(self.s.prop_tilawah, "number")
        expect(self.s.prop_catatan, "rich_text")
        if self.s.sumber_enabled:
            expect(self.s.prop_sumber, "select")
        expect(self.s.prop_sedekah_rutin, "checkbox")
        expect(self.s.prop_sedekah_n, "number")
        expect(self.s.prop_sedekah_ket, "rich_text")
        return issues


_repo: NotionRepo | None = None


def get_repo() -> NotionRepo:
    global _repo
    if _repo is None:
        _repo = NotionRepo()
    return _repo


def set_repo(repo: NotionRepo) -> None:  # dipakai test
    global _repo
    _repo = repo

"""Periksa skema Notion, dan (opsional) tambahkan kolom Sumber (§8, §11.2).

    python -m tools.setup_notion            # hanya memeriksa, tidak mengubah apa pun
    python -m tools.setup_notion --apply    # tambahkan properti 'Sumber' kalau belum ada

Kolom Sumber memisahkan baris yang kamu konfirmasi dari baris yang ditebak
fallback. Tanpa itu, hari yang terlewat tercatat identik dengan hari yang
berjalan baik.
"""
from __future__ import annotations

import asyncio
import sys

from app.config import get_settings
from app.notion import NotionRepo

SUMBER_OPTIONS = [
    {"name": "Konfirmasi", "color": "green"},
    {"name": "Otomatis", "color": "yellow"},
    {"name": "Manual", "color": "blue"},
]


async def main(apply: bool) -> int:
    s = get_settings()
    repo = NotionRepo()
    if not s.notion_token:
        print("NOTION_TOKEN belum diset.")
        return 2

    data = await repo.client.schema()
    props = data.get("properties", {})
    print(f"Database   : {data.get('title', [{}])[0].get('plain_text', '(tanpa judul)')}")
    print(f"Endpoint   : {'data_sources' if repo.client.use_data_source else 'databases'}")
    print(f"Properti   : {len(props)}")
    for name, prop in sorted(props.items()):
        print(f"  - {name} ({prop.get('type')})")

    issues = await repo.validate_schema()
    print()
    if issues:
        print("Masalah yang ditemukan:")
        for issue in issues:
            print("  ✗", issue)
    else:
        print("✓ Skema cocok dengan yang dibutuhkan bot.")

    if s.prop_sumber not in props and apply:
        path = (
            f"/data_sources/{s.notion_data_source_id}"
            if repo.client.use_data_source
            else f"/databases/{s.notion_database_id}"
        )
        await repo.client.request(
            "PATCH", path, {"properties": {s.prop_sumber: {"select": {"options": SUMBER_OPTIONS}}}}
        )
        print(f"✓ Properti '{s.prop_sumber}' ditambahkan (Konfirmasi · Otomatis · Manual).")
    elif s.prop_sumber not in props:
        print(f"\nJalankan dengan --apply untuk menambahkan properti '{s.prop_sumber}'.")
        print("Atau set SUMBER_ENABLED = False di app/config.py kalau tidak mau memakainya.")

    await repo.client.close()
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main("--apply" in sys.argv)))

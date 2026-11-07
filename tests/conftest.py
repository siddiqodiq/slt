import os

os.environ["DOTENV_DISABLE"] = "1"  # tes tidak boleh terpengaruh .env lokal

# Env harus terpasang sebelum app.config dibaca (Settings di-cache lru_cache).
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:TEST-TOKEN-abcdefghijklmnop")
os.environ.setdefault("TELEGRAM_OWNER_ID", "42")
os.environ.setdefault("REDIS_URL", "")
os.environ.setdefault("MINIAPP_DEV_TOKEN", "dev-token")
os.environ.setdefault("TELEGRAM_WEBHOOK_SECRET", "s3cret")

import pytest  # noqa: E402

from app.cache import Cache, set_cache  # noqa: E402

JADWAL = {
    "imsak": "04:25",
    "subuh": "04:35",
    "terbit": "05:52",
    "dhuha": "06:17",
    "dzuhur": "12:05",
    "ashar": "15:24",
    "maghrib": "18:13",
    "isya": "19:25",
}


@pytest.fixture(autouse=True)
def state_file(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    monkeypatch.setenv("STATE_PATH", str(path))
    return path


@pytest.fixture(autouse=True)
def memory_cache():
    cache = Cache("")
    set_cache(cache)
    yield cache


@pytest.fixture
def jadwal_harian():
    return dict(JADWAL)

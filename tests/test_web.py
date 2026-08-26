from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.notion import DayRecord
from tests.test_auth import init_data

HARI_INI = date.today()


@pytest.fixture
def client(monkeypatch):
    async def fake_load(start, end, repo=None, cache=None):
        return [
            DayRecord(
                day=HARI_INI - timedelta(days=i),
                page_id="x",
                prayers={
                    p: {"waktu": "Awal waktu", "cara": "Masjid"}
                    for p in ("Subuh", "Dzuhur", "Ashar", "Maghrib", "Isya")
                },
                checks={"Dhuha": True},
                qabliyah=["Subuh"],
                tilawah=4,
                catatan="alhamdulillah",
            )
            for i in range(3)
        ]

    monkeypatch.setattr("app.miniapp.routes.load_records", fake_load)
    # Tanpa context manager: lifespan tidak dijalankan, jadi tidak ada koneksi keluar.
    return TestClient(app)


def test_shell_dimuat_tanpa_data(client):
    resp = client.get("/app")
    assert resp.status_code == 200
    assert "Dashboard Ibadah" in resp.text
    assert "/static/htmx.min.js" in resp.text
    # Data tidak boleh ikut ter-render sebelum initData tervalidasi.
    assert "alhamdulillah" not in resp.text


def test_panel_tanpa_init_data_ditolak(client):
    assert client.get("/app/panel").status_code == 401


def test_panel_dengan_dev_token(client):
    resp = client.get("/app/panel?preset=7", headers={"X-Dev-Token": "dev-token"})
    assert resp.status_code == 200
    assert "di awal waktu" in resp.text
    assert "100.0%" in resp.text
    assert "alhamdulillah" in resp.text
    assert "<svg" in resp.text


def test_panel_menolak_user_lain(client):
    resp = client.get("/app/panel", headers={"X-Telegram-Init-Data": init_data(user_id=999)})
    assert resp.status_code == 403


def test_panel_menerima_init_data_pemilik(client):
    resp = client.get("/app/panel", headers={"X-Telegram-Init-Data": init_data(user_id=42)})
    assert resp.status_code == 200


def test_filter_diteruskan_ke_agregasi(client):
    resp = client.get(
        "/app/panel?preset=7&prayer=Subuh&hari=0&hari=1",
        headers={"X-Dev-Token": "dev-token"},
    )
    assert resp.status_code == 200
    assert "Subuh" in resp.text


def test_webhook_menolak_secret_salah(client):
    resp = client.post("/telegram/webhook", json={}, headers={"X-Telegram-Bot-Api-Secret-Token": "salah"})
    assert resp.status_code == 403


def test_webhook_secret_benar_tapi_bot_belum_siap(client):
    resp = client.post("/telegram/webhook", json={}, headers={"X-Telegram-Bot-Api-Secret-Token": "s3cret"})
    assert resp.status_code == 503


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    # Melaporkan ada/tidaknya config var, tidak pernah nilainya.
    assert body["config"]["TELEGRAM_BOT_TOKEN"] is True
    assert "8822858925" not in resp.text

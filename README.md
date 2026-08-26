# Bot Ibadah & Mini App Dashboard

Bot Telegram untuk mencatat shalat dan sunnah harian, dengan dashboard yang
dibuka di dalam Telegram. Data tersimpan di Notion dan tetap bisa kamu edit
langsung dari sana. Seluruhnya Python — tidak ada toolchain JavaScript.

Dibangun dari `brief.md`. **Auto-fill shalat aktif**: begitu ambang waktu shalat
lewat, barisnya diisi `Awal waktu + Munfarid`, ditandai `Sumber = Otomatis`, dan
bot mengirim pesan berisi tombol koreksi satu ketukan. Ambangnya jam datar waktu
Jakarta di `JAM_SHALAT` (`app/config.py`) — bukan jadwal adzan yang diambil
online, karena presisi menit tidak mengubah apa yang ditulis. Auto-fill tidak
pernah menimpa entri yang sudah kamu isi sendiri, dan hari yang tidak kamu sentuh
tetap bisa disaring di dashboard.

| Shalat | Ambang |
|---|---|
| Subuh | 04:30 |
| Dzuhur | 11:50 |
| Ashar | 15:10 |
| Maghrib | 17:50 |
| Isya | 19:00 |

```
app/
  config.py      Konstanta terpusat; config var hanya untuk rahasia & identitas
  domain.py      Kualitas hari, asal data, tanggal baris (bebas I/O)
  notion.py      Klien Notion (throttle 3 rps, hormati Retry-After) + repo domain
  data.py        Alur baca: Redis dulu, kalau meleset tarik semua baris dari Notion
  cache.py       Redis, dengan fallback memori untuk dev
  bot/           Perintah, inline keyboard, menu
  miniapp/       Validasi initData, agregasi, generator SVG, rute htmx
  main.py        Proses web: webhook Telegram + halaman Mini App
tools/
  setup_notion.py  Periksa skema, tambahkan kolom Sumber
  preview.py       Render dashboard data contoh ke satu file HTML (tanpa deploy)
  ping.py          Kirim pesan uji ke chat/topik tujuan laporan bot
```

## Config var

Hanya sebelas, dan empat di antaranya opsional. Semua setelan lain — id database
Notion, nama properti, zona waktu, TTL cache, konvensi tahajud — dipatok di
`app/config.py`; sistem ini untuk satu orang, dan knob yang tidak pernah diputar
hanya menambah tempat untuk salah ketik.

| Var | Wajib | Untuk apa |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ya | rahasia, dari BotFather |
| `NOTION_TOKEN` | ya | rahasia, integration token |
| `TELEGRAM_OWNER_ID` | ya | user id kamu; bot menolak siapa pun selain ini |
| `BASE_URL` | di Heroku | URL https app, dipakai memasang webhook & tombol Mini App |
| `TELEGRAM_WEBHOOK_SECRET` | disarankan | dicocokkan pada tiap update masuk |
| `TELEGRAM_PROMPT_CHAT_ID` | — | tujuan laporan otomatis bot; kosong = japri owner |
| `TELEGRAM_PROMPT_THREAD_ID` | — | topik forum di grup tujuan |
| `REDIS_URL` | — | diisi otomatis add-on; kosong = cache memori proses |
| `USE_POLLING` | — | `true` untuk uji lokal tanpa URL https |
| `MINIAPP_DEV_TOKEN` | — | buka dashboard di browser tanpa Telegram |
| `TZ` | — | hanya untuk timestamp log; aplikasi memakai Asia/Jakarta dari kode |

Yang dipatok di `app/config.py` dan boleh diubah satu baris kalau perlu:
`NOTION_DATABASE_ID` / `NOTION_DATA_SOURCE_ID`, semua nama properti (`PROP_*`),
`TAHAJUD_DAY` (`wake` — dengan `previous`, input manual sebelum 05:00 masuk ke
baris kemarin), `TTL_ROWS`, `MINIAPP_MAX_AGE`, `SUMBER_ENABLED`.

## Menyiapkan

```bash
python -m venv .venv && .venv/Scripts/activate   # Linux/mac: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                              # isi token
pytest                                            # 29 tes, tanpa jaringan
```

### Notion

1. Buat integration di notion.so/my-integrations, salin token internal-nya.
2. **Share halaman _Tracker Ibadah_ ke integrasi itu.** Tanpa langkah ini API
   balas 404, bukan 403 — pesan error di kode ini sudah menyebutkannya supaya
   tidak salah didiagnosis.
3. `python -m tools.setup_notion` untuk memeriksa skema; `--apply` untuk
   menambahkan kolom `Sumber` kalau belum ada.

### Telegram

1. Buat bot di @BotFather, salin token.
2. Kirim pesan ke bot itu, lalu isi `TELEGRAM_OWNER_ID` dengan user id kamu —
   selama masih kosong, bot mencetak `Set TELEGRAM_OWNER_ID=...` ke log.
3. Opsional: BotFather → Bot Settings → Menu Button → `https://<app>/app`.

## Ke mana laporan otomatis dikirim

`TELEGRAM_PROMPT_CHAT_ID` menentukan tujuan pesan yang **bot mulai sendiri** —
sekarang hanya laporan skema Notion yang tidak cocok dan error handler. Balasan
perintah selalu kembali ke chat (dan topik) tempat kamu mengetiknya.

| Tujuan | Isi config |
|---|---|
| Japri kamu | kosongkan keduanya — jatuh ke `TELEGRAM_OWNER_ID` |
| Grup | `TELEGRAM_PROMPT_CHAT_ID=-100<id>` |
| Satu topik di grup forum | tambah `TELEGRAM_PROMPT_THREAD_ID=<topik>` |

Ambil dari link pesan: `https://t.me/c/3966896650/2704` → chat id
`-1003966896650`, topik `2704`. Uji dengan `python -m tools.ping` — perintahnya
mencetak identitas chat tujuan lalu mengirim satu pesan uji ke sana.

## Uji lokal

Mode produksi memakai webhook yang butuh URL https publik. Di laptop, pakai long
polling — tidak perlu ngrok. Di `.env`: `USE_POLLING=true`, `MINIAPP_DEV_TOKEN=dev`,
`BASE_URL` dan `REDIS_URL` dibiarkan kosong (cache jatuh ke memori proses).

```bash
uvicorn app.main:app --reload --port 8000
```

Coba `/hariini`, `/tilawah 3`, `/catatan uji`, `/isi`, `/edit`, `/rekap`, lalu
cek barisnya di Notion. `/dashboard` tidak bisa dipakai dari laptop — tombol
`WebAppInfo` Telegram menolak URL non-https; buka langsung
`http://localhost:8000/app?dev=dev`. Tanpa `?dev=`, panel menolak dengan 401,
persis seperti di produksi.

## Deploy ke Heroku

```bash
heroku create <nama-app>
heroku addons:create heroku-redis:mini
heroku config:set TELEGRAM_BOT_TOKEN=... TELEGRAM_OWNER_ID=... NOTION_TOKEN=... \
  TELEGRAM_WEBHOOK_SECRET=$(openssl rand -hex 16) \
  BASE_URL=https://<nama-app>.herokuapp.com TZ=Asia/Jakarta
git push heroku main
```

Satu proses `web` saja: penjadwal auto-fill ikut berjalan di dalamnya, jadi tidak
perlu clock process terpisah (§2 membolehkan penggabungan ini). Restart tidak
merusak apa pun — penjadwal membangun keadaannya ulang dari jam dinding tiap
tick, bukan dari timer. Webhook dan tombol menu Mini App dipasang sendiri saat
boot dari `BASE_URL`. Cek dengan `heroku logs --tail` dan
`curl https://<app>.herokuapp.com/health`.

**Basic dyno wajib** (`heroku ps:scale web=1:basic`). Eco tidur setelah 30 menit
tanpa trafik web, dan dyno yang tidur tidak menjalankan penjadwal — Maghrib lewat
tanpa tercatat. Ini bukan preferensi; §3 brief menjelaskan Eco secara struktural
tidak bisa menjalankan fitur ini.

Ambang waktu shalat dipatok di `app/config.py` (`JAM_SHALAT`), bukan config var —
ia bukan rahasia dan tidak berbeda antara laptop dan Heroku. Ubah dict itu kalau
angkanya terasa meleset; tidak ada tempat lain yang perlu disentuh.

## Perintah

| Perintah | Fungsi |
|---|---|
| `/hariini` | Lima shalat beserta status, sunnah tercentang, tilawah, catatan |
| `/isi` | Inline keyboard sunnah — checkbox, Qabliyah, Ba'diyah; multi-pilih |
| `/tilawah <n>` | Menambah halaman; `=n` untuk menimpa |
| `/catatan <teks>` | Menambah catatan refleksi hari ini |
| `/edit` | Koreksi shalat hari ini atau kemarin: Waktu lalu Cara |
| `/rekap` | Ringkasan 7 & 30 hari langsung di chat |
| `/dashboard` | Tombol pembuka Mini App |

## Mini App

- Shell `/app` tidak memuat data apa pun; isinya datang dari `/app/panel` yang
  menolak permintaan tanpa `initData` lolos HMAC-SHA256 dengan `auth_date` segar.
- Tiap ganti filter = satu `GET` htmx yang mengembalikan potongan HTML. Grafik
  adalah SVG yang dirakit di Python; satu-satunya JS pihak ketiga adalah
  `htmx.min.js` yang di-serve sendiri.
- Blok: ringkasan, rincian per shalat, frekuensi sunnah
  (paling jarang di atas), tren tilawah dengan rata-rata bergerak 7 hari, catatan.
- Filter: rentang (7/30 hari, bulan ini, kustom), per shalat, per kategori waktu,
  per cara, hari dalam pekan, dan sembunyikan hari yang terisi otomatis.

## Catatan implementasi

- **Notion tetap bisa diedit langsung.** Bot membaca ulang tiap kali cache
  kedaluwarsa (60 detik), dan tiap penulisan menghapus cache yang terdampak.
- **Skor tidak disimpan.** Semua persentase dan streak dihitung saat tampil, jadi
  rumusnya bisa diubah tanpa menyentuh satu pun baris data lama.
- **Skema diperiksa saat boot.** Kalau ada properti yang hilang atau berubah
  tipe, bot melapor lewat Telegram alih-alih gagal senyap.
- **Kolom Sumber** kini hanya berisi `Konfirmasi`/`Manual` untuk baris baru;
  nilai `Otomatis` tersisa di baris lama dan masih bisa difilter di dashboard.

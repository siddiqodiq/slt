# Brief Teknis — Bot Ibadah & Mini App Dashboard

**Versi 1 · 24 Agustus 2026**

Bot Telegram yang mengisi catatan ibadah ke Notion dan menyajikan dashboard di dalam Telegram — dibangun penuh dengan Python, dengan Notion tetap sebagai penyimpan datanya.

> **Pembaruan (26 Agu 2026):** Auto-fill **dihidupkan kembali** dalam mode literal §5 — baris ditulis `Awal waktu + Munfarid` begitu ambang waktu shalat lewat, bukan lewat prompt-lalu-fallback, lalu dikoreksi lewat tombol di pesan itu. **Sumber jadwal §4 (`equran.id`) tidak dipakai:** ambangnya jam datar waktu Jakarta di `JAM_SHALAT`, karena presisi menit tidak mengubah apa yang ditulis sementara API-nya membawa 403, cache bulanan, dan pergantian bulan yang harus diurus. *Clock process* juga tidak dibuat terpisah: penjadwalnya berjalan di dalam proses `web`, sesuai opsi penggabungan di §2. Heatmap kalender di Mini App dihapus atas permintaan pengguna.

| | |
|---|---|
| Data | Notion (master) |
| Hosting | Heroku |
| Bot | Baru, terpisah |
| Stack | Python |
| Pengguna | 1 orang |

---

## 1. Tujuan & ruang lingkup

Mengurangi gesekan mencatat ibadah harian sampai mendekati nol, lalu mengembalikan datanya dalam bentuk yang membuat kamu ingin melanjutkannya. Dua sisi itu memisahkan dua komponen sistem: **bot** untuk menangkap data, **mini app** untuk membacanya.

### Masuk ruang lingkup

- Bot Telegram baru, ditambahkan ke grup all-in-one yang sudah kamu punya
- Pengisian shalat fardhu otomatis mengikuti jadwal adzan lokasi kamu
- Input manual seluruh kolom sunnah lewat Telegram
- Mini App berisi dashboard dengan filter
- Notion tetap menjadi tempat data tersimpan dan tetap bisa kamu edit langsung

### Di luar ruang lingkup

- Multi-user — sistem ini untuk satu orang; tidak ada registrasi, tenancy, atau izin akses
- Pengingat/adzan sebagai notifikasi ibadah — bot mengirim pesan hanya sebagai *prompt pencatatan*, bukan sebagai pengingat rohani
- Perhitungan waktu shalat sendiri — seluruhnya diambil dari API eksternal

---

## 2. Arsitektur

Satu aplikasi Heroku menjalankan dua proses: `web` melayani webhook Telegram dan mini app, `clock` memicu prompt shalat pada waktunya. Notion adalah satu-satunya tempat data tersimpan permanen; Redis hanya cache dan state sementara.

```
                    ┌──────────────┐
                    │  Proses web  │───────┐
  ┌──────────┐ ────▶│ webhook+API  │       │
  │ Telegram │      └──────────────┘       ▼
  │ bot+app  │◀──── ┌──────────────┐  ┌─────────┐   ┌──────────────┐
  └──────────┘      │ Proses clock │─▶│  Redis  │──▶│    Notion    │
                    │  penjadwal   │  │ cache   │   │ sumber benar │
                    └──────┬───────┘  └─────────┘   └──────────────┘
                           │  1× per bulan
                           ▼
                    ┌──────────────┐
                    │  equran.id   │
                    └──────────────┘
```

### Alur baca

Mini app meminta data ke proses web. Web mengecek Redis; kalau meleset, ia menarik seluruh baris dari Notion (paginasi 100 baris per permintaan), menghitung agregatnya di memori, lalu menyimpan hasilnya di Redis dengan TTL pendek. Filter dan agregasi **tidak pernah** dilakukan lewat Notion — Notion hanya menyerahkan baris mentah.

### Alur tulis

Setiap penulisan langsung ke Notion, lalu cache yang terdampak dihapus. Tidak ada antrian tulis dan tidak ada penyimpanan lokal yang bisa menyimpang — konsekuensi wajar dari memilih Notion sebagai master.

### Tumpukan teknologi — Python

| Lapisan | Pilihan | Alasan |
|---|---|---|
| Runtime | Python 3.12 | Buildpack Heroku resmi; pin lewat `.python-version` |
| Web | `FastAPI` + `uvicorn` | Async native, melayani webhook, API, dan halaman mini app dalam satu app |
| Bot | `python-telegram-bot` (async) | Paling matang di Python; `WebAppInfo` dan inline keyboard didukung penuh. `aiogram` alternatif setara |
| Notion | `notion-client` | Port Python dari SDK resmi. Kalau ingin nol dependensi, `httpx` langsung ke REST API juga ringkas |
| Penjadwal | `APScheduler` (AsyncIOScheduler) | Clock process in-process, bukan Heroku Scheduler — lihat §3 |
| HTTP client | `httpx` | Async, dipakai untuk equran.id |
| Cache | `redis` (asyncio) → Heroku Key-Value Store | Filesystem dyno bersifat sementara |
| Mini App | `Jinja2` + `htmx`, grafik sebagai SVG yang di-render server | Tanpa toolchain Node sama sekali |

> **Soal "full Python"**
>
> Backend bisa 100% Python. Yang tidak bisa: **halaman mini app berjalan di browser**, jadi hasil akhirnya tetap HTML dan CSS — itu sifat platform, bukan pilihan bahasa. Yang bisa dihindari sepenuhnya adalah **toolchain JavaScript**-nya: tidak ada npm, tidak ada build step, tidak ada React.
>
> Caranya: FastAPI merender halaman dengan Jinja2, dan setiap perubahan filter dikirim sebagai permintaan `htmx` yang mengembalikan potongan HTML. Grafik dibuat sebagai SVG yang dirakit di Python dari data yang sudah diagregasi. Yang berjalan di browser cuma satu file `htmx.min.js` (±14 KB) yang kamu salin sekali dan tidak pernah disentuh lagi.
>
> **Konsekuensinya:** tiap ganti filter ada perjalanan bolak-balik ke server, bukan pembaruan instan di klien. Dengan cache Redis, respons di bawah 100 ms — tidak terasa untuk dashboard pribadi. Kalau kamu ingin interaksi yang benar-benar instan seperti aplikasi native, di situlah Node dan React baru layak dipertimbangkan.

### Struktur proses di Heroku

```
# Procfile
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
clock: python -m app.clock
```

Untuk menekan biaya, keduanya bisa digabung: jalankan APScheduler di dalam event startup FastAPI, sehingga cukup satu Basic dyno. Konsekuensinya restart web ikut mereset penjadwal — dapat diterima, karena jadwal memang dibangun ulang setiap boot.

---

## 3. Batasan yang mengikat

Dua keputusan yang sudah diambil — Notion sebagai master, Heroku sebagai hosting — membawa batasan yang tidak bisa dinegosiasi di level kode. Semuanya bisa diakali, tapi harus disadari sejak awal karena memengaruhi desain, bukan sekadar implementasi.

### Notion sebagai sumber kebenaran

> **⚠ Batas laju**
>
> Notion API membatasi sekitar **3 permintaan per detik** rata-rata per integrasi. Dashboard yang menembak Notion setiap kali filter diubah akan kena limit dalam hitungan detik. Cache bukan optimasi di sini — ia syarat agar sistem berfungsi.

- **Tidak ada agregasi di sisi server.** Notion tidak bisa menghitung "persentase shalat di awal waktu bulan ini". Seluruh baris harus ditarik, lalu dihitung di aplikasi.
- **Latensi 300–800 ms per permintaan.** Setahun data ≈ 365 baris ≈ 4 permintaan berpaginasi. Dapat diterima kalau di-cache, terasa lambat kalau tidak.
- **Halaman harus dibagikan ke integrasi.** Bot baru butuh integration token Notion sendiri, dan halaman *Tracker Ibadah* harus di-share ke integrasi itu. Tanpa langkah ini, API mengembalikan 404, bukan 403 — mudah salah didiagnosis.

> **✓ Yang kamu dapat sebagai gantinya**
>
> Kamu tetap bisa membuka Notion di HP dan mengedit apa pun secara langsung, dan perubahan itu otomatis terbaca bot. Kalau bot mati sebulan, datanya tetap utuh dan tetap bisa diisi manual. Ini nilai nyata dari pilihan Notion-sebagai-master, dan alasan kompleksitas cache di atas sepadan.

### Heroku

> **✕ Eco dyno akan merusak fitur utama**
>
> Eco dyno ($5/bulan) **tidur setelah 30 menit tanpa trafik web**. Prompt shalat yang harus muncul jam 04:35 tidak akan terkirim kalau dyno sedang tidur. Fitur inti brief ini menuntut **Basic dyno** ($0.01/jam, ≈ $7/bulan), yang tidak pernah tidur. Ini bukan preferensi — Eco secara struktural tidak bisa menjalankannya.

> **✕ Heroku Scheduler tidak cocok untuk jadwal shalat**
>
> Heroku Scheduler hanya mendukung interval **10 menit, per jam, atau harian**, dan dokumentasinya menyatakan eksekusi **tidak dijamin** — job bisa terlewat, dan sesekali bisa jalan dua kali. Untuk waktu adzan yang presisi ke menit, ini tidak memadai. Dokumentasi Heroku sendiri menyarankan *custom clock process* untuk pekerjaan yang kritis; itulah yang dipakai di sini.

- **Dyno di-restart setidaknya sekali dalam 24 jam.** Timer yang dipasang di memori akan hilang saat restart. Proses clock wajib membangun ulang jadwal harinya setiap kali boot, dan mencatat di Redis prompt mana yang sudah terkirim agar tidak dobel.
- **Filesystem bersifat sementara.** Jangan menyimpan cache jadwal atau state apa pun di disk — hilang setiap deploy dan setiap restart.
- **Zona waktu default UTC.** Set `TZ=Asia/Jakarta` di config vars, dan tetap simpan timestamp dalam UTC di dalam kode. Kesalahan 7 jam di sini akan menempatkan setiap prompt shalat di waktu yang salah.

---

## 4. Sumber jadwal shalat

API publik equran.id, tanpa autentikasi. Sudah diverifikasi terhadap dokumentasinya.

### Jadwal bulanan

```http
POST https://equran.id/api/v2/shalat
Content-Type: application/json

{
  "provinsi": "DKI Jakarta",
  "kabkota": "Kota Jakarta Pusat",
  "bulan": 8,
  "tahun": 2026
}
```

Respons berisi `data.jadwal[]`, satu objek per tanggal:

```json
{
  "tanggal": 24,
  "tanggal_lengkap": "2026-08-24",
  "hari": "Senin",
  "imsak": "04:25",   "subuh":   "04:35",
  "terbit": "05:52",  "dhuha":   "06:17",
  "dzuhur": "12:05",  "ashar":   "15:24",
  "maghrib": "18:13", "isya":    "19:25"
}
```

### Endpoint pendukung

| Endpoint | Metode | Kegunaan |
|---|---|---|
| `/api/v2/shalat/provinsi` | GET | Daftar 34 provinsi |
| `/api/v2/shalat/kabkota` | POST | Daftar kab/kota dalam satu provinsi (517 total) |
| `/api/v2/shalat` | POST | Jadwal satu bulan penuh |

> **⚠ Nama kabkota harus dicocokkan dulu**
>
> Kamu menulis `"Kota Jakarta"`, tapi DKI Jakarta kemungkinan besar terdaftar sebagai `Kota Jakarta Pusat`, `Kota Jakarta Selatan`, dan seterusnya. String-nya harus persis. Langkah pertama saat implementasi: panggil `/shalat/kabkota` dengan `{"provinsi":"DKI Jakarta"}`, lihat daftar aslinya, lalu simpan nilai yang tepat sebagai config var.

### Strategi pengambilan

- Ambil satu bulan penuh sekaligus, simpan di Redis dengan kunci `jadwal:{kabkota}:{tahun}-{bulan}`, tanpa kedaluwarsa dalam bulan berjalan.
- Ambil ulang saat proses clock boot dan tidak menemukan jadwal bulan berjalan — bukan lewat cron tanggal 1, yang bisa terlewat kalau dyno kebetulan restart.
- Ambil jadwal bulan berikutnya secara pre-fetch pada H-2 akhir bulan, supaya pergantian bulan tidak pernah menemui cache kosong.
- Kalau API tidak dapat dihubungi dan cache kosong, bot mengirim pesan ke kamu bahwa auto-fill nonaktif hari itu — **jangan menebak jadwal**.

---

## 5. Pengisian shalat fardhu

Kamu meminta: terisi otomatis begitu waktu shalat masuk, lalu bisa dikoreksi manual. Itu bisa dibangun apa adanya. Tapi ada satu masalah yang layak diangkat sebelum diputuskan.

> **✕ Masalah dengan menulis tepat saat adzan**
>
> Menulis `Awal waktu + Munfarid` pada detik adzan berkumandang berarti **mencatat sesuatu yang belum terjadi**. Hari yang kamu lupa buka akan tersimpan sebagai lima shalat di awal waktu — data yang terlihat sempurna justru pada hari-hari yang paling tidak kamu perhatikan. Untuk catatan ibadah, data yang diam-diam melebihkan lebih merugikan daripada data yang kosong.

### Desain yang disarankan: prompt lalu fallback

Mempertahankan kemudahan yang kamu inginkan, tapi menempatkan penulisannya setelah ada fakta.

| Momen | Yang terjadi |
|---|---|
| **T+0** — waktu masuk | Bot mengirim pesan: *"Maghrib masuk 18:13."* dengan tiga tombol — **🕌 Masjid** · **👥 Berjamaah** · **🧍 Sendiri** |
| **saat ditekan** | **Cara** diambil dari tombol. **Waktu** dihitung otomatis dari jam penekanan terhadap rentang shalat — memakai konvensi 25% / 25–75% / 75% yang sudah tertulis di halaman panduan Notion. Kamu tidak perlu menilai sendiri. |
| **T+akhir** — rentang habis | Kalau belum ada respons, barulah baris diisi `Awal waktu + Munfarid` dan ditandai sebagai belum dikonfirmasi. |

Hasilnya: perilaku sehari-hari kamu satu ketukan, penilaian *Waktu* jadi objektif dan bukan tebakan ingatan, dan hari yang terlewat tetap bisa dibedakan dari hari yang benar-benar berjalan baik.

> **Tetap tersedia**
>
> Kalau kamu lebih memilih versi literal — tulis langsung saat adzan tanpa prompt — itu satu baris konfigurasi, bukan arsitektur berbeda. Prompt tetap dikirim, hanya penulisannya dimajukan ke T+0.

### Rentang tiap shalat

Seluruh batas diambil dari field API yang sama, jadi tidak ada perhitungan fikih di dalam kode:

| Shalat | Mulai | Berakhir |
|---|---|---|
| Subuh | `subuh` | `terbit` |
| Dzuhur | `dzuhur` | `ashar` |
| Ashar | `ashar` | `maghrib` |
| Maghrib | `maghrib` | `isya` |
| Isya | `isya` | `subuh` hari berikutnya |

> **⚠ Isya melewati tengah malam**
>
> Rentang Isya menyeberangi pergantian tanggal. Fallback-nya jatuh pada dini hari, dan harus ditulis ke baris **hari kemarin**, bukan hari baru. Ini sumber bug yang hampir pasti muncul kalau tidak ditangani sejak awal.

---

## 6. Perintah bot

| Perintah | Fungsi |
|---|---|
| `/hariini` | Ringkasan hari ini: lima shalat beserta status, sunnah yang sudah tercentang, sisa yang kosong |
| `/isi` | Inline keyboard untuk sunnah — Qabliyah, Ba'diyah, Tahajud, Dhuha, Tahiyatul Masjid, Al-Waqiah, Al-Mulk. Multi-pilih, tombol berubah status saat ditekan |
| `/tilawah <n>` | Isi jumlah halaman. Menambah, bukan menimpa, kalau dipanggil dua kali dalam sehari |
| `/catatan <teks>` | Tulis catatan refleksi hari ini |
| `/edit` | Koreksi shalat mana pun hari ini atau kemarin |
| `/jadwal` | Jadwal shalat hari ini untuk lokasi tersimpan |
| `/rekap` | Ringkasan 7 dan 30 hari langsung di chat, tanpa membuka mini app |
| `/dashboard` | Tombol pembuka Mini App |
| `/lokasi` | Ganti provinsi dan kab/kota |

> **Grup versus chat pribadi**
>
> Bot berada di grup all-in-one, tapi **prompt shalat sebaiknya dikirim ke chat pribadi** — lima pesan sehari di grup akan terasa berisik, dan catatan ibadah bukan hal yang perlu tampil di riwayat grup. Biarkan perintah tetap bisa dipanggil dari grup; hanya prompt otomatis yang dipisahkan ke japri.

---

## 7. Mini App

> **✕ Wajib: validasi initData**
>
> Telegram mengirim `initData` ke halaman mini app. Server **harus** memverifikasinya dengan HMAC-SHA256 — `secret = HMAC_SHA256("WebAppData", bot_token)`, lalu bandingkan hash-nya — dan menolak `auth_date` yang terlalu lama. Jangan pernah percaya `user_id` yang dikirim klien. Tanpa langkah ini, siapa pun yang menemukan URL mini app bisa membaca dan mengubah catatan ibadah kamu.
>
> Di Python cukup `hmac` dan `hashlib` dari standard library — tanpa dependensi tambahan. Gunakan `hmac.compare_digest()` untuk membandingkan hash, bukan `==`.

> **Render di server**
>
> Dengan pendekatan Jinja2 + htmx, tiap blok di bawah adalah satu partial template. Filter mengirim permintaan `GET` dengan parameter query, server mengembalikan potongan HTML blok yang terdampak, htmx menukarnya di tempat. Tidak ada state klien yang perlu disinkronkan — halaman selalu mencerminkan apa yang server hitung.

### Isi dashboard

| Blok | Menampilkan |
|---|---|
| Ringkasan | Persentase shalat di awal waktu, persentase berjamaah, streak berjalan, total halaman tilawah — untuk periode terpilih |
| Heatmap kalender | Satu kotak per hari, warnanya dari kualitas shalat hari itu. Pola bolongnya terlihat tanpa membaca angka |
| Rincian per shalat | Lima baris, masing-masing dipecah menjadi proporsi Awal / Tengah / Akhir / Lewat. Ini yang menjawab "shalat mana yang paling sering saya tunda" |
| Sunnah | Frekuensi tiap sunnah dalam periode, diurutkan dari yang paling jarang — bagian yang paling layak diperbaiki muncul di atas |
| Tren tilawah | Halaman per hari dengan garis rata-rata bergerak 7 hari |

### Filter

- Rentang tanggal — 7 hari, 30 hari, bulan ini, kustom
- Per shalat — lihat hanya Subuh, misalnya
- Per kategori waktu dan per cara
- Hari dalam pekan — memunculkan pola seperti Subuh yang selalu meleset di akhir pekan

> **Skor dihitung, bukan disimpan**
>
> Semua kolom skor sudah dihapus dari Notion. Mini app menghitung agregat dari data mentah saat menampilkan. Konsekuensinya bagus: rumus skor bisa diubah kapan saja tanpa menyentuh satu pun baris data lama.

> **⚠ Soal motivasi**
>
> Kamu menyebut dashboard ini untuk mendukung semangat. Dua hal yang perlu dihindari saat merancang tampilannya: **streak yang putus** bisa terasa seperti kegagalan dan justru membuat orang berhenti mencatat, dan **skor tunggal** mudah berubah jadi angka yang dikejar demi angkanya. Menampilkan tren dan pola lebih aman daripada menampilkan peringkat — dan biarkan kolom Catatan punya tempat yang terlihat, karena di situlah sebabnya berada.

---

## 8. Peta data Notion

| Properti | Tipe | Nilai / catatan |
|---|---|---|
| Hari | title | Diisi bot, format `Senin, 24 Agu` |
| Tanggal | date | Diisi bot saat membuat baris — ini yang memperbaiki kekurangan view Kalender |
| Dibuat | created_time | Hanya baca |
| Subuh / Dzuhur / Ashar / Maghrib / Isya **Waktu** | select | `Awal waktu` · `Tengah waktu` · `Akhir waktu` · `Lewat waktu` |
| … **Cara** | select | `Masjid` · `Berjamaah` · `Munfarid` |
| Qabliyah | multi_select | Subuh · Dzuhur · Ashar · Maghrib · Isya |
| Ba'diyah | multi_select | Dzuhur · Maghrib · Isya |
| Tahajud · Dhuha · Tahiyatul Masjid · Al-Waqiah · Al-Mulk | checkbox | Diisi lewat `/isi` |
| Tilawah | number | Jumlah halaman |
| Catatan | rich_text | Teks bebas |

### Identitas

```
Halaman induk : 3c65c765-55ba-8137-9dd3-e01954228d9c
Database      : e77e9807-23d9-4fed-ac13-6b3cf8a015af
Data source   : b35e1f4f-a5ec-4513-84b5-b46ae46bac27
```

> **Satu kolom yang perlu ditambahkan**
>
> Sistem ini menulis dua jenis data ke kolom yang sama: yang kamu konfirmasi, dan yang ditebak fallback. Tanpa pembeda, keduanya tidak bisa dipisahkan lagi setelah tersimpan. Saran: satu kolom **Sumber** (select — `Konfirmasi` · `Otomatis` · `Manual`), supaya dashboard bisa menandai atau mengecualikan hari yang tidak pernah kamu jawab. Kamu sempat menolak checkbox *Ditinjau* sebelumnya — waktu itu belum ada auto-fill, sekarang taruhannya berbeda.

---

## 9. Tahapan pengerjaan

Tiap fase menghasilkan sesuatu yang bisa dipakai. Kalau berhenti di fase 2, kamu sudah punya sistem yang lebih baik daripada sekarang.

**F1 · Fondasi**
App Heroku dengan buildpack Python, Basic dyno, Redis, integration token Notion, halaman di-share ke integrasi. Verifikasi nama kabkota yang benar. Bot merespons `/jadwal` dengan data asli dari equran.id.

**F2 · Auto-fill shalat**
Proses clock, prompt inline keyboard, perhitungan Waktu dari jam penekanan, fallback saat rentang habis, penanganan Isya lintas tengah malam. Ini inti nilainya.

**F3 · Input manual**
`/isi`, `/tilawah`, `/catatan`, `/edit`. Setelah fase ini, Notion tidak perlu dibuka sama sekali untuk pencatatan harian.

**F4 · Mini App**
Validasi initData, lapisan cache, fungsi agregasi, template Jinja2, filter htmx, dan generator SVG untuk grafik.

**F5 · Pemantapan**
`/rekap`, penanganan error yang ramah, pesan peringatan saat API jadwal gagal, logging supaya kegagalan terdeteksi tanpa membuka Notion.

---

## 10. Risiko

| Risiko | Dampak | Penanganan |
|---|---|---|
| Restart dyno menghapus timer | Prompt shalat terlewat atau terkirim dua kali | Bangun ulang jadwal saat boot; catat di Redis prompt mana yang sudah terkirim hari itu |
| Batas laju Notion | Dashboard error saat filter diganti cepat | Cache wajib; antrikan penulisan; hormati header `Retry-After` |
| equran.id tidak dapat dihubungi | Auto-fill mati diam-diam | Cache bulanan menahan sebagian besar gangguan; kalau kosong, kirim pesan eksplisit, jangan menebak |
| Baris fallback tak terbedakan | Statistik terlihat lebih baik dari kenyataan | Kolom **Sumber** di §8 |
| Salah zona waktu | Semua prompt meleset 7 jam | `TZ=Asia/Jakarta`; uji khusus di sekitar tengah malam dan pergantian bulan |
| Perubahan skema Notion | Penulisan gagal senyap saat kamu menambah kolom | Validasi skema saat boot; bot melapor lewat Telegram kalau ada properti yang tak dikenal |

### Perkiraan biaya berjalan

- Heroku Basic dyno — $0,01/jam, sekitar **$7 per bulan** per proses
- Proses `web` dan `clock` bisa digabung dalam satu dyno untuk menekan biaya, dengan konsekuensi restart web ikut mereset penjadwal — dapat diterima karena jadwal memang dibangun ulang saat boot
- Add-on Redis punya tarif tersendiri; cek harga paket terkecil yang berlaku saat kamu berlangganan

---

## 11. Perlu diputuskan sebelum coding

1. **Nama kabkota yang tepat** untuk lokasi kamu — jalankan `/shalat/kabkota` lebih dulu dan pilih dari daftar aslinya.
2. **Kolom Sumber** — ditambahkan atau tidak. Kalau tidak, hari yang terlewat akan tercatat identik dengan hari yang berjalan baik.
3. **Perilaku auto-fill** — prompt lalu fallback (disarankan), atau tulis langsung saat adzan seperti permintaan awal.
4. **Konvensi tahajud** — masuk ke baris tanggal saat bangun, atau tanggal malam sebelumnya. Bot harus tahu ini agar konsisten.
5. **Batas akhir rentang Isya** — sampai Subuh berikutnya, atau sampai tengah malam. Memengaruhi kapan fallback Isya berjalan.
6. **Tujuan prompt** — chat pribadi (disarankan) atau grup all-in-one.

---

*Brief ini disusun terhadap kondisi database Tracker Ibadah per 24 Agustus 2026. Spesifikasi API equran.id dan batasan Heroku telah diverifikasi terhadap dokumentasi resminya.*
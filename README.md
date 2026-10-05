# 💰 Bot Simpan Uang

Bot catat keuangan dual-platform — Telegram Group & WhatsApp Group.

## Stack
- **Telegram:** Telegraf.js
- **WhatsApp:** Baileys (@whiskeysockets)
- **Database:** SQLite (better-sqlite3)
- **Scheduler:** node-cron
- **Deploy:** Railway / VPS

## Cara Setup

### 1. Install dependencies
```bash
npm install
```

### 2. Buat file .env
```bash
cp .env.example .env
```
Isi `TELEGRAM_TOKEN` dengan token dari [@BotFather](https://t.me/BotFather).

### 3. Jalankan
```bash
node index.js
```
- **Telegram:** langsung aktif
- **WhatsApp:** scan QR code yang muncul di terminal

---

## Perintah Telegram (prefix `/`)

| Command | Contoh |
|---|---|
| `/catat masuk` | `/catat masuk 500rb gaji` |
| `/catat keluar` | `/catat keluar 1.5jt belanja` |
| `/saldo` | Lihat saldo |
| `/history` | `/history` atau `/history 20` |
| `/undo` | Batalkan transaksi terakhir |
| `/laporan hari` | Laporan hari ini |
| `/laporan minggu` | Laporan 7 hari terakhir |
| `/laporan bulan` | Laporan bulan ini |
| `/target buat` | `/target buat Liburan 3jt 2026-12-31` |
| `/target lihat` | Lihat semua goal |
| `/target hapus` | `/target hapus Liburan` |
| `/tabung` | `/tabung 100rb Liburan` |
| `/reminder 20:00` | Set notif harian |
| `/reminder off` | Matikan reminder |

## Perintah WhatsApp (prefix `!`)

Sama persis, ganti `/` jadi `!`. Contoh:
```
!catat masuk 500rb gaji
!saldo
!laporan bulan
!target lihat
!tabung 100rb Liburan
```

Alias yang tersedia:
- `!riwayat` = `!history`
- `!batal` = `!undo`
- `!report` = `!laporan`
- `!goal` = `!target`
- `!nabung` = `!tabung`
- `!notif` = `!reminder`
- `!bantuan` = `!help`

## Shorthand Jumlah

| Input | Artinya |
|---|---|
| `500rb` | Rp 500.000 |
| `1.5jt` | Rp 1.500.000 |
| `1k` | Rp 1.000 |
| `2m` | Rp 2.000.000 |

## Deploy ke Railway

1. Push ke GitHub
2. Connect repo di [railway.app](https://railway.app)
3. Set environment variable `TELEGRAM_TOKEN`
4. Tambah **Volume** → mount ke `/app/data` (biar SQLite persistent)
5. Deploy 🚀

> **Catatan WA di Railway:** Scan QR harus dilakukan sekali lewat terminal Railway.
> Setelah session tersimpan di volume, bot tidak perlu scan ulang.

## Struktur Folder
```
money-bot/
├── index.js              ← Entry point
├── config.js             ← Config dari .env
├── package.json
├── .env.example
└── src/
    ├── core/
    │   ├── database.js   ← SQLite init + schema
    │   ├── finance.js    ← Logic transaksi & saldo
    │   ├── goals.js      ← Logic target tabungan
    │   ├── formatter.js  ← Format pesan Rupiah, progress bar
    │   └── reminder.js   ← Cron job notif harian
    ├── telegram/
    │   └── bot.js        ← Telegraf + semua command
    └── whatsapp/
        └── bot.js        ← Baileys + semua command
```

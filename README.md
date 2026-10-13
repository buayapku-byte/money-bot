# 💰 Bot Simpan Uang — Python

Bot Telegram pencatat keuangan pribadi, dikonversi dari Node.js ke Python.

## Fitur
- Catat transaksi masuk/keluar via teks natural (NLP)
- Multi-currency (USD, SGD, MYR, THB, dst)
- Goals / tabungan dengan progress bar
- Budget per kategori + alert 80%/100%
- Transaksi berulang (rutin)
- Grafik pengeluaran & trend bulanan (QuickChart.io)
- Export CSV
- Wishlist + proyeksi kapan bisa beli
- Analisis keuangan mingguan
- Berbagi wallet antar pengguna
- Bahasa Indonesia & English
- Reminder harian
- Auto backup DB

## Instalasi

```bash
# 1. Clone / extract project ini
# 2. Install dependencies
pip install -r requirements.txt

# 3. Salin .env.example ke .env dan isi token
cp .env.example .env
nano .env

# 4. Jalankan bot
python main.py
```

## Konfigurasi (.env)

| Variable | Wajib | Keterangan |
|----------|-------|------------|
| `TELEGRAM_TOKEN` | ✅ | Token dari @BotFather |
| `DB_PATH` | ❌ | Path database (default: `./data/money.db`) |
| `TIMEZONE` | ❌ | Zona waktu (default: `Asia/Jakarta`) |
| `REMINDER_TIME` | ❌ | Reminder harian (default: `20:00`) |
| `BACKUP_CHAT_ID` | ❌ | Chat ID untuk backup otomatis DB |
| `GOOGLE_SHEETS_ID` | ❌ | ID Google Sheets (perlu modul tambahan) |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | ❌ | Path JSON service account Google |

## Perintah Bot

| Perintah | Keterangan |
|---------|------------|
| `/start` | Mulai / daftar |
| `/help` | Daftar perintah |
| `/saldo` | Lihat saldo semua mata uang |
| `/laporan [hari\|minggu\|bulan]` | Laporan pengeluaran |
| `/history [n]` | Riwayat transaksi |
| `/undo` | Hapus transaksi terakhir |
| `/target` | Kelola savings goals |
| `/tabung <nama> <jumlah>` | Setor ke goal |
| `/kategori [hari\|minggu\|bulan]` | Laporan per kategori |
| `/grafik [hari\|minggu\|bulan]` | Bar chart pengeluaran |
| `/trend [3\|6\|12]` | Line chart trend bulanan |
| `/budget` | Kelola budget per kategori |
| `/rutin` | Kelola transaksi berulang |
| `/analisis` | Analisis keuangan (savings rate, dll) |
| `/kekayaan` | Ringkasan total aset |
| `/kurs` | Kelola kurs mata uang |
| `/export` | Export data ke CSV |
| `/wishlist` | Kelola wishlist |
| `/reminder HH:MM` | Set pengingat harian |
| `/wallet` | Kelola wallet (share/gabung) |
| `/bahasa [id\|en]` | Ganti bahasa |

## Catat Transaksi (NLP)

Cukup ketik teks biasa:

```
50rb makan siang
1jt gaji
bayar listrik 200000
USD 50 transfer luar
```

## Requirements

- Python 3.11+
- `python-telegram-bot==21.6`
- `apscheduler==3.10.4`
- `python-dotenv==1.0.1`
- `requests==2.32.3`

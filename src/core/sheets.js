// ─── Google Sheets Auto-Sync ──────────────────────────────
// Push transaksi harian ke Google Sheets
// Setup: buat Service Account, share sheet ke email SA, isi .env

'use strict';

const { google }   = require('googleapis');
const { getDb }    = require('./database');

let sheetsClient = null;

/**
 * Inisialisasi Google Sheets client dari env vars
 * Dipanggil satu kali saat startup (kalau GOOGLE_SHEETS_ID ada)
 */
function initSheets() {
  const sheetsId = process.env.GOOGLE_SHEETS_ID;
  const saJson   = process.env.GOOGLE_SERVICE_ACCOUNT_JSON;

  if (!sheetsId || !saJson) {
    console.log('[Sheets] GOOGLE_SHEETS_ID atau GOOGLE_SERVICE_ACCOUNT_JSON tidak diset — skip Google Sheets sync.');
    return false;
  }

  try {
    const credentials = JSON.parse(saJson);
    const auth = new google.auth.GoogleAuth({
      credentials,
      scopes: ['https://www.googleapis.com/auth/spreadsheets'],
    });
    sheetsClient = google.sheets({ version: 'v4', auth });
    console.log('[Sheets] Google Sheets client siap ✅');
    return true;
  } catch (err) {
    console.error('[Sheets] Gagal init Google Sheets client:', err.message);
    return false;
  }
}

/**
 * Pastikan header ada di baris 1 Sheet "Transaksi"
 */
async function ensureHeader(spreadsheetId) {
  const HEADERS = [
    'ID', 'Wallet ID', 'Tanggal', 'Tipe', 'Jumlah', 'Kategori', 'Catatan', 'Dibuat Oleh', 'Struk', 'Dicatat Pada'
  ];

  // Cek apakah sheet "Transaksi" sudah ada
  const meta = await sheetsClient.spreadsheets.get({ spreadsheetId });
  const sheetNames = meta.data.sheets.map(s => s.properties.title);

  if (!sheetNames.includes('Transaksi')) {
    // Buat sheet baru
    await sheetsClient.spreadsheets.batchUpdate({
      spreadsheetId,
      requestBody: {
        requests: [{
          addSheet: { properties: { title: 'Transaksi' } },
        }],
      },
    });
  }

  // Cek baris 1
  const res = await sheetsClient.spreadsheets.values.get({
    spreadsheetId,
    range: 'Transaksi!A1:J1',
  });

  if (!res.data.values || res.data.values.length === 0) {
    // Tulis header
    await sheetsClient.spreadsheets.values.update({
      spreadsheetId,
      range: 'Transaksi!A1:J1',
      valueInputOption: 'USER_ENTERED',
      requestBody: { values: [HEADERS] },
    });
    console.log('[Sheets] Header ditambahkan ke sheet Transaksi');
  }
}

/**
 * Cari baris terakhir yang terisi di kolom A (ID transaksi)
 * Untuk tahu dari mana mulai push transaksi baru
 */
async function getLastSyncedId(spreadsheetId) {
  try {
    const res = await sheetsClient.spreadsheets.values.get({
      spreadsheetId,
      range: 'Transaksi!A2:A',
    });
    const values = res.data.values || [];
    if (values.length === 0) return 0;
    // Ambil ID terbesar yang sudah ada
    const ids = values.map(r => parseInt(r[0]) || 0).filter(id => id > 0);
    return ids.length > 0 ? Math.max(...ids) : 0;
  } catch (_) {
    return 0;
  }
}

/**
 * Push transaksi baru ke Google Sheets (incremental — hanya yang belum ada)
 * @returns {{ pushed: number, sheetId: string }}
 */
async function pushTransactionsToSheets() {
  const spreadsheetId = process.env.GOOGLE_SHEETS_ID;
  if (!sheetsClient || !spreadsheetId) {
    return { pushed: 0, error: 'Google Sheets tidak dikonfigurasi' };
  }

  const db = getDb();

  try {
    await ensureHeader(spreadsheetId);

    const lastId = await getLastSyncedId(spreadsheetId);

    // Ambil semua transaksi baru (id > lastId), urutkan dari lama ke baru
    const transactions = db.prepare(`
      SELECT t.*, w.name AS wallet_name
      FROM transactions t
      LEFT JOIN wallets w ON w.id = t.wallet_id
      WHERE t.id > ?
      ORDER BY t.id ASC
    `).all(lastId);

    if (transactions.length === 0) {
      console.log('[Sheets] Tidak ada transaksi baru untuk di-push.');
      return { pushed: 0 };
    }

    const rows = transactions.map(tx => [
      tx.id,
      tx.wallet_id,
      tx.date,
      tx.type === 'in' ? 'Masuk' : 'Keluar',
      tx.amount,
      tx.category || 'umum',
      tx.note || '',
      tx.created_by || '',
      tx.receipt_path || '',
      tx.created_at,
    ]);

    // Append setelah baris terakhir
    await sheetsClient.spreadsheets.values.append({
      spreadsheetId,
      range: 'Transaksi!A2',
      valueInputOption: 'USER_ENTERED',
      insertDataOption: 'INSERT_ROWS',
      requestBody: { values: rows },
    });

    console.log(`[Sheets] Push ${rows.length} transaksi ke Google Sheets ✅`);
    return { pushed: rows.length };

  } catch (err) {
    console.error('[Sheets] Error push ke Google Sheets:', err.message);
    return { pushed: 0, error: err.message };
  }
}

/**
 * Update ringkasan saldo di sheet "Ringkasan"
 * Tampilkan saldo semua wallet, total masuk/keluar
 */
async function pushSummaryToSheets() {
  const spreadsheetId = process.env.GOOGLE_SHEETS_ID;
  if (!sheetsClient || !spreadsheetId) return;

  const db  = getDb();
  const now = new Date().toLocaleString('id-ID', { timeZone: 'Asia/Jakarta' });

  try {
    // Pastiin sheet Ringkasan ada
    const meta = await sheetsClient.spreadsheets.get({ spreadsheetId });
    const sheetNames = meta.data.sheets.map(s => s.properties.title);

    if (!sheetNames.includes('Ringkasan')) {
      await sheetsClient.spreadsheets.batchUpdate({
        spreadsheetId,
        requestBody: {
          requests: [{ addSheet: { properties: { title: 'Ringkasan' } } }],
        },
      });
    }

    const wallets = db.prepare('SELECT * FROM wallets').all();
    const rows = [
      ['💰 Ringkasan Saldo', '', `Update: ${now}`],
      ['Wallet ID', 'Nama', 'Platform', 'Total Masuk', 'Total Keluar', 'Saldo'],
    ];

    for (const w of wallets) {
      const masuk  = db.prepare(`SELECT COALESCE(SUM(amount),0) AS t FROM transactions WHERE wallet_id=? AND type='in'`).get(w.id)?.t || 0;
      const keluar = db.prepare(`SELECT COALESCE(SUM(amount),0) AS t FROM transactions WHERE wallet_id=? AND type='out'`).get(w.id)?.t || 0;
      rows.push([w.id, w.name || '', w.platform, masuk, keluar, masuk - keluar]);
    }

    await sheetsClient.spreadsheets.values.update({
      spreadsheetId,
      range: 'Ringkasan!A1',
      valueInputOption: 'USER_ENTERED',
      requestBody: { values: rows },
    });

    console.log('[Sheets] Ringkasan saldo diupdate ✅');
  } catch (err) {
    console.error('[Sheets] Error push ringkasan:', err.message);
  }
}

/**
 * Jalankan full sync: transaksi + ringkasan
 */
async function syncToSheets() {
  const result = await pushTransactionsToSheets();
  await pushSummaryToSheets();
  return result;
}

module.exports = { initSheets, syncToSheets, pushTransactionsToSheets, pushSummaryToSheets };

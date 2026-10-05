// ─── Core Finance Logic ──────────────────────────────────
// Semua operasi transaksi & saldo — dipakai Telegram & WA
// Diisi lengkap di Fase 3

const { getDb } = require('./database');

/**
 * Catat transaksi baru
 * @param {string} walletId - ID wallet (e.g. "tg:123456")
 * @param {string} type - 'in' | 'out'
 * @param {number} amount - Jumlah (harus > 0)
 * @param {string} note - Catatan opsional
 * @param {string} category - Kategori (default: 'umum')
 * @param {string} createdBy - Nama user yang catat
 * @returns {object} transaksi yang baru dibuat
 */
function addTransaction(walletId, type, amount, note = '', category = 'umum', createdBy = '') {
  const db = getDb();
  const result = db.prepare(`
    INSERT INTO transactions (wallet_id, type, amount, note, category, created_by)
    VALUES (?, ?, ?, ?, ?, ?)
  `).run(walletId, type, amount, note, category, createdBy);

  return db.prepare('SELECT * FROM transactions WHERE id = ?').get(result.lastInsertRowid);
}

/**
 * Hitung saldo wallet
 * @param {string} walletId
 * @returns {{ saldo: number, total_masuk: number, total_keluar: number }}
 */
function getSaldo(walletId) {
  const db = getDb();

  const masuk = db.prepare(`
    SELECT COALESCE(SUM(amount), 0) AS total
    FROM transactions WHERE wallet_id = ? AND type = 'in'
  `).get(walletId);

  const keluar = db.prepare(`
    SELECT COALESCE(SUM(amount), 0) AS total
    FROM transactions WHERE wallet_id = ? AND type = 'out'
  `).get(walletId);

  return {
    saldo: masuk.total - keluar.total,
    total_masuk: masuk.total,
    total_keluar: keluar.total,
  };
}

/**
 * Ambil riwayat transaksi terbaru
 * @param {string} walletId
 * @param {number} limit - Jumlah transaksi (default: 10)
 * @returns {Array}
 */
function getHistory(walletId, limit = 10) {
  const db = getDb();
  return db.prepare(`
    SELECT * FROM transactions
    WHERE wallet_id = ?
    ORDER BY created_at DESC
    LIMIT ?
  `).all(walletId, limit);
}

/**
 * Ambil laporan per periode
 * @param {string} walletId
 * @param {string} period - 'hari' | 'minggu' | 'bulan'
 * @returns {{ transactions: Array, summary: object }}
 */
function getLaporan(walletId, period = 'bulan') {
  const db = getDb();

  const dateFilter = {
    hari:   "date = date('now', 'localtime')",
    minggu: "date >= date('now', 'localtime', '-6 days')",
    bulan:  "strftime('%Y-%m', date) = strftime('%Y-%m', 'now', 'localtime')",
  };

  const filter = dateFilter[period] || dateFilter.bulan;

  const transactions = db.prepare(`
    SELECT * FROM transactions
    WHERE wallet_id = ? AND ${filter}
    ORDER BY date DESC, created_at DESC
  `).all(walletId);

  const masuk  = transactions.filter(t => t.type === 'in').reduce((s, t) => s + t.amount, 0);
  const keluar = transactions.filter(t => t.type === 'out').reduce((s, t) => s + t.amount, 0);

  return {
    transactions,
    summary: {
      total_masuk: masuk,
      total_keluar: keluar,
      selisih: masuk - keluar,
      jumlah_transaksi: transactions.length,
    },
  };
}

/**
 * Hapus transaksi terakhir (undo)
 * @param {string} walletId
 * @returns {object|null} transaksi yang dihapus
 */
function undoLast(walletId) {
  const db = getDb();
  const last = db.prepare(`
    SELECT * FROM transactions
    WHERE wallet_id = ?
    ORDER BY created_at DESC LIMIT 1
  `).get(walletId);

  if (!last) return null;

  db.prepare('DELETE FROM transactions WHERE id = ?').run(last.id);
  return last;
}

module.exports = { addTransaction, getSaldo, getHistory, getLaporan, undoLast };

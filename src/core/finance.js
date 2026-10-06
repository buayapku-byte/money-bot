// ─── Core Finance Logic ──────────────────────────────────
// Semua operasi transaksi & saldo — dipakai Telegram & WA
// Diisi lengkap di Fase 3
 
const { getDb, resolveWalletId } = require('./database');
 
// ─── Category Detection ───────────────────────────────────
 
const KATEGORI_KEYWORDS = {
  makan:     ['makan', 'minum', 'resto', 'restoran', 'warteg', 'warung', 'kafe', 'cafe', 'coffee', 'lunch', 'dinner', 'breakfast', 'sarapan', 'nasi', 'ayam', 'bakso', 'mie', 'pizza', 'burger', 'soto', 'pecel', 'gado'],
  jajan:     ['jajan', 'snack', 'cemilan', 'gorengan', 'es', 'minuman', 'boba', 'thai tea', 'kopi', 'starbucks', 'indomie', 'mie cup', 'chiki', 'chitato'],
  transport: ['ojek', 'gojek', 'grab', 'maxim', 'taxi', 'taksi', 'bensin', 'bbm', 'parkir', 'toll', 'tol', 'bus', 'kereta', 'commuter', 'angkot', 'inpres', 'uber'],
  belanja:   ['belanja', 'shopee', 'tokopedia', 'lazada', 'toko', 'mall', 'supermarket', 'indomaret', 'alfamart', 'hypermart', 'carrefour', 'beli'],
  tagihan:   ['listrik', 'air', 'pdam', 'internet', 'wifi', 'pulsa', 'token', 'tagihan', 'iuran', 'sewa', 'kos', 'kontrakan', 'cicilan', 'kredit', 'pln'],
  hiburan:   ['hiburan', 'nonton', 'bioskop', 'game', 'spotify', 'netflix', 'youtube', 'film', 'konser', 'liburan', 'wisata', 'hotel'],
  kesehatan: ['kesehatan', 'dokter', 'obat', 'apotek', 'klinik', 'rumah sakit', 'vitamin', 'gym', 'fitness'],
  gaji:      ['gaji', 'salary', 'upah', 'honor', 'komisi', 'bayaran'],
  bonus:     ['bonus', 'thr', 'reward', 'hadiah', 'cashback'],
  transfer:  ['transfer', 'kirim', 'terima', 'tf'],
};
 
/**
 * Deteksi kategori otomatis dari catatan
 * @param {string} note
 * @returns {string} kategori
 */
function detectCategory(note) {
  if (!note) return 'umum';
  const lower = note.toLowerCase();
  for (const [kategori, keywords] of Object.entries(KATEGORI_KEYWORDS)) {
    if (keywords.some(kw => lower.includes(kw))) return kategori;
  }
  return 'umum';
}
 
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
  // Auto-detect kategori dari note kalau masih 'umum'
  const finalCategory = (category === 'umum' && note) ? detectCategory(note) : category;
  const result = db.prepare(`
    INSERT INTO transactions (wallet_id, type, amount, note, category, created_by)
    VALUES (?, ?, ?, ?, ?, ?)
  `).run(walletId, type, amount, note, finalCategory, createdBy);
 
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
 
/**
 * Hapus transaksi berdasarkan ID
 * @param {string} walletId
 * @param {number} id - ID transaksi
 * @returns {object} transaksi yang dihapus
 */
function deleteTransaction(walletId, id) {
  const db = getDb();
  const trx = db.prepare(
    'SELECT * FROM transactions WHERE id = ? AND wallet_id = ?'
  ).get(id, walletId);
 
  if (!trx) throw new Error(`Transaksi #${id} tidak ditemukan.`);
 
  db.prepare('DELETE FROM transactions WHERE id = ?').run(id);
  return trx;
}
 
/**
 * Ambil laporan transaksi dikelompokkan per kategori
 * @param {string} walletId
 * @param {string} period - 'hari' | 'minggu' | 'bulan'
 * @returns {Array} [{ category, type, total, jumlah }]
 */
function getLaporanKategori(walletId, period = 'bulan') {
  const db = getDb();
 
  const dateFilter = {
    hari:   "date = date('now', 'localtime')",
    minggu: "date >= date('now', 'localtime', '-6 days')",
    bulan:  "strftime('%Y-%m', date) = strftime('%Y-%m', 'now', 'localtime')",
  };
 
  const filter = dateFilter[period] || dateFilter.bulan;
 
  return db.prepare(`
    SELECT category, type,
      SUM(amount) AS total,
      COUNT(*) AS jumlah
    FROM transactions
    WHERE wallet_id = ? AND ${filter}
    GROUP BY category, type
    ORDER BY total DESC
  `).all(walletId);
}
 
// ─── Budget Functions ─────────────────────────────────────
 
/**
 * Set atau update budget kategori bulan ini
 */
function setBudget(walletId, category, amount) {
  const db = getDb();
  const month = new Date().toISOString().slice(0, 7);
  db.prepare(`
    INSERT INTO budgets (wallet_id, category, amount, month)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(wallet_id, category, month) DO UPDATE SET amount = excluded.amount
  `).run(walletId, category, amount, month);
  return { category, amount, month };
}
 
/**
 * Ambil semua budget bulan ini beserta pengeluaran aktual
 */
function getBudgets(walletId) {
  const db = getDb();
  const month = new Date().toISOString().slice(0, 7);
  const budgets = db.prepare(
    'SELECT * FROM budgets WHERE wallet_id = ? AND month = ? ORDER BY category ASC'
  ).all(walletId, month);
 
  return budgets.map(b => {
    const spent = db.prepare(`
      SELECT COALESCE(SUM(amount), 0) AS total
      FROM transactions
      WHERE wallet_id = ? AND category = ? AND type = 'out'
      AND strftime('%Y-%m', date) = ?
    `).get(walletId, b.category, month);
    const persen = b.amount > 0 ? Math.round((spent.total / b.amount) * 100) : 0;
    return { ...b, spent: spent.total, persen };
  });
}
 
/**
 * Hapus budget kategori bulan ini
 */
function deleteBudget(walletId, category) {
  const db = getDb();
  const month = new Date().toISOString().slice(0, 7);
  const budget = db.prepare(
    'SELECT * FROM budgets WHERE wallet_id = ? AND category = ? AND month = ?'
  ).get(walletId, category, month);
  if (!budget) throw new Error(`Budget kategori "${category}" tidak ada bulan ini.`);
  db.prepare('DELETE FROM budgets WHERE wallet_id = ? AND category = ? AND month = ?')
    .run(walletId, category, month);
  return budget;
}
 
/**
 * Cek apakah budget hampir/sudah habis setelah transaksi
 * @returns {{ level: 'warning'|'danger', persen, budget, spent, category }} atau null
 */
function checkBudgetAlert(walletId, category) {
  const db = getDb();
  const month = new Date().toISOString().slice(0, 7);
  const budget = db.prepare(
    'SELECT * FROM budgets WHERE wallet_id = ? AND category = ? AND month = ?'
  ).get(walletId, category, month);
  if (!budget) return null;
 
  const spent = db.prepare(`
    SELECT COALESCE(SUM(amount), 0) AS total
    FROM transactions
    WHERE wallet_id = ? AND category = ? AND type = 'out'
    AND strftime('%Y-%m', date) = ?
  `).get(walletId, category, month);
 
  const persen = Math.round((spent.total / budget.amount) * 100);
  if (persen >= 100) return { level: 'danger',  persen, budget: budget.amount, spent: spent.total, category };
  if (persen >= 80)  return { level: 'warning', persen, budget: budget.amount, spent: spent.total, category };
  return null;
}
 
// ─── Edit Transaction ─────────────────────────────────────
 
/**
 * Edit jumlah dan/atau catatan transaksi
 * @param {string} walletId
 * @param {number} id
 * @param {number|null} amount - null = tidak berubah
 * @param {string|null} note  - null = tidak berubah
 */
function editTransaction(walletId, id, amount, note) {
  const db = getDb();
  const trx = db.prepare('SELECT * FROM transactions WHERE id = ? AND wallet_id = ?').get(id, walletId);
  if (!trx) throw new Error(`Transaksi #${id} tidak ditemukan.`);
 
  const newAmount   = amount !== null ? amount : trx.amount;
  const newNote     = note   !== null ? note   : trx.note;
  const newCategory = (note !== null && note) ? detectCategory(note) : trx.category;
 
  db.prepare(`
    UPDATE transactions SET amount = ?, note = ?, category = ? WHERE id = ?
  `).run(newAmount, newNote, newCategory, id);
 
  return db.prepare('SELECT * FROM transactions WHERE id = ?').get(id);
}
 
// ─── Recurring Functions ──────────────────────────────────
 
/**
 * Tambah transaksi berulang
 */
function addRecurring(walletId, type, amount, note, category, dayOfMonth) {
  const db = getDb();
  const finalCategory = (category === 'umum' && note) ? detectCategory(note) : category;
  const result = db.prepare(`
    INSERT INTO recurring (wallet_id, type, amount, note, category, day_of_month)
    VALUES (?, ?, ?, ?, ?, ?)
  `).run(walletId, type, amount, note, finalCategory, dayOfMonth);
  return db.prepare('SELECT * FROM recurring WHERE id = ?').get(result.lastInsertRowid);
}
 
/**
 * Ambil daftar transaksi berulang aktif
 */
function getRecurring(walletId) {
  const db = getDb();
  return db.prepare(`
    SELECT * FROM recurring WHERE wallet_id = ? AND is_active = 1
    ORDER BY day_of_month ASC
  `).all(walletId);
}
 
/**
 * Hapus transaksi berulang
 */
function deleteRecurring(walletId, id) {
  const db = getDb();
  const rec = db.prepare('SELECT * FROM recurring WHERE id = ? AND wallet_id = ?').get(id, walletId);
  if (!rec) throw new Error(`Rutin #${id} tidak ditemukan.`);
  db.prepare('DELETE FROM recurring WHERE id = ?').run(id);
  return rec;
}
 
/**
 * Proses semua recurring yang harus dijalankan hari ini
 * Dipanggil oleh cron harian di reminder.js
 * @returns {Array} transaksi yang berhasil dicatat
 */
function processRecurring() {
  const db = getDb();
  const today     = new Date();
  const todayStr  = today.toISOString().slice(0, 10);
  const dayOfMonth = today.getDate();
  const monthStr  = today.toISOString().slice(0, 7);
 
  const toProcess = db.prepare(`
    SELECT * FROM recurring
    WHERE is_active = 1
    AND day_of_month = ?
    AND (last_run IS NULL OR strftime('%Y-%m', last_run) != ?)
  `).all(dayOfMonth, monthStr);
 
  const results = [];
  toProcess.forEach(rec => {
    try {
      const trx = addTransaction(rec.wallet_id, rec.type, rec.amount, rec.note, rec.category, 'auto-rutin');
      db.prepare('UPDATE recurring SET last_run = ? WHERE id = ?').run(todayStr, rec.id);
      results.push({ rec, trx });
    } catch (err) {
      console.error(`[Recurring] Error #${rec.id}:`, err.message);
    }
  });
 
  return results;
}
 
/**
 * Analisis pengeluaran mingguan — bandingkan minggu ini vs minggu lalu
 * Dipakai untuk Tips Otomatis
 * @param {string} walletId
 * @returns {{ tips: string[], thisWeekTotal: number, lastWeekTotal: number, byCategory: Array }}
 */
function getWeeklyAnalysis(walletId) {
  const db = getDb();
 
  // Pengeluaran 7 hari terakhir per kategori
  const thisWeek = db.prepare(`
    SELECT category, SUM(amount) AS total, COUNT(*) AS jumlah
    FROM transactions
    WHERE wallet_id = ? AND type = 'out'
      AND date >= date('now', 'localtime', '-6 days')
    GROUP BY category
    ORDER BY total DESC
  `).all(walletId);
 
  // Pengeluaran 7-14 hari lalu per kategori
  const lastWeek = db.prepare(`
    SELECT category, SUM(amount) AS total
    FROM transactions
    WHERE wallet_id = ? AND type = 'out'
      AND date >= date('now', 'localtime', '-13 days')
      AND date <  date('now', 'localtime', '-6 days')
    GROUP BY category
  `).all(walletId);
 
  // Total pemasukan minggu ini
  const incomeRow = db.prepare(`
    SELECT COALESCE(SUM(amount), 0) AS total
    FROM transactions
    WHERE wallet_id = ? AND type = 'in'
      AND date >= date('now', 'localtime', '-6 days')
  `).get(walletId);
 
  const lastWeekMap = {};
  lastWeek.forEach(r => { lastWeekMap[r.category] = r.total; });
 
  const thisWeekTotal = thisWeek.reduce((s, r) => s + r.total, 0);
  const lastWeekTotal = lastWeek.reduce((s, r) => s + r.total, 0);
  const thisWeekIncome = incomeRow.total;
 
  const tips = [];
 
  // Tip 1: Kategori boros vs minggu lalu
  thisWeek.forEach(r => {
    const prev = lastWeekMap[r.category] || 0;
    if (prev > 0) {
      const selisihPersen = Math.round(((r.total - prev) / prev) * 100);
      if (selisihPersen >= 30) {
        tips.push(`📌 Minggu ini kamu boros di *${r.category}* ${selisihPersen}% lebih dari minggu lalu (${formatRupiah(prev)} → ${formatRupiah(r.total)})`);
      }
    } else if (r.jumlah >= 3) {
      tips.push(`📌 Pengeluaran *${r.category}* cukup sering minggu ini (${r.jumlah}x, total ${formatRupiah(r.total)})`);
    }
  });
 
  // Tip 2: Total pengeluaran vs minggu lalu
  if (lastWeekTotal > 0) {
    const diff = Math.round(((thisWeekTotal - lastWeekTotal) / lastWeekTotal) * 100);
    if (diff >= 20) {
      tips.push(`⚠️ Total pengeluaran minggu ini *naik ${diff}%* dibanding minggu lalu`);
    } else if (diff <= -20) {
      tips.push(`✅ Keren! Pengeluaran minggu ini *turun ${Math.abs(diff)}%* dibanding minggu lalu`);
    }
  }
 
  // Tip 3: Rasio pengeluaran vs pemasukan
  if (thisWeekIncome > 0) {
    const ratio = Math.round((thisWeekTotal / thisWeekIncome) * 100);
    if (ratio >= 90) {
      tips.push(`🚨 Pengeluaran minggu ini *${ratio}%* dari pemasukanmu — hampir habis!`);
    } else if (ratio >= 70) {
      tips.push(`⚠️ Pengeluaran minggu ini sudah *${ratio}%* dari pemasukanmu`);
    } else if (ratio <= 40 && thisWeekTotal > 0) {
      tips.push(`💪 Pengeluaran minggu ini hanya *${ratio}%* dari pemasukan — nabungnya bagus!`);
    }
  }
 
  // Tip 4: Kategori terbesar
  if (thisWeek.length > 0) {
    const top = thisWeek[0];
    const persen = thisWeekTotal > 0 ? Math.round((top.total / thisWeekTotal) * 100) : 0;
    if (persen >= 50) {
      tips.push(`💡 *${top.category}* menyumbang *${persen}%* dari total pengeluaranmu minggu ini`);
    }
  }
 
  if (!tips.length) {
    if (thisWeekTotal === 0) {
      tips.push('😮 Tidak ada pengeluaran minggu ini — atau belum dicatat?');
    } else {
      tips.push('👍 Pengeluaran minggu ini terbilang normal, tidak ada yang mencolok.');
    }
  }
 
  return { tips, thisWeekTotal, lastWeekTotal, thisWeekIncome, byCategory: thisWeek };
}
 
// helper format di sini supaya tidak circular import
function formatRupiah(amount) {
  return 'Rp ' + Math.round(amount).toLocaleString('id-ID');
}
 
// ─── Multi-Currency ───────────────────────────────────────
 
const CURRENCY_SYMBOLS = { IDR: 'Rp', THB: '฿', MYR: 'RM', USD: '$', SGD: 'S$', EUR: '€', GBP: '£', JPY: '¥', CNY: '¥', AUD: 'A$' };
// Fallback default rates (dipakai kalau live rates belum tersedia)
const DEFAULT_RATES = { THB: 450, MYR: 3500, USD: 15750, SGD: 11800, EUR: 17200, GBP: 20500, JPY: 102, CNY: 2200, AUD: 10200 };
 
// Mata uang populer untuk ditampilkan di !kurs
const POPULAR_CURRENCIES = ['USD', 'EUR', 'GBP', 'SGD', 'MYR', 'THB', 'JPY', 'CNY', 'AUD', 'KRW', 'AED', 'SAR', 'HKD', 'INR', 'PHP', 'VND', 'TWD', 'CAD', 'CHF', 'NZD'];
 
/**
 * Fetch kurs live — coba beberapa API gratis, tanpa API key
 * Simpan ke tabel live_rates
 */
async function fetchLiveRates() {
  let rates = null;
 
  // API 1: exchangerate-api.com v4 (format: { rates: { IDR: 15750, ... } })
  try {
    const res = await fetch('https://api.exchangerate-api.com/v4/latest/USD', { signal: AbortSignal.timeout(8000) });
    if (res.ok) {
      const data = await res.json();
      if (data.rates?.IDR) rates = data.rates;
    }
  } catch (_) {}
 
  // API 2: open.exchangerate-api.com v6 (format: { conversion_rates: { IDR: 15750, ... } })
  if (!rates) {
    try {
      const res = await fetch('https://open.exchangerate-api.com/v6/latest/USD', { signal: AbortSignal.timeout(8000) });
      if (res.ok) {
        const data = await res.json();
        if (data.conversion_rates?.IDR) rates = data.conversion_rates;
      }
    } catch (_) {}
  }
 
  // API 3: frankfurter.dev (format: { rates: { IDR: 15750, ... } })
  if (!rates) {
    try {
      const res = await fetch('https://api.frankfurter.dev/v1/latest?base=USD', { signal: AbortSignal.timeout(8000) });
      if (res.ok) {
        const data = await res.json();
        if (data.rates?.IDR) rates = data.rates;
      }
    } catch (_) {}
  }
 
  if (!rates?.IDR) throw new Error('Semua API kurs gagal — cek koneksi Railway');
 
  const idrPerUsd = rates.IDR;
 
  const db = getDb();
  const stmt = db.prepare(`
    INSERT INTO live_rates (code, rate_to_idr, updated_at)
    VALUES (?, ?, datetime('now', 'localtime'))
    ON CONFLICT(code) DO UPDATE SET rate_to_idr = excluded.rate_to_idr, updated_at = excluded.updated_at
  `);
 
  let count = 0;
  for (const [code, ratePerUsd] of Object.entries(rates)) {
    if (code === 'IDR') continue;
    const rateToIdr = idrPerUsd / ratePerUsd;
    stmt.run(code, rateToIdr);
    count++;
  }
 
  console.log(`[Kurs] ${count} mata uang diupdate dari API (1 USD = Rp ${Math.round(idrPerUsd).toLocaleString('id-ID')})`);
  return { count, usdRate: Math.round(idrPerUsd) };
}
 
/**
 * Ambil waktu terakhir live rates diupdate
 */
function getLiveRateUpdatedAt() {
  const db = getDb();
  const row = db.prepare('SELECT updated_at FROM live_rates ORDER BY updated_at DESC LIMIT 1').get();
  return row?.updated_at || null;
}
 
/**
 * Set kurs manual (custom) untuk wallet — override live rates
 * Bisa pakai kode apapun, tidak terbatas
 */
function setCurrency(walletId, code, rateToIdr) {
  const db = getDb();
  const upper = code.toUpperCase();
  if (upper.length < 2 || upper.length > 6 || !/^[A-Z]+$/.test(upper)) {
    throw new Error(`Kode mata uang tidak valid: "${upper}"\nContoh yang benar: THB, USD, MYR`);
  }
  db.prepare(`
    INSERT INTO currencies (wallet_id, code, rate_to_idr)
    VALUES (?, ?, ?)
    ON CONFLICT(wallet_id, code) DO UPDATE SET rate_to_idr = excluded.rate_to_idr, updated_at = datetime('now', 'localtime')
  `).run(walletId, upper, rateToIdr);
  return { code: upper, rateToIdr };
}
 
/**
 * Ambil semua kurs: live rates + custom wallet (custom ditandai)
 */
function getCurrencies(walletId) {
  const db = getDb();
  const custom = db.prepare('SELECT code, rate_to_idr, updated_at FROM currencies WHERE wallet_id = ?').all(walletId);
  const live   = db.prepare('SELECT code, rate_to_idr, updated_at FROM live_rates ORDER BY code').all();
 
  const customMap = new Map(custom.map(r => [r.code, r]));
 
  // Merge: custom override live
  const merged = [
    ...custom.map(r => ({ ...r, is_custom: true })),
    ...live.filter(r => !customMap.has(r.code)).map(r => ({ ...r, is_custom: false })),
  ];
 
  return merged;
}
 
/**
 * Convert jumlah dari currency ke IDR
 * Priority: custom wallet → live rates → hardcoded defaults
 * @returns {number} jumlah dalam IDR (dibulatkan)
 */
function convertToIdr(walletId, amount, currencyCode) {
  const upper = currencyCode.toUpperCase();
  if (upper === 'IDR') return amount;
 
  const db = getDb();
 
  // 1. Kurs custom per wallet
  const customRow = db.prepare('SELECT rate_to_idr FROM currencies WHERE wallet_id = ? AND code = ?').get(walletId, upper);
  if (customRow) return Math.round(amount * customRow.rate_to_idr);
 
  // 2. Live rates dari API
  const liveRow = db.prepare('SELECT rate_to_idr FROM live_rates WHERE code = ?').get(upper);
  if (liveRow) return Math.round(amount * liveRow.rate_to_idr);
 
  // 3. Fallback hardcoded
  const rate = DEFAULT_RATES[upper];
  if (rate) return Math.round(amount * rate);
 
  throw new Error(`Kurs ${upper} tidak tersedia.\nCoba: !kurs update untuk refresh, atau !kurs set ${upper} [nilai ke IDR]`);
}
 
module.exports = {
  addTransaction, getSaldo, getHistory, getLaporan, undoLast, deleteTransaction, getLaporanKategori,
  setBudget, getBudgets, deleteBudget, checkBudgetAlert,
  editTransaction,
  addRecurring, getRecurring, deleteRecurring, processRecurring,
  getWeeklyAnalysis,
  fetchLiveRates, getLiveRateUpdatedAt,
  setCurrency, getCurrencies, convertToIdr, CURRENCY_SYMBOLS, POPULAR_CURRENCIES,
};
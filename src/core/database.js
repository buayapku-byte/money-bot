const { DatabaseSync } = require('node:sqlite');
const path = require('path');
const fs = require('fs');
const config = require('../../config');
 
let db;
 
/**
 * Inisialisasi database dan buat semua tabel jika belum ada
 */
function initDatabase() {
  // Pastiin folder data ada
  const dbDir = path.dirname(config.db.path);
  if (!fs.existsSync(dbDir)) {
    fs.mkdirSync(dbDir, { recursive: true });
  }
 
  db = new DatabaseSync(config.db.path);
 
  // Aktifkan WAL mode buat performa lebih baik
  db.exec('PRAGMA journal_mode = WAL');
  db.exec('PRAGMA foreign_keys = ON');
 
  createTables();
 
  // Migration: tambah kolom lang kalau belum ada (untuk DB yang sudah ada)
  try {
    db.exec("ALTER TABLE wallets ADD COLUMN lang TEXT DEFAULT 'id'");
    console.log('[DB] Kolom lang ditambahkan ke wallets');
  } catch (_) {
    // kolom sudah ada — skip
  }
 
  console.log(`✅ Database ready: ${config.db.path}`);
  return db;
}
 
/**
 * Buat semua tabel
 */
function createTables() {
  db.exec(`
    -- ─────────────────────────────────────────────────────
    -- Wallets: satu per chat/group (Telegram atau WhatsApp)
    -- wallet_id = "tg:123456789" atau "wa:628xxx@g.us"
    -- ─────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS wallets (
      id          TEXT PRIMARY KEY,
      platform    TEXT NOT NULL CHECK(platform IN ('telegram', 'whatsapp')),
      name        TEXT,
      created_at  TEXT DEFAULT (datetime('now', 'localtime'))
    );
 
    -- ─────────────────────────────────────────────────────
    -- Transactions: semua pemasukan & pengeluaran
    -- ─────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS transactions (
      id          INTEGER PRIMARY KEY AUTOINCREMENT,
      wallet_id   TEXT NOT NULL,
      type        TEXT NOT NULL CHECK(type IN ('in', 'out')),
      amount      REAL NOT NULL CHECK(amount > 0),
      category    TEXT DEFAULT 'umum',
      note        TEXT,
      created_by  TEXT,
      date        TEXT DEFAULT (date('now', 'localtime')),
      created_at  TEXT DEFAULT (datetime('now', 'localtime')),
      FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
    );
 
    -- Index buat query laporan per tanggal
    CREATE INDEX IF NOT EXISTS idx_transactions_wallet_date
      ON transactions(wallet_id, date);
 
    -- ─────────────────────────────────────────────────────
    -- Goals: target tabungan
    -- ─────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS goals (
      id              INTEGER PRIMARY KEY AUTOINCREMENT,
      wallet_id       TEXT NOT NULL,
      name            TEXT NOT NULL,
      target_amount   REAL NOT NULL CHECK(target_amount > 0),
      current_amount  REAL DEFAULT 0,
      deadline        TEXT,
      is_completed    INTEGER DEFAULT 0,
      created_at      TEXT DEFAULT (datetime('now', 'localtime')),
      FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
    );
 
    -- ─────────────────────────────────────────────────────
    -- Reminders: setting notif per wallet
    -- ─────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS reminders (
      wallet_id   TEXT PRIMARY KEY,
      time        TEXT DEFAULT '20:00',
      is_active   INTEGER DEFAULT 1,
      FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
    );
 
    -- ─────────────────────────────────────────────────────
    -- Budgets: limit pengeluaran per kategori per bulan
    -- ─────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS budgets (
      id          INTEGER PRIMARY KEY AUTOINCREMENT,
      wallet_id   TEXT NOT NULL,
      category    TEXT NOT NULL,
      amount      REAL NOT NULL CHECK(amount > 0),
      month       TEXT NOT NULL,
      created_at  TEXT DEFAULT (datetime('now', 'localtime')),
      UNIQUE(wallet_id, category, month),
      FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
    );
 
    -- ─────────────────────────────────────────────────────
    -- Recurring: transaksi berulang tiap bulan
    -- ─────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS recurring (
      id            INTEGER PRIMARY KEY AUTOINCREMENT,
      wallet_id     TEXT NOT NULL,
      type          TEXT NOT NULL CHECK(type IN ('in', 'out')),
      amount        REAL NOT NULL CHECK(amount > 0),
      note          TEXT,
      category      TEXT DEFAULT 'umum',
      day_of_month  INTEGER NOT NULL CHECK(day_of_month BETWEEN 1 AND 28),
      last_run      TEXT,
      is_active     INTEGER DEFAULT 1,
      created_at    TEXT DEFAULT (datetime('now', 'localtime')),
      FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
    );
 
    -- ─────────────────────────────────────────────────────
    -- Wallet Links: berbagi wallet (share wallet)
    -- member_id → primary_id (member ikut wallet primary)
    -- ─────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS wallet_links (
      member_id   TEXT PRIMARY KEY,
      primary_id  TEXT NOT NULL,
      linked_at   TEXT DEFAULT (datetime('now', 'localtime')),
      FOREIGN KEY (member_id)  REFERENCES wallets(id) ON DELETE CASCADE,
      FOREIGN KEY (primary_id) REFERENCES wallets(id) ON DELETE CASCADE
    );
 
    -- ─────────────────────────────────────────────────────
    -- Invite Codes: kode undangan buat share wallet
    -- ─────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS invite_codes (
      code        TEXT PRIMARY KEY,
      wallet_id   TEXT NOT NULL,
      expires_at  TEXT NOT NULL,
      used        INTEGER DEFAULT 0,
      created_at  TEXT DEFAULT (datetime('now', 'localtime')),
      FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
    );
 
    -- ─────────────────────────────────────────────────────
    -- Live Rates: kurs real-time dari API (global, bukan per wallet)
    -- ─────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS live_rates (
      code          TEXT PRIMARY KEY,
      rate_to_idr   REAL NOT NULL,
      updated_at    TEXT DEFAULT (datetime('now', 'localtime'))
    );
 
    -- ─────────────────────────────────────────────────────
    -- Currencies: kurs custom per wallet (override live_rates)
    -- ─────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS currencies (
      id            INTEGER PRIMARY KEY AUTOINCREMENT,
      wallet_id     TEXT NOT NULL,
      code          TEXT NOT NULL,
      rate_to_idr   REAL NOT NULL,
      updated_at    TEXT DEFAULT (datetime('now', 'localtime')),
      UNIQUE(wallet_id, code),
      FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
    );
  `);
}
 
/**
 * Get atau buat wallet baru berdasarkan platform + chat_id
 * @param {string} platform - 'telegram' | 'whatsapp'
 * @param {string|number} chatId - ID chat/group
 * @param {string} name - Nama chat/group (optional)
 * @returns {object} wallet
 */
function getOrCreateWallet(platform, chatId, name = null) {
  const walletId = `${platform === 'telegram' ? 'tg' : 'wa'}:${chatId}`;
 
  let wallet = db.prepare('SELECT * FROM wallets WHERE id = ?').get(walletId);
 
  if (!wallet) {
    db.prepare(`
      INSERT INTO wallets (id, platform, name)
      VALUES (?, ?, ?)
    `).run(walletId, platform, name);
 
    // Auto-buat reminder default
    db.prepare(`
      INSERT OR IGNORE INTO reminders (wallet_id, time)
      VALUES (?, ?)
    `).run(walletId, '20:00');
 
    wallet = db.prepare('SELECT * FROM wallets WHERE id = ?').get(walletId);
    console.log(`[DB] Wallet baru: ${walletId} (${name || 'unknown'})`);
  }
 
  return wallet;
}
 
/**
 * Ambil instance database (harus sudah diinit dulu)
 */
function getDb() {
  if (!db) throw new Error('Database belum diinisialisasi. Panggil initDatabase() dulu.');
  return db;
}
 
/**
 * Resolve wallet ID ke primary wallet-nya (kalau sedang linked)
 * Kalau tidak linked, return walletId itu sendiri
 * @param {string} walletId
 * @returns {string} primaryWalletId
 */
function resolveWalletId(walletId) {
  const link = db.prepare('SELECT primary_id FROM wallet_links WHERE member_id = ?').get(walletId);
  return link ? link.primary_id : walletId;
}
 
/**
 * Buat invite code untuk share wallet (berlaku 24 jam)
 * @param {string} walletId - Wallet yang mau di-share
 * @returns {string} code
 */
function createInviteCode(walletId) {
  // Hapus kode lama yang expired atau belum dipakai milik wallet ini
  db.prepare(`
    DELETE FROM invite_codes
    WHERE wallet_id = ? AND (used = 1 OR expires_at < datetime('now', 'localtime'))
  `).run(walletId);
 
  // Generate kode 6 karakter uppercase alphanumeric
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  let code;
  do {
    code = Array.from({ length: 6 }, () => chars[Math.floor(Math.random() * chars.length)]).join('');
  } while (db.prepare('SELECT 1 FROM invite_codes WHERE code = ?').get(code));
 
  const expiresAt = new Date(Date.now() + 24 * 60 * 60 * 1000)
    .toISOString()
    .replace('T', ' ')
    .substring(0, 19);
 
  db.prepare(`
    INSERT INTO invite_codes (code, wallet_id, expires_at)
    VALUES (?, ?, ?)
  `).run(code, walletId, expiresAt);
 
  return code;
}
 
/**
 * Gunakan invite code untuk menggabungkan wallet
 * @param {string} memberWalletId - Wallet yang mau bergabung
 * @param {string} code - Kode undangan
 * @returns {object} primary wallet
 * @throws {Error} jika kode tidak valid/expired
 */
function useInviteCode(memberWalletId, code) {
  const invite = db.prepare(`
    SELECT * FROM invite_codes
    WHERE code = ?
      AND used = 0
      AND expires_at > datetime('now', 'localtime')
  `).get(code.toUpperCase());
 
  if (!invite) throw new Error('Kode tidak valid atau sudah kadaluarsa.');
  if (invite.wallet_id === memberWalletId) throw new Error('Tidak bisa bergabung ke wallet sendiri.');
 
  // Tandai kode sudah dipakai
  db.prepare('UPDATE invite_codes SET used = 1 WHERE code = ?').run(code.toUpperCase());
 
  // Buat atau update link
  db.prepare(`
    INSERT OR REPLACE INTO wallet_links (member_id, primary_id)
    VALUES (?, ?)
  `).run(memberWalletId, invite.wallet_id);
 
  const primary = db.prepare('SELECT * FROM wallets WHERE id = ?').get(invite.wallet_id);
  console.log(`[DB] Wallet ${memberWalletId} linked ke ${invite.wallet_id}`);
  return primary;
}
 
/**
 * Pisahkan wallet dari primary (unlink)
 * @param {string} memberWalletId
 * @returns {object|null} link yang dihapus, atau null kalau memang tidak linked
 */
function unlinkWallet(memberWalletId) {
  const link = db.prepare('SELECT * FROM wallet_links WHERE member_id = ?').get(memberWalletId);
  if (!link) return null;
 
  db.prepare('DELETE FROM wallet_links WHERE member_id = ?').run(memberWalletId);
  console.log(`[DB] Wallet ${memberWalletId} unlinked dari ${link.primary_id}`);
  return link;
}
 
/**
 * Ambil bahasa wallet
 * @param {string} walletId
 * @returns {string} 'id' | 'en'
 */
function getLang(walletId) {
  const row = db.prepare('SELECT lang FROM wallets WHERE id = ?').get(walletId);
  return row?.lang || 'id';
}
 
/**
 * Set bahasa wallet
 * @param {string} walletId
 * @param {string} lang - 'id' | 'en'
 */
function setLang(walletId, lang) {
  db.prepare("UPDATE wallets SET lang = ? WHERE id = ?").run(lang, walletId);
}
 
module.exports = {
  initDatabase,
  getOrCreateWallet,
  getDb,
  resolveWalletId,
  createInviteCode,
  useInviteCode,
  unlinkWallet,
  getLang,
  setLang,
};
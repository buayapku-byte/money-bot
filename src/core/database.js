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
 
module.exports = { initDatabase, getOrCreateWallet, getDb };
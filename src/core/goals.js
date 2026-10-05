// ─── Goals / Target Tabungan ─────────────────────────────
// Semua operasi target tabungan — dipakai Telegram & WA

const { getDb } = require('./database');

/**
 * Buat goal baru
 * @param {string} walletId
 * @param {string} name - Nama goal (e.g. "Liburan Bali")
 * @param {number} targetAmount - Target nominal
 * @param {string|null} deadline - Tanggal deadline (YYYY-MM-DD) opsional
 * @returns {object} goal yang dibuat
 */
function createGoal(walletId, name, targetAmount, deadline = null) {
  const db = getDb();

  // Cek apakah nama sudah ada
  const existing = db.prepare(`
    SELECT id FROM goals
    WHERE wallet_id = ? AND LOWER(name) = LOWER(?) AND is_completed = 0
  `).get(walletId, name);

  if (existing) {
    throw new Error(`Goal "${name}" sudah ada. Gunakan /tabung untuk menambah dana.`);
  }

  const result = db.prepare(`
    INSERT INTO goals (wallet_id, name, target_amount, deadline)
    VALUES (?, ?, ?, ?)
  `).run(walletId, name, targetAmount, deadline);

  return db.prepare('SELECT * FROM goals WHERE id = ?').get(result.lastInsertRowid);
}

/**
 * Ambil semua goal aktif
 * @param {string} walletId
 * @returns {Array}
 */
function getGoals(walletId) {
  const db = getDb();
  return db.prepare(`
    SELECT * FROM goals
    WHERE wallet_id = ? AND is_completed = 0
    ORDER BY created_at ASC
  `).all(walletId);
}

/**
 * Tambah dana ke goal
 * @param {string} walletId
 * @param {string} goalName - Nama goal (fuzzy match)
 * @param {number} amount
 * @returns {{ goal: object, isCompleted: boolean }}
 */
function addToGoal(walletId, goalName, amount) {
  const db = getDb();

  // Cari goal — exact match dulu, lalu LIKE
  let goal = db.prepare(`
    SELECT * FROM goals
    WHERE wallet_id = ? AND LOWER(name) = LOWER(?) AND is_completed = 0
  `).get(walletId, goalName);

  if (!goal) {
    goal = db.prepare(`
      SELECT * FROM goals
      WHERE wallet_id = ? AND LOWER(name) LIKE LOWER(?) AND is_completed = 0
    `).get(walletId, `%${goalName}%`);
  }

  if (!goal) {
    throw new Error(`Goal "${goalName}" tidak ditemukan. Cek /target lihat untuk daftar goal.`);
  }

  const newAmount = goal.current_amount + amount;
  const isCompleted = newAmount >= goal.target_amount;

  db.prepare(`
    UPDATE goals
    SET current_amount = ?, is_completed = ?
    WHERE id = ?
  `).run(newAmount, isCompleted ? 1 : 0, goal.id);

  return {
    goal: { ...goal, current_amount: newAmount, is_completed: isCompleted ? 1 : 0 },
    isCompleted,
  };
}

/**
 * Hapus / batalkan goal
 * @param {string} walletId
 * @param {string} goalName
 * @returns {object} goal yang dihapus
 */
function deleteGoal(walletId, goalName) {
  const db = getDb();

  const goal = db.prepare(`
    SELECT * FROM goals
    WHERE wallet_id = ? AND LOWER(name) LIKE LOWER(?) AND is_completed = 0
  `).get(walletId, `%${goalName}%`);

  if (!goal) {
    throw new Error(`Goal "${goalName}" tidak ditemukan.`);
  }

  db.prepare('DELETE FROM goals WHERE id = ?').run(goal.id);
  return goal;
}

/**
 * Hitung progress goal dalam persen + info deadline
 * @param {object} goal
 * @returns {{ persen: number, sisaHari: number|null }}
 */
function getGoalProgress(goal) {
  const persen = Math.min(100, Math.round((goal.current_amount / goal.target_amount) * 100));

  let sisaHari = null;
  if (goal.deadline) {
    const deadline = new Date(goal.deadline);
    const sekarang = new Date();
    sisaHari = Math.ceil((deadline - sekarang) / (1000 * 60 * 60 * 24));
  }

  return { persen, sisaHari };
}

module.exports = { createGoal, getGoals, addToGoal, deleteGoal, getGoalProgress };

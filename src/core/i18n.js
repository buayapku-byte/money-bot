// ─── Internationalization (i18n) ─────────────────────────
// String UI dalam Bahasa Indonesia (id) dan English (en)

const STRINGS = {
  id: {
    // ── Umum ──────────────────────────────────────────────
    no_transaction:  '📭 Belum ada transaksi.',
    showing_last:    (n) => `_Menampilkan ${n} transaksi terakhir_\n_Gunakan /hapus [id] untuk hapus transaksi_`,

    // ── formatSaldo ───────────────────────────────────────
    saldo_title:    '💰 *Saldo Sekarang*',
    saldo_label:    'Saldo',
    income_label:   '📈 Total masuk',
    expense_label:  '📉 Total keluar',

    // ── formatTransaksi ───────────────────────────────────
    type_in:        'Pemasukan',
    type_out:       'Pengeluaran',
    trx_saved:      'dicatat!',
    trx_amount:     'Jumlah',
    trx_note:       'Catatan',
    trx_category:   'Kategori',
    trx_time:       'Waktu',

    // ── formatHistory ─────────────────────────────────────
    history_title:  '📋 *Riwayat Transaksi*',

    // ── formatLaporan ─────────────────────────────────────
    period_hari:    'Hari Ini',
    period_minggu:  'Minggu Ini',
    period_bulan:   'Bulan Ini',
    period_label:   'Periode',
    lap_title:      (p) => `📊 *Laporan ${p}*`,
    lap_income:     '📈 Masuk',
    lap_expense:    '📉 Keluar',
    surplus:        '✅ Surplus',
    deficit:        '⚠️ Defisit',
    lap_total:      (n) => `Total ${n} transaksi`,
    lap_detail:     '*Detail:*',
    lap_more:       (n) => `_...dan ${n} lainnya_`,

    // ── formatKategori ────────────────────────────────────
    kat_title:      (label) => `📊 *Laporan Kategori — ${label}*`,
    kat_expense:    '📉 *Pengeluaran:*',
    kat_income:     '📈 *Pemasukan:*',
    kat_total:      'Total',
    kat_empty:      (pfx) => `_Belum ada transaksi di periode ini._\n\nCoba: \`${pfx}kategori bulan\``,

    // ── formatGoals ───────────────────────────────────────
    goals_empty:    (pfx) => `🎯 Belum ada target tabungan.\n\nGunakan \`${pfx}target buat NamaGoal 1000000\` untuk mulai.`,
    goals_title:    '🎯 *Target Tabungan*',
    goals_target:   'Target',
    goals_days:     (n) => `${n} hari lagi`,
    goals_today:    'Hari ini!',
    goals_overdue:  (n) => `Terlewat ${Math.abs(n)} hari`,

    // ── formatBudgets ─────────────────────────────────────
    budget_title:   '💡 *Budget Bulan Ini*',
    budget_empty:   '💡 *Budget Bulan Ini*\n\n_Belum ada budget.\n\nGunakan:\n/budget makan 500rb\n/budget transport 300rb_',

    // ── formatRecurring ───────────────────────────────────
    rec_title:      '🔄 *Transaksi Berulang*',
    rec_empty:      (pfx) => `🔄 *Transaksi Berulang*\n\n_Belum ada.\n\nContoh:\n${pfx}rutin tambah keluar 150rb netflix 5\n(catat keluar 150rb "netflix" tiap tgl 5)_`,
    rec_every:      'tiap tgl',
    rec_delete:     (pfx) => `_Gunakan ${pfx}rutin hapus [id] untuk hapus_`,

    // ── formatAnalisis ────────────────────────────────────
    an_title:       (label) => `🧠 *Analisis Keuangan — ${label}*`,
    an_income:      '💰 Pemasukan',
    an_expense:     '💸 Pengeluaran',
    an_savings:     '📊 Savings Rate',
    an_up:          (n) => `📈 Pengeluaran vs bulan lalu: *naik ${n}%*`,
    an_down:        (n) => `📉 Pengeluaran vs bulan lalu: *turun ${n}%*`,
    an_txs:         (n, d) => `📋 *${n} transaksi* dalam ${d} hari aktif`,
    an_avg:         '📌 Rata-rata pengeluaran/hari',
    an_busiest:     '📅 Hari paling boros',
    an_top:         '📊 *Top Pengeluaran:*',
    an_advice:      '💡 *Saran:*',
    an_crit:        () => `🚨 Pengeluaran melebihi pemasukan! Segera kurangi.`,
    an_low:         (n) => `⚠️ Savings rate ${n}% — targetkan minimal 20%.`,
    an_high:        (n) => `🎉 Savings rate ${n}% — luar biasa! Pertahankan.`,
    an_ok:          (n) => `✅ Savings rate ${n}% — sudah bagus!`,
    an_twarn:       (n) => `⚠️ Pengeluaran naik *${n}%* dari bulan lalu.`,
    an_tgood:       (n) => `🎉 Berhasil hemat *${n}%* dibanding bulan lalu!`,
    an_topwarn:     (c, n) => `💡 *${c}* makan ${n}% budget — batasi dengan /budget.`,

    // ── formatKekayaan ────────────────────────────────────
    kk_title:       '💎 *Net Worth Snapshot*',
    kk_balance:     '💰 Saldo Aktif',
    kk_savings:     '🎯 Total Tabungan',
    kk_net:         '💎 Net Worth',
    kk_goals:       '📊 *Rincian Goals:*',
    kk_snap:        (d) => `_Snapshot per ${d}_`,

    // ── Bulan & Hari ──────────────────────────────────────
    BULAN: ['Januari','Februari','Maret','April','Mei','Juni','Juli','Agustus','September','Oktober','November','Desember'],
    HARI:  ['Minggu','Senin','Selasa','Rabu','Kamis','Jumat','Sabtu'],

    // ── /bahasa command ───────────────────────────────────
    lang_current:   '🇮🇩 Bahasa saat ini: *Indonesia*',
    lang_switched:  (l) => l === 'en'
      ? '🇬🇧 Language switched to *English*!'
      : '🇮🇩 Bahasa diubah ke *Indonesia*!',
    lang_usage:     '📖 Gunakan:\n`/bahasa id` — Bahasa Indonesia\n`/bahasa en` — English',
  },

  en: {
    // ── Umum ──────────────────────────────────────────────
    no_transaction:  '📭 No transactions yet.',
    showing_last:    (n) => `_Showing last ${n} transactions_\n_Use /hapus [id] to delete a transaction_`,

    // ── formatSaldo ───────────────────────────────────────
    saldo_title:    '💰 *Current Balance*',
    saldo_label:    'Balance',
    income_label:   '📈 Total in',
    expense_label:  '📉 Total out',

    // ── formatTransaksi ───────────────────────────────────
    type_in:        'Income',
    type_out:       'Expense',
    trx_saved:      'recorded!',
    trx_amount:     'Amount',
    trx_note:       'Note',
    trx_category:   'Category',
    trx_time:       'Time',

    // ── formatHistory ─────────────────────────────────────
    history_title:  '📋 *Transaction History*',

    // ── formatLaporan ─────────────────────────────────────
    period_hari:    'Today',
    period_minggu:  'This Week',
    period_bulan:   'This Month',
    period_label:   'Period',
    lap_title:      (p) => `📊 *Report — ${p}*`,
    lap_income:     '📈 In',
    lap_expense:    '📉 Out',
    surplus:        '✅ Surplus',
    deficit:        '⚠️ Deficit',
    lap_total:      (n) => `Total ${n} transactions`,
    lap_detail:     '*Details:*',
    lap_more:       (n) => `_...and ${n} more_`,

    // ── formatKategori ────────────────────────────────────
    kat_title:      (label) => `📊 *Category Report — ${label}*`,
    kat_expense:    '📉 *Expenses:*',
    kat_income:     '📈 *Income:*',
    kat_total:      'Total',
    kat_empty:      (pfx) => `_No transactions this period._\n\nTry: \`${pfx}kategori bulan\``,

    // ── formatGoals ───────────────────────────────────────
    goals_empty:    (pfx) => `🎯 No savings goals yet.\n\nUse \`${pfx}target buat GoalName 1000000\` to start.`,
    goals_title:    '🎯 *Savings Goals*',
    goals_target:   'Target',
    goals_days:     (n) => `${n} days left`,
    goals_today:    'Today!',
    goals_overdue:  (n) => `${Math.abs(n)} days overdue`,

    // ── formatBudgets ─────────────────────────────────────
    budget_title:   "💡 *This Month's Budget*",
    budget_empty:   "💡 *This Month's Budget*\n\n_No budgets yet.\n\nUse:\n/budget makan 500rb\n/budget transport 300rb_",

    // ── formatRecurring ───────────────────────────────────
    rec_title:      '🔄 *Recurring Transactions*',
    rec_empty:      (pfx) => `🔄 *Recurring Transactions*\n\n_None yet.\n\nExample:\n${pfx}rutin tambah keluar 150rb netflix 5\n(record 150rb "netflix" every 5th)_`,
    rec_every:      'every',
    rec_delete:     (pfx) => `_Use ${pfx}rutin hapus [id] to delete_`,

    // ── formatAnalisis ────────────────────────────────────
    an_title:       (label) => `🧠 *Financial Analysis — ${label}*`,
    an_income:      '💰 Income',
    an_expense:     '💸 Expenses',
    an_savings:     '📊 Savings Rate',
    an_up:          (n) => `📈 Expenses vs last month: *up ${n}%*`,
    an_down:        (n) => `📉 Expenses vs last month: *down ${n}%*`,
    an_txs:         (n, d) => `📋 *${n} transactions* in ${d} active days`,
    an_avg:         '📌 Avg. expense / active day',
    an_busiest:     '📅 Busiest spending day',
    an_top:         '📊 *Top Expenses:*',
    an_advice:      '💡 *Tips:*',
    an_crit:        () => `🚨 Expenses exceed income! Cut spending now.`,
    an_low:         (n) => `⚠️ Savings rate ${n}% — aim for at least 20%.`,
    an_high:        (n) => `🎉 Savings rate ${n}% — amazing! Keep it up.`,
    an_ok:          (n) => `✅ Savings rate ${n}% — looking good!`,
    an_twarn:       (n) => `⚠️ Expenses up *${n}%* from last month.`,
    an_tgood:       (n) => `🎉 Saved *${n}%* more than last month!`,
    an_topwarn:     (c, n) => `💡 *${c}* takes ${n}% of budget — set a limit with /budget.`,

    // ── formatKekayaan ────────────────────────────────────
    kk_title:       '💎 *Net Worth Snapshot*',
    kk_balance:     '💰 Active Balance',
    kk_savings:     '🎯 Total Savings',
    kk_net:         '💎 Net Worth',
    kk_goals:       '📊 *Goals Breakdown:*',
    kk_snap:        (d) => `_Snapshot as of ${d}_`,

    // ── Bulan & Hari ──────────────────────────────────────
    BULAN: ['January','February','March','April','May','June','July','August','September','October','November','December'],
    HARI:  ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'],

    // ── /bahasa command ───────────────────────────────────
    lang_current:   '🇬🇧 Current language: *English*',
    lang_switched:  (l) => l === 'en'
      ? '🇬🇧 Language switched to *English*!'
      : '🇮🇩 Bahasa diubah ke *Indonesia*!',
    lang_usage:     '📖 Use:\n`/bahasa id` — Bahasa Indonesia\n`/bahasa en` — English',
  },
};

/**
 * Get translated string
 * @param {string} lang  - 'id' | 'en'
 * @param {string} key
 * @param {...any} args  - passed to function values
 * @returns {string}
 */
function t(lang, key, ...args) {
  const pack = STRINGS[lang] || STRINGS.id;
  const str  = pack[key] ?? STRINGS.id[key] ?? key;
  return typeof str === 'function' ? str(...args) : str;
}

module.exports = { t, STRINGS };

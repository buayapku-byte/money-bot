"""
Internationalization (i18n) — Bahasa Indonesia & English.
Semua string UI ada di sini.
"""
from typing import Any

STRINGS: dict[str, dict] = {
    'id': {
        'no_transaction': '📭 Belum ada transaksi.',
        'showing_last': lambda n: f'_Menampilkan {n} transaksi terakhir_\n_Gunakan /hapus [id] untuk hapus transaksi_',

        'saldo_title':   '💰 *Saldo Sekarang*',
        'saldo_label':   'Saldo',
        'income_label':  '📈 Total masuk',
        'expense_label': '📉 Total keluar',

        'type_in':      'Pemasukan',
        'type_out':     'Pengeluaran',
        'trx_saved':    'dicatat!',
        'trx_amount':   'Jumlah',
        'trx_note':     'Catatan',
        'trx_category': 'Kategori',
        'trx_time':     'Waktu',

        'history_title': '📋 *Riwayat Transaksi*',

        'period_hari':   'Hari Ini',
        'period_minggu': 'Minggu Ini',
        'period_bulan':  'Bulan Ini',
        'period_label':  'Periode',
        'lap_title':     lambda p: f'📊 *Laporan {p}*',
        'lap_income':    '📈 Masuk',
        'lap_expense':   '📉 Keluar',
        'surplus':       '✅ Surplus',
        'deficit':       '⚠️ Defisit',
        'lap_total':     lambda n: f'Total {n} transaksi',
        'lap_detail':    '*Detail:*',
        'lap_more':      lambda n: f'_...dan {n} lainnya_',

        'kat_title':   lambda label: f'📊 *Laporan Kategori — {label}*',
        'kat_expense': '📉 *Pengeluaran:*',
        'kat_income':  '📈 *Pemasukan:*',
        'kat_total':   'Total',
        'kat_empty':   lambda pfx: f'_Belum ada transaksi di periode ini._\n\nCoba: `{pfx}kategori bulan`',

        'goals_empty': lambda pfx: f'🎯 Belum ada target tabungan.\n\nGunakan `{pfx}target buat NamaGoal 1000000` untuk mulai.',
        'goals_title':  '🎯 *Target Tabungan*',
        'goals_target': 'Target',
        'goals_days':   lambda n: f'{n} hari lagi',
        'goals_today':  'Hari ini!',
        'goals_overdue': lambda n: f'Terlewat {abs(n)} hari',

        'budget_title': '💡 *Budget Bulan Ini*',
        'budget_empty': '💡 *Budget Bulan Ini*\n\n_Belum ada budget.\n\nGunakan:\n/budget makan 500rb\n/budget transport 300rb_',

        'rec_title':  '🔄 *Transaksi Berulang*',
        'rec_empty':  lambda pfx: f'🔄 *Transaksi Berulang*\n\n_Belum ada.\n\nContoh:\n{pfx}rutin tambah keluar 150rb netflix 5\n(catat keluar 150rb "netflix" tiap tgl 5)_',
        'rec_every':  'tiap tgl',
        'rec_delete': lambda pfx: f'_Gunakan {pfx}rutin hapus [id] untuk hapus_',

        'an_title':    lambda label: f'🧠 *Analisis Keuangan — {label}*',
        'an_income':   '💰 Pemasukan',
        'an_expense':  '💸 Pengeluaran',
        'an_savings':  '📊 Savings Rate',
        'an_up':       lambda n: f'📈 Pengeluaran vs bulan lalu: *naik {n}%*',
        'an_down':     lambda n: f'📉 Pengeluaran vs bulan lalu: *turun {n}%*',
        'an_txs':      lambda n, d: f'📋 *{n} transaksi* dalam {d} hari aktif',
        'an_avg':      '📌 Rata-rata pengeluaran/hari',
        'an_busiest':  '📅 Hari paling boros',
        'an_top':      '📊 *Top Pengeluaran:*',
        'an_advice':   '💡 *Saran:*',
        'an_crit':     lambda: '🚨 Pengeluaran melebihi pemasukan! Segera kurangi.',
        'an_low':      lambda n: f'⚠️ Savings rate {n}% — targetkan minimal 20%.',
        'an_high':     lambda n: f'🎉 Savings rate {n}% — luar biasa! Pertahankan.',
        'an_ok':       lambda n: f'✅ Savings rate {n}% — sudah bagus!',
        'an_twarn':    lambda n: f'⚠️ Pengeluaran naik *{n}%* dari bulan lalu.',
        'an_tgood':    lambda n: f'🎉 Berhasil hemat *{n}%* dibanding bulan lalu!',
        'an_topwarn':  lambda c, n: f'💡 *{c}* makan {n}% budget — batasi dengan /budget.',

        'kk_title':   '💎 *Net Worth Snapshot*',
        'kk_balance': '💰 Saldo Aktif',
        'kk_savings': '🎯 Total Tabungan',
        'kk_net':     '💎 Net Worth',
        'kk_goals':   '📊 *Rincian Goals:*',
        'kk_snap':    lambda d: f'_Snapshot per {d}_',

        'BULAN': ['Januari','Februari','Maret','April','Mei','Juni','Juli','Agustus','September','Oktober','November','Desember'],
        'HARI':  ['Minggu','Senin','Selasa','Rabu','Kamis','Jumat','Sabtu'],

        'lang_current':  '🇮🇩 Bahasa saat ini: *Indonesia*',
        'lang_switched': lambda l: '🇬🇧 Language switched to *English*!' if l == 'en' else '🇮🇩 Bahasa diubah ke *Indonesia*!',
        'lang_usage':    '📖 Gunakan:\n`/bahasa id` — Bahasa Indonesia\n`/bahasa en` — English',
    },

    'en': {
        'no_transaction': '📭 No transactions yet.',
        'showing_last': lambda n: f'_Showing last {n} transactions_\n_Use /hapus [id] to delete a transaction_',

        'saldo_title':   '💰 *Current Balance*',
        'saldo_label':   'Balance',
        'income_label':  '📈 Total in',
        'expense_label': '📉 Total out',

        'type_in':      'Income',
        'type_out':     'Expense',
        'trx_saved':    'recorded!',
        'trx_amount':   'Amount',
        'trx_note':     'Note',
        'trx_category': 'Category',
        'trx_time':     'Time',

        'history_title': '📋 *Transaction History*',

        'period_hari':   'Today',
        'period_minggu': 'This Week',
        'period_bulan':  'This Month',
        'period_label':  'Period',
        'lap_title':     lambda p: f'📊 *Report — {p}*',
        'lap_income':    '📈 In',
        'lap_expense':   '📉 Out',
        'surplus':       '✅ Surplus',
        'deficit':       '⚠️ Deficit',
        'lap_total':     lambda n: f'Total {n} transactions',
        'lap_detail':    '*Details:*',
        'lap_more':      lambda n: f'_...and {n} more_',

        'kat_title':   lambda label: f'📊 *Category Report — {label}*',
        'kat_expense': '📉 *Expenses:*',
        'kat_income':  '📈 *Income:*',
        'kat_total':   'Total',
        'kat_empty':   lambda pfx: f'_No transactions this period._\n\nTry: `{pfx}kategori bulan`',

        'goals_empty': lambda pfx: f'🎯 No savings goals yet.\n\nUse `{pfx}target buat GoalName 1000000` to start.',
        'goals_title':  '🎯 *Savings Goals*',
        'goals_target': 'Target',
        'goals_days':   lambda n: f'{n} days left',
        'goals_today':  'Today!',
        'goals_overdue': lambda n: f'{abs(n)} days overdue',

        'budget_title': "💡 *This Month's Budget*",
        'budget_empty': "💡 *This Month's Budget*\n\n_No budgets yet.\n\nUse:\n/budget makan 500rb\n/budget transport 300rb_",

        'rec_title':  '🔄 *Recurring Transactions*',
        'rec_empty':  lambda pfx: f'🔄 *Recurring Transactions*\n\n_None yet.\n\nExample:\n{pfx}rutin tambah keluar 150rb netflix 5_',
        'rec_every':  'every',
        'rec_delete': lambda pfx: f'_Use {pfx}rutin hapus [id] to delete_',

        'an_title':    lambda label: f'🧠 *Financial Analysis — {label}*',
        'an_income':   '💰 Income',
        'an_expense':  '💸 Expenses',
        'an_savings':  '📊 Savings Rate',
        'an_up':       lambda n: f'📈 Expenses vs last month: *up {n}%*',
        'an_down':     lambda n: f'📉 Expenses vs last month: *down {n}%*',
        'an_txs':      lambda n, d: f'📋 *{n} transactions* in {d} active days',
        'an_avg':      '📌 Avg. expense / active day',
        'an_busiest':  '📅 Busiest spending day',
        'an_top':      '📊 *Top Expenses:*',
        'an_advice':   '💡 *Tips:*',
        'an_crit':     lambda: '🚨 Expenses exceed income! Cut spending now.',
        'an_low':      lambda n: f'⚠️ Savings rate {n}% — aim for at least 20%.',
        'an_high':     lambda n: f'🎉 Savings rate {n}% — amazing! Keep it up.',
        'an_ok':       lambda n: f'✅ Savings rate {n}% — looking good!',
        'an_twarn':    lambda n: f'⚠️ Expenses up *{n}%* from last month.',
        'an_tgood':    lambda n: f'🎉 Saved *{n}%* more than last month!',
        'an_topwarn':  lambda c, n: f'💡 *{c}* takes {n}% of budget — set a limit with /budget.',

        'kk_title':   '💎 *Net Worth Snapshot*',
        'kk_balance': '💰 Active Balance',
        'kk_savings': '🎯 Total Savings',
        'kk_net':     '💎 Net Worth',
        'kk_goals':   '📊 *Goals Breakdown:*',
        'kk_snap':    lambda d: f'_Snapshot as of {d}_',

        'BULAN': ['January','February','March','April','May','June','July','August','September','October','November','December'],
        'HARI':  ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'],

        'lang_current':  '🇬🇧 Current language: *English*',
        'lang_switched': lambda l: '🇬🇧 Language switched to *English*!' if l == 'en' else '🇮🇩 Bahasa diubah ke *Indonesia*!',
        'lang_usage':    '📖 Use:\n`/bahasa id` — Bahasa Indonesia\n`/bahasa en` — English',
    },
}


def t(lang: str, key: str, *args) -> str:
    """Ambil string terjemahan. Kalau callable, panggil dengan *args."""
    locale = STRINGS.get(lang) or STRINGS['id']
    val = locale.get(key) or STRINGS['id'].get(key, key)
    if callable(val):
        return val(*args)
    return val

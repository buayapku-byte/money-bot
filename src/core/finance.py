"""
Finance — semua operasi transaksi, saldo, budget, kurs, analisis.
Konversi dari finance.js (Node.js) ke Python.
"""
import csv
import io
import requests
from datetime import datetime, date, timedelta
from typing import Optional

from .database import get_db, _row, _rows

# ─── Category Detection ───────────────────────────────────────

KATEGORI_KEYWORDS = {
    'makan':     ['makan', 'minum', 'resto', 'restoran', 'warteg', 'warung', 'kafe', 'cafe', 'coffee',
                  'lunch', 'dinner', 'breakfast', 'sarapan', 'nasi', 'ayam', 'bakso', 'mie', 'pizza',
                  'burger', 'soto', 'pecel', 'gado'],
    'jajan':     ['jajan', 'snack', 'cemilan', 'gorengan', 'es', 'minuman', 'boba', 'thai tea', 'kopi',
                  'starbucks', 'indomie', 'mie cup', 'chiki', 'chitato'],
    'transport': ['ojek', 'gojek', 'grab', 'maxim', 'taxi', 'taksi', 'bensin', 'bbm', 'parkir', 'toll',
                  'tol', 'bus', 'kereta', 'commuter', 'angkot', 'inpres', 'uber'],
    'belanja':   ['belanja', 'shopee', 'tokopedia', 'lazada', 'toko', 'mall', 'supermarket', 'indomaret',
                  'alfamart', 'hypermart', 'carrefour', 'beli'],
    'tagihan':   ['listrik', 'air', 'pdam', 'internet', 'wifi', 'pulsa', 'token', 'tagihan', 'iuran',
                  'sewa', 'kos', 'kontrakan', 'cicilan', 'kredit', 'pln'],
    'hiburan':   ['hiburan', 'nonton', 'bioskop', 'game', 'spotify', 'netflix', 'youtube', 'film',
                  'konser', 'liburan', 'wisata', 'hotel'],
    'kesehatan': ['kesehatan', 'dokter', 'obat', 'apotek', 'klinik', 'rumah sakit', 'vitamin', 'gym',
                  'fitness'],
    'gaji':      ['gaji', 'salary', 'upah', 'honor', 'komisi', 'bayaran'],
    'bonus':     ['bonus', 'thr', 'reward', 'hadiah', 'cashback'],
    'transfer':  ['transfer', 'kirim', 'terima', 'tf'],
}

CURRENCY_SYMBOLS = {
    'IDR': 'Rp', 'THB': '฿', 'MYR': 'RM', 'USD': '$', 'SGD': 'S$',
    'EUR': '€', 'GBP': '£', 'JPY': '¥', 'CNY': '¥', 'AUD': 'A$',
}

DEFAULT_RATES = {
    'THB': 450, 'MYR': 3500, 'USD': 15750, 'SGD': 11800,
    'EUR': 17200, 'GBP': 20500, 'JPY': 102, 'CNY': 2200, 'AUD': 10200,
}

POPULAR_CURRENCIES = [
    'USD', 'EUR', 'GBP', 'SGD', 'MYR', 'THB', 'JPY', 'CNY', 'AUD',
    'KRW', 'AED', 'SAR', 'HKD', 'INR', 'PHP', 'VND', 'TWD', 'CAD', 'CHF', 'NZD',
]

DEFAULT_DISPLAY_CURRENCIES = ['USD', 'SGD', 'MYR', 'THB']


def detect_category(note: str) -> str:
    if not note:
        return 'umum'
    lower = note.lower()
    for kategori, keywords in KATEGORI_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return kategori
    return 'umum'


# ─── Transaction CRUD ────────────────────────────────────────

def add_transaction(wallet_id: str, type_: str, amount: float,
                    note: str = '', category: str = 'umum',
                    created_by: str = '', date_override: str = None) -> dict:
    db = get_db()
    final_cat = detect_category(note) if (category == 'umum' and note) else category
    if date_override:
        cur = db.execute(
            'INSERT INTO transactions (wallet_id, type, amount, note, category, created_by, date) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (wallet_id, type_, amount, note, final_cat, created_by, date_override)
        )
    else:
        cur = db.execute(
            'INSERT INTO transactions (wallet_id, type, amount, note, category, created_by) VALUES (?, ?, ?, ?, ?, ?)',
            (wallet_id, type_, amount, note, final_cat, created_by)
        )
    db.commit()
    return _row(db.execute('SELECT * FROM transactions WHERE id = ?', (cur.lastrowid,)))


def get_saldo(wallet_id: str) -> dict:
    db = get_db()
    masuk  = _row(db.execute(
        "SELECT COALESCE(SUM(amount),0) AS total FROM transactions WHERE wallet_id=? AND type='in'",
        (wallet_id,)
    ))['total']
    keluar = _row(db.execute(
        "SELECT COALESCE(SUM(amount),0) AS total FROM transactions WHERE wallet_id=? AND type='out'",
        (wallet_id,)
    ))['total']
    return {'saldo': masuk - keluar, 'total_masuk': masuk, 'total_keluar': keluar}


def get_history(wallet_id: str, limit: int = 10) -> list:
    db = get_db()
    return _rows(db.execute(
        'SELECT * FROM transactions WHERE wallet_id=? ORDER BY created_at DESC LIMIT ?',
        (wallet_id, limit)
    ))


def get_laporan(wallet_id: str, period: str = 'bulan') -> dict:
    db = get_db()
    date_filter = {
        'hari':   "date = date('now','localtime')",
        'minggu': "date >= date('now','localtime','-6 days')",
        'bulan':  "strftime('%Y-%m',date) = strftime('%Y-%m','now','localtime')",
    }
    f = date_filter.get(period, date_filter['bulan'])
    transactions = _rows(db.execute(
        f"SELECT * FROM transactions WHERE wallet_id=? AND {f} ORDER BY date DESC, created_at DESC",
        (wallet_id,)
    ))
    masuk  = sum(t['amount'] for t in transactions if t['type'] == 'in')
    keluar = sum(t['amount'] for t in transactions if t['type'] == 'out')
    return {
        'transactions': transactions,
        'summary': {
            'total_masuk':       masuk,
            'total_keluar':      keluar,
            'selisih':           masuk - keluar,
            'jumlah_transaksi':  len(transactions),
        },
    }


def undo_last(wallet_id: str) -> Optional[dict]:
    db = get_db()
    last = _row(db.execute(
        'SELECT * FROM transactions WHERE wallet_id=? ORDER BY created_at DESC LIMIT 1',
        (wallet_id,)
    ))
    if not last:
        return None
    db.execute('DELETE FROM transactions WHERE id=?', (last['id'],))
    db.commit()
    return last


def delete_transaction(wallet_id: str, id_: int) -> dict:
    db = get_db()
    trx = _row(db.execute(
        'SELECT * FROM transactions WHERE id=? AND wallet_id=?', (id_, wallet_id)
    ))
    if not trx:
        raise ValueError(f'Transaksi #{id_} tidak ditemukan.')
    db.execute('DELETE FROM transactions WHERE id=?', (id_,))
    db.commit()
    return trx


def edit_transaction(wallet_id: str, id_: int, amount: Optional[float], note: Optional[str]) -> dict:
    db = get_db()
    trx = _row(db.execute('SELECT * FROM transactions WHERE id=? AND wallet_id=?', (id_, wallet_id)))
    if not trx:
        raise ValueError(f'Transaksi #{id_} tidak ditemukan.')
    new_amount   = amount if amount is not None else trx['amount']
    new_note     = note   if note   is not None else trx['note']
    new_category = detect_category(note) if (note is not None and note) else trx['category']
    db.execute(
        'UPDATE transactions SET amount=?, note=?, category=? WHERE id=?',
        (new_amount, new_note, new_category, id_)
    )
    db.commit()
    return _row(db.execute('SELECT * FROM transactions WHERE id=?', (id_,)))


def get_laporan_kategori(wallet_id: str, period: str = 'bulan') -> list:
    db = get_db()
    date_filter = {
        'hari':   "date = date('now','localtime')",
        'minggu': "date >= date('now','localtime','-6 days')",
        'bulan':  "strftime('%Y-%m',date) = strftime('%Y-%m','now','localtime')",
    }
    f = date_filter.get(period, date_filter['bulan'])
    return _rows(db.execute(
        f"SELECT category, type, SUM(amount) AS total, COUNT(*) AS jumlah "
        f"FROM transactions WHERE wallet_id=? AND {f} "
        f"GROUP BY category, type ORDER BY total DESC",
        (wallet_id,)
    ))


# ─── Budget ───────────────────────────────────────────────────

def set_budget(wallet_id: str, category: str, amount: float) -> dict:
    db = get_db()
    month = datetime.now().strftime('%Y-%m')
    db.execute(
        'INSERT INTO budgets (wallet_id, category, amount, month) VALUES (?,?,?,?) '
        'ON CONFLICT(wallet_id, category, month) DO UPDATE SET amount=excluded.amount',
        (wallet_id, category, amount, month)
    )
    db.commit()
    return {'category': category, 'amount': amount, 'month': month}


def get_budgets(wallet_id: str) -> list:
    db = get_db()
    month = datetime.now().strftime('%Y-%m')
    budgets = _rows(db.execute(
        'SELECT * FROM budgets WHERE wallet_id=? AND month=? ORDER BY category ASC',
        (wallet_id, month)
    ))
    result = []
    for b in budgets:
        spent_row = _row(db.execute(
            "SELECT COALESCE(SUM(amount),0) AS total FROM transactions "
            "WHERE wallet_id=? AND category=? AND type='out' AND strftime('%Y-%m',date)=?",
            (wallet_id, b['category'], month)
        ))
        spent = spent_row['total']
        persen = round((spent / b['amount']) * 100) if b['amount'] > 0 else 0
        result.append({**b, 'spent': spent, 'persen': persen})
    return result


def delete_budget(wallet_id: str, category: str) -> dict:
    db = get_db()
    month = datetime.now().strftime('%Y-%m')
    budget = _row(db.execute(
        'SELECT * FROM budgets WHERE wallet_id=? AND category=? AND month=?',
        (wallet_id, category, month)
    ))
    if not budget:
        raise ValueError(f'Budget kategori "{category}" tidak ada bulan ini.')
    db.execute('DELETE FROM budgets WHERE wallet_id=? AND category=? AND month=?',
               (wallet_id, category, month))
    db.commit()
    return budget


def check_budget_alert(wallet_id: str, category: str) -> Optional[dict]:
    db = get_db()
    month = datetime.now().strftime('%Y-%m')
    budget = _row(db.execute(
        'SELECT * FROM budgets WHERE wallet_id=? AND category=? AND month=?',
        (wallet_id, category, month)
    ))
    if not budget:
        return None
    spent_row = _row(db.execute(
        "SELECT COALESCE(SUM(amount),0) AS total FROM transactions "
        "WHERE wallet_id=? AND category=? AND type='out' AND strftime('%Y-%m',date)=?",
        (wallet_id, category, month)
    ))
    spent  = spent_row['total']
    persen = round((spent / budget['amount']) * 100) if budget['amount'] > 0 else 0
    if persen >= 100:
        return {'level': 'danger',  'persen': persen, 'budget': budget['amount'], 'spent': spent, 'category': category}
    if persen >= 80:
        return {'level': 'warning', 'persen': persen, 'budget': budget['amount'], 'spent': spent, 'category': category}
    return None


# ─── Recurring ────────────────────────────────────────────────

def add_recurring(wallet_id: str, type_: str, amount: float,
                  note: str, category: str, day_of_month: int) -> dict:
    db = get_db()
    final_cat = detect_category(note) if (category == 'umum' and note) else category
    cur = db.execute(
        'INSERT INTO recurring (wallet_id, type, amount, note, category, day_of_month) VALUES (?,?,?,?,?,?)',
        (wallet_id, type_, amount, note, final_cat, day_of_month)
    )
    db.commit()
    return _row(db.execute('SELECT * FROM recurring WHERE id=?', (cur.lastrowid,)))


def get_recurring(wallet_id: str) -> list:
    db = get_db()
    return _rows(db.execute(
        'SELECT * FROM recurring WHERE wallet_id=? AND is_active=1 ORDER BY day_of_month ASC',
        (wallet_id,)
    ))


def delete_recurring(wallet_id: str, id_: int) -> dict:
    db = get_db()
    rec = _row(db.execute('SELECT * FROM recurring WHERE id=? AND wallet_id=?', (id_, wallet_id)))
    if not rec:
        raise ValueError(f'Rutin #{id_} tidak ditemukan.')
    db.execute('DELETE FROM recurring WHERE id=?', (id_,))
    db.commit()
    return rec


def process_recurring() -> list:
    db = get_db()
    today      = datetime.now()
    today_str  = today.strftime('%Y-%m-%d')
    month_str  = today.strftime('%Y-%m')
    day        = today.day

    to_process = _rows(db.execute(
        "SELECT * FROM recurring WHERE is_active=1 AND day_of_month=? "
        "AND (last_run IS NULL OR strftime('%Y-%m',last_run) != ?)",
        (day, month_str)
    ))

    results = []
    for rec in to_process:
        try:
            trx = add_transaction(rec['wallet_id'], rec['type'], rec['amount'],
                                  rec['note'], rec['category'], 'auto-rutin')
            db.execute('UPDATE recurring SET last_run=? WHERE id=?', (today_str, rec['id']))
            db.commit()
            results.append({'rec': rec, 'trx': trx})
        except Exception as e:
            print(f"[Recurring] Error #{rec['id']}: {e}")
    return results


# ─── Analysis ─────────────────────────────────────────────────

def _format_rupiah(amount: float) -> str:
    return f"Rp {int(round(amount)):,}".replace(',', '.')


def get_weekly_analysis(wallet_id: str) -> dict:
    db = get_db()
    this_week = _rows(db.execute(
        "SELECT category, SUM(amount) AS total, COUNT(*) AS jumlah "
        "FROM transactions WHERE wallet_id=? AND type='out' "
        "AND date >= date('now','localtime','-6 days') "
        "GROUP BY category ORDER BY total DESC",
        (wallet_id,)
    ))
    last_week = _rows(db.execute(
        "SELECT category, SUM(amount) AS total "
        "FROM transactions WHERE wallet_id=? AND type='out' "
        "AND date >= date('now','localtime','-13 days') "
        "AND date < date('now','localtime','-6 days') "
        "GROUP BY category",
        (wallet_id,)
    ))
    income_row = _row(db.execute(
        "SELECT COALESCE(SUM(amount),0) AS total FROM transactions "
        "WHERE wallet_id=? AND type='in' AND date >= date('now','localtime','-6 days')",
        (wallet_id,)
    ))

    last_week_map = {r['category']: r['total'] for r in last_week}
    this_week_total  = sum(r['total'] for r in this_week)
    last_week_total  = sum(r['total'] for r in last_week)
    this_week_income = income_row['total']
    tips = []

    for r in this_week:
        prev = last_week_map.get(r['category'], 0)
        if prev > 0:
            diff_pct = round(((r['total'] - prev) / prev) * 100)
            if diff_pct >= 30:
                tips.append(f"📌 Minggu ini kamu boros di *{r['category']}* {diff_pct}% lebih dari minggu lalu "
                            f"({_format_rupiah(prev)} → {_format_rupiah(r['total'])})")
        elif r['jumlah'] >= 3:
            tips.append(f"📌 Pengeluaran *{r['category']}* cukup sering minggu ini "
                        f"({r['jumlah']}x, total {_format_rupiah(r['total'])})")

    if last_week_total > 0:
        diff = round(((this_week_total - last_week_total) / last_week_total) * 100)
        if diff >= 20:
            tips.append(f"⚠️ Total pengeluaran minggu ini *naik {diff}%* dibanding minggu lalu")
        elif diff <= -20:
            tips.append(f"✅ Keren! Pengeluaran minggu ini *turun {abs(diff)}%* dibanding minggu lalu")

    if this_week_income > 0:
        ratio = round((this_week_total / this_week_income) * 100)
        if ratio >= 90:
            tips.append(f"🚨 Pengeluaran minggu ini *{ratio}%* dari pemasukanmu — hampir habis!")
        elif ratio >= 70:
            tips.append(f"⚠️ Pengeluaran minggu ini sudah *{ratio}%* dari pemasukanmu")
        elif ratio <= 40 and this_week_total > 0:
            tips.append(f"💪 Pengeluaran minggu ini hanya *{ratio}%* dari pemasukan — nabungnya bagus!")

    if this_week:
        top     = this_week[0]
        persen  = round((top['total'] / this_week_total) * 100) if this_week_total > 0 else 0
        if persen >= 50:
            tips.append(f"💡 *{top['category']}* menyumbang *{persen}%* dari total pengeluaranmu minggu ini")

    if not tips:
        if this_week_total == 0:
            tips.append('😮 Tidak ada pengeluaran minggu ini — atau belum dicatat?')
        else:
            tips.append('👍 Pengeluaran minggu ini terbilang normal, tidak ada yang mencolok.')

    return {
        'tips':            tips,
        'thisWeekTotal':   this_week_total,
        'lastWeekTotal':   last_week_total,
        'thisWeekIncome':  this_week_income,
        'byCategory':      this_week,
    }


def get_analisis(wallet_id: str) -> dict:
    db = get_db()
    now       = datetime.now()
    bulan_ini = now.strftime('%Y-%m')
    # Bulan lalu
    if now.month == 1:
        prev = datetime(now.year - 1, 12, 1)
    else:
        prev = datetime(now.year, now.month - 1, 1)
    bulan_lalu = prev.strftime('%Y-%m')

    trans_ini = _rows(db.execute(
        "SELECT * FROM transactions WHERE wallet_id=? AND strftime('%Y-%m',date)=? ORDER BY date ASC",
        (wallet_id, bulan_ini)
    ))
    ringkas_lalu = _rows(db.execute(
        "SELECT type, SUM(amount) AS total FROM transactions "
        "WHERE wallet_id=? AND strftime('%Y-%m',date)=? GROUP BY type",
        (wallet_id, bulan_lalu)
    ))

    masuk_ini   = sum(t['amount'] for t in trans_ini if t['type'] == 'in')
    keluar_ini  = sum(t['amount'] for t in trans_ini if t['type'] == 'out')
    masuk_lalu  = next((r['total'] for r in ringkas_lalu if r['type'] == 'in'),  0)
    keluar_lalu = next((r['total'] for r in ringkas_lalu if r['type'] == 'out'), 0)

    per_kategori = _rows(db.execute(
        "SELECT category, SUM(amount) AS total, COUNT(*) AS jumlah "
        "FROM transactions WHERE wallet_id=? AND strftime('%Y-%m',date)=? AND type='out' "
        "GROUP BY category ORDER BY total DESC",
        (wallet_id, bulan_ini)
    ))

    savings_rate = round(((masuk_ini - keluar_ini) / masuk_ini) * 100) if masuk_ini > 0 else 0
    tren_keluar  = round(((keluar_ini - keluar_lalu) / keluar_lalu) * 100) if keluar_lalu > 0 else None

    per_hari = _row(db.execute(
        "SELECT strftime('%w',date) AS hari_minggu, SUM(amount) AS total "
        "FROM transactions WHERE wallet_id=? AND strftime('%Y-%m',date)=? AND type='out' "
        "GROUP BY hari_minggu ORDER BY total DESC LIMIT 1",
        (wallet_id, bulan_ini)
    ))
    HARI = ['Minggu', 'Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu']
    hari_boros = HARI[int(per_hari['hari_minggu'])] if per_hari else None

    hari_unik = len(set(t['date'] for t in trans_ini if t['type'] == 'out'))
    rata_hari  = round(keluar_ini / hari_unik) if hari_unik > 0 else 0

    return {
        'bulan':           bulan_ini,
        'masukIni':        masuk_ini,
        'keluarIni':       keluar_ini,
        'masukLalu':       masuk_lalu,
        'keluarLalu':      keluar_lalu,
        'savingsRate':     savings_rate,
        'trenKeluar':      tren_keluar,
        'hariBoros':       hari_boros,
        'perKategori':     per_kategori,
        'hariUnik':        hari_unik,
        'rataHari':        rata_hari,
        'jumlahTransaksi': len(trans_ini),
    }


def get_kekayaan(wallet_id: str) -> dict:
    db = get_db()
    masuk_row  = _row(db.execute("SELECT COALESCE(SUM(amount),0) AS total FROM transactions WHERE wallet_id=? AND type='in'", (wallet_id,)))
    keluar_row = _row(db.execute("SELECT COALESCE(SUM(amount),0) AS total FROM transactions WHERE wallet_id=? AND type='out'", (wallet_id,)))
    saldo = masuk_row['total'] - keluar_row['total']
    goals = _rows(db.execute('SELECT name, current_amount, target_amount, is_completed FROM goals WHERE wallet_id=?', (wallet_id,)))
    total_tabungan = sum(g['current_amount'] for g in goals)
    usd_rate = None
    try:
        row = _row(db.execute("SELECT rate_to_idr FROM live_rates WHERE code='USD'"))
        if row:
            usd_rate = row['rate_to_idr']
    except Exception:
        pass
    return {'saldo': saldo, 'totalTabungan': total_tabungan, 'totalKekayaan': saldo + total_tabungan, 'goals': goals, 'usdRate': usd_rate}


def get_laporan_trend(wallet_id: str, months: int = 6) -> list:
    months = min(max(int(months), 1), 12)
    db = get_db()
    now    = datetime.now()
    cutoff = datetime(now.year, now.month, 1) - timedelta(days=1)
    # go back (months-1) more months
    for _ in range(months - 1):
        cutoff = datetime(cutoff.year, cutoff.month, 1) - timedelta(days=1)
    cutoff_str = datetime(cutoff.year, cutoff.month, 1).strftime('%Y-%m')
    return _rows(db.execute(
        "SELECT strftime('%Y-%m',date) AS month, "
        "COALESCE(SUM(CASE WHEN type='in' THEN amount ELSE 0 END),0) AS masuk, "
        "COALESCE(SUM(CASE WHEN type='out' THEN amount ELSE 0 END),0) AS keluar "
        "FROM transactions WHERE wallet_id=? AND strftime('%Y-%m',date) >= ? "
        "GROUP BY strftime('%Y-%m',date) ORDER BY month ASC",
        (wallet_id, cutoff_str)
    ))


def get_laporan_bulan_lalu(wallet_id: str) -> dict:
    db  = get_db()
    now = datetime.now()
    if now.month == 1:
        y, m = now.year - 1, 12
    else:
        y, m = now.year, now.month - 1
    month_str    = f'{y}-{m:02d}'
    transactions = _rows(db.execute(
        "SELECT * FROM transactions WHERE wallet_id=? AND strftime('%Y-%m',date)=? "
        "ORDER BY date DESC, created_at DESC",
        (wallet_id, month_str)
    ))
    masuk  = sum(t['amount'] for t in transactions if t['type'] == 'in')
    keluar = sum(t['amount'] for t in transactions if t['type'] == 'out')
    return {
        'transactions': transactions,
        'monthStr':     month_str,
        'summary': {
            'total_masuk':      masuk,
            'total_keluar':     keluar,
            'selisih':          masuk - keluar,
            'jumlah_transaksi': len(transactions),
        },
    }


def get_laporan_minggu_lalu(wallet_id: str) -> dict:
    db  = get_db()
    now = datetime.now()
    # day-of-week: 0=Mon, 6=Sun (Python weekday)
    day_of_week = now.weekday()  # 0=Mon
    last_monday = now - timedelta(days=day_of_week + 7)
    last_sunday = last_monday + timedelta(days=6)
    from_str = last_monday.strftime('%Y-%m-%d')
    to_str   = last_sunday.strftime('%Y-%m-%d')
    transactions = _rows(db.execute(
        'SELECT * FROM transactions WHERE wallet_id=? AND date>=? AND date<=? '
        'ORDER BY date DESC, created_at DESC',
        (wallet_id, from_str, to_str)
    ))
    masuk  = sum(t['amount'] for t in transactions if t['type'] == 'in')
    keluar = sum(t['amount'] for t in transactions if t['type'] == 'out')
    return {
        'transactions': transactions,
        'fromStr':      from_str,
        'toStr':        to_str,
        'summary': {
            'total_masuk':      masuk,
            'total_keluar':     keluar,
            'selisih':          masuk - keluar,
            'jumlah_transaksi': len(transactions),
        },
    }


def get_saldo_multi_currency(wallet_id: str) -> dict:
    base = get_saldo(wallet_id)
    db   = get_db()
    customs = _rows(db.execute(
        'SELECT code, rate_to_idr FROM currencies WHERE wallet_id=? ORDER BY code', (wallet_id,)
    ))
    rate_map = {}
    if customs:
        rate_map = {c['code']: c['rate_to_idr'] for c in customs}
    else:
        placeholders = ','.join('?' * len(DEFAULT_DISPLAY_CURRENCIES))
        live_rows = _rows(db.execute(
            f'SELECT code, rate_to_idr FROM live_rates WHERE code IN ({placeholders}) ORDER BY code',
            DEFAULT_DISPLAY_CURRENCIES
        ))
        rate_map = {r['code']: r['rate_to_idr'] for r in live_rows}
    conversions = [
        {'code': code, 'symbol': CURRENCY_SYMBOLS.get(code, code), 'value': base['saldo'] / rate}
        for code, rate in rate_map.items() if rate > 0
    ]
    return {**base, 'conversions': conversions}


def get_savings_rate(wallet_id: str) -> dict:
    db      = get_db()
    now     = datetime.now()
    month_str = now.strftime('%Y-%m')
    rows    = _rows(db.execute(
        "SELECT type, COALESCE(SUM(amount),0) AS total FROM transactions "
        "WHERE wallet_id=? AND strftime('%Y-%m',date)=? GROUP BY type",
        (wallet_id, month_str)
    ))
    masuk   = next((r['total'] for r in rows if r['type'] == 'in'),  0)
    keluar  = next((r['total'] for r in rows if r['type'] == 'out'), 0)
    tabungan = masuk - keluar
    rate    = round((tabungan / masuk) * 100) if masuk > 0 else 0

    three_months = []
    for i in range(1, 4):
        if now.month - i <= 0:
            y = now.year - 1
            m = now.month - i + 12
        else:
            y = now.year
            m = now.month - i
        ms = f'{y}-{m:02d}'
        r2 = _rows(db.execute(
            "SELECT type, COALESCE(SUM(amount),0) AS total FROM transactions "
            "WHERE wallet_id=? AND strftime('%Y-%m',date)=? GROUP BY type",
            (wallet_id, ms)
        ))
        mk = next((x['total'] for x in r2 if x['type'] == 'in'), 0)
        kk = next((x['total'] for x in r2 if x['type'] == 'out'), 0)
        if mk > 0:
            three_months.append(round(((mk - kk) / mk) * 100))
    avg_rate = round(sum(three_months) / len(three_months)) if three_months else None

    return {'rate': rate, 'masuk': masuk, 'keluar': keluar, 'tabungan': tabungan,
            'period': month_str, 'avgRate': avg_rate}


# ─── Proyeksi Akhir Bulan ──────────────────────────────────────

def get_proyeksi_bulan(wallet_id: str) -> dict:
    """
    Proyeksikan saldo akhir bulan berdasarkan rata-rata pengeluaran harian.
    Returns dict:
      hari_berlalu, hari_tersisa, hari_total,
      keluar_hari_ini, rata_keluar_harian, proyeksi_keluar_tersisa,
      masuk_bulan_ini, saldo_sekarang,
      proyeksi_saldo_akhir_bulan, is_defisit
    """
    db  = get_db()
    now = datetime.now()
    month_str = now.strftime('%Y-%m')

    import calendar
    hari_total   = calendar.monthrange(now.year, now.month)[1]
    hari_berlalu = now.day
    hari_tersisa = hari_total - hari_berlalu

    rows = _rows(db.execute(
        "SELECT type, COALESCE(SUM(amount),0) AS total FROM transactions "
        "WHERE wallet_id=? AND strftime('%Y-%m',date)=? GROUP BY type",
        (wallet_id, month_str)
    ))
    masuk  = next((r['total'] for r in rows if r['type'] == 'in'), 0)
    keluar = next((r['total'] for r in rows if r['type'] == 'out'), 0)
    saldo_sekarang = masuk - keluar

    # Pengeluaran harian rata-rata (hanya hari yang sudah berlalu)
    rata_keluar_harian = keluar / hari_berlalu if hari_berlalu > 0 else 0

    # Pengeluaran hari ini saja
    keluar_hari_ini_row = _row(db.execute(
        "SELECT COALESCE(SUM(amount),0) AS total FROM transactions "
        "WHERE wallet_id=? AND type='out' AND date=date('now','localtime')",
        (wallet_id,)
    ))
    keluar_hari_ini = keluar_hari_ini_row['total'] if keluar_hari_ini_row else 0

    proyeksi_keluar_tersisa = rata_keluar_harian * hari_tersisa
    proyeksi_saldo_akhir    = saldo_sekarang - proyeksi_keluar_tersisa

    return {
        'hari_berlalu':              hari_berlalu,
        'hari_tersisa':              hari_tersisa,
        'hari_total':                hari_total,
        'keluar_hari_ini':           keluar_hari_ini,
        'rata_keluar_harian':        round(rata_keluar_harian),
        'proyeksi_keluar_tersisa':   round(proyeksi_keluar_tersisa),
        'masuk_bulan_ini':           masuk,
        'keluar_bulan_ini':          keluar,
        'saldo_sekarang':            saldo_sekarang,
        'proyeksi_saldo_akhir_bulan': round(proyeksi_saldo_akhir),
        'is_defisit':                proyeksi_saldo_akhir < 0,
    }


# ─── Export ───────────────────────────────────────────────────

def get_export_data(wallet_id: str, month_str: Optional[str] = None) -> list:
    db    = get_db()
    month = month_str or datetime.now().strftime('%Y-%m')
    return _rows(db.execute(
        "SELECT id,date,type,amount,category,note,created_by,created_at "
        "FROM transactions WHERE wallet_id=? AND strftime('%Y-%m',date)=? "
        "ORDER BY date ASC, created_at ASC",
        (wallet_id, month)
    ))


def generate_csv(rows: list) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Tanggal', 'Tipe', 'Jumlah', 'Kategori', 'Catatan', 'Dicatat Oleh'])
    for r in rows:
        tipe = 'Pemasukan' if r['type'] == 'in' else 'Pengeluaran'
        writer.writerow([r['id'], r['date'], tipe, r['amount'], r['category'],
                         r.get('note', ''), r.get('created_by', '')])
    return output.getvalue()


# ─── Multi-Currency Live Rates ────────────────────────────────

def fetch_live_rates() -> dict:
    rates = None
    apis = [
        ('https://api.exchangerate-api.com/v4/latest/USD',       lambda d: d.get('rates')),
        ('https://open.exchangerate-api.com/v6/latest/USD',       lambda d: d.get('conversion_rates')),
        ('https://api.frankfurter.dev/v1/latest?base=USD',        lambda d: d.get('rates')),
    ]
    for url, extractor in apis:
        try:
            resp = requests.get(url, timeout=8)
            if resp.ok:
                data = resp.json()
                r = extractor(data)
                if r and r.get('IDR'):
                    rates = r
                    break
        except Exception:
            continue

    if not rates or not rates.get('IDR'):
        raise RuntimeError('Semua API kurs gagal — cek koneksi internet')

    idr_per_usd = rates['IDR']
    db = get_db()
    count = 0
    for code, rate_per_usd in rates.items():
        if code == 'IDR' or rate_per_usd == 0:
            continue
        rate_to_idr = idr_per_usd / rate_per_usd
        db.execute(
            "INSERT INTO live_rates (code, rate_to_idr, updated_at) VALUES (?,?,datetime('now','localtime')) "
            "ON CONFLICT(code) DO UPDATE SET rate_to_idr=excluded.rate_to_idr, updated_at=excluded.updated_at",
            (code, rate_to_idr)
        )
        count += 1
    db.commit()
    usd_rate = round(idr_per_usd)
    print(f"[Kurs] {count} mata uang diupdate (1 USD = Rp {usd_rate:,})")
    return {'count': count, 'usdRate': usd_rate}


def get_live_rate_updated_at() -> Optional[str]:
    db  = get_db()
    row = _row(db.execute('SELECT updated_at FROM live_rates ORDER BY updated_at DESC LIMIT 1'))
    return row['updated_at'] if row else None


def set_currency(wallet_id: str, code: str, rate_to_idr: float) -> dict:
    upper = code.upper()
    import re
    if len(upper) < 2 or len(upper) > 6 or not re.match(r'^[A-Z]+$', upper):
        raise ValueError(f'Kode mata uang tidak valid: "{upper}"\nContoh yang benar: THB, USD, MYR')
    db = get_db()
    db.execute(
        "INSERT INTO currencies (wallet_id, code, rate_to_idr) VALUES (?,?,?) "
        "ON CONFLICT(wallet_id, code) DO UPDATE SET rate_to_idr=excluded.rate_to_idr, updated_at=datetime('now','localtime')",
        (wallet_id, upper, rate_to_idr)
    )
    db.commit()
    return {'code': upper, 'rateToIdr': rate_to_idr}


def get_currencies(wallet_id: str) -> list:
    db     = get_db()
    custom = _rows(db.execute('SELECT code, rate_to_idr, updated_at FROM currencies WHERE wallet_id=?', (wallet_id,)))
    live   = _rows(db.execute('SELECT code, rate_to_idr, updated_at FROM live_rates ORDER BY code'))
    custom_map = {r['code'] for r in custom}
    merged = [{**r, 'is_custom': True} for r in custom] + \
             [{**r, 'is_custom': False} for r in live if r['code'] not in custom_map]
    return merged


def convert_to_idr(wallet_id: str, amount: float, currency_code: str) -> int:
    upper = currency_code.upper()
    if upper == 'IDR':
        return int(round(amount))
    db = get_db()
    row = _row(db.execute('SELECT rate_to_idr FROM currencies WHERE wallet_id=? AND code=?', (wallet_id, upper)))
    if row:
        return int(round(amount * row['rate_to_idr']))
    row = _row(db.execute('SELECT rate_to_idr FROM live_rates WHERE code=?', (upper,)))
    if row:
        return int(round(amount * row['rate_to_idr']))
    rate = DEFAULT_RATES.get(upper)
    if rate:
        return int(round(amount * rate))
    raise ValueError(f'Kurs {upper} tidak tersedia.\nCoba: /kurs update untuk refresh, atau /kurs set {upper} [nilai ke IDR]')


# ─── Wishlist ─────────────────────────────────────────────────

def add_wishlist(wallet_id: str, name: str, price: float) -> int:
    db  = get_db()
    cur = db.execute('INSERT INTO wishlists (wallet_id, name, price) VALUES (?,?,?)', (wallet_id, name, price))
    db.commit()
    return cur.lastrowid


def get_wishlists(wallet_id: str) -> list:
    db = get_db()
    return _rows(db.execute('SELECT * FROM wishlists WHERE wallet_id=? ORDER BY price ASC', (wallet_id,)))


def delete_wishlist(wallet_id: str, id_: int) -> bool:
    db  = get_db()
    cur = db.execute('DELETE FROM wishlists WHERE id=? AND wallet_id=?', (id_, wallet_id))
    db.commit()
    return cur.rowcount > 0


def get_wishlist_projection(wallet_id: str) -> dict:
    sr = get_savings_rate(wallet_id)
    items = get_wishlists(wallet_id)
    savings_per_month = max(0, sr['tabungan']) if sr['masuk'] > 0 else 0
    result_items = []
    for w in items:
        months = -(-w['price'] // savings_per_month) if savings_per_month > 0 else None  # ceiling div
        result_items.append({**w, 'monthsNeeded': int(months) if months is not None else None})
    return {'items': result_items, 'savingsPerMonth': savings_per_month, 'savingsRate': sr['rate']}


# ─── Bank Accounts ────────────────────────────────────────────

BANK_COLORS = {
    'ocbc':    '#e63946', 'mandiri': '#003087', 'jago':    '#ff6b35',
    'bca':     '#0072ce', 'bni':     '#f97316', 'bri':     '#1a6b3c',
    'gopay':   '#00b4d8', 'ovo':     '#7b2d8b', 'dana':    '#118ab2',
    'default': '#6b7280',
}

BANK_ICONS = {
    'ocbc': '🏦', 'mandiri': '🏛️', 'jago': '🦊', 'bca': '🏦',
    'bni': '🏦', 'bri': '🌾', 'gopay': '🟢', 'ovo': '💜',
    'dana': '🔵', 'default': '🏦',
}


def _bank_color(name: str) -> str:
    lower = name.lower()
    for key, color in BANK_COLORS.items():
        if key != 'default' and key in lower:
            return color
    return BANK_COLORS['default']


def _bank_icon(name: str) -> str:
    lower = name.lower()
    for key, icon in BANK_ICONS.items():
        if key != 'default' and key in lower:
            return icon
    return BANK_ICONS['default']


def add_bank_account(wallet_id: str, name: str, initial_balance: float = 0.0) -> dict:
    db = get_db()
    color = _bank_color(name)
    cur = db.execute(
        'INSERT INTO bank_accounts (wallet_id, name, initial_balance, color) VALUES (?,?,?,?)',
        (wallet_id, name.strip(), initial_balance, color)
    )
    db.commit()
    return _row(db.execute('SELECT * FROM bank_accounts WHERE id=?', (cur.lastrowid,)))


def get_bank_accounts(wallet_id: str) -> list:
    db = get_db()
    banks = _rows(db.execute(
        'SELECT * FROM bank_accounts WHERE wallet_id=? ORDER BY created_at ASC',
        (wallet_id,)
    ))
    result = []
    for b in banks:
        masuk_row = _row(db.execute(
            "SELECT COALESCE(SUM(amount),0) AS total FROM transactions "
            "WHERE wallet_id=? AND bank_id=? AND type='in'",
            (wallet_id, b['id'])
        ))
        keluar_row = _row(db.execute(
            "SELECT COALESCE(SUM(amount),0) AS total FROM transactions "
            "WHERE wallet_id=? AND bank_id=? AND type='out'",
            (wallet_id, b['id'])
        ))
        masuk  = masuk_row['total'] if masuk_row else 0
        keluar = keluar_row['total'] if keluar_row else 0
        saldo  = b['initial_balance'] + masuk - keluar
        result.append({
            **b,
            'total_masuk':  masuk,
            'total_keluar': keluar,
            'saldo':        saldo,
            'icon':         _bank_icon(b['name']),
        })
    return result


def get_bank_summary(wallet_id: str) -> dict:
    banks = get_bank_accounts(wallet_id)
    total_saldo = sum(b['saldo'] for b in banks)
    return {'banks': banks, 'total_saldo': total_saldo, 'count': len(banks)}


def set_transaction_bank(wallet_id: str, transaction_id: int, bank_id: Optional[int]) -> dict:
    db = get_db()
    trx = _row(db.execute(
        'SELECT * FROM transactions WHERE id=? AND wallet_id=?', (transaction_id, wallet_id)
    ))
    if not trx:
        raise ValueError(f'Transaksi #{transaction_id} tidak ditemukan.')
    if bank_id is not None:
        bank = _row(db.execute(
            'SELECT * FROM bank_accounts WHERE id=? AND wallet_id=?', (bank_id, wallet_id)
        ))
        if not bank:
            raise ValueError(f'Bank #{bank_id} tidak ditemukan.')
    db.execute('UPDATE transactions SET bank_id=? WHERE id=?', (bank_id, transaction_id))
    db.commit()
    return _row(db.execute('SELECT * FROM transactions WHERE id=?', (transaction_id,)))


def delete_bank_account(wallet_id: str, bank_id: int) -> dict:
    db = get_db()
    bank = _row(db.execute(
        'SELECT * FROM bank_accounts WHERE id=? AND wallet_id=?', (bank_id, wallet_id)
    ))
    if not bank:
        raise ValueError(f'Bank #{bank_id} tidak ditemukan.')
    db.execute('UPDATE transactions SET bank_id=NULL WHERE bank_id=? AND wallet_id=?', (bank_id, wallet_id))
    db.execute('DELETE FROM bank_accounts WHERE id=?', (bank_id,))
    db.commit()
    return bank


def edit_bank_account(wallet_id: str, bank_id: int,
                      name: Optional[str] = None,
                      initial_balance: Optional[float] = None) -> dict:
    db = get_db()
    bank = _row(db.execute(
        'SELECT * FROM bank_accounts WHERE id=? AND wallet_id=?', (bank_id, wallet_id)
    ))
    if not bank:
        raise ValueError(f'Bank #{bank_id} tidak ditemukan.')
    new_name    = name.strip()  if name            is not None else bank['name']
    new_balance = initial_balance if initial_balance is not None else bank['initial_balance']
    new_color   = _bank_color(new_name)
    db.execute(
        'UPDATE bank_accounts SET name=?, initial_balance=?, color=? WHERE id=?',
        (new_name, new_balance, new_color, bank_id)
    )
    db.commit()
    return _row(db.execute('SELECT * FROM bank_accounts WHERE id=?', (bank_id,)))


def find_bank_by_name(wallet_id: str, query: str) -> Optional[dict]:
    """
    Fuzzy search bank by name.
    Priority: exact match → starts with → contains.
    Returns the bank dict (with icon) atau None.
    """
    banks = get_bank_accounts(wallet_id)
    q = query.lower().strip()
    if not q or not banks:
        return None

    # 1. Exact match
    for b in banks:
        if b['name'].lower() == q:
            return b
    # 2. Starts with
    for b in banks:
        if b['name'].lower().startswith(q) or q.startswith(b['name'].lower()):
            return b
    # 3. Contains
    for b in banks:
        if q in b['name'].lower() or b['name'].lower() in q:
            return b
    return None


def transfer_bank(
    wallet_id: str,
    from_bank_id: int,
    to_bank_id: int,
    amount: float,
    note: str = '',
    created_by: str = 'bot',
) -> dict:
    """
    Transfer saldo antar rekening bank.
    Membuat 2 transaksi: out dari rekening asal, in ke rekening tujuan.
    Returns dict dengan info transfer.
    Raises ValueError jika bank tidak ditemukan atau ID sama.
    """
    if from_bank_id == to_bank_id:
        raise ValueError('Rekening asal dan tujuan tidak boleh sama.')

    db = get_db()
    from_bank = _row(db.execute(
        'SELECT * FROM bank_accounts WHERE id = ? AND wallet_id = ?',
        (from_bank_id, wallet_id)
    ))
    to_bank = _row(db.execute(
        'SELECT * FROM bank_accounts WHERE id = ? AND wallet_id = ?',
        (to_bank_id, wallet_id)
    ))
    if not from_bank:
        raise ValueError(f'Rekening asal #{from_bank_id} tidak ditemukan.')
    if not to_bank:
        raise ValueError(f'Rekening tujuan #{to_bank_id} tidak ditemukan.')

    note_out = note or f'Transfer ke {to_bank["name"]}'
    note_in  = note or f'Transfer dari {from_bank["name"]}'

    # Transaksi keluar dari rekening asal
    trx_out = add_transaction(wallet_id, 'out', amount, note_out, 'transfer', created_by)
    set_transaction_bank(wallet_id, trx_out['id'], from_bank_id)

    # Transaksi masuk ke rekening tujuan
    trx_in = add_transaction(wallet_id, 'in', amount, note_in, 'transfer', created_by)
    set_transaction_bank(wallet_id, trx_in['id'], to_bank_id)

    return {
        'from_bank':  dict(from_bank),
        'to_bank':    dict(to_bank),
        'amount':     amount,
        'note':       note,
        'trx_out_id': trx_out['id'],
        'trx_in_id':  trx_in['id'],
    }


# ─── Auto-Tabung ───────────────────────────────────────────────────────────

def set_auto_savings(wallet_id: str, goal_name: str, percentage: float) -> dict:
    """
    Set / update aturan auto-tabung: setiap pemasukan, alokasikan X% ke goal.
    percentage: 0 < pct <= 100
    Raises ValueError jika goal tidak ditemukan atau pct tidak valid.
    """
    from src.core.goals import get_goals
    if not (0 < percentage <= 100):
        raise ValueError('Persentase harus antara 1–100%.')
    goals = get_goals(wallet_id)
    matched = next((g for g in goals if g['name'].lower() == goal_name.lower()), None)
    if not matched:
        # Coba partial match
        matched = next((g for g in goals if goal_name.lower() in g['name'].lower()), None)
    if not matched:
        raise ValueError(f'Goal *{goal_name}* tidak ditemukan. Buat dulu dengan `/target buat {goal_name} <jumlah>`.')
    db = get_db()
    db.execute(
        'INSERT INTO auto_savings (wallet_id, goal_name, percentage) VALUES (?, ?, ?) '
        'ON CONFLICT(wallet_id, goal_name) DO UPDATE SET percentage=excluded.percentage',
        (wallet_id, matched['name'], percentage)
    )
    db.commit()
    return {'goal_name': matched['name'], 'percentage': percentage}


def get_auto_savings(wallet_id: str) -> list:
    """Ambil semua aturan auto-tabung untuk wallet ini."""
    db = get_db()
    return _rows(db.execute(
        'SELECT * FROM auto_savings WHERE wallet_id=? ORDER BY created_at ASC', (wallet_id,)
    ))


def delete_auto_savings(wallet_id: str, goal_name: str) -> bool:
    """Hapus aturan auto-tabung. Returns True jika berhasil dihapus."""
    db = get_db()
    cur = db.execute(
        'DELETE FROM auto_savings WHERE wallet_id=? AND goal_name LIKE ?',
        (wallet_id, f'%{goal_name}%')
    )
    db.commit()
    return cur.rowcount > 0


def apply_auto_savings(wallet_id: str, income_amount: float, created_by: str = 'bot') -> list:
    """
    Jalankan semua aturan auto-tabung setelah ada pemasukan.
    Returns list of dicts: [{'goal_name', 'amount', 'percentage'}]
    """
    from src.core.goals import add_to_goal
    rules = get_auto_savings(wallet_id)
    results = []
    for rule in rules:
        pct = rule['percentage']
        alloc = round(income_amount * pct / 100)
        if alloc <= 0:
            continue
        try:
            add_to_goal(wallet_id, rule['goal_name'], alloc)
            results.append({
                'goal_name':  rule['goal_name'],
                'amount':     alloc,
                'percentage': pct,
            })
        except Exception as e:
            print(f'[auto_savings] Gagal alokasi ke {rule["goal_name"]}: {e}')
    return results


# ─── Utang & Piutang ──────────────────────────────────────────────────────

def add_debt(wallet_id: str, type_: str, person: str, amount: float,
             note: str = '', due_date: str = None) -> dict:
    """Tambah utang (kamu yang berhutang) atau piutang (orang yang hutang ke kamu)."""
    if type_ not in ('utang', 'piutang'):
        raise ValueError('type_ harus "utang" atau "piutang"')
    db = get_db()
    cur = db.execute(
        'INSERT INTO debts (wallet_id, type, person, amount, note, due_date) VALUES (?,?,?,?,?,?)',
        (wallet_id, type_, person.strip(), amount, note.strip(), due_date)
    )
    db.commit()
    row = _row(db.execute('SELECT * FROM debts WHERE id=?', (cur.lastrowid,)))
    return dict(row)


def get_debts(wallet_id: str, type_: str = None, paid: bool = False) -> list:
    """Ambil semua debt. type_='utang'/'piutang', paid=False (aktif) / True (lunas)."""
    db = get_db()
    q = 'SELECT * FROM debts WHERE wallet_id=? AND is_paid=?'
    params = [wallet_id, 1 if paid else 0]
    if type_:
        q += ' AND type=?'
        params.append(type_)
    q += ' ORDER BY created_at DESC'
    return _rows(db.execute(q, params))


def mark_debt_paid(wallet_id: str, debt_id: int) -> dict:
    """Tandai debt sebagai lunas. Returns updated row."""
    db = get_db()
    row = _row(db.execute('SELECT * FROM debts WHERE id=? AND wallet_id=?', (debt_id, wallet_id)))
    if not row:
        raise ValueError(f'Debt #{debt_id} tidak ditemukan.')
    db.execute(
        "UPDATE debts SET is_paid=1, paid_at=datetime('now','localtime') WHERE id=?",
        (debt_id,)
    )
    db.commit()
    return _row(db.execute('SELECT * FROM debts WHERE id=?', (debt_id,)))


def delete_debt(wallet_id: str, debt_id: int) -> bool:
    db = get_db()
    cur = db.execute('DELETE FROM debts WHERE id=? AND wallet_id=?', (debt_id, wallet_id))
    db.commit()
    return cur.rowcount > 0


def find_debt_by_person(wallet_id: str, person: str, type_: str = None) -> list:
    """Cari debt by nama orang (partial, case-insensitive)."""
    all_debts = get_debts(wallet_id, type_=type_, paid=False)
    q = person.lower().strip()
    return [d for d in all_debts if q in d['person'].lower()]


# ─── Cicilan Tracker ──────────────────────────────────────────────────────

def add_installment(wallet_id: str, name: str, total_months: int,
                    monthly_amount: float, due_day: int = 1,
                    note: str = '', start_date: str = None) -> dict:
    """Tambah cicilan baru."""
    from datetime import date
    if not start_date:
        start_date = date.today().strftime('%Y-%m-%d')
    db = get_db()
    cur = db.execute(
        'INSERT INTO installments (wallet_id, name, total_months, monthly_amount, due_day, note, start_date) '
        'VALUES (?,?,?,?,?,?,?)',
        (wallet_id, name.strip(), total_months, monthly_amount, due_day, note.strip(), start_date)
    )
    db.commit()
    return _row(db.execute('SELECT * FROM installments WHERE id=?', (cur.lastrowid,)))


def get_installments(wallet_id: str, done: bool = False) -> list:
    db = get_db()
    return _rows(db.execute(
        'SELECT * FROM installments WHERE wallet_id=? AND is_done=? ORDER BY created_at DESC',
        (wallet_id, 1 if done else 0)
    ))


def pay_installment(wallet_id: str, inst_id: int) -> dict:
    """Bayar 1 bulan cicilan. Auto-catat transaksi keluar."""
    db = get_db()
    row = _row(db.execute('SELECT * FROM installments WHERE id=? AND wallet_id=?', (inst_id, wallet_id)))
    if not row:
        raise ValueError(f'Cicilan #{inst_id} tidak ditemukan.')
    if row['is_done']:
        raise ValueError(f'Cicilan "{row["name"]}" sudah lunas!')
    new_paid = row['paid_months'] + 1
    is_done = 1 if new_paid >= row['total_months'] else 0
    db.execute(
        'UPDATE installments SET paid_months=?, is_done=? WHERE id=?',
        (new_paid, is_done, inst_id)
    )
    db.commit()
    # Catat transaksi
    note = f'Cicilan {row["name"]} ({new_paid}/{row["total_months"]})'
    trx = add_transaction(wallet_id, 'out', row['monthly_amount'], note, 'cicilan', 'bot')
    return {**dict(_row(db.execute('SELECT * FROM installments WHERE id=?', (inst_id,)))),
            'trx_id': trx['id'], 'is_newly_done': bool(is_done)}


def delete_installment(wallet_id: str, inst_id: int) -> bool:
    db = get_db()
    cur = db.execute('DELETE FROM installments WHERE id=? AND wallet_id=?', (inst_id, wallet_id))
    db.commit()
    return cur.rowcount > 0


# ─── Tagihan Jatuh Tempo ──────────────────────────────────────────────────

def add_bill(wallet_id: str, name: str, due_day: int,
             amount: float = 0, note: str = '') -> dict:
    """Tambah tagihan rutin dengan tanggal jatuh tempo per bulan."""
    if not (1 <= due_day <= 31):
        raise ValueError('Tanggal jatuh tempo harus antara 1–31.')
    db = get_db()
    cur = db.execute(
        'INSERT INTO bills (wallet_id, name, due_day, amount, note) VALUES (?,?,?,?,?)',
        (wallet_id, name.strip(), due_day, amount, note.strip())
    )
    db.commit()
    return _row(db.execute('SELECT * FROM bills WHERE id=?', (cur.lastrowid,)))


def get_bills(wallet_id: str, active_only: bool = True) -> list:
    db = get_db()
    q = 'SELECT * FROM bills WHERE wallet_id=?'
    params = [wallet_id]
    if active_only:
        q += ' AND is_active=1'
    q += ' ORDER BY due_day ASC'
    return _rows(db.execute(q, params))


def delete_bill(wallet_id: str, bill_id: int) -> bool:
    db = get_db()
    cur = db.execute('DELETE FROM bills WHERE id=? AND wallet_id=?', (bill_id, wallet_id))
    db.commit()
    return cur.rowcount > 0


def get_upcoming_bills(wallet_id: str, days_ahead: int = 7) -> list:
    """Ambil tagihan yang jatuh tempo dalam N hari ke depan."""
    from datetime import date, timedelta
    today = date.today()
    bills = get_bills(wallet_id)
    upcoming = []
    for b in bills:
        day = b['due_day']
        # Tanggal jatuh tempo bulan ini
        try:
            import calendar
            last_day = calendar.monthrange(today.year, today.month)[1]
            due_this = date(today.year, today.month, min(day, last_day))
        except Exception:
            continue
        # Kalau sudah lewat, cek bulan depan
        if due_this < today:
            nm = today.month % 12 + 1
            ny = today.year + (1 if today.month == 12 else 0)
            try:
                last_day2 = calendar.monthrange(ny, nm)[1]
                due_this = date(ny, nm, min(day, last_day2))
            except Exception:
                continue
        delta = (due_this - today).days
        if 0 <= delta <= days_ahead:
            upcoming.append({**b, 'due_date': due_this.isoformat(), 'days_left': delta})
    return sorted(upcoming, key=lambda x: x['days_left'])


# ─── Laporan Perbandingan Bulan ────────────────────────────────────────────

def get_laporan_comparison(wallet_id: str) -> dict:
    """Bandingkan bulan ini vs bulan lalu."""
    from datetime import datetime
    now = datetime.now()
    bulan_ini  = now.strftime('%Y-%m')
    # Bulan lalu
    if now.month == 1:
        bulan_lalu = f'{now.year - 1}-12'
    else:
        bulan_lalu = f'{now.year}-{now.month - 1:02d}'

    db = get_db()

    def month_agg(month_str):
        rows = _rows(db.execute(
            "SELECT type, COALESCE(SUM(amount),0) AS total, COUNT(*) AS cnt "
            "FROM transactions WHERE wallet_id=? AND strftime('%Y-%m',created_at)=? GROUP BY type",
            (wallet_id, month_str)
        ))
        masuk  = next((r['total'] for r in rows if r['type'] == 'in'), 0)
        keluar = next((r['total'] for r in rows if r['type'] == 'out'), 0)
        count  = sum(r['cnt'] for r in rows)
        return {'masuk': masuk, 'keluar': keluar, 'count': count, 'selisih': masuk - keluar}

    ini  = month_agg(bulan_ini)
    lalu = month_agg(bulan_lalu)

    def pct_change(now_val, prev_val):
        if prev_val == 0:
            return None
        return round((now_val - prev_val) / prev_val * 100, 1)

    return {
        'bulan_ini':  ini,
        'bulan_lalu': lalu,
        'delta_masuk':  ini['masuk']  - lalu['masuk'],
        'delta_keluar': ini['keluar'] - lalu['keluar'],
        'pct_masuk':  pct_change(ini['masuk'],  lalu['masuk']),
        'pct_keluar': pct_change(ini['keluar'], lalu['keluar']),
        'label_ini':  bulan_ini,
        'label_lalu': bulan_lalu,
    }


# ═══════════════════════════════════════════════════════════════════════════
# FITUR MEWAH — Batch 2
# ═══════════════════════════════════════════════════════════════════════════

# ─── Financial Health Score ───────────────────────────────────────────────

def get_health_score(wallet_id: str) -> dict:
    """
    Skor kesehatan keuangan 0–100 berdasarkan:
    - Savings Rate  (30 pts) — target ≥ 20%
    - Budget Compliance (25 pts) — rata-rata % pemakaian budget
    - Goal Progress (20 pts) — rata-rata progress goals aktif
    - Debt Ratio (15 pts) — utang vs pemasukan bulan ini
    - Streak (10 pts) — konsistensi catat (min 5 hari aktif bulan ini)
    """
    from datetime import datetime
    db = get_db()
    now = datetime.now()
    bulan = now.strftime('%Y-%m')

    # ── Savings Rate ──────────────────────────────────────────────────────
    lap = get_laporan(wallet_id, 'bulan')
    masuk  = lap.get('total_masuk', 0) or 0
    keluar = lap.get('total_keluar', 0) or 0
    if masuk > 0:
        savings_rate = max(0, (masuk - keluar) / masuk * 100)
        score_savings = min(30, savings_rate / 20 * 30)
    else:
        savings_rate = 0
        score_savings = 0

    # ── Budget Compliance ─────────────────────────────────────────────────
    budgets = get_budgets(wallet_id)
    if budgets:
        compliant = sum(1 for b in budgets if b.get('persen', 0) <= 100)
        score_budget = compliant / len(budgets) * 25
        budget_pct   = compliant / len(budgets) * 100
    else:
        score_budget = 12.5   # neutral jika belum set budget
        budget_pct   = None

    # ── Goal Progress ─────────────────────────────────────────────────────
    from src.core.goals import get_goals
    goals = get_goals(wallet_id)
    active = [g for g in goals if not g.get('is_completed')]
    if active:
        avg_pct = sum(
            min(100, (g.get('current_amount', 0) / g['target_amount'] * 100))
            for g in active
        ) / len(active)
        score_goals = avg_pct / 100 * 20
    else:
        score_goals = 10    # neutral
        avg_pct     = None

    # ── Debt Ratio ────────────────────────────────────────────────────────
    debts     = get_debts(wallet_id, type_='utang')
    total_utang = sum(d['amount'] for d in debts if not d.get('is_paid'))
    if masuk > 0 and total_utang > 0:
        debt_ratio = total_utang / masuk
        score_debt = max(0, 15 - debt_ratio * 15)
    else:
        score_debt = 15
        debt_ratio = 0

    # ── Streak (hari aktif catat bulan ini) ──────────────────────────────
    rows = _rows(db.execute(
        "SELECT COUNT(DISTINCT date) as hari FROM transactions "
        "WHERE wallet_id=? AND strftime('%Y-%m', date)=?",
        (wallet_id, bulan)
    ))
    hari_aktif = rows[0]['hari'] if rows else 0
    score_streak = min(10, hari_aktif / 5 * 10)

    total = round(score_savings + score_budget + score_goals + score_debt + score_streak)
    total = max(0, min(100, total))

    if total >= 80:
        grade, emoji = 'Excellent', '🟢'
    elif total >= 60:
        grade, emoji = 'Good', '🟡'
    elif total >= 40:
        grade, emoji = 'Fair', '🟠'
    else:
        grade, emoji = 'Needs Work', '🔴'

    return {
        'score': total,
        'grade': grade,
        'emoji': emoji,
        'savings_rate':  round(savings_rate, 1),
        'budget_pct':    round(budget_pct, 1) if budget_pct is not None else None,
        'goal_avg_pct':  round(avg_pct, 1) if avg_pct is not None else None,
        'debt_ratio':    round(debt_ratio * 100, 1),
        'hari_aktif':    hari_aktif,
        'breakdown': {
            'savings':  round(score_savings, 1),
            'budget':   round(score_budget, 1),
            'goals':    round(score_goals, 1),
            'debt':     round(score_debt, 1),
            'streak':   round(score_streak, 1),
        }
    }


# ─── Dana Darurat Tracker ─────────────────────────────────────────────────

def get_dana_darurat_info(wallet_id: str) -> dict:
    """Hitung kebutuhan & status dana darurat."""
    from datetime import datetime
    db = get_db()
    # Ambil config (default 3 bulan)
    cfg = _row(db.execute('SELECT * FROM dana_darurat_config WHERE wallet_id=?', (wallet_id,)))
    months = cfg['months'] if cfg else 3

    # Rata-rata pengeluaran 3 bulan terakhir
    rows = _rows(db.execute("""
        SELECT strftime('%Y-%m', date) as bln, SUM(amount) as total
        FROM transactions WHERE wallet_id=? AND type='out'
          AND date >= date('now','-3 months')
        GROUP BY bln
    """, (wallet_id,)))
    if rows:
        avg_monthly = sum(r['total'] for r in rows) / len(rows)
    else:
        avg_monthly = 0

    target = avg_monthly * months

    # Saldo saat ini sebagai proxy dana darurat
    from src.core.goals import get_goals
    goals = get_goals(wallet_id)
    # Cari goal bertema dana darurat
    dd_keywords = ['darurat', 'emergency', 'dana darurat']
    dd_goal = next(
        (g for g in goals if any(k in g['name'].lower() for k in dd_keywords)),
        None
    )
    current = dd_goal['current_amount'] if dd_goal else get_saldo(wallet_id)['saldo']

    pct = (current / target * 100) if target > 0 else 0
    status = '✅ Aman' if pct >= 100 else ('🟡 Cukup' if pct >= 50 else '🔴 Kurang')

    # Saran tabungan bulanan (supaya tercapai dalam 12 bulan)
    sisa  = max(0, target - current)
    saran = sisa / 12 if sisa > 0 else 0

    return {
        'months':       months,
        'avg_monthly':  avg_monthly,
        'target':       target,
        'current':      current,
        'pct':          round(pct, 1),
        'status':       status,
        'sisa':         sisa,
        'saran_bulanan': saran,
        'dd_goal':      dd_goal,
    }


def set_dana_darurat_months(wallet_id: str, months: int):
    db = get_db()
    db.execute(
        'INSERT OR REPLACE INTO dana_darurat_config (wallet_id, months) VALUES (?,?)',
        (wallet_id, months)
    )
    db.commit()


# ─── Net Worth Tracker ────────────────────────────────────────────────────

def get_net_worth(wallet_id: str) -> dict:
    """Hitung net worth: aset − liabilitas."""
    from src.core.goals import get_goals

    # ── Aset ──────────────────────────────────────────────────────────────
    # 1. Saldo rekening (bank_accounts — gunakan summary)
    bank_summary = get_bank_summary(wallet_id)
    bank_total = bank_summary.get('total_saldo', 0) or 0

    # 2. Dana di goals
    goals = get_goals(wallet_id)
    goal_total = sum(g.get('current_amount', 0) or 0 for g in goals)

    # 3. Investasi (jika ada — pakai nilai beli sebagai proxy)
    db = get_db()
    inv_rows = _rows(db.execute(
        'SELECT buy_price, quantity FROM investments WHERE wallet_id=? AND is_sold=0',
        (wallet_id,)
    ))
    inv_total = sum(r['buy_price'] * r['quantity'] for r in inv_rows)

    aset_total = bank_total + goal_total + inv_total

    # ── Liabilitas ────────────────────────────────────────────────────────
    # 1. Utang belum lunas
    debts = get_debts(wallet_id, type_='utang')
    utang_total = sum(d['amount'] for d in debts if not d.get('is_paid'))

    # 2. Sisa cicilan
    insts = get_installments(wallet_id)
    cicilan_total = sum(
        (i['total_months'] - i['paid_months']) * i['monthly_amount']
        for i in insts
    )

    liabilitas_total = utang_total + cicilan_total
    net_worth = aset_total - liabilitas_total

    return {
        'net_worth':       net_worth,
        'aset': {
            'bank':       bank_total,
            'goals':      goal_total,
            'investasi':  inv_total,
            'total':      aset_total,
        },
        'liabilitas': {
            'utang':      utang_total,
            'cicilan':    cicilan_total,
            'total':      liabilitas_total,
        },
        'banks':    bank_summary.get('banks', []),
        'goals':    goals,
    }


# ─── Spending Anomaly Detection ───────────────────────────────────────────

def get_spending_anomalies(wallet_id: str, threshold: float = 0.5) -> list:
    """
    Bandingkan pengeluaran bulan ini per kategori vs rata-rata 3 bulan sebelumnya.
    Kembalikan kategori yang melebihi threshold (default 50% lebih tinggi).
    """
    from datetime import datetime
    db = get_db()
    now = datetime.now()
    bulan_ini = now.strftime('%Y-%m')

    # Hitung rata-rata 3 bulan lalu per kategori
    hist = _rows(db.execute("""
        SELECT category,
               AVG(monthly) as avg_monthly
        FROM (
            SELECT category,
                   strftime('%Y-%m', date) as mo,
                   SUM(amount) as monthly
            FROM transactions
            WHERE wallet_id=? AND type='out'
              AND date < date('now','start of month')
              AND date >= date('now','start of month','-3 months')
            GROUP BY category, mo
        )
        GROUP BY category
    """, (wallet_id,)))
    avg_by_cat = {r['category']: r['avg_monthly'] for r in hist}

    # Pengeluaran bulan ini per kategori
    this_month = _rows(db.execute("""
        SELECT category, SUM(amount) as total
        FROM transactions
        WHERE wallet_id=? AND type='out'
          AND strftime('%Y-%m', date)=?
        GROUP BY category
    """, (wallet_id, bulan_ini)))

    anomalies = []
    for row in this_month:
        cat   = row['category']
        total = row['total']
        avg   = avg_by_cat.get(cat, 0)
        if avg > 0 and total > avg * (1 + threshold):
            pct_over = (total - avg) / avg * 100
            anomalies.append({
                'category':  cat,
                'this_month': total,
                'avg_3mo':   avg,
                'pct_over':  round(pct_over, 1),
            })

    return sorted(anomalies, key=lambda x: -x['pct_over'])


# ─── Smart Budget Suggestions ─────────────────────────────────────────────

def suggest_budgets(wallet_id: str) -> list:
    """
    Sarankan budget per kategori berdasarkan rata-rata pengeluaran 3 bulan.
    Tambahkan 10% buffer di atas rata-rata.
    """
    db = get_db()
    rows = _rows(db.execute("""
        SELECT category, AVG(monthly) as avg
        FROM (
            SELECT category,
                   strftime('%Y-%m', date) as mo,
                   SUM(amount) as monthly
            FROM transactions
            WHERE wallet_id=? AND type='out'
              AND date >= date('now','start of month','-3 months')
            GROUP BY category, mo
        )
        GROUP BY category
        ORDER BY avg DESC
    """, (wallet_id,)))

    suggestions = []
    for r in rows:
        suggested = r['avg'] * 1.10   # +10% buffer
        suggestions.append({
            'category':  r['category'],
            'avg_3mo':   r['avg'],
            'suggested': suggested,
        })
    return suggestions


# ─── Import Mutasi Bank CSV ───────────────────────────────────────────────

def parse_bank_csv(content: str) -> list:
    """
    Parse berbagai format CSV mutasi bank Indonesia.
    Kembalikan list dict: {date, type, amount, note}
    Support: BCA, Mandiri, BNI, GoPay (auto-detect dari header).
    """
    import csv, io, re

    def clean_amount(s: str) -> float:
        """'1.500.000,00' atau '1,500,000.00' → float."""
        s = s.strip().replace(' ', '')
        # Deteksi format: jika ada koma sebelum 2 digit di akhir → desimal koma
        if re.search(r',\d{2}$', s):
            s = s.replace('.', '').replace(',', '.')
        else:
            s = s.replace(',', '').replace('.', '')
        try:
            return abs(float(s))
        except ValueError:
            return 0.0

    lines = [l for l in content.splitlines() if l.strip()]
    results = []

    # ── Coba detect format berdasarkan header ─────────────────────────────
    header_line = ''
    for l in lines:
        if any(kw in l.lower() for kw in ['tanggal', 'date', 'debet', 'kredit', 'nominal']):
            header_line = l.lower()
            break

    # Determine CSV dialect
    try:
        dialect = csv.Sniffer().sniff(lines[0] + '\n' + (lines[1] if len(lines) > 1 else ''))
    except Exception:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO('\n'.join(lines)), dialect=dialect)
    headers = [h.lower().strip() for h in (reader.fieldnames or [])]

    def find_col(candidates):
        for c in candidates:
            for h in headers:
                if c in h:
                    return h
        return None

    col_date   = find_col(['tanggal', 'date', 'tgl'])
    col_debet  = find_col(['debet', 'debit', 'keluar', 'db'])
    col_kredit = find_col(['kredit', 'credit', 'masuk', 'cr'])
    col_nominal= find_col(['nominal', 'amount', 'jumlah'])
    col_type   = find_col(['jenis', 'type', 'keterangan mutasi'])
    col_note   = find_col(['keterangan', 'description', 'deskripsi', 'ket', 'remark'])

    for row in reader:
        row_lower = {k.lower().strip(): v for k, v in row.items()}
        try:
            # Date
            date_raw = row_lower.get(col_date, '') if col_date else ''
            date_parsed = None
            for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%d %b %Y', '%d/%m/%y']:
                try:
                    from datetime import datetime as _dt
                    date_parsed = _dt.strptime(date_raw.strip(), fmt).strftime('%Y-%m-%d')
                    break
                except Exception:
                    continue
            if not date_parsed:
                continue

            # Amount & type
            if col_debet and col_kredit:
                debet  = clean_amount(row_lower.get(col_debet,  '0') or '0')
                kredit = clean_amount(row_lower.get(col_kredit, '0') or '0')
                if kredit > 0:
                    tx_type, amount = 'in', kredit
                elif debet > 0:
                    tx_type, amount = 'out', debet
                else:
                    continue
            elif col_nominal:
                amount = clean_amount(row_lower.get(col_nominal, '0') or '0')
                if col_type:
                    tv = row_lower.get(col_type, '').lower()
                    tx_type = 'in' if any(k in tv for k in ['kredit', 'cr', 'masuk']) else 'out'
                else:
                    continue
            else:
                continue

            if amount < 100:   # skip nominal tidak masuk akal
                continue

            note = row_lower.get(col_note, '') if col_note else ''
            note = note[:80].strip()

            results.append({
                'date':   date_parsed,
                'type':   tx_type,
                'amount': amount,
                'note':   note or ('Mutasi bank' if tx_type == 'out' else 'Transfer masuk'),
            })
        except Exception:
            continue

    return results


def import_transactions_bulk(wallet_id: str, rows: list, created_by: str = 'csv_import') -> dict:
    """Import list transaksi sekaligus. Return {'imported': n, 'skipped': n}."""
    imported = 0
    skipped  = 0
    for r in rows:
        try:
            cat = detect_category(r.get('note', ''))
            add_transaction(
                wallet_id, r['type'], r['amount'],
                r.get('note', ''), cat, created_by,
                date_override=r.get('date'),
            )
            imported += 1
        except Exception:
            skipped += 1
    return {'imported': imported, 'skipped': skipped}


# ─── Split Bill ───────────────────────────────────────────────────────────

def create_split(wallet_id: str, title: str, note: str = '') -> dict:
    db = get_db()
    cur = db.execute(
        'INSERT INTO split_bills (wallet_id, title, note) VALUES (?,?,?)',
        (wallet_id, title.strip(), note.strip())
    )
    db.commit()
    return _row(db.execute('SELECT * FROM split_bills WHERE id=?', (cur.lastrowid,)))


def add_split_item(split_id: int, person: str, amount: float) -> dict:
    db = get_db()
    cur = db.execute(
        'INSERT INTO split_items (split_id, person, amount) VALUES (?,?,?)',
        (split_id, person.strip(), amount)
    )
    # Update total split
    db.execute(
        'UPDATE split_bills SET total = (SELECT SUM(amount) FROM split_items WHERE split_id=?) WHERE id=?',
        (split_id, split_id)
    )
    db.commit()
    return _row(db.execute('SELECT * FROM split_items WHERE id=?', (cur.lastrowid,)))


def get_split(wallet_id: str, split_id: int) -> dict | None:
    db = get_db()
    s = _row(db.execute(
        'SELECT * FROM split_bills WHERE id=? AND wallet_id=?', (split_id, wallet_id)
    ))
    if not s:
        return None
    s['items'] = _rows(db.execute('SELECT * FROM split_items WHERE split_id=?', (split_id,)))
    return s


def get_splits(wallet_id: str, settled: bool = False) -> list:
    db = get_db()
    rows = _rows(db.execute(
        'SELECT * FROM split_bills WHERE wallet_id=? AND is_settled=? ORDER BY created_at DESC',
        (wallet_id, 1 if settled else 0)
    ))
    for s in rows:
        s['items'] = _rows(db.execute('SELECT * FROM split_items WHERE split_id=?', (s['id'],)))
    return rows


def mark_split_item_paid(split_id: int, person: str) -> bool:
    from datetime import datetime
    db = get_db()
    cur = db.execute(
        "UPDATE split_items SET is_paid=1, paid_at=? WHERE split_id=? AND LOWER(person)=LOWER(?)",
        (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), split_id, person)
    )
    db.commit()
    return cur.rowcount > 0


def calculate_split_settlement(split_id: int) -> list:
    """
    Hitung siapa yang perlu bayar ke siapa untuk settle bill.
    Algoritma: simplifed debt settlement.
    """
    db = get_db()
    items = _rows(db.execute('SELECT * FROM split_items WHERE split_id=?', (split_id,)))
    if not items:
        return []

    total   = sum(i['amount'] for i in items)
    n       = len(items)
    avg     = total / n

    # Net balance per orang (+ = over-bayar, - = kurang bayar)
    balances = {i['person']: i['amount'] - avg for i in items}

    # Greedy settlement
    settlements = []
    creditors = sorted([(p, b) for p, b in balances.items() if b > 0.01], key=lambda x: -x[1])
    debtors   = sorted([(p, -b) for p, b in balances.items() if b < -0.01], key=lambda x: -x[1])

    ci, di = 0, 0
    while ci < len(creditors) and di < len(debtors):
        cp, ca = list(creditors[ci])
        dp, da = list(debtors[di])
        amt = min(ca, da)
        settlements.append({'from': dp, 'to': cp, 'amount': amt})
        creditors[ci] = (cp, ca - amt)
        debtors[di]   = (dp, da - amt)
        if creditors[ci][1] < 0.01:
            ci += 1
        if debtors[di][1] < 0.01:
            di += 1

    return settlements


def settle_split(wallet_id: str, split_id: int):
    db = get_db()
    db.execute(
        'UPDATE split_bills SET is_settled=1 WHERE id=? AND wallet_id=?',
        (split_id, wallet_id)
    )
    db.commit()


# ─── Investment Tracker ───────────────────────────────────────────────────

def add_investment(wallet_id: str, name: str, ticker: str, inv_type: str,
                   buy_price: float, quantity: float, buy_date: str, note: str = '') -> dict:
    db = get_db()
    cur = db.execute(
        'INSERT INTO investments (wallet_id, name, ticker, type, buy_price, quantity, buy_date, note) '
        'VALUES (?,?,?,?,?,?,?,?)',
        (wallet_id, name, ticker.upper() if ticker else '', inv_type, buy_price, quantity, buy_date, note)
    )
    db.commit()
    return _row(db.execute('SELECT * FROM investments WHERE id=?', (cur.lastrowid,)))


def get_investments(wallet_id: str, include_sold: bool = False) -> list:
    db = get_db()
    q = 'SELECT * FROM investments WHERE wallet_id=?'
    if not include_sold:
        q += ' AND is_sold=0'
    q += ' ORDER BY created_at DESC'
    return _rows(db.execute(q, (wallet_id,)))


def sell_investment(wallet_id: str, inv_id: int, sell_price: float) -> dict:
    db = get_db()
    inv = _row(db.execute('SELECT * FROM investments WHERE id=? AND wallet_id=?', (inv_id, wallet_id)))
    if not inv:
        raise ValueError(f'Investasi #{inv_id} tidak ditemukan.')
    db.execute(
        'UPDATE investments SET is_sold=1, sell_price=? WHERE id=?',
        (sell_price, inv_id)
    )
    db.commit()
    # Catat sebagai transaksi masuk
    gain = (sell_price - inv['buy_price']) * inv['quantity']
    revenue = sell_price * inv['quantity']
    add_transaction(wallet_id, 'in', revenue, f'Jual {inv["name"]}', 'investasi', 'bot')
    return {**inv, 'sell_price': sell_price, 'gain': gain, 'revenue': revenue}


def delete_investment(wallet_id: str, inv_id: int) -> bool:
    db = get_db()
    cur = db.execute('DELETE FROM investments WHERE id=? AND wallet_id=?', (inv_id, wallet_id))
    db.commit()
    return cur.rowcount > 0


def get_portfolio_summary(wallet_id: str) -> dict:
    """Ringkasan portofolio: total modal, nilai sekarang (pakai harga beli sebagai proxy), gain/loss."""
    invs = get_investments(wallet_id)
    total_modal   = sum(i['buy_price'] * i['quantity'] for i in invs)
    # Untuk live price, kita butuh API — gunakan harga beli sebagai nilai sementara
    total_nilai   = total_modal   # placeholder sampai ada live price fetch
    total_gain    = 0
    return {
        'investments':  invs,
        'total_modal':  total_modal,
        'total_nilai':  total_nilai,
        'total_gain':   total_gain,
        'count':        len(invs),
    }


# ─── Gamifikasi — Achievement System ─────────────────────────────────────

ACHIEVEMENTS = {
    # code: (emoji, name, desc, condition_hint)
    'first_trx':       ('🎉', 'Transaksi Pertama', 'Catat transaksi pertama kamu!', ''),
    'week_streak':     ('🔥', 'Streak 7 Hari',     'Catat setiap hari selama 7 hari berturut-turut.', ''),
    'month_streak':    ('💪', 'Streak 30 Hari',    '30 hari berturut-turut mencatat keuangan.', ''),
    'saldo_1jt':       ('💰', 'Saldo 1 Juta',      'Saldo kamu mencapai Rp 1.000.000.', ''),
    'saldo_10jt':      ('💎', 'Saldo 10 Juta',     'Saldo kamu mencapai Rp 10.000.000.', ''),
    'goal_done':       ('🎯', 'Goal Tercapai',     'Selesaikan satu target tabungan.', ''),
    'budget_master':   ('📊', 'Budget Master',     'Patuhi semua budget selama sebulan penuh.', ''),
    'no_debt':         ('🕊️', 'Bebas Utang',       'Lunasi semua utang kamu.', ''),
    'savings_20':      ('🌟', 'Hemat Hero',         'Savings rate ≥ 20% selama sebulan.', ''),
    'invest_start':    ('📈', 'Investor Pemula',   'Catat investasi pertama kamu.', ''),
    'networth_pos':    ('🏆', 'Net Worth Positif', 'Net worth kamu pertama kali positif.', ''),
    'trx_100':         ('💯', '100 Transaksi',     'Catat 100 transaksi.', ''),
}


def get_achievements(wallet_id: str) -> list:
    db = get_db()
    earned = _rows(db.execute(
        'SELECT code, earned_at FROM achievements WHERE wallet_id=?', (wallet_id,)
    ))
    earned_codes = {r['code'] for r in earned}

    result = []
    for code, (emoji, name, desc, _) in ACHIEVEMENTS.items():
        result.append({
            'code':      code,
            'emoji':     emoji,
            'name':      name,
            'desc':      desc,
            'earned':    code in earned_codes,
            'earned_at': next((r['earned_at'] for r in earned if r['code'] == code), None),
        })
    return result


def _grant_achievement(wallet_id: str, code: str) -> bool:
    """Grant achievement jika belum earned. Return True jika baru."""
    if code not in ACHIEVEMENTS:
        return False
    db = get_db()
    try:
        db.execute(
            'INSERT INTO achievements (wallet_id, code) VALUES (?,?)',
            (wallet_id, code)
        )
        db.commit()
        print(f'[Achievement] {wallet_id} earned: {code}')
        return True
    except Exception:
        return False   # sudah punya


def check_and_grant_achievements(wallet_id: str) -> list:
    """
    Cek semua kondisi achievement dan grant yang memenuhi syarat.
    Return list kode achievement yang baru diperoleh.
    """
    from datetime import datetime, date
    db   = get_db()
    new_ = []

    # first_trx
    cnt = _row(db.execute('SELECT COUNT(*) as c FROM transactions WHERE wallet_id=?', (wallet_id,)))
    if cnt and cnt['c'] >= 1:
        if _grant_achievement(wallet_id, 'first_trx'): new_.append('first_trx')

    # trx_100
    if cnt and cnt['c'] >= 100:
        if _grant_achievement(wallet_id, 'trx_100'): new_.append('trx_100')

    # saldo checks
    try:
        saldo = get_saldo(wallet_id)
        if saldo >= 1_000_000:
            if _grant_achievement(wallet_id, 'saldo_1jt'): new_.append('saldo_1jt')
        if saldo >= 10_000_000:
            if _grant_achievement(wallet_id, 'saldo_10jt'): new_.append('saldo_10jt')
    except Exception:
        pass

    # savings_20 — bulan ini
    try:
        lap = get_laporan(wallet_id, 'bulan')
        masuk  = lap.get('total_masuk', 0) or 0
        keluar = lap.get('total_keluar', 0) or 0
        if masuk > 0 and (masuk - keluar) / masuk >= 0.2:
            if _grant_achievement(wallet_id, 'savings_20'): new_.append('savings_20')
    except Exception:
        pass

    # no_debt
    try:
        debts = get_debts(wallet_id, type_='utang')
        if all(d.get('is_paid') for d in debts) and debts:
            if _grant_achievement(wallet_id, 'no_debt'): new_.append('no_debt')
    except Exception:
        pass

    # invest_start
    try:
        invs = get_investments(wallet_id, include_sold=True)
        if invs:
            if _grant_achievement(wallet_id, 'invest_start'): new_.append('invest_start')
    except Exception:
        pass

    # networth_pos
    try:
        nw = get_net_worth(wallet_id)
        if nw['net_worth'] > 0:
            if _grant_achievement(wallet_id, 'networth_pos'): new_.append('networth_pos')
    except Exception:
        pass

    # streak checks — cek hari berturut-turut
    try:
        trx_dates = _rows(db.execute(
            "SELECT DISTINCT date FROM transactions WHERE wallet_id=? "
            "ORDER BY date DESC LIMIT 35",
            (wallet_id,)
        ))
        date_set = {r['date'] for r in trx_dates}
        today    = date.today()
        streak   = 0
        for i in range(35):
            d = (today - __import__('datetime').timedelta(days=i)).isoformat()
            if d in date_set:
                streak += 1
            else:
                break
        if streak >= 7:
            if _grant_achievement(wallet_id, 'week_streak'): new_.append('week_streak')
        if streak >= 30:
            if _grant_achievement(wallet_id, 'month_streak'): new_.append('month_streak')
    except Exception:
        pass

    return new_



# ─── WAVE 3 STUBS ────────────────────────────────────────────────────────────
def get_prediksi_saldo(wallet_id):
    return {"saldo_sekarang":0,"saldo_prediksi":0,"warning":False,"sisa_hari":0,
            "rate_keluar_harian":0,"proyeksi_keluar":0,"proyeksi_masuk":0,
            "pending_masuk":0,"pending_keluar":0}

def add_subscription(*a, **kw): return {"error": "Fitur belum tersedia"}
def get_subscriptions(wallet_id): return []
def delete_subscription(*a, **kw): return False
def toggle_subscription(*a, **kw): return {}
def get_upcoming_subscriptions(*a, **kw): return []
def get_subscription_summary(w):
    return {"total_bulanan":0,"total_tahunan":0,"by_category":{},"subscriptions":[]}

CHALLENGE_TYPES = {
    "52week": {"label":"52 Minggu","desc":"Menabung mingguan","total_steps":52,"base_amount":10000},
    "30day":  {"label":"30 Hari","desc":"Menabung harian","total_steps":30,"base_amount":10000},
    "nospend":{"label":"No-Spend Week","desc":"Tidak belanja","total_steps":7,"base_amount":0},
}
def create_challenge(*a, **kw): return {"error": "Fitur belum tersedia"}
def get_active_challenge(w): return None
def advance_challenge(w): return {}
def stop_challenge(w): return False

def get_coach_tips(w): return []

def create_group_wallet(*a, **kw): return {"error": "Fitur belum tersedia"}
def get_my_groups(w): return []
def join_group_wallet(*a, **kw): return {"error": "Fitur belum tersedia"}
def get_group_members(g): return []
def get_group_transactions(*a, **kw): return []
def get_group_summary(g): return {"masuk":0,"keluar":0,"members":0,"per_member":[]}
def leave_group_wallet(*a, **kw): return False
def regen_group_invite(*a, **kw): return ""
def generate_laporan_pdf(*a, **kw): raise ImportError("Install reportlab dulu: pip install reportlab")
# ─── END WAVE 3 STUBS ─────────────────────────────────────────────────────────

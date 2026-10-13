#!/usr/bin/env python3
"""
dashboard.py — Web Dashboard untuk Bot Simpan Uang
Jalankan: python dashboard.py
Akses: http://localhost:5000

Untuk Telegram Mini App, set DASHBOARD_URL di .env ke URL publik (Railway, ngrok, dll)
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
from src.core.database import init_database, get_db, _rows, _row
from src.core.formatter import format_rupiah

try:
    from flask import Flask, request, jsonify, Response
except ImportError:
    print('❌ Flask belum diinstall. Jalankan: pip install flask')
    sys.exit(1)

app = Flask(__name__)
init_database()


# ─── HELPERS ────────────────────────────────────────────────────────────────

def _wallet_id():
    wid = request.args.get('wallet_id', '').strip()
    if wid:
        return wid
    db = get_db()
    row = _row(db.execute("SELECT id FROM wallets ORDER BY created_at ASC LIMIT 1"))
    return row['id'] if row else None


# ─── API ─────────────────────────────────────────────────────────────────────

@app.route('/api/wallets')
def api_wallets():
    db = get_db()
    rows = _rows(db.execute("SELECT id, name, platform FROM wallets ORDER BY created_at ASC"))
    return jsonify([dict(r) for r in rows])


MULTI_CURRENCIES = [
    {'code': 'IDR', 'symbol': 'Rp', 'flag': '🇮🇩', 'name': 'Rupiah',    'decimals': 0, 'rate_to_idr': 1.0},
    {'code': 'USD', 'symbol': '$',  'flag': '🇺🇸', 'name': 'US Dollar',  'decimals': 2, 'rate_to_idr': None},
    {'code': 'THB', 'symbol': '฿',  'flag': '🇹🇭', 'name': 'Baht',       'decimals': 0, 'rate_to_idr': None},
    {'code': 'KHR', 'symbol': '៛',  'flag': '🇰🇭', 'name': 'Riel',       'decimals': 0, 'rate_to_idr': None},
]

def _get_rates(db):
    """Ambil rate live dari DB untuk MULTI_CURRENCIES."""
    rates = {}
    for c in MULTI_CURRENCIES:
        if c['code'] == 'IDR':
            rates['IDR'] = 1.0
            continue
        row = _row(db.execute(
            "SELECT rate_to_idr FROM live_rates WHERE code=? LIMIT 1", (c['code'],)))
        if not row:
            # fallback: cek custom rates wallet
            row = _row(db.execute(
                "SELECT rate_to_idr FROM currencies WHERE code=? LIMIT 1", (c['code'],)))
        rates[c['code']] = row['rate_to_idr'] if row else None
    return rates

def _convert(idr_amount: float, rate_to_idr) -> float | None:
    """Konversi IDR ke mata uang lain."""
    if not rate_to_idr or rate_to_idr == 0:
        return None
    return idr_amount / rate_to_idr

def _fmt_currency(amount, code: str, decimals: int, symbol: str) -> str:
    if amount is None:
        return '—'
    if decimals == 0:
        return f'{symbol}{round(amount):,}'
    return f'{symbol}{amount:,.{decimals}f}'


@app.route('/api/rates')
def api_rates():
    """Kembalikan rates multi-kurs untuk frontend."""
    db = get_db()
    rates = _get_rates(db)
    result = []
    for c in MULTI_CURRENCIES:
        r = dict(c)
        r['rate_to_idr'] = rates.get(c['code'])
        result.append(r)
    return jsonify(result)


@app.route('/api/dashboard')
def api_dashboard():
    from datetime import datetime
    wid = _wallet_id()
    if not wid:
        return jsonify({'error': 'No wallet'}), 404
    db = get_db()

    today = datetime.now().strftime('%Y-%m-%d')
    bulan = datetime.now().strftime('%Y-%m')

    saldo_row = _row(db.execute(
        "SELECT COALESCE(SUM(CASE WHEN type='in' THEN amount ELSE -amount END),0) as v "
        "FROM transactions WHERE wallet_id=?", (wid,)))
    saldo = saldo_row['v'] if saldo_row else 0

    def day_agg(type_):
        r = _row(db.execute(
            "SELECT COALESCE(SUM(amount),0) as v FROM transactions "
            "WHERE wallet_id=? AND type=? AND date(created_at)=?", (wid, type_, today)))
        return r['v'] if r else 0

    def month_agg(type_):
        r = _row(db.execute(
            "SELECT COALESCE(SUM(amount),0) as v FROM transactions "
            "WHERE wallet_id=? AND type=? AND strftime('%Y-%m',created_at)=?", (wid, type_, bulan)))
        return r['v'] if r else 0

    masuk_hari = day_agg('in')
    keluar_hari = day_agg('out')
    masuk_bulan = month_agg('in')
    keluar_bulan = month_agg('out')
    savings_rate = round((masuk_bulan - keluar_bulan) / masuk_bulan * 100) if masuk_bulan else 0

    goals_count = _row(db.execute(
        "SELECT COUNT(*) as c FROM goals WHERE wallet_id=? AND is_completed=0", (wid,)))

    recent = _rows(db.execute(
        "SELECT id,type,amount,note,category,created_at FROM transactions "
        "WHERE wallet_id=? ORDER BY created_at DESC LIMIT 10", (wid,)))

    cats = _rows(db.execute(
        "SELECT category, SUM(amount) as total FROM transactions "
        "WHERE wallet_id=? AND type='out' AND strftime('%Y-%m',created_at)=? "
        "GROUP BY category ORDER BY total DESC LIMIT 8", (wid, bulan)))

    trend = _rows(db.execute(
        "SELECT strftime('%Y-%m',created_at) as month,"
        " SUM(CASE WHEN type='in' THEN amount ELSE 0 END) as masuk,"
        " SUM(CASE WHEN type='out' THEN amount ELSE 0 END) as keluar"
        " FROM transactions WHERE wallet_id=? AND created_at>=date('now','-6 months')"
        " GROUP BY month ORDER BY month ASC", (wid,)))

    wallet_info = _row(db.execute("SELECT name FROM wallets WHERE id=?", (wid,)))

    # Bank summary — hitung DULU supaya bisa dipakai di multi-kurs juga
    from src.core.finance import get_bank_accounts, get_proyeksi_bulan
    from src.core.database import resolve_wallet_id
    primary_id = resolve_wallet_id(wid)
    banks_raw = get_bank_accounts(primary_id)
    bank_summary = [{
        'id':        b['id'],
        'name':      b['name'],
        'icon':      b.get('icon', '🏦'),
        'color':     b.get('color', '#6b7280'),
        'saldo':     b['saldo'],
        'saldo_fmt': format_rupiah(b['saldo']),
        'masuk_fmt': format_rupiah(b['total_masuk']),
        'keluar_fmt': format_rupiah(b['total_keluar']),
    } for b in banks_raw]
    total_bank = sum(b['saldo'] for b in banks_raw)

    # Saldo utama = total bank (kalau ada rekening), fallback ke saldo transaksi
    main_saldo = total_bank if banks_raw else saldo

    # Multi-currency conversion — pakai main_saldo biar konsisten dengan Total Saldo di atas
    rates = _get_rates(db)
    multi_kurs = []
    for c in MULTI_CURRENCIES:
        rate = rates.get(c['code'])
        multi_kurs.append({
            'code': c['code'], 'symbol': c['symbol'],
            'flag': c['flag'], 'name': c['name'],
            'decimals': c['decimals'],
            'rate_to_idr': rate,
            'saldo': _convert(main_saldo, rate) if c['code'] != 'IDR' else main_saldo,
            'saldo_fmt': _fmt_currency(_convert(main_saldo, rate) if c['code'] != 'IDR' else main_saldo, c['code'], c['decimals'], c['symbol']),
            'masuk_bulan': _convert(masuk_bulan, rate) if c['code'] != 'IDR' else masuk_bulan,
            'masuk_bulan_fmt': _fmt_currency(_convert(masuk_bulan, rate) if c['code'] != 'IDR' else masuk_bulan, c['code'], c['decimals'], c['symbol']),
            'keluar_bulan': _convert(keluar_bulan, rate) if c['code'] != 'IDR' else keluar_bulan,
            'keluar_bulan_fmt': _fmt_currency(_convert(keluar_bulan, rate) if c['code'] != 'IDR' else keluar_bulan, c['code'], c['decimals'], c['symbol']),
        })

    # Forecast akhir bulan
    try:
        proj = get_proyeksi_bulan(wid)
    except Exception:
        proj = None

    return jsonify({
        'wallet_name': wallet_info['name'] if wallet_info else wid,
        'saldo': saldo, 'saldo_fmt': format_rupiah(saldo),
        'main_saldo': main_saldo, 'main_saldo_fmt': format_rupiah(main_saldo),
        'masuk_hari': masuk_hari, 'masuk_hari_fmt': format_rupiah(masuk_hari),
        'keluar_hari': keluar_hari, 'keluar_hari_fmt': format_rupiah(keluar_hari),
        'masuk_bulan': masuk_bulan, 'masuk_bulan_fmt': format_rupiah(masuk_bulan),
        'keluar_bulan': keluar_bulan, 'keluar_bulan_fmt': format_rupiah(keluar_bulan),
        'savings_rate': savings_rate,
        'goals_count': goals_count['c'] if goals_count else 0,
        'recent': [dict(r) for r in recent],
        'cats': [dict(c) for c in cats],
        'trend': [dict(t) for t in trend],
        'multi_kurs': multi_kurs,
        'banks': bank_summary,
        'bank_total_fmt': format_rupiah(total_bank),
        'bank_count': len(bank_summary),
        'forecast': {
            'estimasi_keluar': proj.get('proyeksi_keluar_tersisa', 0),
            'estimasi_keluar_fmt': format_rupiah(proj.get('proyeksi_keluar_tersisa', 0)),
            'estimasi_sisa': proj.get('proyeksi_saldo_akhir_bulan', 0),
            'estimasi_sisa_fmt': format_rupiah(proj.get('proyeksi_saldo_akhir_bulan', 0)),
            'hari_tersisa': proj.get('hari_tersisa', 0),
            'rata_keluar_per_hari': proj.get('rata_keluar_harian', 0),
            'rata_keluar_fmt': format_rupiah(proj.get('rata_keluar_harian', 0)),
        } if proj else None,
    })


@app.route('/api/transactions')
def api_transactions():
    wid = _wallet_id()
    if not wid:
        return jsonify([])
    limit = int(request.args.get('limit', 30))
    offset = int(request.args.get('offset', 0))
    db = get_db()
    rows = _rows(db.execute(
        "SELECT id,type,amount,note,category,created_at FROM transactions "
        "WHERE wallet_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (wid, limit, offset)))
    return jsonify([dict(r) for r in rows])


@app.route('/api/goals')
def api_goals():
    wid = _wallet_id()
    if not wid:
        return jsonify([])
    db = get_db()
    rows = _rows(db.execute(
        "SELECT * FROM goals WHERE wallet_id=? AND is_completed=0 ORDER BY created_at ASC", (wid,)))
    result = []
    for g in rows:
        gd = dict(g)
        cur = gd.get('current_amount') or 0
        tgt = gd.get('target_amount') or 1
        gd['persen'] = min(100, round(cur / tgt * 100))
        gd['current_fmt'] = format_rupiah(cur)
        gd['target_fmt'] = format_rupiah(tgt)
        result.append(gd)
    return jsonify(result)


@app.route('/api/kategori')
def api_kategori():
    from datetime import datetime
    wid = _wallet_id()
    if not wid:
        return jsonify({'keluar': [], 'masuk': []})
    db  = get_db()
    period = request.args.get('period', 'bulan')
    date_filter = {
        'hari':   "date = date('now','localtime')",
        'minggu': "date >= date('now','localtime','-6 days')",
        'bulan':  "strftime('%Y-%m',date) = strftime('%Y-%m','now','localtime')",
    }.get(period, "strftime('%Y-%m',date) = strftime('%Y-%m','now','localtime')")

    rows = _rows(db.execute(
        f"SELECT category, type, SUM(amount) AS total, COUNT(*) AS jumlah "
        f"FROM transactions WHERE wallet_id=? AND {date_filter} "
        f"GROUP BY category, type ORDER BY total DESC",
        (wid,)
    ))

    from src.core.formatter import CATEGORY_ICON, CATEGORY_COLOR
    def enrich(r):
        avg = r['total'] / r['jumlah'] if r['jumlah'] else 0
        return {
            'category':  r['category'],
            'total':     r['total'],
            'total_fmt': format_rupiah(r['total']),
            'jumlah':    r['jumlah'],
            'avg':       avg,
            'avg_fmt':   format_rupiah(avg),
            'icon':      CATEGORY_ICON.get(r['category'], '📌'),
            'color':     CATEGORY_COLOR.get(r['category'], '#6b7280'),
        }

    keluar = [enrich(r) for r in rows if r['type'] == 'out']
    masuk  = [enrich(r) for r in rows if r['type'] == 'in']
    total_k = sum(r['total'] for r in keluar)
    total_m = sum(r['total'] for r in masuk)
    for r in keluar:
        r['persen'] = round(r['total'] / total_k * 100) if total_k else 0
    for r in masuk:
        r['persen'] = round(r['total'] / total_m * 100) if total_m else 0

    return jsonify({
        'keluar':       keluar,
        'masuk':        masuk,
        'total_keluar': total_k,
        'total_masuk':  total_m,
        'total_keluar_fmt': format_rupiah(total_k),
        'total_masuk_fmt':  format_rupiah(total_m),
        'net':          total_m - total_k,
        'net_fmt':      format_rupiah(abs(total_m - total_k)),
        'savings':      round((total_m - total_k) / total_m * 100) if total_m else 0,
    })


@app.route('/api/banks')
def api_banks():
    from src.core.finance import get_bank_accounts, _bank_icon
    wid = _wallet_id()
    if not wid:
        return jsonify([])
    from src.core.database import resolve_wallet_id
    primary_id = resolve_wallet_id(wid)
    banks = get_bank_accounts(primary_id)
    result = []
    for b in banks:
        result.append({
            'id':              b['id'],
            'name':            b['name'],
            'color':           b.get('color', '#6b7280'),
            'icon':            b.get('icon', '🏦'),
            'initial_balance': b['initial_balance'],
            'initial_fmt':     format_rupiah(b['initial_balance']),
            'total_masuk':     b['total_masuk'],
            'masuk_fmt':       format_rupiah(b['total_masuk']),
            'total_keluar':    b['total_keluar'],
            'keluar_fmt':      format_rupiah(b['total_keluar']),
            'saldo':           b['saldo'],
            'saldo_fmt':       format_rupiah(b['saldo']),
        })
    return jsonify(result)


@app.route('/api/budgets')
def api_budgets():
    from datetime import datetime
    wid = _wallet_id()
    if not wid:
        return jsonify([])
    db = get_db()
    bulan = datetime.now().strftime('%Y-%m')
    budgets = _rows(db.execute("SELECT category,amount FROM budgets WHERE wallet_id=?", (wid,)))
    result = []
    for b in budgets:
        spent_r = _row(db.execute(
            "SELECT COALESCE(SUM(amount),0) as v FROM transactions "
            "WHERE wallet_id=? AND type='out' AND category=? AND strftime('%Y-%m',created_at)=?",
            (wid, b['category'], bulan)))
        spent = spent_r['v'] if spent_r else 0
        persen = min(100, round(spent / b['amount'] * 100)) if b['amount'] else 0
        result.append({
            'category': b['category'],
            'budget': b['amount'], 'budget_fmt': format_rupiah(b['amount']),
            'spent': spent, 'spent_fmt': format_rupiah(spent),
            'persen': persen,
        })
    return jsonify(result)


# ─── Cashflow Calendar ───────────────────────────────────────────────────────

@app.route('/api/calendar')
def api_calendar():
    """Return cashflow events for a given month (YYYY-MM)."""
    from datetime import datetime, date
    import calendar as cal_module
    wid = _wallet_id()
    if not wid:
        return jsonify({'events': [], 'days': {}})

    month_str = request.args.get('month', datetime.now().strftime('%Y-%m'))
    try:
        year, month = map(int, month_str.split('-'))
    except ValueError:
        return jsonify({'error': 'Invalid month format'}), 400

    db = get_db()
    days: dict = {}

    def add_event(day_key: str, event: dict):
        days.setdefault(day_key, []).append(event)

    # 1. Actual transactions that month
    trx_rows = _rows(db.execute(
        "SELECT date, type, SUM(amount) as total, category "
        "FROM transactions WHERE wallet_id=? AND strftime('%Y-%m', date)=? "
        "GROUP BY date, type, category",
        (wid, month_str)
    ))
    for r in trx_rows:
        add_event(r['date'], {
            'type': r['type'],
            'amount': r['total'],
            'category': r['category'],
            'label': ('+ ' if r['type'] == 'in' else '- ') + format_rupiah(r['total']),
            'source': 'trx',
        })

    # 2. Bills jatuh tempo in this month
    bills = _rows(db.execute(
        "SELECT name, due_day, amount FROM bills WHERE wallet_id=? AND is_active=1",
        (wid,)
    ))
    _, days_in_month = cal_module.monthrange(year, month)
    for b in bills:
        due_day = min(int(b['due_day']), days_in_month)
        day_key = f'{year:04d}-{month:02d}-{due_day:02d}'
        add_event(day_key, {
            'type': 'bill',
            'amount': b['amount'],
            'label': f'🔔 {b["name"]}' + (f' ({format_rupiah(b["amount"])})' if b['amount'] > 0 else ''),
            'source': 'bill',
        })

    # 3. Recurring transactions that month
    recurring = _rows(db.execute(
        "SELECT type, amount, note, day_of_month FROM recurring WHERE wallet_id=? AND is_active=1",
        (wid,)
    ))
    for r in recurring:
        due_day = min(int(r['day_of_month']), days_in_month)
        day_key = f'{year:04d}-{month:02d}-{due_day:02d}'
        add_event(day_key, {
            'type': r['type'],
            'amount': r['amount'],
            'label': ('🔄+ ' if r['type'] == 'in' else '🔄- ') + format_rupiah(r['amount']) + (f' ({r["note"]})' if r.get('note') else ''),
            'source': 'recurring',
        })

    # 4. Installments due this month
    installments = _rows(db.execute(
        "SELECT name, due_day, monthly_amount FROM installments WHERE wallet_id=? AND is_done=0",
        (wid,)
    ))
    for ins in installments:
        due_day = min(int(ins['due_day']), days_in_month)
        day_key = f'{year:04d}-{month:02d}-{due_day:02d}'
        add_event(day_key, {
            'type': 'out',
            'amount': ins['monthly_amount'],
            'label': f'💳 {ins["name"]} ({format_rupiah(ins["monthly_amount"])})',
            'source': 'installment',
        })

    return jsonify({'days': days, 'month': month_str, 'days_in_month': days_in_month})


@app.route('/api/subscriptions')
def api_subscriptions():
    """Return subscription summary + list."""
    wid = _wallet_id()
    if not wid:
        return jsonify({'subscriptions': [], 'total_bulanan': 0})
    try:
        from src.core.finance import get_subscription_summary
        summ = get_subscription_summary(wid)
        return jsonify({
            'subscriptions': [dict(s) for s in summ['subscriptions']],
            'total_bulanan': summ['total_bulanan'],
            'total_tahunan': summ['total_tahunan'],
            'active': summ['active'],
            'total': summ['total'],
            'by_category': summ['by_category'],
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/subscriptions/add', methods=['POST'])
def api_subscriptions_add():
    """Add a subscription via dashboard."""
    wid = _wallet_id()
    if not wid:
        return jsonify({'error': 'No wallet'}), 401
    try:
        from src.core.finance import add_subscription
        data = request.get_json() or {}
        s = add_subscription(
            wallet_id=wid,
            name=data['name'],
            amount=float(data['amount']),
            billing_day=int(data['billing_day']),
            category=data.get('category', 'hiburan'),
            currency=data.get('currency', 'IDR'),
        )
        return jsonify(dict(s))
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/subscriptions/<int:sub_id>', methods=['DELETE'])
def api_subscriptions_delete(sub_id):
    wid = _wallet_id()
    if not wid:
        return jsonify({'error': 'No wallet'}), 401
    from src.core.finance import delete_subscription
    ok = delete_subscription(wid, sub_id)
    return jsonify({'ok': ok})


@app.route('/api/prediksi')
def api_prediksi():
    """Return end-of-month balance prediction."""
    wid = _wallet_id()
    if not wid:
        return jsonify({'error': 'No wallet'}), 401
    try:
        from src.core.finance import get_prediksi_saldo
        return jsonify(get_prediksi_saldo(wid))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/coach')
def api_coach():
    """Return AI financial coach tips."""
    wid = _wallet_id()
    if not wid:
        return jsonify({'tips': []})
    try:
        from src.core.finance import get_coach_tips
        return jsonify({'tips': get_coach_tips(wid)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/challenge')
def api_challenge():
    """Return active challenge status."""
    wid = _wallet_id()
    if not wid:
        return jsonify({'challenge': None})
    try:
        from src.core.finance import get_active_challenge
        ch = get_active_challenge(wid)
        return jsonify({'challenge': dict(ch) if ch else None})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─── FRONTEND ────────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>💰 Dashboard Keuangan</title>
<script src="https://cdn.tailwindcss.com"></script>
<script>tailwind.config={darkMode:'class'}</script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
*{font-family:'Inter',sans-serif;box-sizing:border-box}
.tab-btn{padding:10px 4px;font-size:13px;border-bottom:3px solid transparent;transition:all .2s;white-space:nowrap}
.tab-btn.active{border-color:#10b981;color:#10b981;font-weight:600}
.card{transition:transform .15s,box-shadow .15s}
.card:hover{transform:translateY(-2px);box-shadow:0 4px 20px rgba(0,0,0,.08)}
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-thumb{background:#d1d5db;border-radius:3px}
.skeleton{background:linear-gradient(90deg,#f0f0f0 25%,#e0e0e0 50%,#f0f0f0 75%);background-size:200% 100%;animation:shimmer 1.5s infinite}
@keyframes shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}
.kat-period-btn{color:#6b7280;border-color:#e5e7eb;background:#fff}
.kat-period-btn.active{background:#10b981;color:#fff;border-color:#10b981}
.dark .kat-period-btn{background:#1f2937;border-color:#374151;color:#9ca3af}
.dark .kat-period-btn.active{background:#10b981;color:#fff;border-color:#10b981}
</style>
</head>
<body class="bg-gray-50 dark:bg-gray-900 text-gray-800 dark:text-gray-100 min-h-screen pb-6">

<!-- Header -->
<header class="bg-white dark:bg-gray-800 shadow-sm sticky top-0 z-20">
  <div class="max-w-3xl mx-auto px-4 py-3 flex items-center gap-3">
    <h1 class="text-base font-bold text-emerald-600 dark:text-emerald-400 flex-1">💰 Dashboard Keuangan</h1>
    <button onclick="toggleDark()" id="dark-toggle"
      class="text-lg w-8 h-8 flex items-center justify-center rounded-xl bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
      title="Toggle dark mode">🌙</button>
    <select id="walletSel" onchange="switchWallet(this.value)"
      class="text-xs border border-gray-200 dark:border-gray-600 dark:bg-gray-700 rounded-lg px-2 py-1.5 max-w-[140px] focus:outline-none focus:ring-2 focus:ring-emerald-400">
    </select>
  </div>
  <div class="max-w-3xl mx-auto px-4 flex gap-4 overflow-x-auto border-t dark:border-gray-700 scrollbar-hide">
    <button class="tab-btn active" onclick="showTab('dashboard')" id="btn-dashboard">📊 Dashboard</button>
    <button class="tab-btn" onclick="showTab('transactions')" id="btn-transactions">📋 Transaksi</button>
    <button class="tab-btn" onclick="showTab('goals')" id="btn-goals">🎯 Goals</button>
    <button class="tab-btn" onclick="showTab('budgets')" id="btn-budgets">💸 Budget</button>
    <button class="tab-btn" onclick="showTab('banks')" id="btn-banks">🏦 Bank</button>
    <button class="tab-btn" onclick="showTab('kategori')" id="btn-kategori">🗂️ Kategori</button>
    <button class="tab-btn" onclick="showTab('kalender')" id="btn-kalender">🗓️ Kalender</button>
    <button class="tab-btn" onclick="showTab('subs')" id="btn-subs">📱 Langganan</button>
    <button class="tab-btn" onclick="showTab('coach')" id="btn-coach">🤖 Coach</button>
  </div>
</header>

<main class="max-w-3xl mx-auto px-4 pt-5">

<!-- ══ DASHBOARD ══════════════════════════════════════════════════════════ -->
<div id="sec-dashboard">
  <!-- Cards -->
  <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
    <div class="card bg-white dark:bg-gray-800 rounded-2xl p-4 shadow-sm col-span-2">
      <p id="c-saldo-label" class="text-xs text-gray-400 mb-1">💰 Total Saldo</p>
      <p id="c-saldo" class="text-2xl font-bold text-emerald-600 dark:text-emerald-400">—</p>
    </div>
    <div class="card bg-white dark:bg-gray-800 rounded-2xl p-4 shadow-sm">
      <p class="text-xs text-gray-400 mb-1">📈 Masuk Hari Ini</p>
      <p id="c-masuk-hari" class="text-sm font-semibold text-green-600">—</p>
    </div>
    <div class="card bg-white dark:bg-gray-800 rounded-2xl p-4 shadow-sm">
      <p class="text-xs text-gray-400 mb-1">📉 Keluar Hari Ini</p>
      <p id="c-keluar-hari" class="text-sm font-semibold text-red-500">—</p>
    </div>
    <div class="card bg-white dark:bg-gray-800 rounded-2xl p-4 shadow-sm">
      <p class="text-xs text-gray-400 mb-1">📈 Masuk Bulan Ini</p>
      <p id="c-masuk-bln" class="text-sm font-semibold text-green-600">—</p>
    </div>
    <div class="card bg-white dark:bg-gray-800 rounded-2xl p-4 shadow-sm">
      <p class="text-xs text-gray-400 mb-1">📉 Keluar Bulan Ini</p>
      <p id="c-keluar-bln" class="text-sm font-semibold text-red-500">—</p>
    </div>
    <div class="card bg-white dark:bg-gray-800 rounded-2xl p-4 shadow-sm">
      <p class="text-xs text-gray-400 mb-1">💹 Savings Rate</p>
      <p id="c-savings" class="text-sm font-semibold text-blue-500">—</p>
    </div>
    <div class="card bg-white dark:bg-gray-800 rounded-2xl p-4 shadow-sm">
      <p class="text-xs text-gray-400 mb-1">🎯 Active Goals</p>
      <p id="c-goals" class="text-sm font-semibold text-purple-500">—</p>
    </div>
  </div>

  <!-- Bank Summary -->
  <div id="d-bank-section" class="mb-5 hidden">
    <div class="flex items-center justify-between mb-2">
      <p class="text-xs font-semibold text-gray-500 dark:text-gray-400">🏦 Rekening Bank</p>
      <div class="flex items-center gap-2">
        <span class="text-xs font-bold text-emerald-600 dark:text-emerald-400" id="d-bank-total">—</span>
        <button onclick="showTab('banks')" class="text-xs text-emerald-500 hover:underline">Lihat semua →</button>
      </div>
    </div>
    <div id="d-bank-cards" class="flex gap-3 overflow-x-auto pb-1 snap-x"></div>
  </div>

  <!-- Forecast Akhir Bulan -->
  <div id="d-forecast-section" class="mb-5 hidden">
    <p class="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2">🔮 Proyeksi Akhir Bulan</p>
    <div class="grid grid-cols-3 gap-3">
      <div class="bg-gradient-to-br from-violet-50 to-purple-50 dark:from-violet-900/20 dark:to-purple-900/20 rounded-2xl p-3 shadow-sm">
        <p class="text-[10px] text-gray-500 dark:text-gray-400 mb-1">📅 Sisa Hari</p>
        <p id="fc-hari" class="text-lg font-bold text-violet-600 dark:text-violet-400">—</p>
        <p class="text-[10px] text-gray-400">hari lagi</p>
      </div>
      <div class="bg-gradient-to-br from-red-50 to-orange-50 dark:from-red-900/20 dark:to-orange-900/20 rounded-2xl p-3 shadow-sm">
        <p class="text-[10px] text-gray-500 dark:text-gray-400 mb-1">📉 Est. Keluar</p>
        <p id="fc-keluar" class="text-sm font-bold text-red-500 leading-tight">—</p>
        <p id="fc-perhari" class="text-[10px] text-gray-400 mt-0.5">per hari: —</p>
      </div>
      <div class="bg-gradient-to-br from-emerald-50 to-green-50 dark:from-emerald-900/20 dark:to-green-900/20 rounded-2xl p-3 shadow-sm">
        <p class="text-[10px] text-gray-500 dark:text-gray-400 mb-1">💚 Est. Sisa</p>
        <p id="fc-sisa" class="text-sm font-bold text-emerald-600 dark:text-emerald-400 leading-tight">—</p>
        <p class="text-[10px] text-gray-400 mt-0.5">akhir bulan</p>
      </div>
    </div>
  </div>

  <!-- Multi-Kurs -->
  <div class="mb-5">
    <div class="flex items-center gap-2 mb-2">
      <p class="text-xs font-semibold text-gray-500 dark:text-gray-400">💱 Konversi Multi-Kurs</p>
      <span id="rate-updated" class="text-xs text-gray-400 italic"></span>
    </div>
    <div id="multi-kurs-grid" class="grid grid-cols-2 sm:grid-cols-4 gap-3"></div>
  </div>

  <!-- Charts -->
  <div class="grid grid-cols-1 gap-4 mb-5">
    <div class="bg-white dark:bg-gray-800 rounded-2xl p-4 shadow-sm">
      <p class="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-3">📊 Pengeluaran per Kategori Bulan Ini</p>
      <div id="cat-wrap" style="position:relative;min-height:180px"><canvas id="catChart"></canvas></div>
      <p id="cat-empty" class="hidden text-center text-gray-400 text-sm py-10">Belum ada data pengeluaran</p>
    </div>
    <div class="bg-white dark:bg-gray-800 rounded-2xl p-4 shadow-sm">
      <p class="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-3">📈 Trend Keuangan 6 Bulan</p>
      <div id="trend-wrap" style="position:relative;min-height:220px"><canvas id="trendChart"></canvas></div>
      <p id="trend-empty" class="hidden text-center text-gray-400 text-sm py-10">Belum ada data</p>
    </div>
  </div>

  <!-- Recent -->
  <div class="bg-white dark:bg-gray-800 rounded-2xl shadow-sm overflow-hidden">
    <div class="px-4 py-3 border-b dark:border-gray-700 flex justify-between items-center">
      <p class="text-xs font-semibold text-gray-500 dark:text-gray-400">🕐 Transaksi Terakhir</p>
      <button onclick="showTab('transactions')" class="text-xs text-emerald-500 hover:underline">Lihat semua →</button>
    </div>
    <div id="d-recent"></div>
  </div>
</div>

<!-- ══ TRANSAKSI ══════════════════════════════════════════════════════════ -->
<div id="sec-transactions" class="hidden">
  <div class="bg-white dark:bg-gray-800 rounded-2xl shadow-sm overflow-hidden">
    <div class="px-4 py-3 border-b dark:border-gray-700 flex justify-between items-center">
      <p class="text-xs font-semibold text-gray-500 dark:text-gray-400">📋 Semua Transaksi</p>
      <span id="tx-count" class="text-xs text-gray-400"></span>
    </div>
    <div id="tx-list" class="divide-y dark:divide-gray-700 overflow-y-auto" style="max-height:65vh"></div>
    <div class="p-3 text-center border-t dark:border-gray-700">
      <button id="tx-more" onclick="loadMoreTx()"
        class="text-sm text-emerald-500 hover:underline">Muat lebih banyak</button>
    </div>
  </div>
</div>

<!-- ══ GOALS ══════════════════════════════════════════════════════════════ -->
<div id="sec-goals" class="hidden space-y-3">
  <div id="goals-list"></div>
  <p id="goals-empty" class="hidden text-center text-gray-400 py-16 text-sm">
    🎯 Belum ada goals aktif.<br><br>
    Buat via bot:<br>
    <code class="bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded text-xs">/target buat Liburan 5000000</code>
  </p>
</div>

<!-- ══ BUDGET ══════════════════════════════════════════════════════════════ -->
<div id="sec-budgets" class="hidden space-y-3">
  <div id="budget-list"></div>
  <p id="budget-empty" class="hidden text-center text-gray-400 py-16 text-sm">
    💸 Belum ada budget.<br><br>
    Set via bot:<br>
    <code class="bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded text-xs">/budget makan 500000</code>
  </p>
</div>

<!-- ══ KATEGORI ════════════════════════════════════════════════════════════ -->
<div id="sec-kategori" class="hidden space-y-4">
  <!-- Period selector -->
  <div class="flex gap-2">
    <button onclick="setKatPeriod('hari')"   id="kat-btn-hari"   class="kat-period-btn flex-1 rounded-xl py-2 text-xs font-semibold border transition-colors">Hari Ini</button>
    <button onclick="setKatPeriod('minggu')" id="kat-btn-minggu" class="kat-period-btn flex-1 rounded-xl py-2 text-xs font-semibold border transition-colors">Minggu Ini</button>
    <button onclick="setKatPeriod('bulan')"  id="kat-btn-bulan"  class="kat-period-btn flex-1 rounded-xl py-2 text-xs font-semibold border transition-colors active">Bulan Ini</button>
  </div>

  <!-- Summary row -->
  <div class="grid grid-cols-3 gap-3">
    <div class="bg-green-50 dark:bg-green-900/20 rounded-2xl p-3 text-center">
      <p class="text-xs text-green-600 dark:text-green-400 mb-1">📈 Total Masuk</p>
      <p id="kat-masuk-total" class="text-sm font-bold text-green-600 dark:text-green-400">—</p>
    </div>
    <div class="bg-red-50 dark:bg-red-900/20 rounded-2xl p-3 text-center">
      <p class="text-xs text-red-500 mb-1">📉 Total Keluar</p>
      <p id="kat-keluar-total" class="text-sm font-bold text-red-500">—</p>
    </div>
    <div class="bg-blue-50 dark:bg-blue-900/20 rounded-2xl p-3 text-center">
      <p class="text-xs text-blue-500 mb-1">💹 Savings</p>
      <p id="kat-savings" class="text-sm font-bold text-blue-500">—</p>
    </div>
  </div>

  <!-- Charts row -->
  <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
    <div class="bg-white dark:bg-gray-800 rounded-2xl p-4 shadow-sm">
      <p class="text-xs font-semibold text-red-500 mb-3">📉 Pengeluaran per Kategori</p>
      <div style="position:relative;height:220px"><canvas id="katKeluarChart"></canvas></div>
      <p id="kat-keluar-empty" class="hidden text-center text-gray-400 text-xs py-6">Belum ada pengeluaran</p>
    </div>
    <div class="bg-white dark:bg-gray-800 rounded-2xl p-4 shadow-sm">
      <p class="text-xs font-semibold text-green-600 mb-3">📈 Pemasukan per Kategori</p>
      <div style="position:relative;height:220px"><canvas id="katMasukChart"></canvas></div>
      <p id="kat-masuk-empty" class="hidden text-center text-gray-400 text-xs py-6">Belum ada pemasukan</p>
    </div>
  </div>

  <!-- Expense detail cards -->
  <div>
    <p class="text-xs font-bold text-red-500 mb-2">📉 Detail Pengeluaran</p>
    <div id="kat-keluar-list" class="space-y-2"></div>
  </div>

  <!-- Income detail cards -->
  <div>
    <p class="text-xs font-bold text-green-600 mb-2">📈 Detail Pemasukan</p>
    <div id="kat-masuk-list" class="space-y-2"></div>
  </div>

  <p id="kat-empty" class="hidden text-center text-gray-400 py-12 text-sm">
    🗂️ Belum ada data kategori.<br><br>
    Mulai catat via bot:<br>
    <code class="bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded text-xs">/catat keluar 50rb makan</code>
  </p>
</div>

<!-- ══ BANK ════════════════════════════════════════════════════════════════ -->
<div id="sec-banks" class="hidden">
  <!-- Total saldo semua bank -->
  <div class="bg-gradient-to-r from-emerald-500 to-teal-600 rounded-2xl p-5 shadow-md mb-4 text-white">
    <p class="text-xs opacity-80 mb-1">💰 Total Saldo Semua Bank</p>
    <p id="bank-total" class="text-3xl font-bold tracking-tight">—</p>
    <p id="bank-count" class="text-xs opacity-70 mt-1">0 rekening</p>
  </div>
  <!-- Grid kartu bank -->
  <div id="bank-grid" class="grid grid-cols-1 sm:grid-cols-2 gap-4"></div>
  <!-- Empty state -->
  <p id="bank-empty" class="hidden text-center text-gray-400 py-16 text-sm">
    🏦 Belum ada rekening bank.<br><br>
    Tambah via bot:<br>
    <code class="bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded text-xs">/bank tambah Mandiri 1000000</code>
  </p>
</div>

<!-- ══ CASHFLOW CALENDAR ══════════════════════════════════════════════════ -->
<div id="sec-kalender" class="hidden">
  <div class="flex items-center justify-between mb-4">
    <button id="cal-prev" onclick="calNavigate(-1)" class="p-2 rounded-xl bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 transition">‹</button>
    <h2 id="cal-title" class="text-base font-bold text-gray-800 dark:text-gray-100">—</h2>
    <button id="cal-next" onclick="calNavigate(1)" class="p-2 rounded-xl bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 transition">›</button>
  </div>
  <!-- Legend -->
  <div class="flex gap-3 text-xs mb-3 flex-wrap">
    <span class="flex items-center gap-1"><span class="w-2.5 h-2.5 rounded-full bg-emerald-400 inline-block"></span> Pemasukan</span>
    <span class="flex items-center gap-1"><span class="w-2.5 h-2.5 rounded-full bg-rose-400 inline-block"></span> Pengeluaran</span>
    <span class="flex items-center gap-1"><span class="w-2.5 h-2.5 rounded-full bg-amber-400 inline-block"></span> Tagihan/Rutin</span>
  </div>
  <!-- Day headers -->
  <div class="grid grid-cols-7 text-center text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1">
    <div>Min</div><div>Sen</div><div>Sel</div><div>Rab</div><div>Kam</div><div>Jum</div><div>Sab</div>
  </div>
  <!-- Calendar grid -->
  <div id="cal-grid" class="grid grid-cols-7 gap-1"></div>
  <!-- Day detail panel -->
  <div id="cal-detail" class="hidden mt-4 bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-4">
    <h3 id="cal-detail-date" class="font-bold text-sm mb-2 text-gray-800 dark:text-gray-100"></h3>
    <div id="cal-detail-items" class="space-y-1 text-xs"></div>
  </div>
</div>

<!-- ══ SUBSCRIPTIONS ══════════════════════════════════════════════════════ -->
<div id="sec-subs" class="hidden">
  <div class="flex items-center justify-between mb-4">
    <h2 class="text-base font-bold text-gray-800 dark:text-gray-100">📱 Langganan Bulanan</h2>
    <button onclick="showSubForm()" class="px-3 py-1.5 bg-violet-500 text-white text-xs font-semibold rounded-xl hover:bg-violet-600 transition">+ Tambah</button>
  </div>

  <!-- Summary -->
  <div id="subs-summary" class="grid grid-cols-2 gap-3 mb-4"></div>

  <!-- Add form (hidden by default) -->
  <div id="sub-form" class="hidden mb-4 bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-4">
    <h3 class="font-bold text-sm mb-3 text-gray-800 dark:text-gray-100">Tambah Subscription</h3>
    <div class="space-y-2">
      <input id="sf-name" placeholder="Nama (Netflix, Spotify...)" class="w-full px-3 py-2 text-sm rounded-xl border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 dark:text-gray-100" />
      <div class="flex gap-2">
        <input id="sf-amount" type="number" placeholder="Jumlah (Rp)" class="flex-1 px-3 py-2 text-sm rounded-xl border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 dark:text-gray-100" />
        <input id="sf-day" type="number" min="1" max="28" placeholder="Tgl" class="w-20 px-3 py-2 text-sm rounded-xl border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 dark:text-gray-100" />
      </div>
      <select id="sf-cat" class="w-full px-3 py-2 text-sm rounded-xl border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 dark:text-gray-100">
        <option value="hiburan">Hiburan</option>
        <option value="tagihan">Tagihan</option>
        <option value="kesehatan">Kesehatan</option>
        <option value="pendidikan">Pendidikan</option>
        <option value="umum">Umum</option>
      </select>
      <div class="flex gap-2">
        <button onclick="submitSubForm()" class="flex-1 py-2 bg-violet-500 text-white text-sm font-semibold rounded-xl hover:bg-violet-600 transition">Simpan</button>
        <button onclick="document.getElementById('sub-form').classList.add('hidden')" class="flex-1 py-2 bg-gray-200 dark:bg-gray-600 text-gray-800 dark:text-gray-100 text-sm font-semibold rounded-xl hover:bg-gray-300 dark:hover:bg-gray-500 transition">Batal</button>
      </div>
    </div>
  </div>

  <!-- Subscription list -->
  <div id="subs-list" class="space-y-3"></div>
</div>

<!-- ══ AI COACH ═══════════════════════════════════════════════════════════ -->
<div id="sec-coach" class="hidden">
  <div class="flex items-center justify-between mb-4">
    <h2 class="text-base font-bold text-gray-800 dark:text-gray-100">🤖 Financial Coach</h2>
    <button onclick="loadCoach()" class="px-3 py-1.5 bg-blue-500 text-white text-xs font-semibold rounded-xl hover:bg-blue-600 transition">🔄 Refresh</button>
  </div>

  <!-- Prediksi saldo widget -->
  <div id="prediksi-card" class="mb-4 bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-4 hidden">
    <p class="text-xs text-gray-500 dark:text-gray-400 mb-1 font-semibold uppercase tracking-wide">Prediksi Akhir Bulan</p>
    <div class="flex items-baseline gap-2">
      <span id="prediksi-amount" class="text-2xl font-black text-gray-800 dark:text-gray-100">—</span>
      <span id="prediksi-badge" class="text-xs font-semibold px-2 py-0.5 rounded-full"></span>
    </div>
    <div class="mt-2 space-y-1 text-xs text-gray-500 dark:text-gray-400" id="prediksi-detail"></div>
  </div>

  <!-- Tips list -->
  <div id="coach-tips" class="space-y-3"></div>
</div>

</main>

<script>
// ─── INIT ─────────────────────────────────────────────────────────────────
const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready(); tg.expand();
  if (tg.colorScheme==='dark') document.documentElement.classList.add('dark');
} else {
  // Respek simpanan atau system preference
  const saved = localStorage.getItem('theme');
  if (saved === 'dark' || (!saved && window.matchMedia('(prefers-color-scheme:dark)').matches)) {
    document.documentElement.classList.add('dark');
  }
}

function toggleDark() {
  const isDark = document.documentElement.classList.toggle('dark');
  localStorage.setItem('theme', isDark ? 'dark' : 'light');
  const btn = document.getElementById('dark-toggle');
  if (btn) btn.textContent = isDark ? '☀️' : '🌙';
}
// Sinkron icon tombol setelah load
(function() {
  const isDark = document.documentElement.classList.contains('dark');
  const btn = document.getElementById('dark-toggle');
  if (btn) btn.textContent = isDark ? '☀️' : '🌙';
})();

let wid = new URLSearchParams(location.search).get('wallet_id') || '';
let txOffset = 0, catInst, trendInst;
const COLORS = ['#10b981','#3b82f6','#f59e0b','#ef4444','#8b5cf6','#ec4899','#06b6d4','#84cc16','#f97316','#14b8a6'];
const tabs = ['dashboard','transactions','goals','budgets','banks','kategori','kalender','subs','coach'];
const CURRENCY_COLORS = { IDR:'#10b981', USD:'#3b82f6', THB:'#8b5cf6', KHR:'#f59e0b' };

// ─── WALLET ───────────────────────────────────────────────────────────────
async function initWallets() {
  const r = await fetch('/api/wallets'); const ws = await r.json();
  const sel = document.getElementById('walletSel');
  sel.innerHTML = ws.map(w => `<option value="${w.id}" ${w.id===wid?'selected':''}>${w.name||w.id}</option>`).join('');
  if (!wid && ws.length) wid = ws[0].id;
  loadDashboard();
}
function switchWallet(v) { wid=v; txOffset=0; loadDashboard(); loadCurrentTab(); }

// ─── TABS ─────────────────────────────────────────────────────────────────
function showTab(name) {
  tabs.forEach(t => {
    document.getElementById(`sec-${t}`).classList.toggle('hidden', t!==name);
    document.getElementById(`btn-${t}`).classList.toggle('active', t===name);
  });
  loadCurrentTab(name);
}
function loadCurrentTab(name) {
  const active = name || tabs.find(t => !document.getElementById(`sec-${t}`).classList.contains('hidden'));
  if (active==='transactions' && txOffset===0) loadTransactions();
  if (active==='goals') loadGoals();
  if (active==='budgets') loadBudgets();
  if (active==='banks') loadBanks();
  if (active==='kategori') loadKategori();
  if (active==='kalender') initCalendar();
  if (active==='subs') loadSubs();
  if (active==='coach') loadCoach();
}

// ─── DASHBOARD ────────────────────────────────────────────────────────────
async function loadDashboard() {
  if (!wid) return;
  const r = await fetch(`/api/dashboard?wallet_id=${encodeURIComponent(wid)}`);
  const d = await r.json();
  // Total Saldo = total semua bank kalau ada rekening, fallback ke saldo transaksi
  const hasBanks = d.banks?.length > 0;
  const mainSaldo = hasBanks ? d.bank_total_fmt : d.saldo_fmt;
  setText('c-saldo', mainSaldo, 'text-2xl font-bold text-emerald-600 dark:text-emerald-400');
  const lbl = document.getElementById('c-saldo-label');
  if (lbl) lbl.textContent = hasBanks ? '🏦 Total Saldo Bank' : '💰 Total Saldo';
  setText('c-masuk-hari', d.masuk_hari_fmt);
  setText('c-keluar-hari', d.keluar_hari_fmt);
  setText('c-masuk-bln', d.masuk_bulan_fmt);
  setText('c-keluar-bln', d.keluar_bulan_fmt);
  setText('c-savings', d.savings_rate + '%');
  setText('c-goals', d.goals_count + ' goals');

  // Bank summary mini-cards
  if (d.banks?.length) {
    show('d-bank-section');
    document.getElementById('d-bank-total').textContent = d.bank_total_fmt;
    document.getElementById('d-bank-cards').innerHTML = d.banks.map(b => {
      const isNeg = b.saldo < 0;
      const saldoColor = isNeg ? 'text-red-500' : 'text-emerald-600 dark:text-emerald-400';
      return `<div class="flex-shrink-0 snap-start bg-white dark:bg-gray-800 rounded-2xl p-3 shadow-sm border-l-4 w-40" style="border-color:${b.color}">
        <div class="flex items-center gap-1 mb-2 min-w-0">
          <span class="text-base leading-none">${b.icon}</span>
          <span class="text-xs font-semibold text-gray-700 dark:text-gray-200 truncate">${b.name}</span>
        </div>
        <p class="text-sm font-bold ${saldoColor} leading-tight mb-2">${b.saldo_fmt}</p>
        <div class="space-y-0.5 border-t dark:border-gray-700 pt-2">
          <div class="flex justify-between text-[10px]">
            <span class="text-green-500">↑ Masuk</span>
            <span class="text-gray-500 dark:text-gray-400">${b.masuk_fmt}</span>
          </div>
          <div class="flex justify-between text-[10px]">
            <span class="text-red-400">↓ Keluar</span>
            <span class="text-gray-500 dark:text-gray-400">${b.keluar_fmt}</span>
          </div>
        </div>
      </div>`;
    }).join('');
  } else {
    hide('d-bank-section');
  }

  // Forecast akhir bulan
  if (d.forecast && d.forecast.hari_tersisa > 0) {
    show('d-forecast-section');
    document.getElementById('fc-hari').textContent = d.forecast.hari_tersisa;
    document.getElementById('fc-keluar').textContent = d.forecast.estimasi_keluar_fmt;
    document.getElementById('fc-perhari').textContent = 'per hari: ' + d.forecast.rata_keluar_fmt;
    const sisaEl = document.getElementById('fc-sisa');
    sisaEl.textContent = d.forecast.estimasi_sisa_fmt;
    sisaEl.className = 'text-sm font-bold leading-tight ' + (d.forecast.estimasi_sisa < 0 ? 'text-red-500' : 'text-emerald-600 dark:text-emerald-400');
  } else {
    hide('d-forecast-section');
  }

  // Multi-kurs
  if (d.multi_kurs?.length) renderMultiKurs(d.multi_kurs);

  // Charts
  if (d.cats?.length) { hide('cat-empty'); renderCat(d.cats); } else { show('cat-empty'); hide('cat-wrap'); }
  if (d.trend?.length) { hide('trend-empty'); renderTrend(d.trend); } else { show('trend-empty'); hide('trend-wrap'); }

  // Recent
  const el = document.getElementById('d-recent');
  el.innerHTML = d.recent?.length ? d.recent.map(txRow).join('') : emptyMsg('Belum ada transaksi');
}

function renderMultiKurs(items) {
  const grid = document.getElementById('multi-kurs-grid');
  grid.innerHTML = items.map(c => {
    const color = CURRENCY_COLORS[c.code] || '#6b7280';
    const hasRate = c.rate_to_idr != null || c.code === 'IDR';
    const noRate = !hasRate;
    const rateLine = c.code === 'IDR'
      ? '<span class="text-gray-400 text-[10px]">Base currency</span>'
      : (c.rate_to_idr
          ? `<span class="text-gray-400 text-[10px]">1 ${c.code} = Rp${Math.round(c.rate_to_idr).toLocaleString('id-ID')}</span>`
          : '<span class="text-amber-400 text-[10px]">⚠ Rate belum ada</span>');
    return `<div class="bg-white dark:bg-gray-800 rounded-2xl p-3 shadow-sm border-l-4" style="border-color:${color}">
      <div class="flex items-center gap-1.5 mb-2">
        <span class="text-lg">${c.flag}</span>
        <span class="text-xs font-bold" style="color:${color}">${c.code}</span>
        <span class="text-[10px] text-gray-400 ml-auto">${c.name}</span>
      </div>
      <p class="text-base font-bold text-gray-800 dark:text-gray-100 leading-tight mb-0.5">${noRate ? '—' : c.saldo_fmt}</p>
      <p class="text-[10px] text-gray-400 mb-2">💰 Saldo</p>
      <div class="border-t dark:border-gray-700 pt-2 space-y-0.5">
        <div class="flex justify-between text-[10px]">
          <span class="text-green-500">📈 Masuk</span>
          <span class="font-medium text-gray-700 dark:text-gray-300">${noRate ? '—' : c.masuk_bulan_fmt}</span>
        </div>
        <div class="flex justify-between text-[10px]">
          <span class="text-red-400">📉 Keluar</span>
          <span class="font-medium text-gray-700 dark:text-gray-300">${noRate ? '—' : c.keluar_bulan_fmt}</span>
        </div>
      </div>
      <div class="mt-2">${rateLine}</div>
    </div>`;
  }).join('');
}

function setText(id, val) { const e=document.getElementById(id); if(e) e.textContent=val; }
function hide(id) { document.getElementById(id)?.classList.add('hidden'); }
function show(id) { document.getElementById(id)?.classList.remove('hidden'); }
function emptyMsg(msg) { return `<p class="text-center text-gray-400 text-sm py-10">${msg}</p>`; }

// ─── CHARTS ──────────────────────────────────────────────────────────────
function isDark() { return document.documentElement.classList.contains('dark'); }
function chartTextColor() { return isDark() ? '#9ca3af' : '#6b7280'; }
function gridColor() { return isDark() ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)'; }
function tooltipTheme() {
  return {
    backgroundColor: isDark() ? '#1f2937' : '#ffffff',
    titleColor: isDark() ? '#d1d5db' : '#374151',
    bodyColor: isDark() ? '#e5e7eb' : '#111827',
    borderColor: isDark() ? '#374151' : '#e5e7eb',
    borderWidth: 1, padding: 12, cornerRadius: 10,
  };
}
function fmtTooltip(v) {
  if (v == null) return '—';
  const abs = Math.abs(Math.round(v));
  const sign = v < 0 ? '-' : '';
  if (abs >= 1e9) return sign + 'Rp ' + (abs/1e9).toFixed(2).replace(/\.?0+$/,'') + ' M';
  if (abs >= 1e6) return sign + 'Rp ' + (abs/1e6).toFixed(2).replace(/\.?0+$/,'') + ' jt';
  return sign + 'Rp ' + abs.toLocaleString('id-ID');
}
function fmtAxis(v) {
  if (v >= 1e9) return 'Rp'+(v/1e9).toFixed(1)+'M';
  if (v >= 1e6) return 'Rp'+(v/1e6).toFixed(1)+'jt';
  return 'Rp'+Math.round(v/1e3)+'rb';
}

function renderCat(cats) {
  if (catInst) catInst.destroy();
  const canvas = document.getElementById('catChart');
  const total = cats.reduce((s,c) => s + c.total, 0);
  const palette = COLORS.slice(0, cats.length);

  catInst = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: cats.map(c => cap(c.category||'umum')),
      datasets: [{
        data: cats.map(c => c.total),
        backgroundColor: palette.map(c => c + 'bb'),
        borderColor: palette,
        borderWidth: 2,
        borderRadius: 7,
        borderSkipped: false,
      }]
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      animation: { duration: 750, easing: 'easeOutQuart' },
      plugins: {
        legend: { display: false },
        tooltip: {
          ...tooltipTheme(),
          callbacks: {
            label: ctx => {
              const pct = total ? Math.round(ctx.raw / total * 100) : 0;
              return `  ${fmtTooltip(ctx.raw)}  (${pct}%)`;
            }
          }
        }
      },
      scales: {
        x: {
          beginAtZero: true,
          grid: { color: gridColor() },
          ticks: { color: chartTextColor(), font:{size:10}, callback: fmtAxis }
        },
        y: {
          grid: { display: false },
          ticks: { color: chartTextColor(), font:{size:11} }
        }
      }
    }
  });
}

function renderTrend(trend) {
  if (trendInst) trendInst.destroy();
  const canvas = document.getElementById('trendChart');
  const ctx = canvas.getContext('2d');

  // Gradient fills — built from the canvas height at render time
  const h = canvas.offsetHeight || 240;
  const gradIn = ctx.createLinearGradient(0, 0, 0, h);
  gradIn.addColorStop(0, 'rgba(16,185,129,0.38)');
  gradIn.addColorStop(1, 'rgba(16,185,129,0.02)');

  const gradOut = ctx.createLinearGradient(0, 0, 0, h);
  gradOut.addColorStop(0, 'rgba(239,68,68,0.32)');
  gradOut.addColorStop(1, 'rgba(239,68,68,0.02)');

  const netData = trend.map(r => r.masuk - r.keluar);

  trendInst = new Chart(canvas, {
    type: 'line',
    data: {
      labels: trend.map(r => r.month),
      datasets: [
        {
          label: '📈 Masuk',
          data: trend.map(r => r.masuk),
          borderColor: '#10b981',
          backgroundColor: gradIn,
          borderWidth: 2.5,
          tension: 0.42,
          fill: true,
          pointBackgroundColor: '#fff',
          pointBorderColor: '#10b981',
          pointBorderWidth: 2.5,
          pointRadius: 5,
          pointHoverRadius: 8,
          pointHoverBackgroundColor: '#10b981',
          pointHoverBorderColor: '#fff',
          pointHoverBorderWidth: 2,
        },
        {
          label: '📉 Keluar',
          data: trend.map(r => r.keluar),
          borderColor: '#ef4444',
          backgroundColor: gradOut,
          borderWidth: 2.5,
          tension: 0.42,
          fill: true,
          pointBackgroundColor: '#fff',
          pointBorderColor: '#ef4444',
          pointBorderWidth: 2.5,
          pointRadius: 5,
          pointHoverRadius: 8,
          pointHoverBackgroundColor: '#ef4444',
          pointHoverBorderColor: '#fff',
          pointHoverBorderWidth: 2,
        },
        {
          label: '💹 Net',
          data: netData,
          borderColor: '#6366f1',
          backgroundColor: 'transparent',
          borderWidth: 2,
          borderDash: [6, 4],
          tension: 0.42,
          fill: false,
          pointRadius: 4,
          pointHoverRadius: 7,
          pointBackgroundColor: '#6366f1',
          pointBorderColor: '#fff',
          pointBorderWidth: 2,
          pointHoverBackgroundColor: '#6366f1',
        }
      ]
    },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      animation: { duration: 900, easing: 'easeOutCubic' },
      plugins: {
        legend: {
          labels: {
            font: { size: 11 }, color: chartTextColor(),
            usePointStyle: true, pointStyleWidth: 8, padding: 14
          }
        },
        tooltip: {
          ...tooltipTheme(),
          callbacks: {
            label: ctx => `  ${ctx.dataset.label}: ${fmtTooltip(ctx.raw)}`
          }
        }
      },
      scales: {
        y: {
          beginAtZero: false,
          grid: { color: gridColor() },
          ticks: { color: chartTextColor(), font:{size:10}, callback: fmtAxis }
        },
        x: {
          grid: { display: false },
          ticks: { color: chartTextColor(), font:{size:11} }
        }
      }
    }
  });
}

// ─── TX ROW ──────────────────────────────────────────────────────────────
function txRow(tx) {
  const isIn = tx.type==='in';
  const color = isIn?'text-green-600':'text-red-500';
  const sign = isIn?'+':'-';
  const date = (tx.created_at||'').slice(0,10);
  const cat = cap(tx.category||'umum');
  const icon = catIcon(tx.category);
  return `<div class="flex items-center px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-700/40 transition-colors gap-3">
    <span class="text-xl w-8 text-center">${icon}</span>
    <div class="flex-1 min-w-0">
      <p class="text-sm font-medium truncate">${tx.note||cat}</p>
      <p class="text-xs text-gray-400">${cat} · ${date}</p>
    </div>
    <p class="text-sm font-semibold ${color} shrink-0">${sign}${fmtRp(tx.amount)}</p>
  </div>`;
}

// ─── TRANSACTIONS ─────────────────────────────────────────────────────────
async function loadTransactions(reset=true) {
  if (!wid) return;
  if (reset) { txOffset=0; document.getElementById('tx-list').innerHTML=''; }
  const r = await fetch(`/api/transactions?wallet_id=${encodeURIComponent(wid)}&limit=30&offset=${txOffset}`);
  const txs = await r.json();
  const list = document.getElementById('tx-list');
  list.innerHTML += txs.map(txRow).join('');
  document.getElementById('tx-count').textContent = `${list.children.length} transaksi`;
  document.getElementById('tx-more').style.display = txs.length<30?'none':'';
  txOffset += txs.length;
}
function loadMoreTx() { loadTransactions(false); }

// ─── GOALS ────────────────────────────────────────────────────────────────
async function loadGoals() {
  if (!wid) return;
  const r = await fetch(`/api/goals?wallet_id=${encodeURIComponent(wid)}`);
  const goals = await r.json();
  const el = document.getElementById('goals-list');
  const empty = document.getElementById('goals-empty');
  if (!goals.length) { el.innerHTML=''; show('goals-empty'); return; }
  hide('goals-empty');
  el.innerHTML = goals.map(g => {
    const pct = g.persen;
    const barColor = pct>=100?'bg-emerald-500':pct>=50?'bg-blue-500':'bg-amber-400';
    const dl = g.deadline ? `<span class="text-xs text-gray-400">📅 ${g.deadline.slice(0,10)}</span>` : '';
    return `<div class="bg-white dark:bg-gray-800 rounded-2xl p-4 shadow-sm">
      <div class="flex justify-between items-center mb-2">
        <p class="font-semibold text-sm">🎯 ${g.name}</p>${dl}
      </div>
      <div class="flex justify-between text-xs text-gray-400 mb-2">
        <span>${g.current_fmt}</span><span class="font-semibold text-gray-600 dark:text-gray-300">${pct}%</span><span>${g.target_fmt}</span>
      </div>
      <div class="h-3 rounded-full bg-gray-100 dark:bg-gray-700 overflow-hidden">
        <div class="${barColor} h-full rounded-full transition-all duration-500" style="width:${pct}%"></div>
      </div>
    </div>`;
  }).join('');
}

// ─── BUDGETS ──────────────────────────────────────────────────────────────
async function loadBudgets() {
  if (!wid) return;
  const r = await fetch(`/api/budgets?wallet_id=${encodeURIComponent(wid)}`);
  const budgets = await r.json();
  const el = document.getElementById('budget-list');
  const empty = document.getElementById('budget-empty');
  if (!budgets.length) { el.innerHTML=''; show('budget-empty'); return; }
  hide('budget-empty');
  el.innerHTML = budgets.map(b => {
    const pct = b.persen;
    const barColor = pct>=100?'bg-red-500':pct>=80?'bg-amber-400':'bg-emerald-500';
    const badge = pct>=100?'🚨 Melebihi budget':pct>=80?'⚠️ Hampir habis':'✅ Aman';
    return `<div class="bg-white dark:bg-gray-800 rounded-2xl p-4 shadow-sm">
      <div class="flex justify-between items-center mb-1">
        <p class="font-semibold text-sm">${catIcon(b.category)} ${cap(b.category)}</p>
        <span class="text-xs px-2 py-0.5 rounded-full ${pct>=100?'bg-red-100 text-red-700':pct>=80?'bg-amber-100 text-amber-700':'bg-emerald-100 text-emerald-700'}">${badge}</span>
      </div>
      <div class="flex justify-between text-xs text-gray-400 mb-2">
        <span>Terpakai: <b class="text-gray-700 dark:text-gray-300">${b.spent_fmt}</b></span>
        <span>${pct}%</span>
        <span>Budget: <b class="text-gray-700 dark:text-gray-300">${b.budget_fmt}</b></span>
      </div>
      <div class="h-3 rounded-full bg-gray-100 dark:bg-gray-700 overflow-hidden">
        <div class="${barColor} h-full rounded-full transition-all duration-500" style="width:${Math.min(pct,100)}%"></div>
      </div>
    </div>`;
  }).join('');
}

// ─── KATEGORI ─────────────────────────────────────────────────────────────
let katPeriod = 'bulan', katKeluarInst, katMasukInst;

function setKatPeriod(p) {
  katPeriod = p;
  ['hari','minggu','bulan'].forEach(x => {
    document.getElementById(`kat-btn-${x}`).classList.toggle('active', x === p);
  });
  loadKategori();
}

async function loadKategori() {
  if (!wid) return;
  const r = await fetch(`/api/kategori?wallet_id=${encodeURIComponent(wid)}&period=${katPeriod}`);
  const d = await r.json();

  document.getElementById('kat-masuk-total').textContent  = d.total_masuk_fmt  || 'Rp 0';
  document.getElementById('kat-keluar-total').textContent = d.total_keluar_fmt || 'Rp 0';
  const net = d.net || 0;
  const sEl = document.getElementById('kat-savings');
  sEl.textContent = (net >= 0 ? '+' : '') + (d.savings || 0) + '%';
  sEl.className = `text-sm font-bold ${net >= 0 ? 'text-blue-500' : 'text-red-500'}`;

  const hasData = d.keluar?.length || d.masuk?.length;
  if (!hasData) { show('kat-empty'); return; }
  hide('kat-empty');

  // ── Donut chart pengeluaran ──
  if (d.keluar?.length) {
    hide('kat-keluar-empty');
    if (katKeluarInst) katKeluarInst.destroy();
    katKeluarInst = new Chart(document.getElementById('katKeluarChart'), {
      type: 'doughnut',
      data: {
        labels: d.keluar.map(c => `${c.icon} ${cap(c.category)}`),
        datasets: [{ data: d.keluar.map(c => c.total), backgroundColor: d.keluar.map(c => c.color + 'cc'), borderColor: d.keluar.map(c => c.color), borderWidth: 2, hoverOffset: 8 }]
      },
      options: {
        responsive: true, maintainAspectRatio: false, cutout: '65%',
        animation: { duration: 800, easing: 'easeOutQuart' },
        plugins: {
          legend: { position: 'bottom', labels: { font:{size:10}, color: chartTextColor(), usePointStyle:true, padding:10 } },
          tooltip: { ...tooltipTheme(), callbacks: { label: ctx => `  ${ctx.label}: ${fmtTooltip(ctx.raw)} (${d.keluar[ctx.dataIndex].persen}%)` } }
        }
      }
    });
  } else { show('kat-keluar-empty'); }

  // ── Donut chart pemasukan ──
  if (d.masuk?.length) {
    hide('kat-masuk-empty');
    if (katMasukInst) katMasukInst.destroy();
    katMasukInst = new Chart(document.getElementById('katMasukChart'), {
      type: 'doughnut',
      data: {
        labels: d.masuk.map(c => `${c.icon} ${cap(c.category)}`),
        datasets: [{ data: d.masuk.map(c => c.total), backgroundColor: d.masuk.map(c => c.color + 'cc'), borderColor: d.masuk.map(c => c.color), borderWidth: 2, hoverOffset: 8 }]
      },
      options: {
        responsive: true, maintainAspectRatio: false, cutout: '65%',
        animation: { duration: 800, easing: 'easeOutQuart' },
        plugins: {
          legend: { position: 'bottom', labels: { font:{size:10}, color: chartTextColor(), usePointStyle:true, padding:10 } },
          tooltip: { ...tooltipTheme(), callbacks: { label: ctx => `  ${ctx.label}: ${fmtTooltip(ctx.raw)} (${d.masuk[ctx.dataIndex].persen}%)` } }
        }
      }
    });
  } else { show('kat-masuk-empty'); }

  // ── Detail cards pengeluaran ──
  const kelEl = document.getElementById('kat-keluar-list');
  kelEl.innerHTML = (d.keluar || []).map((c, i) => {
    const rank = i===0?'🥇':i===1?'🥈':i===2?'🥉':`${i+1}.`;
    return `<div class="bg-white dark:bg-gray-800 rounded-2xl p-4 shadow-sm border-l-4" style="border-color:${c.color}">
      <div class="flex items-center gap-3 mb-2">
        <span class="text-xl">${c.icon}</span>
        <div class="flex-1">
          <div class="flex items-center gap-2">
            <span class="text-xs font-bold text-gray-700 dark:text-gray-200">${rank} ${cap(c.category)}</span>
            <span class="ml-auto text-xs font-bold" style="color:${c.color}">${c.persen}%</span>
          </div>
          <div class="mt-1.5 h-2 rounded-full bg-gray-100 dark:bg-gray-700 overflow-hidden">
            <div class="h-full rounded-full" style="width:${c.persen}%;background:${c.color}"></div>
          </div>
        </div>
      </div>
      <div class="flex gap-4 text-xs text-gray-500">
        <span>💵 <b class="text-gray-700 dark:text-gray-300">${c.total_fmt}</b></span>
        <span>🔢 <b class="text-gray-700 dark:text-gray-300">${c.jumlah}x</b></span>
        <span>📊 avg <b class="text-gray-700 dark:text-gray-300">${c.avg_fmt}</b></span>
      </div>
    </div>`;
  }).join('');

  // ── Detail cards pemasukan ──
  const masEl = document.getElementById('kat-masuk-list');
  masEl.innerHTML = (d.masuk || []).map((c, i) => {
    const rank = i===0?'🥇':i===1?'🥈':i===2?'🥉':`${i+1}.`;
    return `<div class="bg-white dark:bg-gray-800 rounded-2xl p-4 shadow-sm border-l-4" style="border-color:${c.color}">
      <div class="flex items-center gap-3 mb-2">
        <span class="text-xl">${c.icon}</span>
        <div class="flex-1">
          <div class="flex items-center gap-2">
            <span class="text-xs font-bold text-gray-700 dark:text-gray-200">${rank} ${cap(c.category)}</span>
            <span class="ml-auto text-xs font-bold" style="color:${c.color}">${c.persen}%</span>
          </div>
          <div class="mt-1.5 h-2 rounded-full bg-gray-100 dark:bg-gray-700 overflow-hidden">
            <div class="h-full rounded-full" style="width:${c.persen}%;background:${c.color}"></div>
          </div>
        </div>
      </div>
      <div class="flex gap-4 text-xs text-gray-500">
        <span>💵 <b class="text-gray-700 dark:text-gray-300">${c.total_fmt}</b></span>
        <span>🔢 <b class="text-gray-700 dark:text-gray-300">${c.jumlah}x</b></span>
        <span>📊 avg <b class="text-gray-700 dark:text-gray-300">${c.avg_fmt}</b></span>
      </div>
    </div>`;
  }).join('');
}

// ─── BANKS ────────────────────────────────────────────────────────────────
async function loadBanks() {
  if (!wid) return;
  const r = await fetch(`/api/banks?wallet_id=${encodeURIComponent(wid)}`);
  const banks = await r.json();
  const grid = document.getElementById('bank-grid');
  const empty = document.getElementById('bank-empty');

  if (!banks.length) {
    grid.innerHTML = '';
    show('bank-empty');
    document.getElementById('bank-total').textContent = 'Rp 0';
    document.getElementById('bank-count').textContent = '0 rekening';
    return;
  }
  hide('bank-empty');

  const totalSaldo = banks.reduce((s, b) => s + b.saldo, 0);
  document.getElementById('bank-total').textContent = fmtRp(totalSaldo);
  document.getElementById('bank-count').textContent = `${banks.length} rekening`;

  grid.innerHTML = banks.map(b => {
    const pctUsed = b.total_masuk > 0
      ? Math.min(100, Math.round(b.total_keluar / b.total_masuk * 100))
      : 0;
    const isPositive = b.saldo >= 0;
    const saldoColor = isPositive ? 'text-white' : 'text-red-200';
    // Lighten color for bar background
    return `<div class="card rounded-2xl shadow-md overflow-hidden">
      <!-- Header berwarna -->
      <div class="p-4 text-white" style="background:${b.color}">
        <div class="flex items-center gap-2 mb-3">
          <span class="text-2xl">${b.icon}</span>
          <div class="flex-1 min-w-0">
            <p class="font-bold text-base leading-tight truncate">${b.name}</p>
            <p class="text-xs opacity-75">Saldo Awal: ${b.initial_fmt}</p>
          </div>
        </div>
        <p class="text-xs opacity-75 mb-0.5">💰 Saldo Saat Ini</p>
        <p class="text-2xl font-bold ${saldoColor} leading-tight">${b.saldo_fmt}</p>
      </div>
      <!-- Detail -->
      <div class="bg-white dark:bg-gray-800 p-4 space-y-2">
        <div class="flex justify-between text-xs">
          <span class="text-green-500 font-medium">📈 Total Masuk</span>
          <span class="font-semibold text-gray-700 dark:text-gray-200">${b.masuk_fmt}</span>
        </div>
        <div class="flex justify-between text-xs">
          <span class="text-red-400 font-medium">📉 Total Keluar</span>
          <span class="font-semibold text-gray-700 dark:text-gray-200">${b.keluar_fmt}</span>
        </div>
        ${b.total_masuk > 0 ? `
        <div class="pt-1">
          <div class="flex justify-between text-[10px] text-gray-400 mb-1">
            <span>Pengeluaran</span><span>${pctUsed}% dari pemasukan</span>
          </div>
          <div class="h-2 rounded-full bg-gray-100 dark:bg-gray-700 overflow-hidden">
            <div class="h-full rounded-full transition-all duration-500"
              style="width:${pctUsed}%;background:${b.color}"></div>
          </div>
        </div>` : ''}
      </div>
    </div>`;
  }).join('');
}

// ─── UTILS ────────────────────────────────────────────────────────────────
function cap(s) { return s ? s.charAt(0).toUpperCase()+s.slice(1) : s; }
function fmtRp(n) { return 'Rp '+Math.round(n).toLocaleString('id-ID'); }
function catIcon(cat) {
  const icons = { makan:'🍽️',minum:'☕',transport:'🚗',belanja:'🛍️',hiburan:'🎮',kesehatan:'💊',
    pendidikan:'📚',tagihan:'💡',gaji:'💼',investasi:'📈',transfer:'💸',tabungan:'🏦',umum:'📝' };
  return icons[(cat||'').toLowerCase()] || '📝';
}

// ─── CASHFLOW CALENDAR ────────────────────────────────────────────────────
let calYear = new Date().getFullYear();
let calMonth = new Date().getMonth() + 1; // 1-based
let calData = {};
let calCalledOnce = false;

const MONTH_NAMES = ['Januari','Februari','Maret','April','Mei','Juni',
                     'Juli','Agustus','September','Oktober','November','Desember'];
const DAY_NAMES   = ['Min','Sen','Sel','Rab','Kam','Jum','Sab'];

async function initCalendar() {
  if (!wid) return;
  await loadCalendar(calYear, calMonth);
}

function calNavigate(delta) {
  calMonth += delta;
  if (calMonth > 12) { calMonth = 1; calYear++; }
  if (calMonth < 1)  { calMonth = 12; calYear--; }
  loadCalendar(calYear, calMonth);
}

async function loadCalendar(year, month) {
  const monthStr = `${year}-${String(month).padStart(2,'0')}`;
  document.getElementById('cal-title').textContent = `${MONTH_NAMES[month-1]} ${year}`;
  document.getElementById('cal-detail').classList.add('hidden');
  const grid = document.getElementById('cal-grid');
  grid.innerHTML = '<div class="col-span-7 text-center text-gray-400 text-xs py-8">⏳ Memuat...</div>';

  try {
    const r = await fetch(`/api/calendar?wallet_id=${encodeURIComponent(wid)}&month=${monthStr}`);
    calData = await r.json();
    renderCalendar(year, month, calData);
  } catch(e) {
    grid.innerHTML = '<div class="col-span-7 text-center text-gray-400 text-xs py-8">❌ Gagal memuat kalender</div>';
  }
}

function renderCalendar(year, month, data) {
  const grid = document.getElementById('cal-grid');
  grid.innerHTML = '';
  const days = data.days || {};
  const daysInMonth = data.days_in_month || 31;
  const firstDay = new Date(year, month-1, 1).getDay(); // 0=Sun
  const today = new Date();
  const todayStr = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;

  // Empty cells before first day
  for (let i = 0; i < firstDay; i++) {
    const empty = document.createElement('div');
    empty.className = 'h-14 rounded-xl';
    grid.appendChild(empty);
  }

  for (let d = 1; d <= daysInMonth; d++) {
    const dayKey = `${year}-${String(month).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
    const events = days[dayKey] || [];
    const isToday = dayKey === todayStr;

    const cell = document.createElement('div');
    cell.className = `h-14 rounded-xl p-1 cursor-pointer border transition relative
      ${isToday ? 'border-emerald-400 bg-emerald-50 dark:bg-emerald-900/30' : 'border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700'}
    `;
    if (events.length > 0) cell.onclick = () => showCalDetail(dayKey, events);

    const dayNum = document.createElement('div');
    dayNum.className = `text-xs font-semibold ${isToday ? 'text-emerald-600 dark:text-emerald-400' : 'text-gray-600 dark:text-gray-400'}`;
    dayNum.textContent = d;
    cell.appendChild(dayNum);

    // Dots for events
    if (events.length > 0) {
      const dotRow = document.createElement('div');
      dotRow.className = 'flex gap-0.5 flex-wrap mt-0.5';
      const hasIn     = events.some(e => e.type==='in');
      const hasOut    = events.some(e => e.type==='out');
      const hasBill   = events.some(e => e.source==='bill' || e.source==='recurring' || e.source==='installment');
      if (hasIn)   dotRow.innerHTML += '<span class="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block"></span>';
      if (hasOut)  dotRow.innerHTML += '<span class="w-1.5 h-1.5 rounded-full bg-rose-400 inline-block"></span>';
      if (hasBill) dotRow.innerHTML += '<span class="w-1.5 h-1.5 rounded-full bg-amber-400 inline-block"></span>';
      cell.appendChild(dotRow);

      // Amount summary
      const inAmt  = events.filter(e=>e.type==='in').reduce((s,e)=>s+e.amount,0);
      const outAmt = events.filter(e=>e.type==='out').reduce((s,e)=>s+e.amount,0);
      if (inAmt > 0 || outAmt > 0) {
        const amt = document.createElement('div');
        amt.className = 'text-[9px] leading-tight truncate';
        if (inAmt > 0) amt.innerHTML += `<span class="text-emerald-500">+${fmtRp(inAmt).replace('Rp ','')}</span>`;
        if (outAmt > 0) amt.innerHTML += `<span class="text-rose-500"> -${fmtRp(outAmt).replace('Rp ','')}</span>`;
        cell.appendChild(amt);
      }
    }
    grid.appendChild(cell);
  }
}

function showCalDetail(dayKey, events) {
  const panel = document.getElementById('cal-detail');
  const dateEl = document.getElementById('cal-detail-date');
  const itemsEl = document.getElementById('cal-detail-items');
  const [y,m,d] = dayKey.split('-');
  dateEl.textContent = `${parseInt(d)} ${MONTH_NAMES[parseInt(m)-1]} ${y}`;
  itemsEl.innerHTML = '';
  events.forEach(ev => {
    const row = document.createElement('div');
    const color = ev.type==='in' ? 'text-emerald-600 dark:text-emerald-400'
                : (ev.source==='bill'||ev.source==='recurring'||ev.source==='installment') ? 'text-amber-600 dark:text-amber-400'
                : 'text-rose-600 dark:text-rose-400';
    row.className = `flex justify-between items-center py-1 border-b border-gray-100 dark:border-gray-700 last:border-0`;
    row.innerHTML = `<span class="text-gray-700 dark:text-gray-300 truncate max-w-[70%]">${ev.label}</span>
                     <span class="${color} font-semibold">${fmtRp(ev.amount)}</span>`;
    itemsEl.appendChild(row);
  });
  panel.classList.remove('hidden');
}

// ═══════════════════════════════════════════════════════════════════════════
// SUBSCRIPTIONS
// ═══════════════════════════════════════════════════════════════════════════

async function loadSubs() {
  const r = await fetch(`/api/subscriptions?wallet_id=${wid}`);
  const data = await r.json();
  renderSubsSummary(data);
  renderSubsList(data.subscriptions || []);
}

function renderSubsSummary(data) {
  const el = document.getElementById('subs-summary');
  const bulanan = data.total_bulanan || 0;
  const tahunan = data.total_tahunan || 0;
  el.innerHTML = `
    <div class="bg-violet-50 dark:bg-violet-900/20 rounded-2xl p-3">
      <p class="text-xs text-violet-500 dark:text-violet-400 font-semibold mb-1">Bulanan</p>
      <p class="text-lg font-black text-violet-700 dark:text-violet-300">${fmtRp(bulanan)}</p>
      <p class="text-xs text-gray-400">${data.active || 0} aktif dari ${data.total || 0}</p>
    </div>
    <div class="bg-indigo-50 dark:bg-indigo-900/20 rounded-2xl p-3">
      <p class="text-xs text-indigo-500 dark:text-indigo-400 font-semibold mb-1">Tahunan</p>
      <p class="text-lg font-black text-indigo-700 dark:text-indigo-300">${fmtRp(tahunan)}</p>
      <p class="text-xs text-gray-400">estimasi per tahun</p>
    </div>
  `;
}

function renderSubsList(subs) {
  const el = document.getElementById('subs-list');
  if (!subs.length) {
    el.innerHTML = '<p class="text-center text-gray-400 text-sm py-8">Belum ada subscription.<br>Klik <b>+ Tambah</b> untuk mulai.</p>';
    return;
  }
  const CAT_ICONS = {hiburan:'🎬', tagihan:'💡', kesehatan:'❤️', pendidikan:'📚', umum:'📦'};
  el.innerHTML = subs.map(s => {
    const icon = CAT_ICONS[s.category] || '📱';
    const active = s.is_active ? '' : 'opacity-40';
    const badge = s.is_active
      ? `<span class="text-xs px-1.5 py-0.5 bg-emerald-100 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400 rounded-full">Aktif</span>`
      : `<span class="text-xs px-1.5 py-0.5 bg-gray-200 dark:bg-gray-600 text-gray-500 rounded-full">Nonaktif</span>`;
    return `
    <div class="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-4 flex items-center gap-3 ${active}">
      <div class="text-2xl">${icon}</div>
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-2 flex-wrap">
          <span class="font-bold text-sm text-gray-800 dark:text-gray-100 truncate">${s.name}</span>
          ${badge}
        </div>
        <div class="text-xs text-gray-400 mt-0.5">Tgl ${s.billing_day} · ${s.category}</div>
      </div>
      <div class="text-right shrink-0">
        <div class="font-black text-sm text-gray-800 dark:text-gray-100">${fmtRp(s.amount)}</div>
        <div class="text-xs text-gray-400">/bulan</div>
      </div>
      <button onclick="deleteSub(${s.id})" class="ml-1 text-rose-400 hover:text-rose-600 transition text-lg" title="Hapus">×</button>
    </div>`;
  }).join('');
}

function showSubForm() {
  document.getElementById('sub-form').classList.remove('hidden');
}

async function submitSubForm() {
  const name = document.getElementById('sf-name').value.trim();
  const amount = parseFloat(document.getElementById('sf-amount').value);
  const day = parseInt(document.getElementById('sf-day').value);
  const cat = document.getElementById('sf-cat').value;
  if (!name || !amount || !day) return alert('Isi semua field!');
  await fetch(`/api/subscriptions/add?wallet_id=${wid}`, {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({name, amount, billing_day: day, category: cat})
  });
  document.getElementById('sub-form').classList.add('hidden');
  ['sf-name','sf-amount','sf-day'].forEach(id => document.getElementById(id).value = '');
  loadSubs();
}

async function deleteSub(id) {
  if (!confirm('Hapus subscription ini?')) return;
  await fetch(`/api/subscriptions/${id}?wallet_id=${wid}`, {method:'DELETE'});
  loadSubs();
}

// ═══════════════════════════════════════════════════════════════════════════
// AI COACH
// ═══════════════════════════════════════════════════════════════════════════

async function loadCoach() {
  const tipsEl = document.getElementById('coach-tips');
  tipsEl.innerHTML = '<p class="text-center text-gray-400 text-sm py-4">🤖 Menganalisis keuanganmu...</p>';

  // Load prediksi
  try {
    const rp = await fetch(`/api/prediksi?wallet_id=${wid}`);
    const pred = await rp.json();
    renderPrediksi(pred);
  } catch(e) {}

  // Load tips
  try {
    const rt = await fetch(`/api/coach?wallet_id=${wid}`);
    const data = await rt.json();
    renderCoachTips(data.tips || []);
  } catch(e) {
    tipsEl.innerHTML = '<p class="text-center text-rose-400 text-sm py-4">Gagal load tips.</p>';
  }
}

function renderPrediksi(pred) {
  const card = document.getElementById('prediksi-card');
  const amountEl = document.getElementById('prediksi-amount');
  const badgeEl  = document.getElementById('prediksi-badge');
  const detailEl = document.getElementById('prediksi-detail');
  if (!pred || pred.error) return;

  card.classList.remove('hidden');
  const saldo = pred.saldo_prediksi || 0;
  amountEl.textContent = fmtRp(Math.abs(saldo));
  if (saldo < 0) {
    amountEl.classList.add('text-rose-600','dark:text-rose-400');
    amountEl.textContent = '-' + fmtRp(Math.abs(saldo));
    badgeEl.className = 'text-xs font-semibold px-2 py-0.5 rounded-full bg-rose-100 dark:bg-rose-900/30 text-rose-600 dark:text-rose-400';
    badgeEl.textContent = '⚠️ Diprediksi minus!';
  } else {
    amountEl.classList.add('text-emerald-600','dark:text-emerald-400');
    badgeEl.className = 'text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400';
    badgeEl.textContent = '✅ Aman';
  }
  detailEl.innerHTML = `
    <div class="flex justify-between"><span>Rate harian:</span><span>${fmtRp(pred.rate_keluar_harian || 0)}/hari</span></div>
    <div class="flex justify-between"><span>Tagihan pending:</span><span class="text-rose-400">${fmtRp(pred.pending_keluar || 0)}</span></div>
    <div class="flex justify-between"><span>Sisa hari:</span><span>${pred.sisa_hari} hari</span></div>
  `;
}

function renderCoachTips(tips) {
  const el = document.getElementById('coach-tips');
  if (!tips.length) {
    el.innerHTML = '<p class="text-center text-gray-400 text-sm py-4">Tidak ada tips untuk saat ini.</p>';
    return;
  }
  el.innerHTML = tips.map(t => `
    <div class="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-4">
      <div class="flex items-start gap-3">
        <div class="text-2xl mt-0.5">${t.icon}</div>
        <div>
          <p class="font-bold text-sm text-gray-800 dark:text-gray-100 mb-1">${t.title}</p>
          <p class="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">${t.tip}</p>
        </div>
      </div>
    </div>
  `).join('');
}

// ─── START ────────────────────────────────────────────────────────────────
initWallets();
</script>
</body>
</html>"""


@app.route('/')
def index():
    return Response(HTML, mimetype='text/html')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Bot Simpan Uang — Web Dashboard')
    parser.add_argument('--port', type=int, default=5000)
    parser.add_argument('--host', default='0.0.0.0')
    args = parser.parse_args()
    print(f'🌐 Dashboard: http://localhost:{args.port}')
    print('   Ctrl+C untuk stop.')
    app.run(host=args.host, port=args.port, debug=False)

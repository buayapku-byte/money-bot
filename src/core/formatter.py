"""
Message Formatter — format pesan Telegram yang konsisten.
Konversi dari formatter.js (Node.js) ke Python.
"""
from datetime import datetime
from typing import Optional, Callable

from .i18n import t

CATEGORY_ICON = {
    # Pengeluaran
    'makan':       '🍽️', 'jajan':       '🧃', 'minum':    '☕',
    'transport':   '🚗', 'bensin':      '⛽', 'parkir':   '🅿️',
    'belanja':     '🛍️', 'pakaian':     '👕',
    'tagihan':     '💡', 'listrik':     '⚡', 'internet': '📶', 'pulsa': '📱',
    'hiburan':     '🎮', 'nonton':      '🎬', 'musik':    '🎵',
    'kesehatan':   '🏥', 'obat':        '💊',
    'pendidikan':  '📚', 'kursus':      '🎓',
    'tabungan':    '🏦', 'investasi':   '📈',
    'cicilan':     '🏠', 'sewa':        '🏡',
    # Pemasukan
    'gaji':        '💼', 'salary':      '💼',
    'bonus':       '🎁', 'thr':         '🎊',
    'freelance':   '💻', 'bisnis':      '🏪',
    'investasi_in':'📊', 'dividen':     '💰',
    'hadiah':      '🎀', 'cashback':    '🔄',
    # Umum
    'transfer':    '💸', 'umum':        '📌',
}

CATEGORY_COLOR = {
    'makan': '#f97316', 'jajan': '#fb923c', 'minum': '#a78bfa',
    'transport': '#3b82f6', 'bensin': '#60a5fa', 'parkir': '#93c5fd',
    'belanja': '#ec4899', 'pakaian': '#f472b6',
    'tagihan': '#eab308', 'listrik': '#facc15', 'internet': '#84cc16', 'pulsa': '#a3e635',
    'hiburan': '#8b5cf6', 'nonton': '#a78bfa', 'musik': '#c4b5fd',
    'kesehatan': '#ef4444', 'obat': '#fca5a5',
    'pendidikan': '#06b6d4', 'kursus': '#67e8f9',
    'tabungan': '#10b981', 'investasi': '#34d399',
    'cicilan': '#78716c', 'sewa': '#a8a29e',
    'gaji': '#10b981', 'bonus': '#059669', 'freelance': '#0ea5e9',
    'bisnis': '#0284c7', 'hadiah': '#d946ef', 'cashback': '#7c3aed',
    'transfer': '#6b7280', 'umum': '#9ca3af',
}

BULAN_ID = ['Januari','Februari','Maret','April','Mei','Juni',
            'Juli','Agustus','September','Oktober','November','Desember']
HARI_ID  = ['Minggu','Senin','Selasa','Rabu','Kamis','Jumat','Sabtu']


def format_rupiah(amount: float) -> str:
    return f"Rp {int(abs(round(amount))):,}".replace(',', '.')


def progress_bar(persen: int, panjang: int = 10) -> str:
    filled = round((persen / 100) * panjang)
    empty  = panjang - filled
    return '█' * filled + '░' * empty + f' {persen}%'


def format_tanggal(date_str: str, lang: str = 'id') -> str:
    """Format YYYY-MM-DD → 'Senin, 5 Oktober 2026'"""
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d')
        HARI  = t(lang, 'HARI')
        BULAN = t(lang, 'BULAN')
        hari  = HARI[d.weekday() + 1 if d.weekday() < 6 else 0]  # Python weekday 0=Mon; JS getDay() 0=Sun
        # Convert Python weekday (0=Mon) to JS getDay() (0=Sun) style:
        day_js = (d.weekday() + 1) % 7  # 0=Sun
        hari   = HARI[day_js]
        return f"{hari}, {d.day} {BULAN[d.month - 1]} {d.year}"
    except Exception:
        return date_str


def format_datetime(dt_str: str, lang: str = 'id') -> str:
    """Format datetime string → 'Selasa, 6 Oktober 2026 · 15:29'"""
    try:
        d = datetime.strptime(dt_str[:19], '%Y-%m-%d %H:%M:%S')
        HARI  = t(lang, 'HARI')
        BULAN = t(lang, 'BULAN')
        day_js = (d.weekday() + 1) % 7
        hari   = HARI[day_js]
        return f"{hari}, {d.day} {BULAN[d.month - 1]} {d.year} · {d.hour:02d}:{d.minute:02d}"
    except Exception:
        return dt_str


def to_usd(idr: float, usd_rate: Optional[float] = None) -> str:
    rate = usd_rate or 15750
    return f"${idr / rate:,.2f}"


# ─── Message formatters ───────────────────────────────────────

def format_saldo(data: dict, lang: str = 'id') -> str:
    saldo = data['saldo']
    sign  = '✅' if saldo >= 0 else '⚠️'
    return (
        f"{t(lang, 'saldo_title')}\n\n"
        f"{sign} {t(lang, 'saldo_label')}: *{format_rupiah(saldo)}*\n"
        f"{t(lang, 'income_label')}: {format_rupiah(data['total_masuk'])}\n"
        f"{t(lang, 'expense_label')}: {format_rupiah(data['total_keluar'])}"
    )


def format_transaksi(trx: dict, lang: str = 'id') -> str:
    icon  = '📈' if trx['type'] == 'in' else '📉'
    label = t(lang, 'type_in' if trx['type'] == 'in' else 'type_out')
    msg   = f"{icon} *{label} {t(lang, 'trx_saved')}*\n\n"
    msg  += f"{t(lang, 'trx_amount')}: *{format_rupiah(trx['amount'])}*\n"
    if trx.get('note'):
        msg += f"{t(lang, 'trx_note')}: {trx['note']}\n"
    if trx.get('category') and trx['category'] != 'umum':
        msg += f"{t(lang, 'trx_category')}: {trx['category']}\n"
    msg += f"{t(lang, 'trx_time')}: {format_datetime(trx.get('created_at',''), lang)}"
    return msg


def format_history(transactions: list, lang: str = 'id') -> str:
    if not transactions:
        return t(lang, 'no_transaction')
    rows = []
    for tx in transactions:
        icon = '📈' if tx['type'] == 'in' else '📉'
        note = f" · {tx['note']}" if tx.get('note') else ''
        rows.append(f"{icon} *#{tx['id']}* {format_rupiah(tx['amount'])}{note}\n   _{tx['date']}_")
    return (
        f"{t(lang, 'history_title')}\n\n"
        + '\n'.join(rows) + '\n\n'
        + t(lang, 'showing_last', len(transactions))
    )


def format_laporan(data: dict, period: str, lang: str = 'id') -> str:
    transactions = data['transactions']
    summary      = data['summary']
    label_map = {
        'hari':   t(lang, 'period_hari'),
        'minggu': t(lang, 'period_minggu'),
        'bulan':  t(lang, 'period_bulan'),
    }
    label = label_map.get(period, t(lang, 'period_label'))
    msg  = f"{t(lang, 'lap_title', label)}\n\n"
    msg += f"{t(lang, 'lap_income')}:  *{format_rupiah(summary['total_masuk'])}*\n"
    msg += f"{t(lang, 'lap_expense')}: *{format_rupiah(summary['total_keluar'])}*\n"
    msg += "─────────────────\n"
    selisih = summary['selisih']
    msg += f"{t(lang, 'surplus' if selisih >= 0 else 'deficit')}: *{format_rupiah(selisih)}*\n"
    msg += f"\n{t(lang, 'lap_total', summary['jumlah_transaksi'])}"
    if transactions:
        msg += f"\n\n{t(lang, 'lap_detail')}\n"
        for tx in transactions[:8]:
            icon = '↑' if tx['type'] == 'in' else '↓'
            note = f" {tx['note']}" if tx.get('note') else ''
            msg += f"{icon} {format_rupiah(tx['amount'])}{note} _({tx['date']})_\n"
        if len(transactions) > 8:
            msg += t(lang, 'lap_more', len(transactions) - 8)
    return msg


def format_kategori(rows: list, period: str, lang: str = 'id', prefix: str = '/') -> str:
    label_map = {
        'hari':   t(lang, 'period_hari'),
        'minggu': t(lang, 'period_minggu'),
        'bulan':  t(lang, 'period_bulan'),
    }
    label = label_map.get(period, t(lang, 'period_bulan'))
    keluar = sorted([r for r in rows if r['type'] == 'out'], key=lambda r: -r['total'])
    masuk  = sorted([r for r in rows if r['type'] == 'in'],  key=lambda r: -r['total'])
    total_keluar = sum(r['total'] for r in keluar)
    total_masuk  = sum(r['total'] for r in masuk)

    now   = datetime.now()
    bulan = ['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Agu','Sep','Okt','Nov','Des'][now.month - 1]
    header = f'🗂️ *Laporan Kategori — {label.title()}*\n_{bulan} {now.year}_\n'

    msg = header + '\n'

    # ── Pengeluaran ──────────────────────────────────────────
    if keluar:
        msg += '┌─────────────────────────────┐\n'
        msg += '│  📉 *PENGELUARAN*\n'
        msg += '└─────────────────────────────┘\n'
        for i, r in enumerate(keluar, 1):
            icon   = CATEGORY_ICON.get(r['category'], '📌')
            persen = round((r['total'] / total_keluar) * 100) if total_keluar > 0 else 0
            bar    = progress_bar(persen, 10)
            avg    = r['total'] / r['jumlah'] if r['jumlah'] > 0 else 0
            rank   = '🥇' if i == 1 else '🥈' if i == 2 else '🥉' if i == 3 else f'{i}.'
            msg   += (
                f'\n{rank} {icon} *{r["category"].upper()}*\n'
                f'   {bar}\n'
                f'   💵 {format_rupiah(r["total"])}  ·  {r["jumlah"]}x transaksi\n'
                f'   📊 Rata-rata: {format_rupiah(avg)}/transaksi\n'
            )
        msg += (
            '\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
            f'💸 *Total Keluar: {format_rupiah(total_keluar)}*\n\n'
        )

    # ── Pemasukan ───────────────────────────────────────────
    if masuk:
        msg += '┌─────────────────────────────┐\n'
        msg += '│  📈 *PEMASUKAN*\n'
        msg += '└─────────────────────────────┘\n'
        for i, r in enumerate(masuk, 1):
            icon   = CATEGORY_ICON.get(r['category'], '💰')
            persen = round((r['total'] / total_masuk) * 100) if total_masuk > 0 else 0
            bar    = progress_bar(persen, 10)
            avg    = r['total'] / r['jumlah'] if r['jumlah'] > 0 else 0
            rank   = '🥇' if i == 1 else '🥈' if i == 2 else '🥉' if i == 3 else f'{i}.'
            msg   += (
                f'\n{rank} {icon} *{r["category"].upper()}*\n'
                f'   {bar}\n'
                f'   💵 {format_rupiah(r["total"])}  ·  {r["jumlah"]}x transaksi\n'
                f'   📊 Rata-rata: {format_rupiah(avg)}/transaksi\n'
            )
        msg += (
            '\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
            f'💰 *Total Masuk: {format_rupiah(total_masuk)}*\n\n'
        )

    # ── Ringkasan ────────────────────────────────────────────
    if total_keluar or total_masuk:
        net     = total_masuk - total_keluar
        net_str = ('➕ ' if net >= 0 else '➖ ') + format_rupiah(abs(net))
        savings = round((net / total_masuk) * 100) if total_masuk else 0
        msg += (
            '┌─────────────────────────────┐\n'
            '│  📊 *RINGKASAN*\n'
            '└─────────────────────────────┘\n'
            f'📈 Masuk  : *{format_rupiah(total_masuk)}*\n'
            f'📉 Keluar : *{format_rupiah(total_keluar)}*\n'
            f'💹 Net    : *{net_str}*\n'
            f'🏦 Savings: *{savings}%*\n'
        )
    else:
        msg += t(lang, 'kat_empty', prefix)

    return msg.strip()


def format_goals(goals: list, get_goal_progress: Callable, usd_rate: Optional[float] = None,
                 lang: str = 'id', prefix: str = '/') -> str:
    if not goals:
        return t(lang, 'goals_empty', prefix)
    rate_label = (f"_Kurs: 1 USD = {format_rupiah(round(usd_rate))}_"
                  if usd_rate else f"_Kurs: 1 USD = {format_rupiah(15750)} (default)_")
    msg = f"{t(lang, 'goals_title')}\n{rate_label}\n\n"
    for i, g in enumerate(goals, 1):
        prog = get_goal_progress(g)
        persen   = prog['persen']
        sisa_hari = prog['sisaHari']
        msg += f"*{i}. {g['name']}*\n"
        msg += f"   {progress_bar(persen)}\n"
        msg += f"   {format_rupiah(g['current_amount'])} _({to_usd(g['current_amount'], usd_rate)})_\n"
        msg += f"   {t(lang, 'goals_target')}: {format_rupiah(g['target_amount'])} _({to_usd(g['target_amount'], usd_rate)})_\n"
        if sisa_hari is not None:
            if sisa_hari > 0:
                sisa_label = t(lang, 'goals_days', sisa_hari)
            elif sisa_hari == 0:
                sisa_label = t(lang, 'goals_today')
            else:
                sisa_label = t(lang, 'goals_overdue', sisa_hari)
            msg += f"   ⏰ {sisa_label} _({g['deadline']})_\n"
        msg += '\n'
    return msg.strip()


def format_budgets(budgets: list, lang: str = 'id') -> str:
    if not budgets:
        return t(lang, 'budget_empty')
    msg = f"{t(lang, 'budget_title')}\n\n"
    for b in budgets:
        icon  = CATEGORY_ICON.get(b['category'], '📌')
        persen = min(b['persen'], 100)
        bar   = progress_bar(persen, 8)
        level = '🚨' if b['persen'] >= 100 else ('⚠️' if b['persen'] >= 80 else '✅')
        msg  += f"{icon} *{b['category']}*  {level}\n"
        msg  += f"   {bar}\n"
        msg  += f"   {format_rupiah(b['spent'])} / {format_rupiah(b['amount'])}\n\n"
    return msg.strip()


def format_recurring(items: list, prefix: str = '/', lang: str = 'id') -> str:
    if not items:
        return t(lang, 'rec_empty', prefix)
    msg = f"{t(lang, 'rec_title')}\n\n"
    for r in items:
        dir_icon = '📈' if r['type'] == 'in' else '📉'
        cat_icon = CATEGORY_ICON.get(r['category'], '📌')
        msg += f"*#{r['id']}* {dir_icon} *{format_rupiah(r['amount'])}*"
        if r.get('note'):
            msg += f" · {r['note']}"
        msg += f"\n   {cat_icon} {r['category']} · {t(lang, 'rec_every')} *{r['day_of_month']}*\n"
    msg += f"\n{t(lang, 'rec_delete', prefix)}"
    return msg


def format_analisis(data: dict, lang: str = 'id') -> str:
    masuk_ini      = data['masukIni']
    keluar_ini     = data['keluarIni']
    savings_rate   = data['savingsRate']
    tren_keluar    = data['trenKeluar']
    hari_boros     = data['hariBoros']
    per_kategori   = data['perKategori']
    hari_unik      = data['hariUnik']
    rata_hari      = data['rataHari']
    jumlah_trx     = data['jumlahTransaksi']
    bulan          = data['bulan']

    BULAN  = t(lang, 'BULAN')
    y, m   = bulan.split('-')
    label  = f"{BULAN[int(m) - 1]} {y}"

    dot = '🟢' if savings_rate >= 30 else ('🟡' if savings_rate >= 10 else '🔴')
    msg  = f"{t(lang, 'an_title', label)}\n\n"
    msg += f"{t(lang, 'an_income')}:   *{format_rupiah(masuk_ini)}*\n"
    msg += f"{t(lang, 'an_expense')}: *{format_rupiah(keluar_ini)}*\n"
    msg += f"{t(lang, 'an_savings')}: *{savings_rate}%*  {dot}\n"

    if tren_keluar is not None:
        if tren_keluar > 0:
            msg += f"{t(lang, 'an_up', tren_keluar)}\n"
        else:
            msg += f"{t(lang, 'an_down', abs(tren_keluar))}\n"

    msg += f"\n{t(lang, 'an_txs', jumlah_trx, hari_unik)}\n"
    if rata_hari > 0:
        msg += f"{t(lang, 'an_avg')}: *{format_rupiah(rata_hari)}*\n"
    if hari_boros:
        msg += f"{t(lang, 'an_busiest')}: *{hari_boros}*\n"

    if per_kategori:
        msg += f"\n{t(lang, 'an_top')}\n"
        for i, k in enumerate(per_kategori[:5], 1):
            persen = round((k['total'] / keluar_ini) * 100) if keluar_ini > 0 else 0
            msg   += f"{i}. *{k['category']}* — {format_rupiah(k['total'])} ({persen}%) · {k['jumlah']}x\n"

    msg += f"\n{t(lang, 'an_advice')}\n"
    if savings_rate < 0:
        msg += f"{t(lang, 'an_crit')}\n"
    elif savings_rate < 20:
        msg += f"{t(lang, 'an_low', savings_rate)}\n"
    elif savings_rate >= 50:
        msg += f"{t(lang, 'an_high', savings_rate)}\n"
    else:
        msg += f"{t(lang, 'an_ok', savings_rate)}\n"

    if tren_keluar is not None and tren_keluar >= 30:
        msg += f"{t(lang, 'an_twarn', tren_keluar)}\n"
    elif tren_keluar is not None and tren_keluar <= -20:
        msg += f"{t(lang, 'an_tgood', abs(tren_keluar))}\n"

    if per_kategori:
        top    = per_kategori[0]
        persen = round((top['total'] / keluar_ini) * 100) if keluar_ini > 0 else 0
        if persen >= 40:
            msg += f"{t(lang, 'an_topwarn', top['category'], persen)}\n"

    return msg.strip()


def format_kekayaan(data: dict, lang: str = 'id') -> str:
    saldo          = data['saldo']
    total_tabungan = data['totalTabungan']
    total_kekayaan = data['totalKekayaan']
    goals          = data['goals']
    usd_rate       = data.get('usdRate')

    rate = usd_rate or 15750
    def to_usd_str(idr):
        return f"${round(idr / rate):,}"

    rate_label = (f"_Kurs: 1 USD = {format_rupiah(round(usd_rate))}_"
                  if usd_rate else f"_Kurs: 1 USD = {format_rupiah(15750)} (default)_")

    BULAN  = t(lang, 'BULAN')
    now    = datetime.now()
    tanggal = f"{now.day} {BULAN[now.month - 1]} {now.year}"

    msg  = f"{t(lang, 'kk_title')}\n{rate_label}\n\n"
    msg += f"{t(lang, 'kk_balance')}:   *{format_rupiah(saldo)}* _({to_usd_str(saldo)})_\n"
    msg += f"{t(lang, 'kk_savings')}: *{format_rupiah(total_tabungan)}* _({to_usd_str(total_tabungan)})_\n"
    msg += "─────────────────\n"
    net_sign = '💎' if total_kekayaan >= 0 else '⚠️'
    msg += f"{net_sign} *{t(lang, 'kk_net')}: {format_rupiah(total_kekayaan)}* _({to_usd_str(total_kekayaan)})_\n"
    if goals:
        msg += f"\n{t(lang, 'kk_goals')}\n"
        for g in goals:
            persen = min(100, round((g['current_amount'] / g['target_amount']) * 100)) if g['target_amount'] > 0 else 0
            status = '✅' if g['is_completed'] or persen >= 100 else '🎯'
            msg   += f"{status} *{g['name']}*: {format_rupiah(g['current_amount'])} _({persen}%)_\n"
    msg += f"\n{t(lang, 'kk_snap', tanggal)}"
    return msg.strip()

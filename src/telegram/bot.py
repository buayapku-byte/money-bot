"""
Telegram bot — Python async version menggunakan python-telegram-bot v20+.
Konversi dari bot.js (Telegraf/Node.js).
"""
import io
import re
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)

import config
from src.core.database import (
    get_or_create_wallet, resolve_wallet_id, get_lang, set_lang,
    create_invite_code, use_invite_code, unlink_wallet, get_db, _row,
)
from src.core.i18n import t
from src.core.finance import (
    add_transaction, get_saldo, get_history, get_laporan, undo_last,
    delete_transaction, edit_transaction,
    get_laporan_kategori,
    set_budget, get_budgets, delete_budget, check_budget_alert,
    add_recurring, get_recurring, delete_recurring,
    set_currency, get_currencies, convert_to_idr, CURRENCY_SYMBOLS,
    fetch_live_rates, get_live_rate_updated_at, POPULAR_CURRENCIES,
    get_export_data, generate_csv, get_analisis, get_kekayaan,
    get_saldo_multi_currency, get_savings_rate,
    add_wishlist, get_wishlists, delete_wishlist, get_wishlist_projection,
    get_proyeksi_bulan,
    add_bank_account, get_bank_accounts, get_bank_summary,
    set_transaction_bank, delete_bank_account, edit_bank_account,
    find_bank_by_name, _bank_icon, transfer_bank,
    set_auto_savings, get_auto_savings, delete_auto_savings, apply_auto_savings,
    add_debt, get_debts, mark_debt_paid, delete_debt, find_debt_by_person,
    add_installment, get_installments, pay_installment, delete_installment,
    add_bill, get_bills, delete_bill, get_upcoming_bills,
    get_laporan_comparison,
    get_health_score, get_dana_darurat_info, set_dana_darurat_months,
    get_net_worth, get_spending_anomalies, suggest_budgets,
    create_split, add_split_item, get_split, get_splits,
    mark_split_item_paid, calculate_split_settlement, settle_split,
    add_investment, get_investments, sell_investment, delete_investment,
    get_portfolio_summary,
    get_achievements, check_and_grant_achievements,
    # Wave 3
    get_prediksi_saldo,
    add_subscription, get_subscriptions, delete_subscription,
    toggle_subscription, get_upcoming_subscriptions, get_subscription_summary,
    create_challenge, get_active_challenge, advance_challenge, stop_challenge, CHALLENGE_TYPES,
    get_coach_tips,
    create_group_wallet, get_my_groups, join_group_wallet, get_group_members,
    get_group_transactions, get_group_summary, leave_group_wallet, regen_group_invite,
    generate_laporan_pdf,
)
from src.core.nlp import parse_nlp
from src.core.goals import create_goal, get_goals, add_to_goal, delete_goal, get_goal_progress
from src.core.reminder import set_reminder, disable_reminder
from src.core.formatter import (
    format_rupiah, format_saldo, format_transaksi, format_history,
    format_laporan, format_kategori, format_goals, format_budgets,
    format_recurring, format_analisis, format_kekayaan, progress_bar,
)
from src.core.grafik import (
    build_chart_config, fetch_grafik_buffer, build_grafik_caption,
    build_trend_config, build_trend_caption,
)

NAMA_BULAN = ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
              'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']


# ─── Helpers ──────────────────────────────────────────────

def format_bulan(month_str: str) -> str:
    """'2026-10' → 'Oktober 2026 (1 – 31 Okt 2026)'"""
    try:
        year, mon = map(int, month_str.split('-'))
        import calendar
        last_day = calendar.monthrange(year, mon)[1]
        nama = NAMA_BULAN[mon - 1]
        singkat = nama[:3]
        return f'{nama} {year} (1 – {last_day} {singkat} {year})'
    except Exception:
        return month_str


def parse_jumlah(s: str) -> float | None:
    """Parse string jumlah: '1.5jt', '500rb', '1k', '500000' → float."""
    if not s:
        return None
    s = s.lower().replace('.', '').strip()

    mul_match = re.match(r'^(\d+(?:\.\d+)?)(jt|rb|k|m)$', s)
    if mul_match:
        num = float(mul_match.group(1))
        suffix = mul_match.group(2)
        multipliers = {'jt': 1_000_000, 'rb': 1_000, 'k': 1_000, 'm': 1_000_000}
        return num * multipliers[suffix]

    try:
        return float(re.sub(r'[^\d.]', '', s))
    except ValueError:
        return None


def get_wallet(update: Update) -> dict:
    """Ambil atau buat wallet dari Update Telegram, resolve ke primary jika linked."""
    chat = update.effective_chat
    chat_id = chat.id
    name = chat.title or chat.first_name or 'Unknown'
    wallet = get_or_create_wallet('telegram', chat_id, name)
    primary_id = resolve_wallet_id(wallet['id'])
    if primary_id != wallet['id']:
        primary = _row(get_db().execute('SELECT * FROM wallets WHERE id = ?', (primary_id,)))
        if primary:
            wallet = primary
    wallet = dict(wallet)
    wallet['lang'] = get_lang(wallet['id'])
    return wallet


def build_savings_bar(rate: float) -> str:
    """Buat progress bar savings rate."""
    clamped = max(0, min(100, rate))
    filled = round(clamped / 10)
    bar = '█' * filled + '░' * (10 - filled)
    emoji = '🟢' if rate >= 20 else ('🟡' if rate >= 10 else ('🟠' if rate > 0 else '🔴'))
    return f'{emoji} [{bar}]'


def build_trx_keyboard(tx_id: int) -> InlineKeyboardMarkup:
    """Inline keyboard untuk konfirmasi transaksi."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton('✏️ Edit', callback_data=f'edit_{tx_id}'),
        InlineKeyboardButton('🗑️ Hapus', callback_data=f'hapus_{tx_id}'),
        InlineKeyboardButton('💰 Saldo', callback_data='lihat_saldo'),
    ]])


async def reply_md(update: Update, text: str, reply_markup=None):
    """Reply dengan Markdown parse mode."""
    kwargs = {'parse_mode': 'Markdown'}
    if reply_markup:
        kwargs['reply_markup'] = reply_markup
    await update.message.reply_text(text, **kwargs)


async def reply_error(update: Update, msg: str):
    """Reply dengan pesan error."""
    await reply_md(update, f'❌ {msg}')


# ─── Command Handlers ─────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    get_wallet(update)  # auto-create wallet
    name = update.effective_chat.first_name or 'Sobat'
    await reply_md(update,
        f'👋 *Halo {name}! Bot Keuangan siap!*\n\n'
        '💡 *Mulai dengan 3 langkah mudah:*\n\n'
        '1️⃣ *Catat transaksi pertama:*\n'
        '   `/c masuk 500rb gaji` atau\n'
        '   `/c keluar 25rb kopi`\n\n'
        '2️⃣ *Cek saldo & laporan:*\n'
        '   `/saldo` · `/laporan bulan`\n\n'
        '3️⃣ *Fitur lanjutan:*\n'
        '   `/target buat Liburan 5jt` — buat goal\n'
        '   `/budget makan 1jt` — set budget\n'
        '   `/bank tambah BCA 2jt` — kelola rekening\n'
        '   `/hutang Budi 300rb` — catat utang\n'
        '   `/cicilan tambah Motor 36 500rb` — track cicilan\n\n'
        '📋 Ketik /help untuk semua perintah.\n'
        '🌐 Ketik /dashboard untuk buka web dashboard.'
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply_md(update,
        '📋 *Daftar Perintah*\n\n'
        '💰 *Transaksi*\n'
        '`/catat masuk 500000 gaji` — catat pemasukan\n'
        '`/catat keluar 50rb makan` — catat pengeluaran\n'
        '`/catat keluar 1.5jt belanja` — support shorthand (rb/jt/k)\n'
        '`/saldo` — lihat saldo sekarang\n'
        '`/history` — 10 transaksi terakhir\n'
        '`/undo` — batalkan transaksi terakhir\n'
        '`/hapus 42` — hapus transaksi by ID\n'
        '`/edit 42 75rb kopi susu` — edit jumlah & catatan\n\n'
        '🎯 *Target Tabungan*\n'
        '`/target buat Liburan 3jt` — buat goal baru\n'
        '`/target buat HP 5000000 2026-12-31` — dengan deadline\n'
        '`/target lihat` — lihat semua goal\n'
        '`/target hapus Liburan` — hapus goal\n'
        '`/tabung 100rb Liburan` — tambah dana ke goal\n\n'
        '📊 *Laporan*\n'
        '`/laporan hari` — laporan hari ini\n'
        '`/laporan minggu` — laporan 7 hari terakhir\n'
        '`/laporan bulan` — laporan bulan ini\n'
        '`/kategori [hari/minggu/bulan]` — breakdown per kategori\n\n'
        '💡 *Budget*\n'
        '`/budget` — lihat budget bulan ini\n'
        '`/budget makan 500rb` — set budget kategori\n'
        '`/budget hapus makan` — hapus budget\n\n'
        '🔄 *Rutin (Berulang)*\n'
        '`/rutin` — lihat daftar rutin\n'
        '`/rutin tambah keluar 150rb netflix 5` — tiap tgl 5\n'
        '`/rutin hapus [id]` — hapus rutin\n\n'
        '⏰ *Reminder*\n'
        '`/reminder 20:00` — set notif harian jam 20:00\n'
        '`/reminder off` — matiin reminder\n\n'
        '🔗 *Share Wallet*\n'
        '`/wallet share` — buat kode undangan\n'
        '`/wallet gabung KODE` — gabung ke wallet orang\n'
        '`/wallet pisah` — berhenti berbagi\n\n'
        '💱 *Multi-Kurs (160+ mata uang)*\n'
        '`/kurs` — lihat kurs populer (live)\n'
        '`/kurs JPY` — cek kurs mata uang spesifik\n'
        '`/kurs set THB 435` — set kurs manual\n'
        '`/kurs update` — refresh dari server\n'
        '`/catat keluar 500THB makan` — auto-konversi ke IDR\n\n'
        '🏦 *Rekening Bank*\n'
        '`/bank` — lihat semua rekening & saldo\n'
        '`/bank tambah Mandiri 2000000` — tambah rekening + saldo awal\n'
        '`/bank tambah OCBC` — tambah rekening (saldo awal 0)\n'
        '`/bank set 42 1` — assign transaksi #42 ke bank id 1\n'
        '`/bank edit 1 BCA Jago 500000` — rename / ubah saldo awal\n'
        '`/bank hapus 1` — hapus rekening\n\n'
        '`/catat keluar dari jago 150rb makan` — catat & langsung assign ke bank Jago\n'
        '`/catat masuk dari mandiri 2jt gaji` — pemasukan ke bank Mandiri\n\n'
        '💸 *Transfer Antar Bank*\n'
        '`/transfer jago ocbc 500rb` — transfer dari Jago ke OCBC\n'
        '`/transfer mandiri bca 2jt bayar cicilan` — dengan catatan\n\n'
        '📅 *Ringkasan Otomatis*\n'
        '`/summary` — ringkasan keuangan bulan ini\n'
        '`/summary minggu` — ringkasan 7 hari terakhir\n\n'
        '🤖 *Auto-Tabung*\n'
        '`/autotabung` — lihat aturan aktif\n'
        '`/autotabung set 10 Liburan` — 10% dari setiap pemasukan → goal Liburan\n'
        '`/autotabung hapus Liburan` — matikan aturan\n\n'
        '💳 *Utang & Piutang*\n'
        '`/hutang Budi 500rb` — catat saya berhutang ke Budi\n'
        '`/piutang Ani 200rb` — catat Ani berhutang ke saya\n'
        '`/hutang lihat` — lihat semua utang & piutang\n'
        '`/hutang lunas <id>` — tandai lunas\n'
        '`/hutang hapus <id>` — hapus catatan\n\n'
        '🔖 *Cicilan*\n'
        '`/cicilan` — lihat cicilan aktif\n'
        '`/cicilan tambah Motor 36 500rb 10` — nama, total bln, per bln, tgl jatuh\n'
        '`/cicilan bayar <id>` — bayar 1 bulan cicilan\n'
        '`/cicilan hapus <id>` — hapus cicilan\n\n'
        '🗒️ *Tagihan Jatuh Tempo*\n'
        '`/tagihan` — tagihan jatuh tempo 7 hari ke depan\n'
        '`/tagihan semua` — lihat semua tagihan\n'
        '`/tagihan tambah Netflix 15 150rb` — nama, tgl jatuh, jumlah\n'
        '`/tagihan hapus <id>` — hapus tagihan\n\n'
        '⚡ *Shortcut*\n'
        '`/c masuk 500rb gaji` — alias singkat untuk /catat\n'
    )


async def cmd_catat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args or []

        # ── Deteksi "dari <bank>" di mana saja dalam args ─────────────────
        # Contoh: /catat keluar dari jago 150rb makan
        #         /catat keluar 150rb makan dari jago
        bank_query = None
        clean_args = list(args)
        dari_idx = next(
            (i for i, a in enumerate(clean_args) if a.lower() == 'dari' and i > 0),
            None,
        )
        if dari_idx is not None:
            # Kumpulkan token setelah "dari" sampai ketemu token yang dimulai digit (= amount)
            bank_tokens = []
            tail = []
            j = dari_idx + 1
            while j < len(clean_args):
                tok = clean_args[j]
                if re.match(r'^\d', tok):      # token numerik → batas bank name
                    tail = clean_args[j:]
                    break
                bank_tokens.append(tok)
                j += 1
            if bank_tokens:
                bank_query = ' '.join(bank_tokens)
                # Rekonstruksi args tanpa "dari <bank>" tapi sertakan sisa numerik
                clean_args = clean_args[:dari_idx] + tail

        type_raw = clean_args[0].lower() if clean_args else ''
        amount_raw = clean_args[1] if len(clean_args) > 1 else ''
        note = ' '.join(clean_args[2:]) if len(clean_args) > 2 else ''

        if not type_raw or type_raw not in ['masuk', 'keluar', 'in', 'out']:
            return await reply_error(update,
                'Format salah!\nGunakan: `/catat masuk 500000 catatan` atau `/catat keluar 50rb makan`\n'
                'Atau dengan mata uang asing: `/catat keluar 500THB makan`'
            )

        # Deteksi currency suffix: 500THB, 100USD, 50MYR
        # PENTING: rb/jt/k/m adalah multiplier angka — jangan salah baca sebagai kode mata uang
        _MULTIPLIER_ONLY = {'rb', 'ribu', 'jt', 'juta', 'k', 'm'}
        final_amount = None
        currency_note = ''
        currency_match = re.match(r'^(\d+(?:[.,]\d+)?(?:rb|jt|k|m)?)([A-Za-z]{2,6})$', amount_raw, re.IGNORECASE)
        if currency_match and currency_match.group(2).lower() in _MULTIPLIER_ONLY:
            currency_match = None  # "15rb" bukan "15 mata uang RB" — ini 15.000 IDR
        if currency_match:
            raw_num = currency_match.group(1)
            curr_code = currency_match.group(2).upper()
            num_val = parse_jumlah(raw_num)
            if num_val and num_val > 0:
                wallet = get_wallet(update)
                converted = convert_to_idr(wallet['id'], num_val, curr_code)
                final_amount = converted
                currency_note = f' ({num_val} {curr_code} → {format_rupiah(converted)})'
        else:
            final_amount = parse_jumlah(amount_raw)

        if not final_amount or final_amount <= 0:
            return await reply_error(update,
                f'Jumlah tidak valid: *{amount_raw}*\nContoh: `500000`, `500rb`, `1.5jt`, `500THB`'
            )

        type_ = 'in' if type_raw in ['masuk', 'in'] else 'out'
        wallet = get_wallet(update)
        created_by = update.effective_user.first_name or update.effective_user.username or 'Unknown'
        full_note = (note + currency_note).strip()

        trx = add_transaction(wallet['id'], type_, final_amount, full_note, 'umum', created_by)
        saldo_data = get_saldo(wallet['id'])
        saldo = saldo_data['saldo']

        reply_text = format_transaksi(trx, wallet['lang']) + f'\n\n💰 Saldo sekarang: *{format_rupiah(saldo)}*'

        # ── Assign ke bank jika "dari <bank>" terdeteksi ───────────────────
        if bank_query:
            matched_bank = find_bank_by_name(wallet['id'], bank_query)
            if matched_bank:
                set_transaction_bank(wallet['id'], trx['id'], matched_bank['id'])
                icon = matched_bank.get('icon', '🏦')
                reply_text += f'\n{icon} Bank: *{matched_bank["name"]}*'
            else:
                reply_text += f'\n⚠️ Bank *{bank_query}* tidak ditemukan — transaksi dicatat tanpa bank.\nCek `/bank` untuk daftar rekening.'

        # ── Auto-tabung jika pemasukan ─────────────────────────────────────
        if type_ == 'in':
            savings_results = apply_auto_savings(wallet['id'], final_amount, created_by)
            if savings_results:
                lines = '\n'.join(
                    f'  💚 {r["goal_name"]}: +{format_rupiah(r["amount"])} ({r["percentage"]}%)'
                    for r in savings_results
                )
                reply_text += f'\n\n🏦 *Auto-Tabung:*\n{lines}'

        # Cek budget alert jika pengeluaran
        if type_ == 'out':
            alert = check_budget_alert(wallet['id'], trx['category'])
            if alert:
                icon = '🚨' if alert['level'] == 'danger' else '⚠️'
                label = 'Budget HABIS' if alert['level'] == 'danger' else 'Budget hampir habis'
                reply_text += (
                    f'\n\n{icon} *{label}!*\n'
                    f'Kategori: {alert["category"]}\n'
                    f'Terpakai: {format_rupiah(alert["spent"])} / {format_rupiah(alert["budget"])} ({alert["persen"]}%)'
                )

        # Cek achievement baru
        try:
            new_achievements = check_and_grant_achievements(wallet['id'])
            ACHIEVEMENT_LABELS = {
                'first_trx':    ('🎉', 'First Transaction', 'Transaksi pertamamu!'),
                'week_streak':  ('🔥', 'Week Streak', '7 hari berturut-turut mencatat!'),
                'month_streak': ('💎', 'Month Streak', '30 hari konsisten mencatat!'),
                'saldo_1jt':    ('💰', 'Jutawan', 'Saldo tembus 1 juta!'),
                'saldo_10jt':   ('🤑', 'Miliuner', 'Saldo tembus 10 juta!'),
                'savings_20':   ('📈', 'Savings Hero', 'Saving rate >20% bulan ini!'),
                'invest_start': ('📊', 'Investor', 'Mulai investasi pertamamu!'),
                'networth_pos': ('✨', 'Net Worth Positif', 'Net worth kamu > 0!'),
                'trx_100':      ('🏅', 'Century', '100 transaksi tercatat!'),
            }
            for code in new_achievements:
                if code in ACHIEVEMENT_LABELS:
                    icon, name, desc = ACHIEVEMENT_LABELS[code]
                    reply_text += f'\n\n{icon} *Achievement Unlocked!*\n_{name}: {desc}_'
        except Exception:
            pass

        await update.message.reply_text(
            reply_text,
            parse_mode='Markdown',
            reply_markup=build_trx_keyboard(trx['id']),
        )
    except Exception as err:
        print(f'[TG /catat] {err}')
        await reply_error(update, str(err) or 'Terjadi error. Coba lagi.')


async def cmd_saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        wallet = get_wallet(update)
        data = get_saldo_multi_currency(wallet['id'])
        text = format_saldo(data, wallet['lang'])

        # Tampilkan konversi currency jika ada
        if data.get('conversions'):
            lines = []
            for c in data['conversions']:
                val = c['value']
                val_str = f"{round(val):,}" if abs(val) >= 100 else f"{val:.2f}"
                lines.append(f"   ≈ {c['symbol']} {val_str} ({c['code']})")
            text += '\n' + '\n'.join(lines)

        # Savings Rate Widget
        sr = get_savings_rate(wallet['id'])
        if sr.get('masuk', 0) > 0:
            rate_bar = build_savings_bar(sr['rate'])
            month_label = 'This Month' if wallet['lang'] == 'en' else 'Bulan Ini'
            avg_label = '3-mo avg' if wallet['lang'] == 'en' else 'Rata-rata 3 bln'
            sr_block = (
                f'\n\n📊 *Savings Rate {month_label}*\n'
                f'{rate_bar} *{sr["rate"]}%*\n'
                f'💵 Masuk: {format_rupiah(sr["masuk"])}\n'
                f'💸 Keluar: {format_rupiah(sr["keluar"])}\n'
                f'🏦 Tabungan: {format_rupiah(sr["tabungan"])}'
            )
            if sr.get('avgRate') is not None:
                sr_block += f'\n_{avg_label}: {sr["avgRate"]}%_'
            text += sr_block

        # Proyeksi Akhir Bulan
        try:
            proj = get_proyeksi_bulan(wallet['id'])
            if proj['hari_berlalu'] > 0 and proj['rata_keluar_harian'] > 0:
                proj_icon = '📉' if proj['is_defisit'] else '🔮'
                sisa = proj['hari_tersisa']
                proj_block = (
                    f'\n\n{proj_icon} *Proyeksi Akhir Bulan*\n'
                    f'Sisa {sisa} hari | Rata Rp {format_rupiah(proj["rata_keluar_harian"])}/hari\n'
                    f'Estimasi saldo akhir bulan: *{format_rupiah(proj["proyeksi_saldo_akhir_bulan"])}*'
                )
                if proj['is_defisit']:
                    proj_block += '\n⚠️ _Proyeksi defisit! Hemat pengeluaranmu._'
                text += proj_block
        except Exception:
            pass

        await reply_md(update, text)
    except Exception as err:
        print(f'[TG /saldo] {err}')
        await reply_error(update, 'Gagal ambil saldo.')


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args or []
        limit = min(int(args[0]) if args and args[0].isdigit() else 10, 30)
        wallet = get_wallet(update)
        transactions = get_history(wallet['id'], limit)
        await reply_md(update, format_history(transactions, wallet['lang']))
    except Exception as err:
        print(f'[TG /history] {err}')
        await reply_error(update, 'Gagal ambil history.')


async def cmd_undo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        wallet = get_wallet(update)
        deleted = undo_last(wallet['id'])

        if not deleted:
            return await reply_md(update, '📭 Tidak ada transaksi yang bisa dibatalkan.')

        icon = '📈' if deleted['type'] == 'in' else '📉'
        saldo = get_saldo(wallet['id'])['saldo']
        await reply_md(update,
            f'✅ *Transaksi dibatalkan!*\n\n'
            f'{icon} {format_rupiah(deleted["amount"])}'
            + (f' · {deleted["note"]}' if deleted.get('note') else '') +
            f'\n\n💰 Saldo sekarang: *{format_rupiah(saldo)}*'
        )
    except Exception as err:
        print(f'[TG /undo] {err}')
        await reply_error(update, 'Gagal undo transaksi.')


async def cmd_laporan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args or []
        period = args[0].lower() if args else 'bulan'

        # ── PDF subcommand ─────────────────────────────────────
        if period == 'pdf':
            wallet = get_wallet(update)
            month_arg = args[1] if len(args) > 1 else None  # '2026-10' opsional

            await update.message.reply_text('⏳ Sedang generate PDF laporan...')
            try:
                from src.core.pdf_report import generate_monthly_pdf
                month_str = month_arg or datetime.now().strftime('%Y-%m')
                pdf_bytes = generate_monthly_pdf(
                    wallet_id   = wallet['id'],
                    wallet_name = wallet.get('name', wallet['id']),
                    month_str   = month_str,
                )
                try:
                    y, m = map(int, month_str.split('-'))
                    bulan_label = ['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Agu','Sep','Okt','Nov','Des'][m-1]
                    fname = f'laporan_{bulan_label}{y}.pdf'
                except Exception:
                    fname = 'laporan.pdf'

                await update.message.reply_document(
                    document = io.BytesIO(pdf_bytes),
                    filename = fname,
                    caption  = f'📊 Laporan PDF {month_str} siap!',
                )
            except RuntimeError as e:
                await reply_error(update, str(e))
            return

        # ── Period normal ──────────────────────────────────────
        if period not in ['hari', 'minggu', 'bulan']:
            return await reply_error(update,
                'Period tidak valid.\nGunakan:\n'
                '`/laporan hari` · `/laporan minggu` · `/laporan bulan`\n'
                '`/laporan pdf` — laporan PDF bulan ini\n'
                '`/laporan pdf 2026-09` — laporan PDF bulan tertentu'
            )

        wallet = get_wallet(update)
        data = get_laporan(wallet['id'], period)
        text = format_laporan(data, period, wallet['lang'])

        # ── Tambahkan MoM comparison untuk laporan bulan ──────────────────
        if period == 'bulan':
            try:
                comp = get_laporan_comparison(wallet['id'])
                lalu = comp['bulan_lalu']
                if lalu['masuk'] > 0 or lalu['keluar'] > 0:
                    def fmt_delta(delta, pct):
                        sign = '+' if delta >= 0 else ''
                        pct_str = f' ({sign}{pct}%)' if pct is not None else ''
                        return f'{sign}{format_rupiah(delta)}{pct_str}'

                    dm = fmt_delta(comp['delta_masuk'],  comp['pct_masuk'])
                    dk = fmt_delta(comp['delta_keluar'], comp['pct_keluar'])
                    text += (
                        f'\n\n📈 *vs Bulan Lalu ({comp["label_lalu"]})*\n'
                        f'💚 Pemasukan: {dm}\n'
                        f'🔴 Pengeluaran: {dk}'
                    )
            except Exception:
                pass

        await reply_md(update, text)
    except Exception as err:
        print(f'[TG /laporan] {err}')
        await reply_error(update, 'Gagal buat laporan.')


async def cmd_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args or []
        sub = args[0].lower() if args else ''

        if not sub or sub not in ['lihat', 'buat', 'hapus', 'setor']:
            return await reply_error(update,
                'Subcommand tidak valid.\nGunakan:\n'
                '`/target lihat`\n'
                '`/target buat NamaGoal Jumlah [deadline]`\n'
                '`/target setor NamaGoal Jumlah`\n'
                '`/target hapus NamaGoal`'
            )

        wallet = get_wallet(update)

        if sub == 'lihat':
            goals = get_goals(wallet['id'])
            # Ambil USD rate
            usd_rate = None
            try:
                row = _row(get_db().execute('SELECT rate_to_idr FROM live_rates WHERE code = ?', ('USD',)))
                if row:
                    usd_rate = row['rate_to_idr']
            except Exception:
                pass
            buttons = []
            for g in goals:
                buttons.append([InlineKeyboardButton(
                    f'🗑️ Hapus: {g["name"][:25]}',
                    callback_data=f'goal_del_{g["id"]}'
                )])
            reply_markup = InlineKeyboardMarkup(buttons) if buttons else None
            return await update.message.reply_text(
                format_goals(goals, get_goal_progress, usd_rate, wallet['lang'], '/'),
                parse_mode='Markdown',
                reply_markup=reply_markup,
            )

        if sub == 'hapus':
            name = ' '.join(args[1:])
            if not name:
                return await reply_error(update, 'Ketik nama goal yang mau dihapus.\nContoh: `/target hapus Liburan`')
            deleted = delete_goal(wallet['id'], name)
            return await reply_md(update,
                f'✅ *Goal dihapus!*\n\n'
                f'🎯 {deleted["name"]}\n'
                f'Dana terkumpul: {format_rupiah(deleted["current_amount"] or 0)}'
            )

        if sub == 'setor':
            amount_raw = args[-1] if len(args) > 1 else ''
            amount = parse_jumlah(amount_raw)
            if not amount or amount <= 0 or len(args) < 3:
                return await reply_error(update, 'Format salah!\nContoh: `/target setor Liburan Bali 500rb`')
            goal_name = ' '.join(args[1:-1])
            if not goal_name:
                return await reply_error(update, 'Ketik nama goal.\nContoh: `/target setor Liburan 500rb`')

            updated_goal = add_to_goal(wallet['id'], goal_name, amount)
            prog = get_goal_progress(updated_goal)
            persen = prog['persen']
            is_completed = updated_goal.get('is_completed', 0)

            text = f'✅ *Setor berhasil!*\n\n🎯 *{updated_goal["name"]}*\n'
            text += f'Disetor: *{format_rupiah(amount)}*\n'
            text += f'Terkumpul: {format_rupiah(updated_goal["current_amount"])} / {format_rupiah(updated_goal["target_amount"])}\n'
            text += f'Progress: {persen}%\n'
            if is_completed:
                text += '\n🎉 *GOAL TERCAPAI! Selamat!* 🎉'
            else:
                text += f'Sisa: {format_rupiah(updated_goal["target_amount"] - updated_goal["current_amount"])}'
            return await reply_md(update, text)

        if sub == 'buat':
            last_arg = args[-1] if args else ''
            is_deadline = bool(re.match(r'^\d{4}-\d{2}-\d{2}$', last_arg))
            deadline = last_arg if is_deadline else None

            amount_arg = args[-2] if is_deadline else args[-1]
            amount = parse_jumlah(amount_arg)

            if not amount or amount <= 0:
                return await reply_error(update,
                    'Format salah!\nGunakan: `/target buat NamaGoal Jumlah`\nContoh: `/target buat Liburan 3jt`'
                )

            name_end = -2 if is_deadline else -1
            name = ' '.join(args[1:name_end])

            if not name:
                return await reply_error(update, 'Ketik nama goal.\nContoh: `/target buat Liburan Bali 3jt`')

            goal = create_goal(wallet['id'], name, amount, deadline)
            return await reply_md(update,
                f'✅ *Goal dibuat!*\n\n'
                f'🎯 *{goal["name"]}*\n'
                f'Target: {format_rupiah(goal["target_amount"])}\n'
                + (f'Deadline: {deadline}\n' if deadline else '') +
                f'\nGunakan `/tabung jumlah {goal["name"]}` untuk mulai nabung!'
            )
    except Exception as err:
        print(f'[TG /target] {err}')
        await reply_error(update, str(err) or 'Terjadi error.')


async def cmd_tabung(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args or []
        amount_raw = args[0] if args else ''
        goal_name = ' '.join(args[1:]) if len(args) > 1 else ''

        amount = parse_jumlah(amount_raw)
        if not amount or amount <= 0:
            return await reply_error(update,
                'Format salah!\nGunakan: `/tabung JumlahUang NamaGoal`\nContoh: `/tabung 100rb Liburan`'
            )
        if not goal_name:
            return await reply_error(update, 'Ketik nama goal tujuan.\nContoh: `/tabung 100rb Liburan`')

        wallet = get_wallet(update)
        updated_goal = add_to_goal(wallet['id'], goal_name, amount)
        prog = get_goal_progress(updated_goal)
        persen = prog['persen']
        is_completed = updated_goal.get('is_completed', 0)

        msg = f'✅ *Tabungan bertambah!*\n\n🎯 *{updated_goal["name"]}*\n'
        msg += f'Ditambah: *{format_rupiah(amount)}*\n'
        msg += f'Terkumpul: {format_rupiah(updated_goal["current_amount"])} / {format_rupiah(updated_goal["target_amount"])}\n'
        msg += f'Progress: {persen}%\n'
        if is_completed:
            msg += '\n🎉 *GOAL TERCAPAI! Selamat!* 🎉'
        else:
            sisa = updated_goal['target_amount'] - updated_goal['current_amount']
            msg += f'Sisa: {format_rupiah(sisa)}'

        await reply_md(update, msg)
    except Exception as err:
        print(f'[TG /tabung] {err}')
        await reply_error(update, str(err) or 'Terjadi error.')


async def cmd_kategori(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args or []
        period = args[0].lower() if args else 'bulan'

        if period not in ['hari', 'minggu', 'bulan']:
            return await reply_error(update,
                'Period tidak valid.\nGunakan: `/kategori hari`, `/kategori minggu`, atau `/kategori bulan`'
            )

        wallet = get_wallet(update)
        rows = get_laporan_kategori(wallet['id'], period)
        await reply_md(update, format_kategori(rows, period, wallet['lang'], '/'))
    except Exception as err:
        print(f'[TG /kategori] {err}')
        await reply_error(update, 'Gagal buat laporan kategori.')


async def cmd_hapus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args or []
        if not args or not args[0].isdigit():
            return await reply_error(update,
                'Ketik ID transaksi.\nContoh: `/hapus 42`\n\nGunakan `/history` untuk lihat ID transaksi.'
            )

        id_ = int(args[0])
        wallet = get_wallet(update)
        deleted = delete_transaction(wallet['id'], id_)
        saldo = get_saldo(wallet['id'])['saldo']

        icon = '📈' if deleted['type'] == 'in' else '📉'
        await reply_md(update,
            f'🗑️ *Transaksi dihapus!*\n\n'
            f'{icon} #{deleted["id"]} {format_rupiah(deleted["amount"])}'
            + (f' · {deleted["note"]}' if deleted.get('note') else '') +
            f'\n\n💰 Saldo sekarang: *{format_rupiah(saldo)}*'
        )
    except Exception as err:
        print(f'[TG /hapus] {err}')
        await reply_error(update, str(err) or 'Gagal hapus transaksi.')


async def cmd_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args or []
        if not args or not args[0].isdigit():
            return await reply_error(update,
                'Format salah!\nContoh:\n'
                '`/edit 42 75rb` — ubah jumlah\n'
                '`/edit 42 75rb kopi susu` — ubah jumlah & catatan'
            )

        id_ = int(args[0])
        new_amount = parse_jumlah(args[1]) if len(args) > 1 else None
        new_note = ' '.join(args[2:]) if len(args) > 2 else None

        if new_amount is None and new_note is None:
            return await reply_error(update, 'Ketik jumlah atau catatan baru.\nContoh: `/edit 42 75rb kopi susu`')
        if len(args) > 1 and new_amount is None:
            return await reply_error(update, f'Jumlah tidak valid: *{args[1]}*\nContoh: `75000`, `75rb`, `1.5jt`')

        wallet = get_wallet(update)
        updated = edit_transaction(wallet['id'], id_, new_amount, new_note)

        await reply_md(update,
            f'✏️ *Transaksi diupdate!*\n\n'
            f'#{updated["id"]} {"📈" if updated["type"] == "in" else "📉"} *{format_rupiah(updated["amount"])}*'
            + (f'\nCatatan: {updated["note"]}' if updated.get('note') else '') +
            f'\nKategori: {updated["category"]}'
        )
    except Exception as err:
        print(f'[TG /edit] {err}')
        await reply_error(update, str(err) or 'Gagal edit transaksi.')


async def cmd_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args or []
        input_ = args[0].lower() if args else ''

        if not input_:
            return await reply_error(update,
                'Ketik jam atau "off".\nContoh: `/reminder 20:00` atau `/reminder off`'
            )

        wallet = get_wallet(update)

        if input_ == 'off':
            disable_reminder(wallet['id'])
            return await reply_md(update, '🔕 Reminder dimatikan.')

        time = set_reminder(wallet['id'], 'telegram', input_)
        return await reply_md(update,
            f'⏰ *Reminder diset!*\n\nKamu akan dapat notif harian jam *{time}* WIB.'
        )
    except Exception as err:
        print(f'[TG /reminder] {err}')
        await reply_error(update, str(err) or 'Terjadi error.')


async def cmd_budget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args or []
        wallet = get_wallet(update)

        if not args:
            budgets = get_budgets(wallet['id'])
            return await reply_md(update, format_budgets(budgets, wallet['lang']))

        sub = args[0].lower()

        if sub == 'hapus':
            category = ' '.join(args[1:]).lower()
            if not category:
                return await reply_error(update, 'Ketik nama kategori.\nContoh: `/budget hapus makan`')
            deleted = delete_budget(wallet['id'], category)
            return await reply_md(update,
                f'✅ *Budget dihapus!*\n\nKategori: {deleted["category"]}\nBudget: {format_rupiah(deleted["amount"])}'
            )

        if sub == 'smart':
            suggestions = suggest_budgets(wallet['id'])
            if not suggestions:
                return await reply_md(update,
                    '📊 *Smart Budget*\n\n'
                    '_Belum ada data transaksi 3 bulan terakhir untuk analisis._\n'
                    'Coba lagi setelah beberapa waktu mencatat pengeluaran!'
                )
            lines = ['🧠 *Smart Budget Suggestions*\n',
                     '_Berdasarkan rata-rata pengeluaran 3 bulan terakhir (+10% buffer):_\n']
            for s in suggestions:
                lines.append(f'• *{s["category"].title()}*: {format_rupiah(s["suggested"])} _(avg: {format_rupiah(s["avg"])})_')
            lines.append('\n_Ketik `/budget <kategori> <jumlah>` untuk set budget._')
            lines.append('_Contoh: `/budget makan 800rb`_')
            return await reply_md(update, '\n'.join(lines))

        amount_raw = args[-1] if args else ''
        amount = parse_jumlah(amount_raw)
        if not amount or amount <= 0 or len(args) < 2:
            return await reply_error(update,
                'Format salah!\nContoh:\n'
                '`/budget makan 500rb`\n'
                '`/budget belanja online 1jt`\n'
                '`/budget transport 300rb`'
            )
        category = ' '.join(args[:-1]).lower()

        budget = set_budget(wallet['id'], category, amount)
        return await reply_md(update,
            f'✅ *Budget diset!*\n\n'
            f'Kategori: *{budget["category"]}*\n'
            f'Budget: *{format_rupiah(budget["amount"])}*\n'
            f'Periode: {format_bulan(budget["month"])}\n\n'
            f'_Kamu akan dapat peringatan saat mencapai 80% dan 100%._'
        )
    except Exception as err:
        print(f'[TG /budget] {err}')
        await reply_error(update, str(err) or 'Gagal proses budget.')


async def cmd_rutin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args or []
        wallet = get_wallet(update)

        if not args:
            list_ = get_recurring(wallet['id'])
            return await reply_md(update, format_recurring(list_, '/', wallet['lang']))

        sub = args[0].lower()

        if sub == 'hapus':
            if not args[1:] or not args[1].isdigit():
                return await reply_error(update, 'Ketik ID rutin.\nContoh: `/rutin hapus 3`')
            id_ = int(args[1])
            deleted = delete_recurring(wallet['id'], id_)
            return await reply_md(update,
                f'✅ *Rutin dihapus!*\n\n'
                f'{"📈" if deleted["type"] == "in" else "📉"} {format_rupiah(deleted["amount"])}'
                + (f' · {deleted["note"]}' if deleted.get('note') else '') +
                f'\nTiap tgl {deleted["day_of_month"]}'
            )

        if sub == 'tambah':
            type_raw = args[1].lower() if len(args) > 1 else ''
            if not type_raw or type_raw not in ['masuk', 'keluar', 'in', 'out']:
                return await reply_error(update,
                    'Format salah!\nContoh:\n'
                    '`/rutin tambah keluar 150rb netflix 5`\n'
                    '`/rutin tambah masuk 5jt gaji 25`'
                )

            type_ = 'in' if type_raw in ['masuk', 'in'] else 'out'
            amount = parse_jumlah(args[2]) if len(args) > 2 else None
            if not amount or amount <= 0:
                return await reply_error(update, 'Jumlah tidak valid.\nContoh: `/rutin tambah keluar 150rb netflix 5`')

            last_arg = args[-1] if args else ''
            try:
                day = int(last_arg)
                if day < 1 or day > 28:
                    raise ValueError()
            except ValueError:
                return await reply_error(update, 'Tanggal tidak valid (1-28).\nContoh: `/rutin tambah keluar 150rb netflix 5`')

            note = ' '.join(args[3:-1]) if len(args) > 4 else ''
            rec = add_recurring(wallet['id'], type_, amount, note, 'umum', day)

            return await reply_md(update,
                f'✅ *Transaksi rutin ditambah!*\n\n'
                f'{"📈" if rec["type"] == "in" else "📉"} *{format_rupiah(rec["amount"])}*'
                + (f' · {rec["note"]}' if rec.get('note') else '') + '\n'
                f'Kategori: {rec["category"]}\n'
                f'Tiap tanggal: *{rec["day_of_month"]}*\n\n'
                f'_Akan dicatat otomatis setiap bulan._'
            )

        return await reply_error(update,
            'Subcommand tidak valid.\nGunakan:\n'
            '`/rutin`\n'
            '`/rutin tambah keluar 150rb netflix 5`\n'
            '`/rutin hapus [id]`'
        )
    except Exception as err:
        print(f'[TG /rutin] {err}')
        await reply_error(update, str(err) or 'Gagal proses rutin.')


async def cmd_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args or []
        sub = args[0].lower() if args else ''
        chat = update.effective_chat
        my_wallet = get_or_create_wallet('telegram', chat.id, chat.title or chat.first_name or 'Unknown')

        if sub in ['share', 'bagikan']:
            code = create_invite_code(my_wallet['id'])
            return await reply_md(update,
                f'🔗 *Kode Share Wallet*\n\n'
                f'Kode: `{code}`\n'
                f'Berlaku: 24 jam\n\n'
                f'Kirim ke orang yang mau bergabung:\n'
                f'`/wallet gabung {code}`'
            )

        if sub == 'gabung':
            code = args[1] if len(args) > 1 else ''
            if not code:
                return await reply_error(update, 'Ketik kode undangan.\nContoh: `/wallet gabung ABC123`')
            primary = use_invite_code(my_wallet['id'], code)
            return await reply_md(update,
                f'✅ *Berhasil bergabung!*\n\n'
                f'Sekarang kamu mengakses wallet: *{primary["name"] or primary["id"]}*\n'
                f'Semua transaksi akan dicatat ke wallet tersebut.\n\n'
                f'Gunakan `/wallet pisah` untuk berhenti berbagi.'
            )

        if sub == 'pisah':
            unlink_wallet(my_wallet['id'])
            return await reply_md(update, '✅ *Wallet dipisah!*\n\nKamu sekarang kembali menggunakan wallet sendiri.')

        if sub == 'info':
            db = get_db()
            link = _row(db.execute('SELECT * FROM wallet_links WHERE member_id = ?', (my_wallet['id'],)))
            if link:
                primary = _row(db.execute('SELECT * FROM wallets WHERE id = ?', (link['primary_id'],)))
                return await reply_md(update,
                    f'🔗 *Status Wallet*\n\n'
                    f'Kamu sedang berbagi wallet dengan:\n*{primary.get("name") or link["primary_id"]}*\n\n'
                    f'Gunakan `/wallet pisah` untuk berhenti.'
                )
            return await reply_md(update,
                '👛 *Status Wallet*\n\nKamu menggunakan wallet sendiri.\n\nBagikan ke orang lain: `/wallet share`'
            )

        return await reply_md(update,
            '❓ *Subcommand wallet:*\n'
            '`/wallet share` — buat kode undangan\n'
            '`/wallet gabung KODE` — gabung ke wallet orang lain\n'
            '`/wallet pisah` — berhenti berbagi\n'
            '`/wallet info` — cek status'
        )
    except Exception as err:
        print(f'[TG /wallet] {err}')
        await reply_error(update, str(err) or 'Terjadi error.')


async def cmd_kurs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args or []
        sub = args[0].lower() if args else ''
        wallet = get_wallet(update)

        if sub == 'update':
            await reply_md(update, '🔄 Mengambil kurs terbaru dari server...')
            try:
                result = fetch_live_rates()
                return await reply_md(update,
                    f'✅ *Kurs berhasil diperbarui!*\n\n'
                    f'📊 {result["count"]} mata uang tersedia\n'
                    f'💵 1 USD = Rp {int(result["usdRate"]):,}\n\n'
                    f'Cek kurs: `/kurs`'
                )
            except Exception as e:
                return await reply_error(update, f'Gagal update kurs: {e}\nCoba lagi nanti.')

        if sub == 'set':
            code = args[1].upper() if len(args) > 1 else ''
            try:
                rate = float(args[2]) if len(args) > 2 else 0
            except ValueError:
                rate = 0
            if not code or rate <= 0:
                return await reply_error(update, 'Format: `/kurs set THB 435`\n(1 THB = 435 IDR)')
            result = set_currency(wallet['id'], code, rate)
            return await reply_md(update,
                f'✅ *Kurs custom disimpan!*\n\n1 {result["code"]} = Rp {int(rate):,}\n'
                f'_(Override live rate — hanya berlaku di wallet ini)_\n\n'
                f'Contoh pakai: `/catat keluar 500{result["code"]} makan`'
            )

        if sub and re.match(r'^[a-z]{2,6}$', sub):
            code = sub.upper()
            all_currencies = get_currencies(wallet['id'])
            found = next((r for r in all_currencies if r['code'] == code), None)
            if not found:
                return await reply_error(update,
                    f'Kurs *{code}* tidak ditemukan.\n\n'
                    f'Coba: `/kurs update` untuk refresh data\n'
                    f'Atau: `/kurs set {code} [nilai]` untuk set manual'
                )
            label = '*(custom)*' if found.get('is_custom') else '_(live rate)_'
            return await reply_md(update,
                f'💱 *Kurs {code}*\n\n'
                f'1 {code} = Rp {int(found["rate_to_idr"]):,} {label}\n\n'
                f'_Update: {found.get("updated_at") or "-"}_'
            )

        # /kurs — tampilkan kurs populer
        updated_at = get_live_rate_updated_at()
        all_currencies = get_currencies(wallet['id'])
        custom_map = {r['code']: r for r in all_currencies if r.get('is_custom')}
        live_map = {r['code']: r for r in all_currencies if not r.get('is_custom')}

        out = '💱 *Kurs Mata Uang*\n'
        if updated_at:
            out += f'_Update: {updated_at} WIB_\n'
        out += '\n'

        if custom_map:
            out += '🔧 *Custom (wallet kamu):*\n'
            for r in custom_map.values():
                out += f'• {r["code"]}: Rp {int(r["rate_to_idr"]):,}\n'
            out += '\n'

        out += '📊 *Kurs Populer (live):*\n'
        shown = 0
        for code in POPULAR_CURRENCIES:
            if code in custom_map:
                continue
            r = live_map.get(code)
            if r:
                out += f'• {code}: Rp {int(r["rate_to_idr"]):,}\n'
                shown += 1

        if not updated_at and shown == 0:
            out += '_Data live belum tersedia._\n'

        out += '\n💡 *Perintah lain:*\n'
        out += '• `/kurs JPY` — cek kurs spesifik\n'
        out += '• `/kurs set THB 435` — set kurs manual\n'
        out += '• `/kurs update` — refresh dari server\n'
        out += '\n_160+ mata uang tersedia · auto-refresh tiap hari 07:00 WIB_'

        return await reply_md(update, out)
    except Exception as err:
        print(f'[TG /kurs] {err}')
        await reply_error(update, str(err) or 'Terjadi error.')


async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        wallet = get_wallet(update)
        args = context.args or []
        month_arg = args[0] if args else None
        month_str = month_arg if month_arg and re.match(r'^\d{4}-\d{2}$', month_arg) else None

        rows = get_export_data(wallet['id'], month_str)
        month = month_str or datetime.now().strftime('%Y-%m')

        if not rows:
            return await reply_md(update, f'📭 Tidak ada transaksi untuk periode *{month}*')

        csv_content = generate_csv(rows)
        filename = f'transaksi_{month}.csv'
        bio = io.BytesIO(csv_content.encode('utf-8'))
        bio.name = filename

        await update.message.reply_document(
            document=bio,
            caption=f'📊 Export *{month}* — {len(rows)} transaksi',
            parse_mode='Markdown',
        )
    except Exception as err:
        print(f'[TG /export] {err}')
        await reply_error(update, str(err) or 'Terjadi error.')


async def cmd_analisis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        wallet = get_wallet(update)
        data = get_analisis(wallet['id'])
        await reply_md(update, format_analisis(data, wallet['lang']))
    except Exception as err:
        print(f'[TG /analisis] {err}')
        await reply_error(update, str(err) or 'Terjadi error.')


async def cmd_kekayaan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        wallet = get_wallet(update)
        data = get_kekayaan(wallet['id'])
        await reply_md(update, format_kekayaan(data, wallet['lang']))
    except Exception as err:
        print(f'[TG /kekayaan] {err}')
        await reply_error(update, str(err) or 'Terjadi error.')


async def cmd_grafik(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args or []
        period = args[0].lower() if args else 'bulan'

        if period not in ['hari', 'minggu', 'bulan']:
            return await reply_error(update,
                'Period tidak valid.\nGunakan: `/grafik`, `/grafik hari`, `/grafik minggu`, atau `/grafik bulan`'
            )

        wallet = get_wallet(update)
        result = build_chart_config(wallet['id'], period, wallet['lang'])

        if not result:
            msg = '📭 No expenses recorded for this period.' if wallet['lang'] == 'en' else '📭 Belum ada pengeluaran untuk periode ini.'
            return await reply_md(update, msg)

        await update.message.chat.send_action('upload_photo')
        buffer = fetch_grafik_buffer(result['config'])
        if not buffer:
            return await reply_error(update, 'Gagal buat grafik. Coba lagi.')

        caption = build_grafik_caption(result['keluar'], result['total'], period, wallet['lang'])
        await update.message.reply_photo(
            photo=io.BytesIO(buffer),
            caption=caption,
            parse_mode='Markdown',
        )
    except Exception as err:
        print(f'[TG /grafik] {err}')
        await reply_error(update, 'Gagal buat grafik. Coba lagi.')


async def cmd_trend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args or []
        try:
            months = int(args[0]) if args else 6
        except ValueError:
            months = 6

        if months not in [3, 6, 12]:
            return await reply_error(update, 'Jumlah bulan tidak valid.\nGunakan: `/trend 3`, `/trend 6`, atau `/trend 12`')

        wallet = get_wallet(update)
        result = build_trend_config(wallet['id'], months, wallet['lang'])

        if not result:
            msg = f'📭 No data for the last {months} months.' if wallet['lang'] == 'en' else f'📭 Belum ada data untuk {months} bulan terakhir.'
            return await reply_md(update, msg)

        await update.message.chat.send_action('upload_photo')
        buffer = fetch_grafik_buffer(result['config'])
        if not buffer:
            return await reply_error(update, 'Gagal buat grafik trend. Coba lagi.')

        caption = build_trend_caption(result['rows'], months, wallet['lang'])
        await update.message.reply_photo(
            photo=io.BytesIO(buffer),
            caption=caption,
            parse_mode='Markdown',
        )
    except Exception as err:
        print(f'[TG /trend] {err}')
        await reply_error(update, 'Gagal buat grafik trend. Coba lagi.')


async def cmd_bahasa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args or []
        lang_arg = args[0].lower() if args else ''
        chat = update.effective_chat
        my_wallet = get_or_create_wallet('telegram', chat.id, chat.title or chat.first_name or 'Unknown')

        if not lang_arg:
            current_lang = get_lang(my_wallet['id'])
            return await reply_md(update, t(current_lang, 'lang_current') + '\n\n' + t(current_lang, 'lang_usage'))

        if lang_arg not in ['id', 'en']:
            return await reply_error(update, t(get_lang(my_wallet['id']), 'lang_usage'))

        set_lang(my_wallet['id'], lang_arg)
        return await reply_md(update, t(lang_arg, 'lang_switched', lang_arg))
    except Exception as err:
        print(f'[TG /bahasa] {err}')
        await reply_error(update, 'Terjadi error.')


async def cmd_wishlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args or []
        chat = update.effective_chat
        wallet = get_or_create_wallet('telegram', chat.id, chat.title or chat.first_name or 'Unknown')
        sub = args[0].lower() if args else ''

        if sub in ['tambah', 'add']:
            rest = args[1:]
            if len(rest) < 2:
                return await reply_error(update, 'Format: `/wishlist tambah <nama barang> <harga>`\nContoh: `/wishlist tambah iPhone 15 15000000`')
            price_str = rest[-1]
            try:
                price = float(re.sub(r'[^\d.]', '', price_str))
            except ValueError:
                price = 0
            if not price:
                return await reply_error(update, 'Harga tidak valid.')
            name = ' '.join(rest[:-1])
            item_id = add_wishlist(wallet['id'], name, price)
            proj = get_wishlist_projection(wallet['id'])
            item = next((i for i in proj['items'] if i['id'] == item_id), None)
            msg = f'✨ *{name}* ditambahkan ke wishlist!\n💰 Harga: *{format_rupiah(price)}*\n'
            if item and item.get('monthsNeeded'):
                msg += f'📅 Perkiraan bisa beli: *{item["monthsNeeded"]} bulan lagi*\n'
                msg += f'_Berdasarkan savings rate {proj["savingsRate"]}% bulan ini_'
            else:
                msg += '_Tambah pemasukan dulu biar bisa proyeksi waktu beli 😁_'
            return await reply_md(update, msg)

        # List semua
        proj = get_wishlist_projection(wallet['id'])
        if not proj['items']:
            return await update.message.reply_text(
                '📝 Wishlist kamu kosong.\n\nTambahkan dengan: /wishlist tambah <nama> <harga>'
            )

        msg = '💖 *Wishlist Kamu*\n'
        if proj.get('savingsPerMonth', 0) > 0:
            msg += f'_Savings/bulan: {format_rupiah(proj["savingsPerMonth"])} ({proj["savingsRate"]}%)_\n'
        msg += '\n'

        buttons = []
        for i, w in enumerate(proj['items']):
            num = i + 1
            msg += f'*{num}. {w["name"]}*\n'
            msg += f'   💵 {format_rupiah(w["price"])}'
            if w.get('monthsNeeded'):
                msg += f' • 📅 ~{w["monthsNeeded"]} bulan lagi'
            else:
                msg += ' • _belum ada data savings_'
            msg += '\n'
            buttons.append([InlineKeyboardButton(f'🗑️ Hapus: {w["name"][:20]}', callback_data=f'wl_del_{w["id"]}')])

        await update.message.reply_text(
            msg,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(buttons) if buttons else None,
        )
    except Exception as err:
        print(f'[TG /wishlist] {err}')
        await update.message.reply_text('❌ Gagal memuat wishlist.')


# ─── Bank Account ─────────────────────────────────────────

async def cmd_bank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /bank                  — lihat semua rekening bank
    /bank tambah <nama> <saldo_awal>   — tambah rekening baru
    /bank hapus <id>       — hapus rekening
    /bank set <tx_id> <bank_id>        — assign transaksi ke bank
    /bank edit <id> <nama> [saldo]     — ganti nama/saldo awal
    """
    args = context.args or []
    chat = update.effective_chat
    wallet = get_or_create_wallet('telegram', chat.id, chat.title or chat.first_name or 'Unknown')
    primary_id = resolve_wallet_id(wallet['id'])

    async def reply_md(text, **kw):
        await update.message.reply_text(text, parse_mode='Markdown', **kw)

    sub = args[0].lower() if args else 'lihat'

    # ── lihat ──────────────────────────────────────────────
    if sub in ('lihat', 'list', 'daftar') or not args:
        banks = get_bank_accounts(primary_id)
        if not banks:
            return await reply_md(
                '🏦 *Rekening Bank*\n\nBelum ada rekening.\n\n'
                'Tambah rekening:\n`/bank tambah Mandiri 5000000`\n'
                '`/bank tambah BCA 2500000`\n`/bank tambah Jago 1000000`'
            )

        total = sum(b['saldo'] for b in banks)
        lines = [f'🏦 *Rekening Bank* ({len(banks)} rekening)\n']
        for b in banks:
            icon = b.get('icon', '🏦')
            saldo_str = format_rupiah(b['saldo'])
            masuk_str = format_rupiah(b['total_masuk'])
            keluar_str = format_rupiah(b['total_keluar'])
            lines.append(
                f'{icon} *{b["name"]}* (ID: {b["id"]})\n'
                f'   💰 Saldo: *{saldo_str}*\n'
                f'   🏁 Saldo Awal: {format_rupiah(b["initial_balance"])}\n'
                f'   📈 Masuk: {masuk_str}  📉 Keluar: {keluar_str}'
            )

        lines.append(f'\n💼 *Total semua rekening: {format_rupiah(total)}*')
        lines.append(
            '\nCmd:\n'
            '`/bank tambah <nama> <saldo>`  — Tambah\n'
            '`/bank hapus <id>`  — Hapus\n'
            '`/bank set <tx_id> <bank_id>`  — Assign transaksi'
        )

        # Edit + Delete buttons per bank
        buttons = [
            [
                InlineKeyboardButton(f'✏️ {b["name"][:15]}', callback_data=f'bank_edit_{b["id"]}'),
                InlineKeyboardButton(f'🗑️ Hapus', callback_data=f'bank_del_{b["id"]}'),
            ]
            for b in banks
        ]

        return await reply_md('\n'.join(lines), reply_markup=InlineKeyboardMarkup(buttons) if buttons else None)

    # ── tambah ─────────────────────────────────────────────
    elif sub == 'tambah':
        if len(args) < 2:
            return await reply_md(
                '❌ Format: `/bank tambah <nama> [saldo_awal]`\n'
                'Contoh: `/bank tambah Mandiri 5000000`'
            )
        # Parse saldo dari arg terakhir jika angka
        last = args[-1].replace('.', '').replace(',', '')
        try:
            saldo_awal = float(last)
            name_parts = args[1:-1]
        except ValueError:
            saldo_awal = 0.0
            name_parts = args[1:]

        if not name_parts:
            return await reply_md('❌ Nama bank tidak boleh kosong.')

        name = ' '.join(name_parts)
        try:
            bank = add_bank_account(primary_id, name, saldo_awal)
            icon = _bank_icon(name)
            return await reply_md(
                f'{icon} *Rekening ditambahkan!*\n\n'
                f'🏦 Nama: *{bank["name"]}*\n'
                f'💰 Saldo Awal: *{format_rupiah(bank["initial_balance"])}*\n'
                f'🆔 ID Bank: `{bank["id"]}`\n\n'
                f'Assign transaksi: `/bank set <tx_id> {bank["id"]}`'
            )
        except Exception as e:
            return await reply_md(f'❌ Gagal tambah rekening: {e}')

    # ── hapus ──────────────────────────────────────────────
    elif sub == 'hapus':
        if len(args) < 2 or not args[1].isdigit():
            return await reply_md('❌ Format: `/bank hapus <id>`')
        bank_id = int(args[1])
        try:
            deleted = delete_bank_account(primary_id, bank_id)
            icon = _bank_icon(deleted['name'])
            return await reply_md(
                f'🗑️ *Rekening dihapus!*\n\n'
                f'{icon} {deleted["name"]}\n'
                f'💰 Saldo Awal: {format_rupiah(deleted["initial_balance"])}'
            )
        except ValueError as e:
            return await reply_md(f'❌ {e}')

    # ── set (assign transaksi ke bank) ─────────────────────
    elif sub == 'set':
        if len(args) < 3 or not args[1].isdigit() or not args[2].isdigit():
            return await reply_md('❌ Format: `/bank set <tx_id> <bank_id>`')
        tx_id   = int(args[1])
        bank_id = int(args[2])
        try:
            set_transaction_bank(primary_id, tx_id, bank_id)
            db = get_db()
            bank_row = _row(db.execute('SELECT name FROM bank_accounts WHERE id=?', (bank_id,)))
            bank_name = bank_row['name'] if bank_row else f'Bank #{bank_id}'
            icon = _bank_icon(bank_name)
            return await reply_md(
                f'✅ *Transaksi #{tx_id}* → {icon} *{bank_name}*\n\n'
                f'Lihat semua rekening: /bank'
            )
        except ValueError as e:
            return await reply_md(f'❌ {e}')

    # ── edit ───────────────────────────────────────────────
    elif sub == 'edit':
        if len(args) < 3 or not args[1].isdigit():
            return await reply_md('❌ Format: `/bank edit <id> <nama_baru> [saldo_baru]`')
        bank_id = int(args[1])
        # Parse saldo dari arg terakhir jika angka
        last = args[-1].replace('.', '').replace(',', '')
        try:
            new_saldo = float(last)
            name_parts = args[2:-1]
        except ValueError:
            new_saldo = None
            name_parts = args[2:]
        new_name = ' '.join(name_parts) if name_parts else None
        try:
            updated = edit_bank_account(primary_id, bank_id, name=new_name, initial_balance=new_saldo)
            icon = _bank_icon(updated['name'])
            return await reply_md(
                f'✏️ *Rekening diperbarui!*\n\n'
                f'{icon} *{updated["name"]}*\n'
                f'💰 Saldo Awal: {format_rupiah(updated["initial_balance"])}'
            )
        except ValueError as e:
            return await reply_md(f'❌ {e}')

    else:
        return await reply_md(
            '🏦 *Bank — Perintah tersedia:*\n\n'
            '`/bank` — Lihat semua rekening\n'
            '`/bank tambah <nama> <saldo>` — Tambah rekening\n'
            '`/bank hapus <id>` — Hapus rekening\n'
            '`/bank set <tx_id> <bank_id>` — Assign transaksi ke bank\n'
            '`/bank edit <id> <nama> [saldo]` — Edit rekening'
        )


async def callback_bank_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hapus bank account dari inline button."""
    query = update.callback_query
    await query.answer()
    try:
        bank_id = int(query.data.split('_')[-1])
        chat    = query.message.chat
        wallet  = get_or_create_wallet('telegram', chat.id, chat.title or chat.first_name or 'Unknown')
        primary_id = resolve_wallet_id(wallet['id'])
        deleted = delete_bank_account(primary_id, bank_id)
        icon    = _bank_icon(deleted['name'])
        await query.edit_message_text(
            f'🗑️ *Rekening dihapus!*\n\n'
            f'{icon} {deleted["name"]}\n'
            f'💰 Saldo Awal: {format_rupiah(deleted["initial_balance"])}',
            parse_mode='Markdown',
        )
    except Exception as err:
        print(f'[TG bank_del] {err}')
        await query.answer('❌ Gagal hapus rekening.')


async def callback_bank_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tombol ✏️ Edit bank — minta user ketik nama/saldo baru."""
    query = update.callback_query
    await query.answer()
    try:
        bank_id = int(query.data.split('_')[-1])
        chat    = query.message.chat
        wallet  = get_or_create_wallet('telegram', chat.id, chat.title or chat.first_name or 'Unknown')
        primary_id = resolve_wallet_id(wallet['id'])

        from src.core.database import get_db, _row
        db  = get_db()
        row = _row(db.execute(
            'SELECT * FROM bank_accounts WHERE id=? AND wallet_id=?', (bank_id, primary_id)
        ))
        if not row:
            return await query.answer('❌ Rekening tidak ditemukan.')

        await query.edit_message_text(
            f'✏️ *Edit Rekening Bank*\n\n'
            f'Rekening: *{row["name"]}* (ID: {bank_id})\n'
            f'Saldo Awal Sekarang: {format_rupiah(row["initial_balance"])}\n\n'
            f'Ketik perintah edit:\n'
            f'`/bank edit {bank_id} <nama_baru> <saldo_baru>`\n\n'
            f'Contoh:\n'
            f'`/bank edit {bank_id} Mandiri Syariah 3000000`\n'
            f'`/bank edit {bank_id} {row["name"]} 5000000`  — ganti saldo saja',
            parse_mode='Markdown',
        )
    except Exception as err:
        print(f'[TG bank_edit] {err}')
        await query.answer('❌ Gagal memuat rekening.')


# ─── Auto-Tabung ──────────────────────────────────────────

async def cmd_autotabung(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /autotabung                      — lihat aturan aktif
    /autotabung set <persen> <goal>  — set aturan (mis. /autotabung set 10 Liburan)
    /autotabung hapus <goal>         — hapus aturan
    """
    wallet = get_wallet(update)
    args   = context.args or []
    subcmd = args[0].lower() if args else 'lihat'

    if subcmd == 'set':
        if len(args) < 3:
            await reply_md(update,
                '⚙️ Format: `/autotabung set <persen> <nama_goal>`\n\n'
                'Contoh: `/autotabung set 10 Liburan`\n'
                '_Artinya: setiap pemasukan, 10% otomatis masuk ke goal Liburan._'
            )
            return
        try:
            pct = float(args[1].replace('%', ''))
        except ValueError:
            await update.message.reply_text('❌ Persentase tidak valid. Contoh: 10 atau 10%')
            return
        goal_name = ' '.join(args[2:])
        try:
            result = set_auto_savings(wallet['id'], goal_name, pct)
            await reply_md(update,
                f'✅ *Auto-Tabung Diaktifkan!*\n\n'
                f'🎯 Goal: *{result["goal_name"]}*\n'
                f'💹 Alokasi: *{result["percentage"]}%* dari setiap pemasukan\n\n'
                f'_Mulai sekarang, setiap `/catat masuk` akan otomatis menabung._'
            )
        except ValueError as err:
            await reply_md(update, f'❌ {err}')

    elif subcmd in ('hapus', 'del', 'delete', 'remove'):
        if len(args) < 2:
            await update.message.reply_text('❌ Sebutkan nama goal yang ingin dihapus.\nContoh: `/autotabung hapus Liburan`', parse_mode='Markdown')
            return
        goal_name = ' '.join(args[1:])
        ok = delete_auto_savings(wallet['id'], goal_name)
        if ok:
            await update.message.reply_text(f'🗑️ Aturan auto-tabung untuk *{goal_name}* dihapus.', parse_mode='Markdown')
        else:
            await update.message.reply_text(f'❌ Aturan untuk *{goal_name}* tidak ditemukan.', parse_mode='Markdown')

    else:  # lihat
        rules = get_auto_savings(wallet['id'])
        if not rules:
            await reply_md(update,
                '💤 *Belum ada aturan auto-tabung.*\n\n'
                'Buat dengan:\n'
                '`/autotabung set 10 Liburan`\n'
                '_= 10% dari setiap pemasukan → goal Liburan_'
            )
            return
        total_pct = sum(r['percentage'] for r in rules)
        lines = '\n'.join(
            f'  • *{r["goal_name"]}*: {r["percentage"]}%'
            for r in rules
        )
        await reply_md(update,
            f'🏦 *Auto-Tabung Aktif*\n\n{lines}\n\n'
            f'📊 Total dialokasikan: *{total_pct}%* dari setiap pemasukan\n\n'
            f'_Gunakan `/autotabung hapus <goal>` untuk menonaktifkan._'
        )


# ─── Transfer Antar Bank ──────────────────────────────────

async def cmd_transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /transfer <bank_asal> <bank_tujuan> <jumlah> [catatan]
    Contoh: /transfer jago ocbc 500rb
            /transfer mandiri bca 2jt bayar cicilan
    """
    wallet = get_wallet(update)
    args = context.args or []

    if len(args) < 3:
        await reply_md(update,
            '💸 *Transfer Antar Bank*\n\n'
            'Format: `/transfer <asal> <tujuan> <jumlah> [catatan]`\n\n'
            'Contoh:\n'
            '`/transfer jago ocbc 500rb`\n'
            '`/transfer mandiri bca 2jt bayar cicilan`\n\n'
            '_Ketik `/bank` untuk melihat daftar rekening._'
        )
        return

    bank_asal_q  = args[0]
    bank_tuju_q  = args[1]
    amount_raw   = args[2]
    note         = ' '.join(args[3:]) if len(args) > 3 else ''

    amount = parse_jumlah(amount_raw)
    if not amount or amount <= 0:
        await update.message.reply_text(f'❌ Jumlah tidak valid: `{amount_raw}`', parse_mode='Markdown')
        return

    from_bank = find_bank_by_name(wallet['id'], bank_asal_q)
    if not from_bank:
        await reply_md(update,
            f'❌ Bank asal *{bank_asal_q}* tidak ditemukan.\n'
            'Ketik `/bank` untuk melihat daftar rekening.'
        )
        return

    to_bank = find_bank_by_name(wallet['id'], bank_tuju_q)
    if not to_bank:
        await reply_md(update,
            f'❌ Bank tujuan *{bank_tuju_q}* tidak ditemukan.\n'
            'Ketik `/bank` untuk melihat daftar rekening.'
        )
        return

    if from_bank['id'] == to_bank['id']:
        await update.message.reply_text('❌ Rekening asal dan tujuan tidak boleh sama.')
        return

    try:
        result = transfer_bank(
            wallet['id'],
            from_bank['id'],
            to_bank['id'],
            amount,
            note=note,
            created_by=str(update.effective_user.id),
        )
        icon_from = from_bank.get('icon', '🏦')
        icon_to   = to_bank.get('icon', '🏦')
        amt_fmt   = format_rupiah(amount)
        note_line = f'\n📝 _{note}_' if note else ''
        await reply_md(update,
            f'💸 *Transfer Berhasil!*\n\n'
            f'{icon_from} *{from_bank["name"]}*  →  {icon_to} *{to_bank["name"]}*\n'
            f'💰 {amt_fmt}{note_line}\n\n'
            f'_ID transaksi: #{result["trx_out_id"]} (keluar) & #{result["trx_in_id"]} (masuk)_'
        )
    except ValueError as err:
        await update.message.reply_text(f'❌ {err}')
    except Exception as err:
        print(f'[TG /transfer] {err}')
        await update.message.reply_text('❌ Gagal melakukan transfer.')


# ─── Ringkasan Manual ──────────────────────────────────────

async def cmd_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /summary          — ringkasan bulan ini
    /summary minggu   — ringkasan 7 hari terakhir
    """
    wallet = get_wallet(update)
    args   = context.args or []
    period = (args[0].lower() if args else 'bulan')

    try:
        now = datetime.now()
        if period in ('minggu', 'week', '7hari'):
            lap = get_laporan(wallet['id'], 'minggu')
            period_label = '7 Hari Terakhir'
        else:
            lap = get_laporan(wallet['id'], 'bulan')
            period_label = f'{NAMA_BULAN[now.month - 1]} {now.year}'

        masuk  = lap.get('total_masuk', 0)
        keluar = lap.get('total_keluar', 0)
        selisih = masuk - keluar
        selisih_label = '📈 Surplus' if selisih >= 0 else '📉 Defisit'
        selisih_emoji = '🟢' if selisih >= 0 else '🔴'
        trx_count = lap.get('count', 0)

        # Top kategori
        kat_lines = ''
        kat_data = lap.get('by_category', {})
        if kat_data:
            top = sorted(kat_data.items(), key=lambda x: x[1].get('total', 0), reverse=True)[:3]
            kat_lines = '\n'.join(
                f'  • {k.capitalize()}: {format_rupiah(v.get("total", 0))}'
                for k, v in top
            )
            kat_lines = f'\n\n📂 *Top Kategori:*\n{kat_lines}'

        # Proyeksi akhir bulan (hanya untuk mode bulan)
        proj_line = ''
        if period not in ('minggu', 'week', '7hari'):
            try:
                proj = get_proyeksi_bulan(wallet['id'])
                if proj:
                    proj_line = (
                        f'\n\n🔮 *Proyeksi Akhir Bulan:*\n'
                        f'  Estimasi pengeluaran: {format_rupiah(proj.get("proyeksi_keluar_tersisa", 0))}\n'
                        f'  Estimasi sisa: {format_rupiah(proj.get("proyeksi_saldo_akhir_bulan", 0))}'
                    )
            except Exception:
                pass

        text = (
            f'📊 *Ringkasan {period_label}*\n\n'
            f'💚 Pemasukan:  {format_rupiah(masuk)}\n'
            f'🔴 Pengeluaran: {format_rupiah(keluar)}\n'
            f'{selisih_emoji} {selisih_label}: {format_rupiah(abs(selisih))}\n'
            f'🔢 Transaksi: {trx_count}'
            f'{kat_lines}{proj_line}'
        )
        await reply_md(update, text)
    except Exception as err:
        print(f'[TG /summary] {err}')
        await update.message.reply_text('❌ Gagal mengambil ringkasan.')


# ─── NLP Text Handler ──────────────────────────────────────

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan menu utama dengan inline keyboard."""
    keyboard = [
        [
            InlineKeyboardButton('💰 Saldo', callback_data='menu_saldo'),
            InlineKeyboardButton('📝 Laporan', callback_data='menu_laporan'),
            InlineKeyboardButton('📜 History', callback_data='menu_history'),
        ],
        [
            InlineKeyboardButton('🎯 Goals', callback_data='menu_target'),
            InlineKeyboardButton('💸 Budget', callback_data='menu_budget'),
            InlineKeyboardButton('🔁 Rutin', callback_data='menu_rutin'),
        ],
        [
            InlineKeyboardButton('📊 Grafik', callback_data='menu_grafik'),
            InlineKeyboardButton('📈 Trend', callback_data='menu_trend'),
            InlineKeyboardButton('🧠 Analisis', callback_data='menu_analisis'),
        ],
        [
            InlineKeyboardButton('💎 Kekayaan', callback_data='menu_kekayaan'),
            InlineKeyboardButton('🛍️ Wishlist', callback_data='menu_wishlist'),
            InlineKeyboardButton('💱 Kurs', callback_data='menu_kurs'),
        ],
        [
            InlineKeyboardButton('🏦 Bank', callback_data='menu_bank'),
            InlineKeyboardButton('⏰ Reminder', callback_data='menu_reminder'),
            InlineKeyboardButton('🔗 Wallet', callback_data='menu_wallet'),
        ],
        [
            InlineKeyboardButton('📤 Export', callback_data='menu_export'),
            InlineKeyboardButton('↩️ Undo', callback_data='menu_undo'),
            InlineKeyboardButton('🌐 Bahasa', callback_data='menu_bahasa'),
        ],
        [
            InlineKeyboardButton('❓ Help', callback_data='menu_help'),
        ],
    ]

    # Tambah tombol Dashboard jika DASHBOARD_URL sudah diset
    if config.DASHBOARD_URL:
        keyboard.append([
            InlineKeyboardButton(
                '🌐 Buka Dashboard',
                web_app=WebAppInfo(url=config.DASHBOARD_URL),
            )
        ])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        '🏦 *Bot Simpan Uang*\n\nPilih menu di bawah atau langsung ketik transaksi:\n_Contoh: `50rb makan siang`_',
        parse_mode='Markdown',
        reply_markup=reply_markup,
    )


async def cmd_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kirim link dashboard."""
    if not config.DASHBOARD_URL:
        return await reply_md(update,
            '🌐 *Dashboard belum dikonfigurasi.*\n\n'
            'Tambahkan `DASHBOARD_URL=https://...` di file `.env`\n'
            'lalu jalankan: `python dashboard.py`\n\n'
            '_Lihat instruksi di README untuk setup ngrok / Railway._'
        )
    keyboard = [[InlineKeyboardButton('🌐 Buka Dashboard', web_app=WebAppInfo(url=config.DASHBOARD_URL))]]
    await update.message.reply_text(
        f'🌐 *Dashboard Keuangan*\n\n{config.DASHBOARD_URL}\n\n_Tap tombol di bawah untuk buka:_',
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def callback_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle tombol menu utama."""
    query = update.callback_query
    await query.answer()
    data = query.data  # e.g. 'menu_saldo'
    action = data.replace('menu_', '')

    # Pesan panduan per fitur
    guides = {
        'saldo':    '💰 *Saldo*\n\n`/saldo` — lihat saldo semua mata uang',
        'laporan':  '📝 *Laporan*\n\n`/laporan hari` — hari ini\n`/laporan minggu` — 7 hari terakhir\n`/laporan bulan` — bulan ini',
        'history':  '📜 *History*\n\n`/history` — 10 transaksi terakhir\n`/history 20` — 20 transaksi terakhir',
        'target':   '🎯 *Goals / Tabungan*\n\n`/target` — lihat semua goals\n`/target buat Liburan 5000000` — buat goal baru\n`/target hapus Liburan` — hapus goal\n`/tabung 100rb Liburan` — setor dana ke goal',
        'budget':   '💸 *Budget*\n\n`/budget` — lihat budget bulan ini\n`/budget makan 500rb` — set budget kategori\n`/budget hapus makan` — hapus budget',
        'rutin':    '🔁 *Transaksi Rutin*\n\n`/rutin` — lihat daftar rutin\n`/rutin tambah keluar 150rb netflix 5` — tiap tgl 5\n`/rutin hapus [id]` — hapus rutin',
        'grafik':   '📊 *Grafik*\n\n`/grafik` — bar chart bulan ini\n`/grafik hari` — hari ini\n`/grafik minggu` — minggu ini',
        'trend':    '📈 *Trend Bulanan*\n\n`/trend` — 6 bulan terakhir\n`/trend 3` — 3 bulan\n`/trend 12` — 12 bulan',
        'analisis': '🧠 *Analisis Keuangan*\n\n`/analisis` — savings rate, rata-rata harian, tips',
        'kekayaan': '💎 *Kekayaan*\n\n`/kekayaan` — total aset bersih semua mata uang',
        'wishlist':  '🛍️ *Wishlist*\n\n`/wishlist` — lihat daftar\n`/wishlist tambah PS5 8000000` — tambah item\n`/wishlist hapus PS5` — hapus item',
        'kurs':     '💱 *Kurs*\n\n`/kurs` — lihat kurs populer live\n`/kurs JPY` — cek kurs spesifik\n`/kurs set THB 435` — set kurs manual\n`/kurs update` — refresh dari server',
        'bank':     '🏦 *Rekening Bank*\n\n`/bank` — lihat semua rekening\n`/bank tambah Mandiri 5000000` — tambah rekening\n`/bank hapus <id>` — hapus rekening\n`/bank set <tx_id> <bank_id>` — assign transaksi ke bank\n`/bank edit <id> <nama> [saldo]` — edit rekening',
        'reminder': '⏰ *Reminder*\n\n`/reminder 20:00` — set notif harian jam 20:00\n`/reminder off` — matiin reminder',
        'wallet':   '🔗 *Share Wallet*\n\n`/wallet share` — buat kode undangan\n`/wallet gabung KODE` — gabung ke wallet orang\n`/wallet pisah` — berhenti berbagi\n`/wallet info` — info wallet saat ini',
        'export':   '📤 *Export Data*\n\n`/export` — download CSV semua transaksi\n`/export bulan` — bulan ini saja',
        'undo':     '↩️ *Undo*\n\n`/undo` — hapus transaksi terakhir',
        'bahasa':   '🌐 *Bahasa*\n\n`/bahasa id` — ganti ke Bahasa Indonesia\n`/bahasa en` — switch to English',
        'help':     '❓ *Help*\n\n`/help` — lihat semua perintah lengkap',
    }

    msg = guides.get(action, '❓ Menu tidak ditemukan.')
    await query.edit_message_text(
        text=msg + '\n\n_Ketik perintah di atas, atau /menu untuk kembali ke menu._',
        parse_mode='Markdown',
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle foto yang dikirim — scan struk / receipt OCR."""
    if not update.message or not update.message.photo:
        return
    try:
        from src.core.ocr import scan_receipt, OCR_AVAILABLE
        if not OCR_AVAILABLE:
            return await reply_md(update,
                '❌ *OCR belum tersedia*\n\n'
                'Untuk scan struk, install dulu:\n'
                '1. `pip install pytesseract Pillow`\n'
                '2. Install Tesseract OCR dari tesseract-ocr.github.io\n\n'
                '_Setelah install, kirim ulang foto struk._'
            )

        # Ambil foto resolusi terbaik
        photo = update.message.photo[-1]
        tg_file = await photo.get_file()
        buf = io.BytesIO()
        await tg_file.download_to_memory(buf)
        image_bytes = buf.getvalue()

        await update.message.reply_text('🔍 Sedang scan struk...')

        result = scan_receipt(image_bytes)
        amount   = result.get('amount')
        category = result.get('category', 'umum')
        note     = result.get('note', 'struk')

        if not amount or amount <= 0:
            preview = '\n'.join(result.get('raw_lines', [])[:5])
            return await reply_md(update,
                f'❓ *Tidak bisa baca nominal dari struk.*\n\n'
                f'Teks terbaca:\n```\n{preview}\n```\n\n'
                f'Coba catat manual: `/catat keluar [jumlah] [catatan]`'
            )

        wallet = get_wallet(update)
        tx = add_transaction(
            wallet['id'], 'out', amount, note, category,
            update.effective_user.first_name or 'OCR'
        )

        msg = (
            f'📸 *Struk berhasil discan!*\n\n'
            f'{format_transaksi(tx, wallet["lang"])}\n\n'
            f'_Catatan OCR: "{note}" · {category}_\n'
            f'_Ketik /undo jika ingin batalkan_'
        )
        await reply_md(update, msg)

    except Exception as err:
        print(f'[TG OCR] {err}')
        await reply_md(update,
            '❌ Gagal scan struk. Coba foto ulang dengan pencahayaan yang lebih baik.\n'
            'Atau catat manual: `/catat keluar [jumlah] [catatan]`'
        )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle file CSV mutasi rekening yang dikirim."""
    if not update.message or not update.message.document:
        return

    doc = update.message.document
    fname = (doc.file_name or '').lower()

    # Hanya proses file CSV
    if not fname.endswith('.csv'):
        return  # Biarkan, mungkin handler lain atau diabaikan

    try:
        tg_file = await doc.get_file()
        buf = io.BytesIO()
        await tg_file.download_to_memory(buf)
        csv_bytes = buf.getvalue()

        await update.message.reply_text('⏳ Sedang import mutasi CSV...')

        from src.core.csv_import import import_csv_mutasi
        wallet = get_wallet(update)
        result = import_csv_mutasi(
            wallet_id  = wallet['id'],
            csv_bytes  = csv_bytes,
            created_by = f'csv-{update.effective_user.first_name or "import"}'
        )

        imported = result['imported']
        skipped  = result['skipped']
        bank     = result['bank']
        errors   = result.get('errors', [])

        msg = (
            f'📥 *Import Mutasi Selesai!*\n\n'
            f'🏦 Bank terdeteksi: *{bank}*\n'
            f'✅ Berhasil diimport: *{imported} transaksi*\n'
            f'⏭️ Dilewati: *{skipped} baris*'
        )
        if errors:
            msg += f'\n\n⚠️ _Beberapa error (maks 5):_\n'
            for e in errors[:5]:
                msg += f'• {e}\n'

        if imported == 0:
            msg += '\n\n_Tidak ada transaksi yang bisa diimport. Cek format CSV bank kamu._'
        else:
            saldo = get_saldo(wallet['id'])['saldo']
            msg += f'\n\n💰 Saldo sekarang: *{format_rupiah(saldo)}*'

        await reply_md(update, msg)

    except ValueError as e:
        await reply_error(update, f'❌ Format CSV tidak valid: {e}')
    except Exception as err:
        print(f'[TG CSV Import] {err}')
        await reply_error(update, '❌ Gagal import CSV. Pastikan file adalah mutasi rekening bank.')


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pesan teks biasa — NLP catat cepat."""
    if not update.message or not update.message.text:
        return
    if update.message.text.startswith('/'):
        return

    nlp = parse_nlp(update.message.text)
    if not nlp:
        return

    try:
        wallet = get_wallet(update)
        today = datetime.now().strftime('%Y-%m-%d')
        tx = add_transaction(
            wallet['id'], nlp['type'], nlp['amount'], nlp['note'], 'umum',
            update.effective_user.first_name or 'Unknown',
        )

        budget_alert = check_budget_alert(wallet['id'], tx['category'])
        msg = format_transaksi(tx, wallet['lang'])
        if budget_alert:
            msg += f'\n\n⚠️ Budget {budget_alert["category"]}: {budget_alert["persen"]}% terpakai'

        msg += '\n\n_Ketik /undo untuk batalkan_' if wallet['lang'] == 'id' else '\n\n_Tap /undo to cancel_'

        await update.message.reply_text(
            msg,
            parse_mode='Markdown',
            reply_markup=build_trx_keyboard(tx['id']),
        )
    except Exception as err:
        print(f'[TG NLP] {err}')
        # Diam saja jika error — user mungkin hanya chat biasa


# ─── Callback Query Handlers ──────────────────────────────

async def callback_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tx_id = query.data.split('_')[1]
    await query.message.reply_text(
        f'✏️ *Edit Transaksi #{tx_id}*\n\nGunakan perintah:\n`/edit {tx_id} [jumlah] [catatan]`',
        parse_mode='Markdown',
    )


async def callback_hapus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tx_id = int(query.data.split('_')[1])
    try:
        chat = query.message.chat
        wallet = get_or_create_wallet('telegram', chat.id, chat.title or chat.first_name or 'Unknown')
        primary_id = resolve_wallet_id(wallet['id'])
        delete_transaction(primary_id, tx_id)
        await query.edit_message_text(f'✅ Transaksi #{tx_id} berhasil dihapus.', parse_mode='Markdown')
    except Exception as err:
        print(f'[TG action hapus] {err}')
        await query.answer('❌ Gagal hapus transaksi.')


async def callback_saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        chat = query.message.chat
        wallet = get_or_create_wallet('telegram', chat.id, chat.title or chat.first_name or 'Unknown')
        primary_id = resolve_wallet_id(wallet['id'])
        wallet_dict = dict(wallet)
        wallet_dict['lang'] = get_lang(primary_id)
        data = get_saldo_multi_currency(primary_id)
        text = format_saldo(data, wallet_dict['lang'])
        sr = get_savings_rate(primary_id)
        if sr.get('masuk', 0) > 0:
            bar = build_savings_bar(sr['rate'])
            text += f'\n\n📊 Savings Rate: {bar} *{sr["rate"]}%*'
        await query.message.reply_text(text, parse_mode='Markdown')
    except Exception as err:
        print(f'[TG action saldo] {err}')
        await query.answer('❌ Gagal ambil saldo.')


async def callback_goal_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        goal_id = int(query.data.split('_')[-1])
        chat = query.message.chat
        wallet = get_or_create_wallet('telegram', chat.id, chat.title or chat.first_name or 'Unknown')
        primary_id = resolve_wallet_id(wallet['id'])
        db = get_db()
        goal_row = _row(db.execute(
            'SELECT * FROM goals WHERE id = ? AND wallet_id = ?', (goal_id, primary_id)
        ))
        if not goal_row:
            return await query.answer('❌ Goal tidak ditemukan.')
        deleted = delete_goal(primary_id, goal_row['name'])
        await query.edit_message_text(
            f'🗑️ *Goal dihapus!*\n\n🎯 {deleted["name"]}\n'
            f'Dana terkumpul: {format_rupiah(deleted["current_amount"] or 0)}',
            parse_mode='Markdown',
        )
    except Exception as err:
        print(f'[TG goal_del] {err}')
        await query.answer('❌ Gagal hapus goal.')


async def callback_wl_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        wishlist_id = int(query.data.split('_')[-1])
        chat = query.message.chat
        wallet = get_or_create_wallet('telegram', chat.id, chat.title or chat.first_name or 'Unknown')
        items = get_wishlists(wallet['id'])
        item = next((i for i in items if i['id'] == wishlist_id), None)
        deleted = delete_wishlist(wallet['id'], wishlist_id)
        if deleted:
            await query.edit_message_text(
                f'✅ *{item.get("name") or "Item"}* dihapus dari wishlist.',
                parse_mode='Markdown',
            )
        else:
            await query.message.reply_text('❌ Item tidak ditemukan.')
    except Exception as err:
        print(f'[TG wl_del] {err}')


# ─── Utang & Piutang ──────────────────────────────────────

async def cmd_hutang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /hutang <orang> <jumlah> [catatan] — catat utang (saya yang berhutang)
    /piutang <orang> <jumlah> [catatan] — catat piutang (orang lain berhutang ke saya)
    /hutang lihat — lihat semua utang/piutang
    /hutang lunas <id> — tandai lunas
    /hutang hapus <id> — hapus catatan
    """
    try:
        args = context.args or []
        cmd_name = update.message.text.split('@')[0].lstrip('/').split()[0].lower()
        # cmd_name: 'hutang' atau 'piutang'

        sub = args[0].lower() if args else ''

        wallet = get_wallet(update)
        wid = wallet['id']

        # ── /hutang lihat  ─────────────────────────────────────────────────
        if sub == 'lihat' or not args:
            utang    = get_debts(wid, type_='utang')
            piutang  = get_debts(wid, type_='piutang')

            lines = ['💳 *Utang & Piutang*\n']

            if utang:
                lines.append('🔴 *Saya berhutang ke:*')
                for d in utang:
                    tgl = f' _(jatuh: {d["due_date"]})_' if d.get('due_date') else ''
                    note_str = f' — _{d["note"]}_' if d.get('note') else ''
                    lines.append(f'  #{d["id"]} {d["person"]}: {format_rupiah(d["amount"])}{note_str}{tgl}')
            else:
                lines.append('🔴 Tidak ada utang 🎉')

            lines.append('')

            if piutang:
                lines.append('💚 *Orang yang berhutang ke saya:*')
                for d in piutang:
                    tgl = f' _(jatuh: {d["due_date"]})_' if d.get('due_date') else ''
                    note_str = f' — _{d["note"]}_' if d.get('note') else ''
                    lines.append(f'  #{d["id"]} {d["person"]}: {format_rupiah(d["amount"])}{note_str}{tgl}')
            else:
                lines.append('💚 Tidak ada piutang')

            total_utang   = sum(d['amount'] for d in utang)
            total_piutang = sum(d['amount'] for d in piutang)
            lines.append(f'\n📊 Total utang: {format_rupiah(total_utang)}')
            lines.append(f'📊 Total piutang: {format_rupiah(total_piutang)}')
            lines.append(
                '\n_Tip: `/hutang lunas <id>` untuk tandai lunas_\n'
                '_`/hutang hapus <id>` untuk hapus_'
            )
            return await reply_md(update, '\n'.join(lines))

        # ── /hutang lunas <id>  ────────────────────────────────────────────
        if sub == 'lunas':
            if len(args) < 2:
                return await reply_error(update, 'Format: `/hutang lunas <id>`')
            try:
                debt_id = int(args[1])
            except ValueError:
                return await reply_error(update, 'ID harus angka. Lihat `/hutang lihat` untuk ID.')
            result = mark_debt_paid(wid, debt_id)
            if not result:
                return await reply_error(update, f'Catatan #{debt_id} tidak ditemukan.')
            tipe_str = '🔴 Utang' if result['type'] == 'utang' else '💚 Piutang'
            return await reply_md(update,
                f'✅ *Lunas!*\n\n'
                f'{tipe_str} ke *{result["person"]}*\n'
                f'💵 {format_rupiah(result["amount"])}\n'
                f'📅 Lunas pada: {result["paid_at"][:10]}'
            )

        # ── /hutang hapus <id>  ────────────────────────────────────────────
        if sub == 'hapus':
            if len(args) < 2:
                return await reply_error(update, 'Format: `/hutang hapus <id>`')
            try:
                debt_id = int(args[1])
            except ValueError:
                return await reply_error(update, 'ID harus angka.')
            deleted = delete_debt(wid, debt_id)
            if not deleted:
                return await reply_error(update, f'Catatan #{debt_id} tidak ditemukan.')
            return await reply_md(update, f'🗑️ Catatan #{debt_id} dihapus.')

        # ── Tambah utang/piutang baru  ─────────────────────────────────────
        # Format: /hutang <orang> <jumlah> [catatan] [jatuh: YYYY-MM-DD]
        if len(args) < 2:
            tipe = 'utang' if cmd_name == 'hutang' else 'piutang'
            return await reply_error(update,
                f'Format: `/{cmd_name} <orang> <jumlah> [catatan]`\n'
                f'Contoh: `/{cmd_name} Budi 500rb'\
                f'{"" if cmd_name == "hutang" else " beli laptop"}`'
            )

        person_raw = args[0]
        amount_raw = args[1]
        note_parts = args[2:]

        # Deteksi due_date di akhir note, format 'jatuh: 2026-12-31' atau tanggal ISO
        due_date = None
        note_final_parts = []
        for p in note_parts:
            m = re.match(r'^(\d{4}-\d{2}-\d{2})$', p)
            if m:
                due_date = m.group(1)
            else:
                note_final_parts.append(p)

        amount = parse_jumlah(amount_raw)
        if not amount or amount <= 0:
            return await reply_error(update, f'Jumlah tidak valid: *{amount_raw}*')

        tipe = 'utang' if cmd_name == 'hutang' else 'piutang'
        note = ' '.join(note_final_parts)

        debt = add_debt(wid, tipe, person_raw, amount, note, due_date)

        emoji = '🔴' if tipe == 'utang' else '💚'
        label = 'Utang' if tipe == 'utang' else 'Piutang'
        to_from = 'ke' if tipe == 'utang' else 'dari'
        tgl_str = f'\n📅 Jatuh tempo: {due_date}' if due_date else ''
        note_str = f'\n📝 Catatan: {note}' if note else ''

        await reply_md(update,
            f'{emoji} *{label} dicatat!*\n\n'
            f'👤 {to_from.capitalize()}: *{person_raw}*\n'
            f'💵 Jumlah: {format_rupiah(amount)}'
            f'{note_str}{tgl_str}\n\n'
            f'_Ketik `/hutang lihat` untuk melihat semua._'
        )

    except Exception as err:
        print(f'[TG /hutang] {err}')
        await reply_error(update, 'Gagal catat utang/piutang.')


# ─── Cicilan ──────────────────────────────────────────────

async def cmd_cicilan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /cicilan — lihat semua cicilan aktif
    /cicilan tambah <nama> <total_bulan> <cicilan_per_bulan> [tgl_jatuh]
    /cicilan bayar <id>
    /cicilan hapus <id>
    """
    try:
        args = context.args or []
        sub = args[0].lower() if args else 'lihat'
        wallet = get_wallet(update)
        wid = wallet['id']

        # ── Lihat  ─────────────────────────────────────────────────────────
        if sub == 'lihat' or not args:
            items = get_installments(wid)
            if not items:
                return await reply_md(update,
                    '📋 *Cicilan*\n\nBelum ada cicilan aktif.\n\n'
                    '_Tambah: `/cicilan tambah <nama> <total_bulan> <jumlah_per_bulan>`_'
                )
            lines = ['📋 *Cicilan Aktif*\n']
            total_monthly = 0
            for c in items:
                sisa = c['total_months'] - c['paid_months']
                total_monthly += c['monthly_amount']
                bar_filled = round(c['paid_months'] / c['total_months'] * 10)
                bar = '█' * bar_filled + '░' * (10 - bar_filled)
                lines.append(
                    f'#{c["id"]} *{c["name"]}*\n'
                    f'  [{bar}] {c["paid_months"]}/{c["total_months"]} bulan\n'
                    f'  {format_rupiah(c["monthly_amount"])}/bln · tgl {c["due_day"]} · sisa {sisa} bln\n'
                    f'  Total sisa: {format_rupiah(c["monthly_amount"] * sisa)}'
                )
            lines.append(f'\n💸 *Total cicilan/bulan: {format_rupiah(total_monthly)}*')
            lines.append('\n_`/cicilan bayar <id>` untuk bayar cicilan_')
            return await reply_md(update, '\n'.join(lines))

        # ── Bayar  ─────────────────────────────────────────────────────────
        if sub == 'bayar':
            if len(args) < 2:
                return await reply_error(update, 'Format: `/cicilan bayar <id>`')
            try:
                inst_id = int(args[1])
            except ValueError:
                return await reply_error(update, 'ID harus angka. Lihat `/cicilan` untuk ID.')
            result = pay_installment(wid, inst_id)
            if not result:
                return await reply_error(update, f'Cicilan #{inst_id} tidak ditemukan.')

            done_msg = '\n\n🎊 *Lunas! Semua cicilan sudah terbayar!*' if result.get('is_newly_done') else ''
            await reply_md(update,
                f'✅ *Cicilan dibayar!*\n\n'
                f'📝 {result["name"]}\n'
                f'💵 {format_rupiah(result["monthly_amount"])}\n'
                f'📊 Progress: {result["paid_months"]}/{result["total_months"]} bulan\n'
                f'🔢 Trx #{result.get("trx_id", "-")} dicatat otomatis'
                f'{done_msg}'
            )
            return

        # ── Hapus  ─────────────────────────────────────────────────────────
        if sub == 'hapus':
            if len(args) < 2:
                return await reply_error(update, 'Format: `/cicilan hapus <id>`')
            try:
                inst_id = int(args[1])
            except ValueError:
                return await reply_error(update, 'ID harus angka.')
            deleted = delete_installment(wid, inst_id)
            if not deleted:
                return await reply_error(update, f'Cicilan #{inst_id} tidak ditemukan.')
            return await reply_md(update, f'🗑️ Cicilan #{inst_id} dihapus.')

        # ── Tambah  ────────────────────────────────────────────────────────
        if sub == 'tambah':
            # /cicilan tambah <nama> <total_bulan> <jumlah_per_bulan> [tgl_jatuh]
            if len(args) < 4:
                return await reply_error(update,
                    'Format: `/cicilan tambah <nama> <total_bulan> <jumlah/bulan> [tgl_jatuh]`\n'
                    'Contoh: `/cicilan tambah Motor 36 500rb 10`'
                )
            name       = args[1]
            try:
                total_bln  = int(args[2])
            except ValueError:
                return await reply_error(update, 'Total bulan harus angka bulat.')
            amount_raw = args[3]
            monthly    = parse_jumlah(amount_raw)
            if not monthly or monthly <= 0:
                return await reply_error(update, f'Jumlah tidak valid: *{amount_raw}*')
            due_day = 1
            if len(args) >= 5:
                try:
                    due_day = int(args[4])
                except ValueError:
                    pass

            inst = add_installment(wid, name, total_bln, monthly, due_day)
            total_val = total_bln * monthly
            return await reply_md(update,
                f'✅ *Cicilan ditambahkan!*\n\n'
                f'📝 {inst["name"]}\n'
                f'💵 {format_rupiah(monthly)}/bulan × {total_bln} bulan\n'
                f'💰 Total: {format_rupiah(total_val)}\n'
                f'📅 Jatuh tempo: setiap tgl {due_day}\n\n'
                f'_Ketik `/cicilan` untuk lihat semua._'
            )

        await reply_error(update,
            'Subcommand tidak dikenal.\n'
            'Gunakan: `/cicilan lihat` · `/cicilan tambah` · `/cicilan bayar` · `/cicilan hapus`'
        )

    except Exception as err:
        print(f'[TG /cicilan] {err}')
        await reply_error(update, 'Gagal proses cicilan.')


# ─── Tagihan ──────────────────────────────────────────────

async def cmd_tagihan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /tagihan — lihat tagihan upcoming (7 hari ke depan)
    /tagihan semua — semua tagihan aktif
    /tagihan tambah <nama> <tgl_jatuh> [jumlah]
    /tagihan hapus <id>
    """
    try:
        args = context.args or []
        sub = args[0].lower() if args else ''
        wallet = get_wallet(update)
        wid = wallet['id']

        # ── Semua  ─────────────────────────────────────────────────────────
        if sub == 'semua':
            bills = get_bills(wid)
            if not bills:
                return await reply_md(update,
                    '🗒️ *Tagihan*\n\nBelum ada tagihan.\n\n'
                    '_Tambah: `/tagihan tambah <nama> <tgl_jatuh> [jumlah]`_'
                )
            lines = ['🗒️ *Semua Tagihan Aktif*\n']
            for b in bills:
                amt = f' — {format_rupiah(b["amount"])}' if b['amount'] > 0 else ''
                note_str = f' _{b["note"]}_' if b.get('note') else ''
                lines.append(f'#{b["id"]} *{b["name"]}* · tgl {b["due_day"]}{amt}{note_str}')
            lines.append('\n_`/tagihan hapus <id>` untuk hapus tagihan_')
            return await reply_md(update, '\n'.join(lines))

        # ── Tambah  ────────────────────────────────────────────────────────
        if sub == 'tambah':
            if len(args) < 3:
                return await reply_error(update,
                    'Format: `/tagihan tambah <nama> <tgl_jatuh> [jumlah]`\n'
                    'Contoh: `/tagihan tambah Netflix 15 150rb`\n'
                    'Contoh: `/tagihan tambah Listrik 20`'
                )
            name    = args[1]
            try:
                due_day = int(args[2])
            except ValueError:
                return await reply_error(update, 'Tanggal jatuh tempo harus angka (1–31).')
            amount = 0.0
            note_parts = []
            for a in args[3:]:
                val = parse_jumlah(a)
                if val and val > 0 and amount == 0:
                    amount = val
                else:
                    note_parts.append(a)
            note = ' '.join(note_parts)

            bill = add_bill(wid, name, due_day, amount, note)
            amt_str = f' ({format_rupiah(amount)})' if amount > 0 else ''
            return await reply_md(update,
                f'✅ *Tagihan ditambahkan!*\n\n'
                f'📄 {bill["name"]}{amt_str}\n'
                f'📅 Jatuh tempo: setiap tgl {due_day}\n\n'
                f'_Ketik `/tagihan` untuk lihat yang jatuh tempo minggu ini._'
            )

        # ── Hapus  ─────────────────────────────────────────────────────────
        if sub == 'hapus':
            if len(args) < 2:
                return await reply_error(update, 'Format: `/tagihan hapus <id>`')
            try:
                bill_id = int(args[1])
            except ValueError:
                return await reply_error(update, 'ID harus angka. Lihat `/tagihan semua` untuk ID.')
            deleted = delete_bill(wid, bill_id)
            if not deleted:
                return await reply_error(update, f'Tagihan #{bill_id} tidak ditemukan.')
            return await reply_md(update, f'🗑️ Tagihan #{bill_id} dihapus.')

        # ── Default: upcoming (7 hari)  ────────────────────────────────────
        upcoming = get_upcoming_bills(wid, days_ahead=7)
        all_bills = get_bills(wid)

        if not all_bills:
            return await reply_md(update,
                '🗒️ *Tagihan*\n\nBelum ada tagihan.\n\n'
                '_Tambah: `/tagihan tambah <nama> <tgl_jatuh> [jumlah]`_'
            )

        if not upcoming:
            return await reply_md(update,
                f'🗒️ *Tagihan*\n\n'
                f'✅ Tidak ada tagihan jatuh tempo 7 hari ke depan.\n\n'
                f'Total tagihan terdaftar: {len(all_bills)}\n'
                f'_Lihat semua: `/tagihan semua`_'
            )

        lines = ['🗒️ *Tagihan Jatuh Tempo (7 hari ke depan)*\n']
        for b in upcoming:
            days_left = b['days_left']
            if days_left == 0:
                urgency = '🔴 *HARI INI!*'
            elif days_left == 1:
                urgency = '🟠 *Besok*'
            elif days_left <= 3:
                urgency = f'🟡 {days_left} hari lagi'
            else:
                urgency = f'🟢 {days_left} hari lagi'
            amt = f' — {format_rupiah(b["amount"])}' if b['amount'] > 0 else ''
            lines.append(f'{urgency} *{b["name"]}*{amt} (tgl {b["due_day"]})')

        lines.append(f'\n_Total {len(all_bills)} tagihan. Lihat semua: `/tagihan semua`_')
        await reply_md(update, '\n'.join(lines))

    except Exception as err:
        print(f'[TG /tagihan] {err}')
        await reply_error(update, 'Gagal tampilkan tagihan.')


# ─── Financial Health Score ────────────────────────────────

async def cmd_skor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        wallet = get_wallet(update)
        s = get_health_score(wallet['id'])
        score = s['score']
        grade = s['grade']
        emoji_map = {'Excellent': '🏆', 'Good': '🌟', 'Fair': '📊', 'Needs Work': '⚠️'}
        emoji = emoji_map.get(grade, '📊')
        bd = s.get('breakdown', {})

        bar = progress_bar(score, 100, width=10)
        lines = [
            f'{emoji} *Financial Health Score*\n',
            f'`{bar}` *{score}/100* — _{grade}_\n',
            f'📦 *Breakdown:*',
            f'  💰 Savings Rate:      {bd.get("savings", 0):.0f}/30 pts',
            f'  📋 Budget Compliance: {bd.get("budget", 0):.0f}/25 pts',
            f'  🎯 Goal Progress:     {bd.get("goals", 0):.0f}/20 pts',
            f'  💳 Debt Ratio:        {bd.get("debt", 0):.0f}/15 pts',
            f'  🔥 Streak:            {bd.get("streak", 0):.0f}/10 pts',
        ]
        tips = s.get('tips', [])
        if tips:
            lines.append('\n💡 *Tips:*')
            for tip in tips[:3]:
                lines.append(f'  • _{tip}_')
        await reply_md(update, '\n'.join(lines))
    except Exception as err:
        print(f'[TG /skor] {err}')
        await reply_error(update, 'Gagal hitung skor keuangan.')


# ─── Dana Darurat ─────────────────────────────────────────

async def cmd_darutat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args or []
        wallet = get_wallet(update)

        if args and args[0].isdigit():
            months = int(args[0])
            if months not in (3, 6, 9, 12):
                return await reply_error(update, 'Pilih: 3, 6, 9, atau 12 bulan.')
            set_dana_darurat_months(wallet['id'], months)
            await reply_md(update, f'✅ Target dana darurat diubah ke *{months} bulan* pengeluaran.')
            # fallthrough to show info

        info = get_dana_darurat_info(wallet['id'])
        pct = info['pct']
        bar = progress_bar(pct, 100, width=12)

        status_raw = info['status']  # e.g. '✅ Aman' or '🔴 Kurang'
        status_emoji = ''  # already embedded in status string
        lines = [
            f'🛡️ *Dana Darurat Tracker*\n',
            f'Target: *{info["months"]} bulan* pengeluaran',
            f'Target jumlah: *{format_rupiah(info["target"])}*',
            f'Terkumpul: *{format_rupiah(info["current"])}*\n',
            f'`{bar}` *{pct:.0f}%* — {status_raw}',
        ]
        if info['sisa'] > 0:
            lines.append(f'\nKurang: *{format_rupiah(info["sisa"])}*')
        if info.get('saran_bulanan', 0) > 0:
            lines.append(f'Saran sisihkan/bln: *{format_rupiah(info["saran_bulanan"])}*')

        lines.append('\n_Ubah target: `/darutat 6` (untuk 6 bulan)_')
        lines.append('_Untuk menabung: `/target` atau `/tabung`_')
        await reply_md(update, '\n'.join(lines))
    except Exception as err:
        print(f'[TG /darutat] {err}')
        await reply_error(update, 'Gagal hitung dana darurat.')


# ─── Net Worth ────────────────────────────────────────────

async def cmd_networth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        wallet = get_wallet(update)
        nw = get_net_worth(wallet['id'])

        net = nw['net_worth']
        net_emoji = '🟢' if net >= 0 else '🔴'
        a = nw['aset']
        l = nw['liabilitas']

        lines = [
            f'💼 *Net Worth Tracker*\n',
            f'📈 *Total Aset:* {format_rupiah(a["total"])}',
            f'  🏦 Bank/Saldo: {format_rupiah(a["bank"])}',
            f'  🎯 Goals/Tabungan: {format_rupiah(a["goals"])}',
            f'  📊 Investasi: {format_rupiah(a["investasi"])}',
            f'\n📉 *Total Liabilitas:* {format_rupiah(l["total"])}',
            f'  💸 Utang: {format_rupiah(l["utang"])}',
            f'  🔄 Sisa Cicilan: {format_rupiah(l["cicilan"])}',
            f'\n{net_emoji} *Net Worth: {format_rupiah(net)}*',
        ]
        if net < 0:
            lines.append('\n_Net worth negatif — fokus lunasi utang dulu!_')
        else:
            lines.append('\n_Net worth positif — terus tingkatkan asetmu! 💪_')
        await reply_md(update, '\n'.join(lines))
    except Exception as err:
        print(f'[TG /networth] {err}')
        await reply_error(update, 'Gagal hitung net worth.')


# ─── Split Bill ───────────────────────────────────────────

async def cmd_split(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args or []
        wallet = get_wallet(update)

        # /split → list semua aktif
        if not args:
            splits = get_splits(wallet['id'], settled=False)
            if not splits:
                return await reply_md(update,
                    '🧾 *Split Bill*\n\n_Belum ada split bill aktif._\n\n'
                    'Buat baru: `/split baru <judul>`\n'
                    'Contoh: `/split baru Makan Malam SCBD`'
                )
            lines = ['🧾 *Split Bill Aktif*\n']
            for sp in splits:
                lines.append(f'• *#{sp["id"]}* — {sp["title"]} (Total: {format_rupiah(sp["total"])})')
            lines.append('\nDetail: `/split lihat <id>`')
            return await reply_md(update, '\n'.join(lines))

        sub = args[0].lower()

        # /split baru <judul>
        if sub == 'baru':
            title = ' '.join(args[1:])
            if not title:
                return await reply_error(update, 'Ketik judul split.\nContoh: `/split baru Makan Malam`')
            sp = create_split(wallet['id'], title)
            return await reply_md(update,
                f'✅ *Split Bill Dibuat!*\n\n'
                f'ID: *#{sp["id"]}*\nJudul: *{title}*\n\n'
                f'Tambah item: `/split tambah {sp["id"]} <nama> <jumlah>`\n'
                f'Contoh: `/split tambah {sp["id"]} Budi 150rb`'
            )

        # /split tambah <id> <nama> <jumlah>
        if sub == 'tambah':
            if len(args) < 4:
                return await reply_error(update, 'Format: `/split tambah <id> <nama> <jumlah>`')
            try:
                split_id = int(args[1])
            except ValueError:
                return await reply_error(update, 'ID harus angka.')
            amount = parse_jumlah(args[-1])
            if not amount:
                return await reply_error(update, 'Jumlah tidak valid.')
            person = ' '.join(args[2:-1])
            add_split_item(split_id, person, amount)
            sp = get_split(wallet['id'], split_id)
            total = sum(i['amount'] for i in sp.get('items', []))
            return await reply_md(update,
                f'✅ *Item ditambah!*\n\n'
                f'*{person}*: {format_rupiah(amount)}\n'
                f'Total sejauh ini: {format_rupiah(total)}\n\n'
                f'Lihat split: `/split lihat {split_id}`'
            )

        # /split lihat <id>
        if sub == 'lihat':
            if len(args) < 2:
                return await reply_error(update, 'Format: `/split lihat <id>`')
            try:
                split_id = int(args[1])
            except ValueError:
                return await reply_error(update, 'ID harus angka.')
            sp = get_split(wallet['id'], split_id)
            if not sp:
                return await reply_error(update, 'Split bill tidak ditemukan.')
            lines = [f'🧾 *{sp["title"]}* (#{sp["id"]})\n']
            items = sp.get('items', [])
            for item in items:
                paid_mark = '✅' if item['is_paid'] else '⬜'
                lines.append(f'{paid_mark} *{item["person"]}*: {format_rupiah(item["amount"])}')
            total = sum(i['amount'] for i in items)
            lines.append(f'\n💰 Total: *{format_rupiah(total)}*')
            if items:
                avg = total / len(items)
                lines.append(f'Per orang (rata-rata): *{format_rupiah(avg)}*')
            lines.append(f'\nHitung siapa bayar ke siapa: `/split hitung {split_id}`')
            lines.append(f'Tandai lunas per orang: `/split lunas {split_id} <nama>`')
            return await reply_md(update, '\n'.join(lines))

        # /split hitung <id>
        if sub == 'hitung':
            if len(args) < 2:
                return await reply_error(update, 'Format: `/split hitung <id>`')
            try:
                split_id = int(args[1])
            except ValueError:
                return await reply_error(update, 'ID harus angka.')
            settlements = calculate_split_settlement(split_id)
            if not settlements:
                return await reply_md(update, '✅ Semua sudah impas — tidak ada yang perlu transfer!')
            lines = ['💸 *Settlement Plan*\n', '_Siapa transfer ke siapa:_\n']
            for s in settlements:
                lines.append(f'→ *{s["from"]}* bayar *{s["to"]}* — {format_rupiah(s["amount"])}')
            lines.append(f'\nSetelah selesai: `/split settle {args[1]}`')
            return await reply_md(update, '\n'.join(lines))

        # /split lunas <id> <nama>
        if sub == 'lunas':
            if len(args) < 3:
                return await reply_error(update, 'Format: `/split lunas <id> <nama>`')
            try:
                split_id = int(args[1])
            except ValueError:
                return await reply_error(update, 'ID harus angka.')
            person = ' '.join(args[2:])
            ok = mark_split_item_paid(split_id, person)
            if ok:
                return await reply_md(update, f'✅ *{person}* ditandai sudah bayar!')
            return await reply_error(update, f'Nama "{person}" tidak ditemukan di split ini.')

        # /split settle <id>
        if sub == 'settle':
            if len(args) < 2:
                return await reply_error(update, 'Format: `/split settle <id>`')
            try:
                split_id = int(args[1])
            except ValueError:
                return await reply_error(update, 'ID harus angka.')
            settle_split(wallet['id'], split_id)
            return await reply_md(update, f'✅ Split bill *#{args[1]}* ditutup dan diselesaikan!')

        return await reply_error(update,
            '🧾 *Perintah Split Bill:*\n\n'
            '`/split` — lihat semua aktif\n'
            '`/split baru <judul>` — buat split baru\n'
            '`/split tambah <id> <nama> <jml>` — tambah item\n'
            '`/split lihat <id>` — detail split\n'
            '`/split hitung <id>` — siapa bayar ke siapa\n'
            '`/split lunas <id> <nama>` — tandai sudah bayar\n'
            '`/split settle <id>` — tutup split'
        )
    except Exception as err:
        print(f'[TG /split] {err}')
        await reply_error(update, str(err) or 'Gagal proses split bill.')


# ─── Investment Tracker ───────────────────────────────────

async def cmd_investasi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args or []
        wallet = get_wallet(update)

        if not args:
            # Portfolio summary
            summary = get_portfolio_summary(wallet['id'])
            invs = get_investments(wallet['id'], include_sold=False)
            if not invs:
                return await reply_md(update,
                    '📈 *Investment Tracker*\n\n'
                    '_Belum ada portofolio._\n\n'
                    'Tambah: `/investasi tambah <nama> <harga_beli> <qty>`\n'
                    'Contoh: `/investasi tambah BBCA 9500 100`'
                )
            lines = ['📈 *Portofolio Investasi*\n']
            for inv in invs:
                gain = ''
                if inv.get('current_value'):
                    pnl = inv['current_value'] - (inv['buy_price'] * inv['quantity'])
                    pnl_pct = (pnl / (inv['buy_price'] * inv['quantity'])) * 100
                    arrow = '▲' if pnl >= 0 else '▼'
                    gain = f' {arrow} {format_rupiah(abs(pnl))} ({pnl_pct:+.1f}%)'
                ticker = f' ({inv["ticker"]})' if inv.get('ticker') else ''
                modal = inv['buy_price'] * inv['quantity']
                lines.append(f'• *{inv["name"]}{ticker}*{gain}\n  Modal: {format_rupiah(modal)} | {inv["quantity"]} unit @ {format_rupiah(inv["buy_price"])}')
            lines.append(f'\n💰 Total Modal: *{format_rupiah(summary["total_modal"])}*')
            if summary.get('total_current'):
                total_pnl = summary['total_current'] - summary['total_modal']
                lines.append(f'📊 Total P&L: *{format_rupiah(total_pnl)}* ({(total_pnl/summary["total_modal"]*100) if summary["total_modal"] else 0:+.1f}%)')
            lines.append('\n`/investasi jual <id> <harga_jual>` — catat penjualan')
            lines.append('`/investasi hapus <id>` — hapus investasi')
            return await reply_md(update, '\n'.join(lines))

        sub = args[0].lower()

        # /investasi tambah <nama> <harga_beli> <qty> [ticker] [jenis]
        if sub == 'tambah':
            if len(args) < 4:
                return await reply_error(update,
                    'Format: `/investasi tambah <nama> <harga_beli> <qty>`\n'
                    'Opsional: `/investasi tambah BBCA 9500 100 BBCA saham`'
                )
            name = args[1]
            try:
                buy_price = float(args[2].replace(',', '.'))
                qty = float(args[3].replace(',', '.'))
            except ValueError:
                return await reply_error(update, 'Harga dan qty harus angka.')
            ticker = args[4].upper() if len(args) > 4 else None
            inv_type = args[5].lower() if len(args) > 5 else 'saham'
            from datetime import date
            inv = add_investment(wallet['id'], name, ticker, inv_type, buy_price, qty, date.today().isoformat())
            modal = buy_price * qty
            return await reply_md(update,
                f'✅ *Investasi ditambah!*\n\n'
                f'📊 *{name}*{f" ({ticker})" if ticker else ""}\n'
                f'Harga beli: {format_rupiah(buy_price)}/unit\n'
                f'Qty: {qty} unit\n'
                f'Modal: *{format_rupiah(modal)}*\n\n'
                f'ID: #{inv["id"]}'
            )

        # /investasi jual <id> <harga_jual>
        if sub == 'jual':
            if len(args) < 3:
                return await reply_error(update, 'Format: `/investasi jual <id> <harga_jual>`')
            try:
                inv_id = int(args[1])
                sell_price = float(args[2].replace(',', '.'))
            except ValueError:
                return await reply_error(update, 'ID dan harga harus angka.')
            result = sell_investment(wallet['id'], inv_id, sell_price)
            if not result:
                return await reply_error(update, 'Investasi tidak ditemukan.')
            gain = result.get('gain', 0)
            revenue = result.get('revenue', 0)
            modal = result.get('buy_price', 0) * result.get('quantity', 0)
            pnl_pct = (gain / modal * 100) if modal else 0
            arrow = '▲' if gain >= 0 else '▼'
            return await reply_md(update,
                f'✅ *Investasi Dijual!*\n\n'
                f'📊 *{result["name"]}*\n'
                f'Harga jual: {format_rupiah(sell_price)}/unit\n'
                f'Revenue: {format_rupiah(revenue)}\n'
                f'{arrow} Gain/Loss: *{format_rupiah(gain)} ({pnl_pct:+.1f}%)*\n\n'
                f'_Revenue otomatis dicatat sebagai pemasukan._'
            )

        # /investasi hapus <id>
        if sub == 'hapus':
            if len(args) < 2:
                return await reply_error(update, 'Format: `/investasi hapus <id>`')
            try:
                inv_id = int(args[1])
            except ValueError:
                return await reply_error(update, 'ID harus angka.')
            ok = delete_investment(wallet['id'], inv_id)
            if ok:
                return await reply_md(update, f'✅ Investasi *#{inv_id}* dihapus.')
            return await reply_error(update, 'Investasi tidak ditemukan.')

        return await reply_error(update,
            '📈 *Perintah Investasi:*\n\n'
            '`/investasi` — lihat portofolio\n'
            '`/investasi tambah <nama> <harga> <qty>` — tambah\n'
            '`/investasi jual <id> <harga_jual>` — catat jual\n'
            '`/investasi hapus <id>` — hapus'
        )
    except Exception as err:
        print(f'[TG /investasi] {err}')
        await reply_error(update, str(err) or 'Gagal proses investasi.')


# ─── Gamifikasi & Achievement ─────────────────────────────

async def cmd_pencapaian(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        wallet = get_wallet(update)
        earned = get_achievements(wallet['id'])
        earned_codes = {a['code'] for a in earned}

        ALL_ACHIEVEMENTS = {
            'first_trx':    ('🎉', 'First Transaction', 'Catat transaksi pertama'),
            'week_streak':  ('🔥', 'Week Streak', '7 hari berturut mencatat'),
            'month_streak': ('💎', 'Month Streak', '30 hari konsisten mencatat'),
            'saldo_1jt':    ('💰', 'Jutawan', 'Saldo tembus Rp 1 juta'),
            'saldo_10jt':   ('🤑', 'Miliuner', 'Saldo tembus Rp 10 juta'),
            'goal_done':    ('🏆', 'Goal Getter', 'Capai 1 goal tabungan'),
            'budget_master':('📋', 'Budget Master', 'Semua kategori under budget 1 bln'),
            'no_debt':      ('✨', 'Debt Free', 'Lunasin semua utang'),
            'savings_20':   ('📈', 'Savings Hero', 'Saving rate >20% dalam 1 bulan'),
            'invest_start': ('📊', 'Investor', 'Mulai investasi pertama'),
            'networth_pos': ('🌟', 'Net Worth Positif', 'Net worth kamu > 0'),
            'trx_100':      ('🏅', 'Century', 'Catat 100 transaksi'),
        }

        lines = [f'🏆 *Pencapaianmu* ({len(earned_codes)}/{len(ALL_ACHIEVEMENTS)})\n']
        unlocked = []
        locked = []
        for code, (icon, name, desc) in ALL_ACHIEVEMENTS.items():
            if code in earned_codes:
                unlocked.append(f'{icon} *{name}* — _{desc}_')
            else:
                locked.append(f'🔒 ~{name}~ — _{desc}_')

        if unlocked:
            lines.append('*✅ Sudah diraih:*')
            lines.extend(unlocked)
        if locked:
            lines.append('\n*🔒 Belum diraih:*')
            lines.extend(locked)

        if len(earned_codes) == len(ALL_ACHIEVEMENTS):
            lines.append('\n🎊 *WOW! Kamu sudah unlock semua achievement!*')
        await reply_md(update, '\n'.join(lines))
    except Exception as err:
        print(f'[TG /pencapaian] {err}')
        await reply_error(update, 'Gagal load pencapaian.')


# ═══════════════════════════════════════════════════════════════
# WAVE 3 — Command Handlers
# ═══════════════════════════════════════════════════════════════

# ─── /prediksi ───────────────────────────────────────────────

async def cmd_prediksi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prediksi saldo akhir bulan berdasarkan spending rate + pending bills."""
    try:
        wallet = get_wallet(update)
        pred = get_prediksi_saldo(wallet['id'])

        saldo_now  = pred['saldo_sekarang']
        saldo_pred = pred['saldo_prediksi']
        sisa       = pred['sisa_hari']
        hari_ini   = pred['hari_ini']
        total_hari = pred['total_hari']

        status_icon = '🚨' if pred['warning'] else ('⚠️' if saldo_pred < saldo_now * 0.3 else '✅')
        prog_bar = progress_bar(hari_ini, total_hari)

        lines = [
            f'🔮 *Prediksi Saldo Akhir Bulan*\n',
            f'{prog_bar}',
            f'_{hari_ini}/{total_hari} hari · {sisa} hari lagi_\n',
            f'💰 *Saldo sekarang:* {format_rupiah(saldo_now)}',
            f'{status_icon} *Prediksi akhir bulan:* {format_rupiah(saldo_pred)}\n',
            f'📊 *Detail kalkulasi:*',
            f'  · Proyeksi keluar: {format_rupiah(pred["proyeksi_keluar"])}',
            f'  · Proyeksi masuk:  {format_rupiah(pred["proyeksi_masuk"])}',
        ]
        if pred['pending_keluar'] > 0:
            lines.append(f'  · Tagihan pending: {format_rupiah(pred["pending_keluar"])}')
        if pred['pending_masuk'] > 0:
            lines.append(f'  · Income pending:  {format_rupiah(pred["pending_masuk"])}')

        daily_rate = pred['rate_keluar_harian']
        lines.append(f'\n📉 *Rata-rata harian:* {format_rupiah(daily_rate)}/hari')

        if pred['warning']:
            lines.append(
                f'\n🚨 *PERINGATAN!* Saldo diprediksi minus di akhir bulan!\n'
                f'Kurangi pengeluaran ≥ {format_rupiah(abs(saldo_pred)/max(sisa,1))}/hari '
                f'untuk balik ke positif.'
            )
        elif saldo_pred < saldo_now * 0.2:
            lines.append('\n⚠️ _Saldo tersisa sangat tipis di akhir bulan. Waspada!_')

        await reply_md(update, '\n'.join(lines))
    except Exception as err:
        print(f'[TG /prediksi] {err}')
        await reply_error(update, 'Gagal hitung prediksi.')


# ─── /laporan pdf ────────────────────────────────────────────

async def cmd_laporan_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Export laporan bulanan sebagai file PDF."""
    from datetime import date as _date
    args = context.args or []
    bulan_arg = args[0] if args else _date.today().strftime('%Y-%m')

    # Validasi format bulan
    import re
    if not re.match(r'^\d{4}-\d{2}$', bulan_arg):
        return await reply_md(update,
            '❌ Format bulan salah.\n\nContoh: `/laporan pdf 2026-10` atau `/laporan pdf` (bulan ini)')

    try:
        wallet = get_wallet(update)
        await update.message.reply_text(f'⏳ Membuat PDF laporan {bulan_arg}...')

        pdf_bytes = generate_laporan_pdf(wallet['id'], bulan_arg)

        import io as _io
        buf = _io.BytesIO(pdf_bytes)
        buf.name = f'laporan_{bulan_arg}.pdf'
        await update.message.reply_document(
            document=buf,
            filename=f'laporan_{bulan_arg}.pdf',
            caption=f'📄 Laporan Keuangan {bulan_arg}\nDibuat oleh MoneyBot 💰'
        )
    except ImportError as e:
        await reply_md(update,
            f'❌ *reportlab belum terpasang*\n\n'
            f'Install dulu dengan:\n`pip install reportlab --break-system-packages`\n\n'
            f'Atau gunakan export CSV: `/export`')
    except Exception as err:
        print(f'[TG /laporan pdf] {err}')
        await reply_error(update, f'Gagal buat PDF: {err}')


# ─── /subs ──────────────────────────────────────────────────

async def cmd_subs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /subs                   → lihat semua subscription
    /subs tambah [nama] [jumlah] [tanggal] [kategori]
    /subs hapus [id]
    /subs toggle [id]
    /subs upcoming          → jatuh tempo 7 hari ke depan
    """
    args = context.args or []
    sub  = args[0].lower() if args else 'lihat'

    try:
        wallet = get_wallet(update)

        # ── tambah
        if sub == 'tambah':
            if len(args) < 3:
                return await reply_md(update,
                    '❓ *Format:*\n`/subs tambah [nama] [jumlah] [tanggal_tagih] [kategori]`\n\n'
                    '*Contoh:*\n'
                    '`/subs tambah Netflix 54000 15 hiburan`\n'
                    '`/subs tambah Spotify 27000 1`')
            name    = args[1]
            amount  = parse_jumlah(args[2])
            if not amount:
                return await reply_md(update, '❌ Jumlah tidak valid.')
            day = int(args[3]) if len(args) > 3 and args[3].isdigit() else 1
            cat = args[4].lower() if len(args) > 4 else 'hiburan'
            s = add_subscription(wallet['id'], name, amount, day, cat)
            await reply_md(update,
                f'✅ *Subscription ditambahkan!*\n\n'
                f'📱 *{s["name"]}*\n'
                f'💰 {format_rupiah(s["amount"])}/bulan\n'
                f'📅 Tagih setiap tanggal {s["billing_day"]}\n'
                f'🏷️ Kategori: {s["category"].title()}\n\n'
                f'_Lihat semua: /subs_')

        # ── hapus
        elif sub == 'hapus':
            if len(args) < 2 or not args[1].isdigit():
                return await reply_md(update, '❓ Format: `/subs hapus [id]`')
            ok = delete_subscription(wallet['id'], int(args[1]))
            await reply_md(update, '✅ Subscription dihapus.' if ok else '❌ ID tidak ditemukan.')

        # ── toggle
        elif sub == 'toggle':
            if len(args) < 2 or not args[1].isdigit():
                return await reply_md(update, '❓ Format: `/subs toggle [id]`')
            result = toggle_subscription(wallet['id'], int(args[1]))
            status = '✅ Aktif' if result['is_active'] else '⏸️ Nonaktif'
            await reply_md(update, f'{status} · {result["name"]}')

        # ── upcoming
        elif sub == 'upcoming':
            upcoming = get_upcoming_subscriptions(wallet['id'], days=10)
            if not upcoming:
                return await reply_md(update, '✅ Tidak ada subscription jatuh tempo dalam 10 hari ke depan.')
            lines = ['📅 *Subscription Jatuh Tempo (10 Hari)*\n']
            for s in upcoming:
                d = s['days_until']
                label = 'Hari ini!' if d == 0 else (f'{d} hari lagi')
                lines.append(f'• *{s["name"]}* — {format_rupiah(s["amount"])} · _{label}_')
            await reply_md(update, '\n'.join(lines))

        # ── lihat (default)
        else:
            summ = get_subscription_summary(wallet['id'])
            if not summ['subscriptions']:
                return await reply_md(update,
                    '📱 *Belum ada subscription.*\n\n'
                    'Tambahkan dengan:\n`/subs tambah Netflix 54000 15 hiburan`')

            lines = [
                f'📱 *Daftar Subscription*\n',
                f'💸 Total: {format_rupiah(summ["total_bulanan"])}/bulan '
                f'({format_rupiah(summ["total_tahunan"])}  /tahun)\n',
            ]
            for s in summ['subscriptions']:
                icon = '✅' if s['is_active'] else '⏸️'
                lines.append(
                    f'{icon} `#{s["id"]}` *{s["name"]}* — {format_rupiah(s["amount"])}\n'
                    f'    📅 tgl {s["billing_day"]} · {s["category"].title()}'
                )
            lines.append('\n💡 `/subs tambah` · `/subs hapus [id]` · `/subs upcoming`')
            await reply_md(update, '\n'.join(lines))

    except Exception as err:
        print(f'[TG /subs] {err}')
        await reply_error(update, 'Gagal load subscriptions.')


# ─── /challenge ──────────────────────────────────────────────

async def cmd_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /challenge              → lihat progress challenge aktif
    /challenge baru 52week  → mulai challenge 52 minggu
    /challenge baru 30day   → tantangan 30 hari
    /challenge baru nospend → no-spend week
    /challenge setor        → tandai langkah selesai
    /challenge stop         → hentikan challenge
    """
    args = context.args or []
    sub  = args[0].lower() if args else 'status'

    try:
        wallet = get_wallet(update)

        # ── baru / mulai
        if sub in ('baru', 'mulai', 'start'):
            type_ = args[1].lower() if len(args) > 1 else ''
            if type_ not in CHALLENGE_TYPES:
                opts = '\n'.join(
                    f'• `{k}` — {v["label"]}: _{v["desc"]}_'
                    for k, v in CHALLENGE_TYPES.items()
                )
                return await reply_md(update,
                    f'🎯 *Pilih Tipe Challenge:*\n\n{opts}\n\n'
                    f'Contoh: `/challenge baru 52week`')
            ch = create_challenge(wallet['id'], type_)
            cfg = CHALLENGE_TYPES[type_]
            await reply_md(update,
                f'🚀 *Challenge Dimulai!*\n\n'
                f'🎯 *{cfg["label"]}*\n'
                f'_{cfg["desc"]}_\n\n'
                f'Total target: {cfg["total_steps"]} langkah\n'
                f'Mulai: {ch["started_at"]}\n\n'
                f'_Ketik `/challenge setor` tiap selesai 1 langkah_\n'
                f'_Ketik `/challenge` untuk cek progress_')

        # ── setor / done / check
        elif sub in ('setor', 'done', 'ceklis', 'check'):
            ch = get_active_challenge(wallet['id'])
            if not ch:
                return await reply_md(update, '❌ Tidak ada challenge aktif. Mulai dengan `/challenge baru`')
            old_done = ch['done']
            ch = advance_challenge(wallet['id'])
            next_amt = ch['next_amount']
            pct = ch['pct']
            bar = progress_bar(ch['done'], ch['total_steps'])

            # Jumlah yang harus disetor (52week = minggu N * 10rb)
            type_label = CHALLENGE_TYPES.get(ch['type'], {}).get('label', ch['type'])
            setor_label = ''
            if ch['type'] == '52week':
                setor_label = f'\n\n💵 Langkah ini: setor *{format_rupiah(old_done + 1) }*'
            if ch['is_complete']:
                return await reply_md(update,
                    f'🎊 *CHALLENGE SELESAI!*\n\n'
                    f'🏆 Kamu berhasil menyelesaikan challenge *{type_label}*!\n'
                    f'💰 Total tersimpan: {format_rupiah(ch["total_saved"])}\n\n'
                    f'_Hebat banget! Mulai challenge baru: `/challenge baru`_')

            await reply_md(update,
                f'✅ *Langkah {ch["done"]}/{ch["total_steps"]} selesai!*\n\n'
                f'{bar} {pct}%{setor_label}\n\n'
                f'Sisa: {ch["remaining"]} langkah · '
                f'Berikutnya: {format_rupiah(next_amt) if next_amt else "—"}')

        # ── stop
        elif sub == 'stop':
            ok = stop_challenge(wallet['id'])
            await reply_md(update,
                '⏹️ Challenge dihentikan.' if ok else '❌ Tidak ada challenge aktif.')

        # ── status (default)
        else:
            ch = get_active_challenge(wallet['id'])
            if not ch:
                opts = ' · '.join(f'`{k}`' for k in CHALLENGE_TYPES)
                return await reply_md(update,
                    f'🎯 *Tidak ada challenge aktif.*\n\n'
                    f'Mulai challenge:\n`/challenge baru [tipe]`\n\n'
                    f'Tipe: {opts}')

            cfg = CHALLENGE_TYPES.get(ch['type'], {})
            bar = progress_bar(ch['done'], ch['total_steps'])
            lines = [
                f'🎯 *Challenge: {cfg.get("label", ch["type"])}*\n',
                f'{bar} {ch["pct"]}%',
                f'{ch["done"]}/{ch["total_steps"]} langkah · {ch["remaining"]} tersisa\n',
                f'💰 Terkumpul: {format_rupiah(ch["total_saved"])}',
                f'🎯 Target total: {format_rupiah(ch["total_target"])}',
            ]
            if not ch['is_complete'] and ch['next_amount'] > 0:
                lines.append(f'\n➡️ Langkah berikutnya: *{format_rupiah(ch["next_amount"])}*')
            lines.append('\n_`/challenge setor` untuk tandai langkah selesai_')
            await reply_md(update, '\n'.join(lines))

    except ValueError as ve:
        await reply_md(update, f'❌ {ve}')
    except Exception as err:
        print(f'[TG /challenge] {err}')
        await reply_error(update, 'Gagal load challenge.')


# ─── /coach ──────────────────────────────────────────────────

async def cmd_coach(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """AI Financial Coach — tips personal berdasarkan data keuanganmu."""
    try:
        wallet = get_wallet(update)
        await update.message.reply_text('🤖 Analisis keuanganmu...')

        tips = get_coach_tips(wallet['id'])
        from datetime import date as _date
        bulan_str = _date.today().strftime('%B %Y')

        lines = [f'🤖 *Financial Coach · {bulan_str}*\n']
        for i, tip in enumerate(tips, 1):
            lines.append(f'{tip["icon"]} *{tip["title"]}*')
            lines.append(f'_{tip["tip"]}_\n')

        lines.append('_Tips ini di-generate otomatis dari data keuanganmu._')
        await reply_md(update, '\n'.join(lines))
    except Exception as err:
        print(f'[TG /coach] {err}')
        await reply_error(update, 'Gagal generate tips.')


# ─── /grupwallet ─────────────────────────────────────────────

async def cmd_grupwallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /grupwallet                    → lihat grup saya
    /grupwallet buat [nama grup]   → buat grup baru
    /grupwallet gabung [kode]      → gabung via kode undangan
    /grupwallet info [id]          → detail & summary grup
    /grupwallet member [id]        → lihat anggota grup
    /grupwallet keluar [id]        → keluar dari grup
    /grupwallet kode [id]          → lihat/regen kode undangan (admin)
    """
    args = context.args or []
    sub  = args[0].lower() if args else 'lihat'

    try:
        wallet = get_wallet(update)

        # ── buat
        if sub in ('buat', 'baru', 'create'):
            if len(args) < 2:
                return await reply_md(update,
                    '❓ Format: `/grupwallet buat [nama grup]`\n\n'
                    'Contoh: `/grupwallet buat Keuangan Keluarga`')
            nama = ' '.join(args[1:])
            grp = create_group_wallet(wallet['id'], nama)
            await reply_md(update,
                f'✅ *Grup dibuat!*\n\n'
                f'👥 *{grp["name"]}*\n'
                f'🔑 Kode undangan: `{grp["invite_code"]}`\n\n'
                f'_Share kode ini ke anggota keluarga/pasangan._\n'
                f'_Mereka gabung dengan: `/grupwallet gabung {grp["invite_code"]}`_')

        # ── gabung
        elif sub == 'gabung':
            if len(args) < 2:
                return await reply_md(update, '❓ Format: `/grupwallet gabung [kode]`')
            grp = join_group_wallet(wallet['id'], args[1])
            await reply_md(update,
                f'🎉 *Berhasil bergabung!*\n\n'
                f'👥 Grup: *{grp["name"]}*\n\n'
                f'_Lihat detail: `/grupwallet info`_')

        # ── info / summary
        elif sub in ('info', 'summary', 'lihat'):
            groups = get_my_groups(wallet['id'])
            if not groups:
                return await reply_md(update,
                    '👥 *Belum ada grup.*\n\n'
                    'Buat grup: `/grupwallet buat [nama]`\n'
                    'Gabung grup: `/grupwallet gabung [kode]`')
            # Jika ada arg id, tampilkan grup tertentu
            if len(args) > 1 and args[1].isdigit():
                group_id = int(args[1])
            else:
                group_id = groups[0]['id']
            summ = get_group_summary(group_id)
            members = get_group_members(group_id)

            lines = [
                f'👥 *Grup: {groups[0]["name"] if group_id == groups[0]["id"] else "—"}*\n',
                f'📅 Bulan ini:',
                f'  💰 Total masuk:  {format_rupiah(summ["masuk"])}',
                f'  💸 Total keluar: {format_rupiah(summ["keluar"])}',
                f'  👤 Anggota: {summ["members"]}\n',
                f'🧑‍🤝‍🧑 *Per anggota:*',
            ]
            for m in summ['per_member']:
                role_icon = '👑' if m['role'] == 'admin' else '👤'
                lines.append(
                    f'  {role_icon} *{m["wallet_name"] or m["wallet_id"][:8]}*\n'
                    f'      Masuk: {format_rupiah(m["masuk"])} · '
                    f'Keluar: {format_rupiah(m["keluar"])}'
                )

            # Kode undangan (hanya admin)
            my_member = next((m for m in members if m['wallet_id'] == wallet['id']), None)
            if my_member and my_member['role'] == 'admin':
                from src.core.finance import get_group_by_code, get_group_wallet as _ggw
                grp_obj = _ggw(group_id)
                if grp_obj:
                    lines.append(f'\n🔑 Kode undangan: `{grp_obj["invite_code"]}`')

            await reply_md(update, '\n'.join(lines))

        # ── member
        elif sub in ('member', 'anggota'):
            groups = get_my_groups(wallet['id'])
            if not groups:
                return await reply_md(update, '❌ Kamu tidak ada di grup manapun.')
            group_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else groups[0]['id']
            members = get_group_members(group_id)
            lines = [f'👥 *Anggota Grup #{group_id}*\n']
            for m in members:
                role_icon = '👑' if m['role'] == 'admin' else '👤'
                lines.append(f'{role_icon} {m.get("wallet_name", m["wallet_id"][:10])} · _{m["role"]}_')
            await reply_md(update, '\n'.join(lines))

        # ── keluar
        elif sub == 'keluar':
            groups = get_my_groups(wallet['id'])
            if not groups:
                return await reply_md(update, '❌ Kamu tidak ada di grup manapun.')
            group_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else groups[0]['id']
            ok = leave_group_wallet(wallet['id'], group_id)
            await reply_md(update, '✅ Berhasil keluar dari grup.' if ok else '❌ Gagal keluar.')

        # ── kode (regen)
        elif sub in ('kode', 'invite'):
            groups = get_my_groups(wallet['id'])
            if not groups:
                return await reply_md(update, '❌ Kamu tidak ada di grup manapun.')
            group_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else groups[0]['id']
            # Cek existing kode dulu
            from src.core.finance import get_group_wallet as _ggw2
            grp_obj = _ggw2(group_id)
            if not grp_obj:
                return await reply_md(update, '❌ Grup tidak ditemukan.')
            # Regen jika ada arg 'baru'
            if len(args) > 2 and args[2].lower() == 'baru':
                new_code = regen_group_invite(wallet['id'], group_id)
                await reply_md(update, f'🔄 Kode baru: `{new_code}`')
            else:
                await reply_md(update,
                    f'🔑 *Kode Undangan Grup*\n\n`{grp_obj["invite_code"]}`\n\n'
                    f'_Share ke anggota baru. Regenerate: `/grupwallet kode {group_id} baru`_')

        # ── daftar grup saya
        else:
            groups = get_my_groups(wallet['id'])
            if not groups:
                return await reply_md(update,
                    '👥 *Belum ada grup.*\n\n'
                    '`/grupwallet buat [nama]` — buat grup baru\n'
                    '`/grupwallet gabung [kode]` — gabung via kode')
            lines = [f'👥 *Grup Saya ({len(groups)})*\n']
            for g in groups:
                role_icon = '👑' if g['role'] == 'admin' else '👤'
                lines.append(f'{role_icon} `#{g["id"]}` *{g["name"]}* · _{g["role"]}_')
            lines.append('\n_`/grupwallet info [id]` untuk detail_')
            await reply_md(update, '\n'.join(lines))

    except ValueError as ve:
        await reply_md(update, f'❌ {ve}')
    except Exception as err:
        print(f'[TG /grupwallet] {err}')
        await reply_error(update, 'Gagal proses grup wallet.')


# ─── Bot Factory ──────────────────────────────────────────

def create_telegram_bot() -> Application | None:
    """Buat dan konfigurasi Telegram bot Application."""
    if not config.TELEGRAM_TOKEN:
        print('⚠️  TELEGRAM_TOKEN tidak ada di .env — Telegram bot dilewati.')
        return None

    async def _auto_weekly_summary(context) -> None:
        """Job: kirim ringkasan mingguan ke semua chat yang aktif."""
        from src.core.database import get_db, _rows
        db = get_db()
        wallets = _rows(db.execute(
            "SELECT DISTINCT w.id, w.chat_id FROM wallets w "
            "WHERE w.platform='telegram' AND w.chat_id IS NOT NULL "
            "AND EXISTS (SELECT 1 FROM transactions t WHERE t.wallet_id=w.id "
            "            AND t.created_at >= datetime('now','-7 days'))"
        ))
        now = datetime.now()
        for w in wallets:
            try:
                lap = get_laporan(w['id'], 'minggu')
                masuk  = lap.get('total_masuk', 0)
                keluar = lap.get('total_keluar', 0)
                selisih = masuk - keluar
                emoji = '📈' if selisih >= 0 else '📉'
                text = (
                    f'📊 *Ringkasan Mingguan*\n'
                    f'_{now.strftime("%d %b %Y")}_\n\n'
                    f'💚 Pemasukan: {format_rupiah(masuk)}\n'
                    f'🔴 Pengeluaran: {format_rupiah(keluar)}\n'
                    f'{emoji} Selisih: {format_rupiah(abs(selisih))}\n'
                    f'🔢 Transaksi: {lap.get("count", 0)}\n\n'
                    f'_Ringkasan otomatis setiap Senin pagi. '
                    f'Ketik /summary untuk cek kapan saja!_'
                )
                await context.bot.send_message(
                    chat_id=w['chat_id'], text=text, parse_mode='Markdown'
                )
            except Exception as e:
                print(f'[weekly_summary] Gagal kirim ke {w["chat_id"]}: {e}')

    async def _post_init(application: Application) -> None:
        """Start reminder scheduler setelah event loop berjalan."""
        from src.core.reminder import init_reminders
        init_reminders(application)

        # ── Weekly summary: setiap Senin jam 08:00 ──────────────────────
        try:
            import pytz
            from datetime import time as dtime
            jq = application.job_queue
            if jq:
                tz = pytz.timezone('Asia/Jakarta')
                jq.run_daily(
                    _auto_weekly_summary,
                    time=dtime(hour=8, minute=0, tzinfo=tz),
                    days=(0,),   # 0 = Senin
                    name='weekly_summary',
                )
                print('✅ Weekly summary job dijadwalkan (Senin 08:00 WIB)')

                # ── Bill reminder: setiap hari jam 09:00 WIB ─────────────
                async def _daily_bill_reminder(ctx) -> None:
                    from src.core.database import _rows as db_rows, get_db as _get_db
                    try:
                        wallets = db_rows(_get_db().execute(
                            "SELECT id FROM wallets WHERE platform='telegram'"
                        ))
                        for w in wallets:
                            try:
                                upcoming = get_upcoming_bills(w['id'], days_ahead=3)
                                if not upcoming:
                                    continue
                                lines = ['⏰ *Tagihan Jatuh Tempo (3 hari ke depan)*\n']
                                for b in upcoming:
                                    days_left = b['days_left']
                                    if days_left == 0:
                                        urg = '🔴 *HARI INI!*'
                                    elif days_left == 1:
                                        urg = '🟠 *Besok*'
                                    else:
                                        urg = f'🟡 {days_left} hari lagi'
                                    amt = f' — {format_rupiah(b["amount"])}' if b['amount'] > 0 else ''
                                    lines.append(f'{urg} *{b["name"]}*{amt}')
                                lines.append('\n_Ketik /tagihan untuk detail lengkap._')
                                chat_id = w['id'].replace('tg:', '')
                                await ctx.bot.send_message(
                                    chat_id=int(chat_id),
                                    text='\n'.join(lines),
                                    parse_mode='Markdown'
                                )
                            except Exception as e2:
                                print(f'[bill_reminder] Skip {w["id"]}: {e2}')
                    except Exception as e:
                        print(f'[bill_reminder] Error: {e}')

                jq.run_daily(
                    _daily_bill_reminder,
                    time=dtime(hour=9, minute=0, tzinfo=tz),
                    name='bill_reminder',
                )
                print('✅ Bill reminder job dijadwalkan (daily 09:00 WIB)')

                # ── Spending anomaly check: setiap hari jam 20:30 WIB ────
                async def _daily_anomaly_check(ctx) -> None:
                    from src.core.database import _rows as db_rows, get_db as _get_db
                    try:
                        wallets = db_rows(_get_db().execute(
                            "SELECT id FROM wallets WHERE platform='telegram'"
                        ))
                        for w in wallets:
                            try:
                                anomalies = get_spending_anomalies(w['id'], threshold=0.5)
                                if not anomalies:
                                    continue
                                lines = ['🔍 *Spending Alert!*\n',
                                         '_Pengeluaran kategori berikut jauh di atas rata-rata:_\n']
                                for a in anomalies[:5]:
                                    lines.append(
                                        f'• *{a["category"].title()}*: {format_rupiah(a["current"])} '
                                        f'(+{a["pct_over"]:.0f}% vs avg {format_rupiah(a["avg"])})'
                                    )
                                lines.append('\n_Cek /laporan untuk detail pengeluaran._')
                                chat_id = w['id'].replace('tg:', '')
                                await ctx.bot.send_message(
                                    chat_id=int(chat_id),
                                    text='\n'.join(lines),
                                    parse_mode='Markdown'
                                )
                            except Exception as e2:
                                pass
                    except Exception as e:
                        print(f'[anomaly_check] Error: {e}')

                jq.run_daily(
                    _daily_anomaly_check,
                    time=dtime(hour=20, minute=30, tzinfo=tz),
                    name='anomaly_check',
                )
                print('✅ Spending anomaly check dijadwalkan (daily 20:30 WIB)')

                # ── Subscription reminder (daily 08:00)
                async def _daily_sub_reminder(ctx) -> None:
                    from src.core.database import get_db as _gdb, _rows as _rws
                    db = _gdb()
                    wallets = _rws(db.execute("SELECT * FROM wallets"))
                    for w in wallets:
                        try:
                            upcoming = get_upcoming_subscriptions(w['id'], days=3)
                            if not upcoming:
                                continue
                            lines = ['📱 *Reminder: Subscription Jatuh Tempo!*\n']
                            for s in upcoming:
                                d = s['days_until']
                                label = '⚡ HARI INI!' if d == 0 else f'{d} hari lagi'
                                lines.append(
                                    f'• *{s["name"]}* — {format_rupiah(s["amount"])} · _{label}_'
                                )
                            lines.append('\n_Cek semua subscription: /subs_')
                            await ctx.bot.send_message(
                                chat_id=w['id'].split('_', 1)[-1],
                                text='\n'.join(lines),
                                parse_mode='Markdown'
                            )
                        except Exception as e:
                            print(f'[sub_reminder] {w["id"]}: {e}')

                jq.run_daily(
                    _daily_sub_reminder,
                    time=dtime(hour=8, minute=0, tzinfo=tz),
                    name='sub_reminder',
                )
                print('✅ Subscription reminder dijadwalkan (daily 08:00 WIB)')

                # ── Challenge weekly reminder (Senin 08:30)
                from telegram.ext import filters as _filters
                async def _weekly_challenge_remind(ctx) -> None:
                    from src.core.database import get_db as _gdb2, _rows as _rws2
                    db = _gdb2()
                    wallets = _rws2(db.execute("SELECT * FROM wallets"))
                    for w in wallets:
                        try:
                            ch = get_active_challenge(w['id'])
                            if not ch or ch['is_complete']:
                                continue
                            cfg = CHALLENGE_TYPES.get(ch['type'], {})
                            next_amt = ch['next_amount']
                            msg = (
                                f'🎯 *Reminder Challenge: {cfg.get("label", ch["type"])}*\n\n'
                                f'Progress: {ch["done"]}/{ch["total_steps"]} langkah '
                                f'({ch["pct"]}%)\n'
                            )
                            if next_amt:
                                msg += f'Langkah berikutnya: *{format_rupiah(next_amt)}*\n'
                            msg += '\n_/challenge setor untuk tandai selesai_'
                            await ctx.bot.send_message(
                                chat_id=w['id'].split('_', 1)[-1],
                                text=msg,
                                parse_mode='Markdown'
                            )
                        except Exception as e:
                            print(f'[challenge_remind] {w["id"]}: {e}')

                jq.run_daily(
                    _weekly_challenge_remind,
                    time=dtime(hour=8, minute=30, tzinfo=tz),
                    name='challenge_remind',
                )
                print('✅ Challenge reminder dijadwalkan (daily 08:30 WIB)')

        except Exception as e:
            print(f'⚠️  Weekly summary job gagal dijadwal: {e}')

    app = (
        Application.builder()
        .token(config.TELEGRAM_TOKEN)
        .post_init(_post_init)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(10)
        .build()
    )

    # Commands
    app.add_handler(CommandHandler('start', cmd_start))
    app.add_handler(CommandHandler('menu', cmd_menu))
    app.add_handler(CommandHandler('help', cmd_help))
    app.add_handler(CommandHandler('catat', cmd_catat))
    app.add_handler(CommandHandler('saldo', cmd_saldo))
    app.add_handler(CommandHandler('history', cmd_history))
    app.add_handler(CommandHandler('undo', cmd_undo))
    app.add_handler(CommandHandler('laporan', cmd_laporan))
    app.add_handler(CommandHandler('target', cmd_target))
    app.add_handler(CommandHandler('tabung', cmd_tabung))
    app.add_handler(CommandHandler('kategori', cmd_kategori))
    app.add_handler(CommandHandler('hapus', cmd_hapus))
    app.add_handler(CommandHandler('edit', cmd_edit))
    app.add_handler(CommandHandler('reminder', cmd_reminder))
    app.add_handler(CommandHandler('budget', cmd_budget))
    app.add_handler(CommandHandler('rutin', cmd_rutin))
    app.add_handler(CommandHandler('wallet', cmd_wallet))
    app.add_handler(CommandHandler('kurs', cmd_kurs))
    app.add_handler(CommandHandler('export', cmd_export))
    app.add_handler(CommandHandler('analisis', cmd_analisis))
    app.add_handler(CommandHandler('kekayaan', cmd_kekayaan))
    app.add_handler(CommandHandler('grafik', cmd_grafik))
    app.add_handler(CommandHandler('trend', cmd_trend))
    app.add_handler(CommandHandler('bahasa', cmd_bahasa))
    app.add_handler(CommandHandler('wishlist', cmd_wishlist))
    app.add_handler(CommandHandler('dashboard', cmd_dashboard))
    app.add_handler(CommandHandler('bank', cmd_bank))
    app.add_handler(CommandHandler('transfer', cmd_transfer))
    app.add_handler(CommandHandler('summary', cmd_summary))
    app.add_handler(CommandHandler('autotabung', cmd_autotabung))
    app.add_handler(CommandHandler('hutang', cmd_hutang))
    app.add_handler(CommandHandler('piutang', cmd_hutang))   # alias, cmd_hutang baca dari update.message.text
    app.add_handler(CommandHandler('cicilan', cmd_cicilan))
    app.add_handler(CommandHandler('tagihan', cmd_tagihan))
    app.add_handler(CommandHandler('c', cmd_catat))          # /c = shortcut /catat
    app.add_handler(CommandHandler('skor', cmd_skor))
    app.add_handler(CommandHandler('darutat', cmd_darutat))
    app.add_handler(CommandHandler('networth', cmd_networth))
    app.add_handler(CommandHandler('split', cmd_split))
    app.add_handler(CommandHandler('investasi', cmd_investasi))
    app.add_handler(CommandHandler('pencapaian', cmd_pencapaian))
    # Wave 3
    app.add_handler(CommandHandler('prediksi', cmd_prediksi))
    app.add_handler(CommandHandler('laporan', cmd_laporan))    # existing — handled via args inside
    app.add_handler(CommandHandler('laporanpdf', cmd_laporan_pdf))
    app.add_handler(CommandHandler('subs', cmd_subs))
    app.add_handler(CommandHandler('challenge', cmd_challenge))
    app.add_handler(CommandHandler('coach', cmd_coach))
    app.add_handler(CommandHandler('grupwallet', cmd_grupwallet))

    # Photo handler (OCR struk)
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Document handler (CSV mutasi)
    app.add_handler(MessageHandler(filters.Document.MimeType('text/csv') | filters.Document.FileExtension('csv'), handle_document))

    # NLP text handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Callback query handlers
    app.add_handler(CallbackQueryHandler(callback_edit, pattern=r'^edit_\d+$'))
    app.add_handler(CallbackQueryHandler(callback_hapus, pattern=r'^hapus_\d+$'))
    app.add_handler(CallbackQueryHandler(callback_saldo, pattern=r'^lihat_saldo$'))
    app.add_handler(CallbackQueryHandler(callback_goal_del, pattern=r'^goal_del_\d+$'))
    app.add_handler(CallbackQueryHandler(callback_wl_del, pattern=r'^wl_del_\d+$'))
    app.add_handler(CallbackQueryHandler(callback_bank_del,  pattern=r'^bank_del_\d+$'))
    app.add_handler(CallbackQueryHandler(callback_bank_edit, pattern=r'^bank_edit_\d+$'))
    app.add_handler(CallbackQueryHandler(callback_menu, pattern=r'^menu_'))

    print('✅ Telegram bot dikonfigurasi')
    return app

"""
Reminder module — penjadwalan notif pakai APScheduler.
Menggantikan node-cron dari versi Node.js.
"""
import asyncio
import re
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import config
from src.core.database import get_db, _row, _rows

# Referensi global ke bot Telegram dan scheduler
_bot = None
_scheduler: Optional[AsyncIOScheduler] = None


def init_reminders(tg_bot):
    """Inisialisasi scheduler dan simpan referensi bot Telegram."""
    global _bot, _scheduler
    _bot = tg_bot

    _scheduler = AsyncIOScheduler(timezone=config.TIMEZONE)

    # Jadwal-jadwal global
    _schedule_recurring_processor()
    _schedule_weekly_tips()
    _schedule_auto_backup()
    _schedule_sheets_sync()
    _schedule_rate_fetch()
    _schedule_night_summary()

    # Load semua reminder wallet yang aktif
    schedule_all_reminders()

    _scheduler.start()
    print('[REMINDER] Scheduler started')


def schedule_all_reminders():
    """Load semua reminder aktif dari DB dan jadwalkan masing-masing."""
    db = get_db()
    rows = _rows(db.execute(
        "SELECT wallet_id, time FROM reminders WHERE is_active = 1"
    ))
    for row in rows:
        wallet_id = row['wallet_id']
        platform = 'telegram' if wallet_id.startswith('tg:') else 'whatsapp'
        _schedule_reminder_job(wallet_id, platform, row['time'])

    print(f'[REMINDER] Loaded {len(rows)} active reminders')


def _schedule_reminder_job(wallet_id: str, platform: str, time_str: str):
    """Jadwalkan job reminder untuk satu wallet."""
    if not _scheduler:
        return

    job_id = f'reminder_{wallet_id}'

    # Hapus job lama kalau ada
    if _scheduler.get_job(job_id):
        _scheduler.remove_job(job_id)

    try:
        hour, minute = time_str.split(':')
        _scheduler.add_job(
            _send_reminder_message,
            CronTrigger(hour=int(hour), minute=int(minute), timezone=config.TIMEZONE),
            args=[wallet_id, platform],
            id=job_id,
            replace_existing=True,
        )
    except Exception as e:
        print(f'[REMINDER] Gagal jadwalkan {wallet_id}: {e}')


async def _send_reminder_message(wallet_id: str, platform: str):
    """Kirim pesan reminder ke wallet (saldo + goals progress)."""
    if not _bot:
        return

    try:
        from src.core.finance import get_saldo_multi_currency, get_savings_rate
        from src.core.goals import get_goals, get_goal_progress
        from src.core.formatter import format_rupiah, format_saldo, progress_bar
        from src.core.database import get_lang

        lang = get_lang(wallet_id)
        data = get_saldo_multi_currency(wallet_id)
        saldo_text = format_saldo(data, lang)

        goals = get_goals(wallet_id)
        goals_text = ''
        if goals:
            goals_text = '\n\n🎯 *Goals:*\n'
            for g in goals:
                prog = get_goal_progress(g)
                persen = prog['persen']
                bar = progress_bar(persen)
                goals_text += f'• {g["name"]}: {bar} {persen}%\n'

        msg = saldo_text + goals_text
        if lang == 'id':
            msg += '\n\n_Jangan lupa catat pengeluaran hari ini! 💪_'
        else:
            msg += '\n\n_Don\'t forget to log today\'s expenses! 💪_'

        if platform == 'telegram':
            chat_id = wallet_id.replace('tg:', '')
            await _bot.bot.send_message(
                chat_id=chat_id,
                text=msg,
                parse_mode='Markdown',
            )
    except Exception as e:
        print(f'[REMINDER] Gagal kirim reminder ke {wallet_id}: {e}')


def set_reminder(wallet_id: str, platform: str, time_str: str) -> str:
    """
    Set/update reminder waktu untuk wallet.
    Returns time_str yang valid.
    Raises ValueError jika format tidak valid.
    """
    # Validasi format HH:MM
    if not re.match(r'^\d{1,2}:\d{2}$', time_str):
        raise ValueError('Format waktu harus HH:MM. Contoh: 20:00')

    hour, minute = time_str.split(':')
    if not (0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
        raise ValueError('Waktu tidak valid. Gunakan format 00:00–23:59')

    # Normalkan ke HH:MM
    normalized = f'{int(hour):02d}:{int(minute):02d}'

    db = get_db()
    db.execute(
        '''INSERT INTO reminders (wallet_id, time, is_active)
           VALUES (?, ?, 1)
           ON CONFLICT(wallet_id) DO UPDATE SET time = excluded.time, is_active = 1''',
        (wallet_id, normalized)
    )
    db.commit()

    # Reschedule job
    _schedule_reminder_job(wallet_id, platform, normalized)
    print(f'[REMINDER] Set reminder {wallet_id} → {normalized}')
    return normalized


def disable_reminder(wallet_id: str):
    """Matikan reminder untuk wallet."""
    db = get_db()
    db.execute(
        'UPDATE reminders SET is_active = 0 WHERE wallet_id = ?',
        (wallet_id,)
    )
    db.commit()

    # Hapus scheduled job
    if _scheduler:
        job_id = f'reminder_{wallet_id}'
        if _scheduler.get_job(job_id):
            _scheduler.remove_job(job_id)

    print(f'[REMINDER] Disabled reminder {wallet_id}')


def _schedule_recurring_processor():
    """Proses transaksi berulang setiap hari 00:05."""
    if not _scheduler:
        return

    async def run():
        try:
            from src.core.finance import process_recurring
            count = process_recurring()
            if count > 0:
                print(f'[RECURRING] Processed {count} transactions')
        except Exception as e:
            print(f'[RECURRING] Error: {e}')

    _scheduler.add_job(
        run,
        CronTrigger(hour=0, minute=5, timezone=config.TIMEZONE),
        id='recurring_processor',
        replace_existing=True,
    )


def _schedule_weekly_tips():
    """Kirim tips mingguan tiap Senin jam 08:00."""
    if not _scheduler:
        return

    async def run():
        if not _bot:
            return
        try:
            from src.core.finance import get_weekly_analysis
            from src.core.formatter import format_rupiah
            from src.core.database import get_lang, _rows as db_rows, get_db

            db = get_db()
            wallets = db_rows(db.execute(
                "SELECT w.id FROM wallets w "
                "JOIN reminders r ON r.wallet_id = w.id "
                "WHERE r.is_active = 1 AND w.platform = 'telegram'"
            ))

            for row in wallets:
                wid = row['id']
                try:
                    lang = get_lang(wid)
                    analysis = get_weekly_analysis(wid)
                    if not analysis or not analysis.get('thisWeekTotal'):
                        continue

                    tips = analysis.get('tips', [])
                    this_week = analysis.get('thisWeekTotal', 0)
                    last_week = analysis.get('lastWeekTotal', 0)
                    diff_pct = round(((this_week - last_week) / last_week) * 100) if last_week else 0

                    if lang == 'en':
                        msg = f'💡 *Weekly Spending Insight*\n\n'
                        msg += f'This week: *{format_rupiah(this_week)}*\n'
                        if last_week:
                            emoji = '📈' if diff_pct > 0 else '📉'
                            msg += f'{emoji} vs last week: *{abs(diff_pct)}%* {"more" if diff_pct > 0 else "less"}\n'
                        if tips:
                            msg += f'\n💡 *Tips:*\n'
                            for tip in tips[:3]:
                                msg += f'• {tip}\n'
                    else:
                        msg = f'💡 *Insight Pengeluaran Mingguan*\n\n'
                        msg += f'Minggu ini: *{format_rupiah(this_week)}*\n'
                        if last_week:
                            emoji = '📈' if diff_pct > 0 else '📉'
                            msg += f'{emoji} vs minggu lalu: *{abs(diff_pct)}%* {"lebih banyak" if diff_pct > 0 else "lebih hemat"}\n'
                        if tips:
                            msg += f'\n💡 *Tips:*\n'
                            for tip in tips[:3]:
                                msg += f'• {tip}\n'

                    chat_id = wid.replace('tg:', '')
                    await _bot.bot.send_message(
                        chat_id=chat_id,
                        text=msg,
                        parse_mode='Markdown',
                    )
                except Exception as inner:
                    print(f'[WEEKLY_TIPS] Gagal kirim ke {wid}: {inner}')
        except Exception as e:
            print(f'[WEEKLY_TIPS] Error: {e}')

    _scheduler.add_job(
        run,
        CronTrigger(day_of_week='mon', hour=8, minute=0, timezone=config.TIMEZONE),
        id='weekly_tips',
        replace_existing=True,
    )


def _schedule_auto_backup():
    """Kirim backup DB ke BACKUP_CHAT_ID jam 22:00 setiap hari."""
    if not _scheduler or not config.BACKUP_CHAT_ID:
        return

    async def run():
        if not _bot:
            return
        try:
            from src.core.database import get_db_path
            db_path = get_db_path()
            now = datetime.now().strftime('%Y-%m-%d %H:%M')
            await _bot.bot.send_document(
                chat_id=config.BACKUP_CHAT_ID,
                document=open(db_path, 'rb'),
                caption=f'🗄️ Auto backup — {now}',
            )
            print(f'[BACKUP] Backup terkirim ke {config.BACKUP_CHAT_ID}')
        except Exception as e:
            print(f'[BACKUP] Error: {e}')

    _scheduler.add_job(
        run,
        CronTrigger(hour=22, minute=0, timezone=config.TIMEZONE),
        id='auto_backup',
        replace_existing=True,
    )


def _schedule_sheets_sync():
    """Sinkronisasi ke Google Sheets jam 23:00 (skip jika modul tidak ada)."""
    if not _scheduler or not config.SHEETS_ID:
        return

    async def run():
        try:
            from src.core.sheets import sync_to_sheets
            await sync_to_sheets()
            print('[SHEETS] Sync selesai')
        except ImportError:
            pass  # Modul sheets tidak diinstal, skip
        except Exception as e:
            print(f'[SHEETS] Sync error: {e}')

    _scheduler.add_job(
        run,
        CronTrigger(hour=23, minute=0, timezone=config.TIMEZONE),
        id='sheets_sync',
        replace_existing=True,
    )


def _schedule_rate_fetch():
    """Ambil kurs tiap hari jam 07:00."""
    if not _scheduler:
        return

    async def run():
        try:
            from src.core.finance import fetch_live_rates
            result = fetch_live_rates()
            print(f'[RATES] Updated {result.get("count", 0)} currencies')
        except Exception as e:
            print(f'[RATES] Error: {e}')

    # Fetch segera saat startup (delay 10 detik)
    _scheduler.add_job(
        run,
        'date',
        run_date=datetime.now().replace(second=0, microsecond=0),
        id='rate_fetch_startup',
        replace_existing=True,
    )

    # Fetch harian jam 07:00
    _scheduler.add_job(
        run,
        CronTrigger(hour=7, minute=0, timezone=config.TIMEZONE),
        id='rate_fetch_daily',
        replace_existing=True,
    )


def _schedule_night_summary():
    """Kirim ringkasan malam (21:00) ke semua wallet dengan reminder aktif."""
    if not _scheduler:
        return

    async def run():
        if not _bot:
            return
        try:
            from src.core.finance import get_laporan, get_budgets, get_proyeksi_bulan
            from src.core.formatter import format_rupiah
            from src.core.database import get_lang, _rows as db_rows, get_db

            db = get_db()
            wallets = db_rows(db.execute(
                "SELECT w.id FROM wallets w "
                "JOIN reminders r ON r.wallet_id = w.id "
                "WHERE r.is_active = 1 AND w.platform = 'telegram'"
            ))

            for row in wallets:
                wid = row['id']
                try:
                    lap = get_laporan(wid, 'hari')
                    summary = lap.get('summary', {})
                    masuk  = summary.get('total_masuk', 0)
                    keluar = summary.get('total_keluar', 0)
                    net    = masuk - keluar

                    # Proyeksi bulan
                    proj = get_proyeksi_bulan(wid)

                    now = datetime.now()
                    tanggal = now.strftime('%-d %b %Y') if hasattr(now, 'strftime') else now.strftime('%d %b %Y')

                    net_icon = '💚' if net >= 0 else '🔴'
                    lines = [
                        f'🌙 *Ringkasan Malam — {tanggal}*\n',
                        f'📥 Pemasukan hari ini: *{format_rupiah(masuk)}*',
                        f'📤 Pengeluaran hari ini: *{format_rupiah(keluar)}*',
                        f'{net_icon} Net hari ini: *{format_rupiah(net)}*',
                    ]

                    # Budget alert
                    budgets = get_budgets(wid)
                    over_budget = [b for b in budgets if b['persen'] >= 80]
                    if over_budget:
                        lines.append('\n⚠️ *Budget Alert:*')
                        for b in over_budget[:3]:
                            icon = '🚨' if b['persen'] >= 100 else '⚠️'
                            lines.append(f'{icon} {b["category"]}: {b["persen"]}% terpakai')

                    # Proyeksi akhir bulan
                    sisa = proj['hari_tersisa']
                    proj_saldo = proj['proyeksi_saldo_akhir_bulan']
                    proj_icon = '📉' if proj['is_defisit'] else '📊'
                    lines.append(
                        f'\n{proj_icon} Proyeksi akhir bulan: *{format_rupiah(proj_saldo)}*'
                        f'\n_({sisa} hari lagi | rata Rp {format_rupiah(proj["rata_keluar_harian"])}/hari)_'
                    )

                    lines.append('\n_Selamat istirahat! 😴_')

                    msg = '\n'.join(lines)
                    chat_id = wid.replace('tg:', '')
                    await _bot.bot.send_message(
                        chat_id=chat_id,
                        text=msg,
                        parse_mode='Markdown',
                    )
                except Exception as inner:
                    print(f'[NIGHT_SUMMARY] Gagal kirim ke {wid}: {inner}')
        except Exception as e:
            print(f'[NIGHT_SUMMARY] Error: {e}')

    _scheduler.add_job(
        run,
        CronTrigger(hour=21, minute=0, timezone=config.TIMEZONE),
        id='night_summary',
        replace_existing=True,
    )

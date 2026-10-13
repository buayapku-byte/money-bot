"""
main.py — Entry point untuk Bot Simpan Uang (Python version).
"""
import asyncio
import logging
import sys

# Fix Windows: pastikan SelectorEventLoop untuk kompatibilitas httpx/asyncio
if sys.platform == 'win32':
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', DeprecationWarning)
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.set_event_loop(asyncio.new_event_loop())

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)],
)
logging.getLogger('apscheduler').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)

import config
from src.core.database import init_database
from src.telegram.bot import create_telegram_bot


def main():
    if not config.TELEGRAM_TOKEN:
        print('[ERROR] TELEGRAM_TOKEN belum di-set di .env!')
        sys.exit(1)

    print('[MAIN] Inisialisasi database...')
    init_database()

    print('[MAIN] Membuat Telegram bot...')
    app = create_telegram_bot()
    if not app:
        print('[ERROR] Gagal membuat bot. Cek TELEGRAM_TOKEN.')
        sys.exit(1)

    print('[MAIN] Bot berjalan... (Ctrl+C untuk stop)')
    app.run_polling(
        allowed_updates=['message', 'callback_query', 'channel_post'],
        drop_pending_updates=True,
    )


if __name__ == '__main__':
    main()

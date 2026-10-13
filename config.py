import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')

DB_PATH = os.getenv('DB_PATH', './data/money.db')

REMINDER_TIME = os.getenv('REMINDER_TIME', '20:00')
TIMEZONE = os.getenv('TIMEZONE', 'Asia/Jakarta')

WA_PREFIX = '!'  # Tidak dipakai di versi Python-only

BACKUP_CHAT_ID = os.getenv('BACKUP_CHAT_ID', '')

DASHBOARD_URL = os.getenv('DASHBOARD_URL', '')

SHEETS_ID = os.getenv('GOOGLE_SHEETS_ID', '')
SHEETS_SA_JSON = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON', '')

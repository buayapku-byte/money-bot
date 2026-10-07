require('dotenv').config();
 
module.exports = {
  telegram: {
    token: process.env.TELEGRAM_TOKEN || '',
  },
 
  whatsapp: {
    sessionPath: process.env.WA_SESSION_PATH || './data/wa-session',
    phoneNumber: process.env.WA_PHONE_NUMBER || '',  // e.g. '85569981401'
    silent: process.env.SILENT_WA === 'true',
  },
 
  db: {
    path: process.env.DB_PATH || './data/money.db',
  },
 
  reminder: {
    defaultTime: process.env.REMINDER_TIME || '20:00',
    timezone: process.env.TIMEZONE || 'Asia/Jakarta',
  },
 
  // Prefix command untuk WhatsApp (bisa diganti '.' atau '!')
  wa: {
    prefix: '!',
  },
 
  // Auto-backup Telegram: isi BACKUP_CHAT_ID untuk backup harian ke satu chat
  // Biarkan kosong untuk backup mingguan ke semua wallet (perilaku default)
  backup: {
    chatId: process.env.BACKUP_CHAT_ID || '',
  },
 
  // Google Sheets sync (opsional)
  // Buat Service Account, share spreadsheet ke email SA, lalu isi env vars
  sheets: {
    spreadsheetId: process.env.GOOGLE_SHEETS_ID || '',
    serviceAccountJson: process.env.GOOGLE_SERVICE_ACCOUNT_JSON || '',
  },
};
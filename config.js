require('dotenv').config();

module.exports = {
  telegram: {
    token: process.env.TELEGRAM_TOKEN || '',
  },

  whatsapp: {
    sessionPath: process.env.WA_SESSION_PATH || './data/wa-session',
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
};

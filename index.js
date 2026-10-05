require('dotenv').config();

const { initDatabase } = require('./src/core/database');
const { createTelegramBot } = require('./src/telegram/bot');
const { createWhatsAppBot, getWASocket } = require('./src/whatsapp/bot');
const { initReminders } = require('./src/core/reminder');

async function main() {
  console.log('');
  console.log('╔══════════════════════════════════════╗');
  console.log('║         💰 Bot Simpan Uang           ║');
  console.log('║    Telegram + WhatsApp · v1.0.0      ║');
  console.log('╚══════════════════════════════════════╝');
  console.log('');

  // 1. Init database
  initDatabase();

  // 2. Start Telegram bot (sync)
  const tgBot = createTelegramBot();

  // 3. Start WhatsApp bot (async — scan QR kalau belum punya session)
  await createWhatsAppBot();

  // 4. Init reminder setelah keduanya ready
  //    Delay 3 detik kasih WA socket waktu buat fully connect
  setTimeout(() => {
    initReminders(tgBot, getWASocket());
  }, 3000);

  // Graceful shutdown
  const shutdown = (signal) => {
    console.log(`\n🛑 Received ${signal}. Shutting down...`);
    if (tgBot) tgBot.stop(signal);
    process.exit(0);
  };

  process.once('SIGINT',  () => shutdown('SIGINT'));
  process.once('SIGTERM', () => shutdown('SIGTERM'));
}

main().catch((err) => {
  console.error('❌ Fatal error:', err);
  process.exit(1);
});

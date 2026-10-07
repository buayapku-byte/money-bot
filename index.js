require('dotenv').config();
 
const { initDatabase } = require('./src/core/database');
const { createTelegramBot } = require('./src/telegram/bot');
const { createWhatsAppBot, getWASocket } = require('./src/whatsapp/bot');
const { initReminders } = require('./src/core/reminder');
const { startQRServer } = require('./src/core/qr-server');
const { startScheduler } = require('./src/core/scheduler');
const { fetchLiveRates } = require('./src/core/finance');
 
async function main() {
  console.log('');
  console.log('╔══════════════════════════════════════╗');
  console.log('║         💰 Bot Simpan Uang           ║');
  console.log('║    Telegram + WhatsApp · v1.0.0      ║');
  console.log('╚══════════════════════════════════════╝');
  console.log('');
 
  // 1. Start web server untuk QR code (Railway butuh port aktif)
  const PORT = process.env.PORT || 3000;
  startQRServer(PORT);
 
  // 2. Init database
  initDatabase();
 
  // 3. Start Telegram bot (sync)
  const tgBot = createTelegramBot();
 
  // 4. Start WhatsApp bot (async — scan QR kalau belum punya session)
  await createWhatsAppBot();
 
  // 5. Init reminder + scheduler setelah keduanya ready
  //    Delay 3 detik kasih WA socket waktu buat fully connect
  setTimeout(() => {
    initReminders(tgBot, getWASocket());
    startScheduler(tgBot, getWASocket);  // laporan bulanan otomatis tiap tgl 1
  }, 3000);
 
  // 6. Fetch live rates saat startup (untuk multi-currency saldo otomatis)
  //    Refresh tiap 6 jam
  fetchLiveRates()
    .then(r => console.log(`[Kurs] Live rates loaded: ${r.count} currencies, USD=${r.usdRate}`))
    .catch(e => console.warn('[Kurs] Gagal fetch live rates saat startup:', e.message));
  setInterval(() => {
    fetchLiveRates()
      .then(r => console.log(`[Kurs] Refreshed: ${r.count} currencies`))
      .catch(e => console.warn('[Kurs] Gagal refresh live rates:', e.message));
  }, 6 * 60 * 60 * 1000); // tiap 6 jam
 
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
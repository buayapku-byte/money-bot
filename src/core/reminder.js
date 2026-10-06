// ─── Reminder / Cron Job ─────────────────────────────────
// Kirim notif harian otomatis ke semua wallet yang aktif
// Di-init setelah Telegram & WA bot ready
 
const cron = require('node-cron');
const { getDb } = require('./database');
const { getSaldo, processRecurring } = require('./finance');
const { getGoals, getGoalProgress } = require('./goals');
const { formatRupiah, progressBar } = require('./formatter');
 
// Simpan referensi ke bot instances
let telegramBot = null;
let waSock = null;
 
// Simpan semua cron jobs aktif (per wallet_id)
const activeCrons = {};
 
/**
 * Init reminder system — dipanggil di index.js setelah bot ready
 * @param {object} tgBot - Telegraf instance
 * @param {object} sock - Baileys socket
 */
function initReminders(tgBot, sock) {
  telegramBot = tgBot;
  waSock = sock;
 
  scheduleAllReminders();
  scheduleRecurringProcessor();
  console.log('✅ Reminder scheduler aktif');
}
 
/**
 * Load semua reminder dari DB dan jadwalkan
 */
function scheduleAllReminders() {
  const db = getDb();
  const reminders = db.prepare(`
    SELECT r.*, w.platform FROM reminders r
    JOIN wallets w ON w.id = r.wallet_id
    WHERE r.is_active = 1
  `).all();
 
  reminders.forEach((r) => scheduleReminder(r.wallet_id, r.platform, r.time));
  console.log(`[Reminder] ${reminders.length} reminder dijadwalkan`);
}
 
/**
 * Jadwalkan cron job untuk 1 wallet
 * @param {string} walletId
 * @param {string} platform - 'telegram' | 'whatsapp'
 * @param {string} time - Format "HH:MM"
 */
function scheduleReminder(walletId, platform, time) {
  // Hentikan cron lama kalau ada
  if (activeCrons[walletId]) {
    activeCrons[walletId].stop();
    delete activeCrons[walletId];
  }
 
  const [hour, minute] = time.split(':');
  if (!hour || !minute) return;
 
  const cronExpr = `${minute} ${hour} * * *`;
 
  const job = cron.schedule(cronExpr, async () => {
    await sendReminderMessage(walletId, platform);
  }, {
    timezone: 'Asia/Jakarta',
  });
 
  activeCrons[walletId] = job;
}
 
/**
 * Set jam reminder untuk wallet tertentu
 * @param {string} walletId
 * @param {string} platform
 * @param {string} time - Format "HH:MM"
 */
function setReminder(walletId, platform, time) {
  const db = getDb();
 
  // Validasi format waktu
  const match = time.match(/^([01]\d|2[0-3]):([0-5]\d)$/);
  if (!match) throw new Error('Format waktu salah. Gunakan HH:MM (contoh: 20:00)');
 
  db.prepare(`
    INSERT INTO reminders (wallet_id, time, is_active)
    VALUES (?, ?, 1)
    ON CONFLICT(wallet_id) DO UPDATE SET time = excluded.time, is_active = 1
  `).run(walletId, time);
 
  scheduleReminder(walletId, platform, time);
  return time;
}
 
/**
 * Matiin reminder untuk wallet
 * @param {string} walletId
 */
function disableReminder(walletId) {
  const db = getDb();
  db.prepare(`UPDATE reminders SET is_active = 0 WHERE wallet_id = ?`).run(walletId);
 
  if (activeCrons[walletId]) {
    activeCrons[walletId].stop();
    delete activeCrons[walletId];
  }
}
 
/**
 * Kirim pesan reminder ke chat
 */
async function sendReminderMessage(walletId, platform) {
  try {
    const { saldo, total_masuk, total_keluar } = getSaldo(walletId);
    const goals = getGoals(walletId);
 
    let msg = `⏰ *Reminder Harian*\n\n`;
    msg += `💰 Saldo: *${formatRupiah(saldo)}*\n`;
    msg += `📈 Masuk hari ini: ${formatRupiah(total_masuk)}\n`;
    msg += `📉 Keluar hari ini: ${formatRupiah(total_keluar)}\n`;
 
    if (goals.length > 0) {
      msg += `\n🎯 *Progress Goals:*\n`;
      goals.forEach((g) => {
        const { persen } = getGoalProgress(g);
        msg += `• ${g.name}: ${progressBar(persen, 8)}\n`;
      });
    }
 
    msg += `\nSemangat menabung! 💪`;
 
    if (platform === 'telegram') {
      const chatId = walletId.replace('tg:', '');
      await telegramBot?.telegram.sendMessage(chatId, msg, { parse_mode: 'Markdown' });
    } else if (platform === 'whatsapp') {
      const chatId = walletId.replace('wa:', '');
      // Strip markdown untuk WA
      const plainMsg = msg.replace(/\*/g, '').replace(/_/g, '');
      await waSock?.sendMessage(chatId, { text: plainMsg });
    }
  } catch (err) {
    console.error(`[Reminder] Error kirim ke ${walletId}:`, err.message);
  }
}
 
/**
 * Jadwalkan cron harian untuk proses recurring transactions
 * Jalan tiap jam 00:05 WIB supaya slightly after midnight
 */
function scheduleRecurringProcessor() {
  cron.schedule('5 0 * * *', async () => {
    console.log('[Recurring] Mulai proses transaksi berulang...');
    try {
      const results = processRecurring();
      if (!results.length) {
        console.log('[Recurring] Tidak ada yang perlu diproses hari ini.');
        return;
      }
 
      console.log(`[Recurring] Berhasil proses ${results.length} transaksi.`);
 
      // Kirim notif ke wallet yang punya recurring hari ini
      // Group hasil per wallet
      const byWallet = {};
      results.forEach(({ rec, trx }) => {
        if (!byWallet[rec.wallet_id]) byWallet[rec.wallet_id] = [];
        byWallet[rec.wallet_id].push({ rec, trx });
      });
 
      const db = getDb();
      for (const [walletId, items] of Object.entries(byWallet)) {
        try {
          const wallet = db.prepare('SELECT * FROM wallets WHERE id = ?').get(walletId);
          if (!wallet) continue;
 
          let msg = `🔄 *Transaksi Rutin Dicatat*\n\n`;
          items.forEach(({ rec, trx }) => {
            const icon = rec.type === 'in' ? '📈' : '📉';
            msg += `${icon} *${formatRupiah(rec.amount)}*`;
            if (rec.note) msg += ` · ${rec.note}`;
            msg += `\n`;
          });
          msg += `\nTotal ${items.length} transaksi rutin dicatat otomatis.`;
 
          if (wallet.platform === 'telegram' && telegramBot) {
            const chatId = walletId.replace('tg:', '');
            await telegramBot.telegram.sendMessage(chatId, msg, { parse_mode: 'Markdown' });
          } else if (wallet.platform === 'whatsapp' && waSock) {
            const chatId = walletId.replace('wa:', '');
            const plainMsg = msg.replace(/\*/g, '').replace(/_/g, '');
            await waSock.sendMessage(chatId, { text: plainMsg });
          }
        } catch (err) {
          console.error(`[Recurring] Gagal notif ke ${walletId}:`, err.message);
        }
      }
    } catch (err) {
      console.error('[Recurring] Error proses:', err.message);
    }
  }, {
    timezone: 'Asia/Jakarta',
  });
 
  console.log('[Recurring] Cron processor dijadwalkan (00:05 WIB tiap hari)');
}
 
module.exports = { initReminders, setReminder, disableReminder };
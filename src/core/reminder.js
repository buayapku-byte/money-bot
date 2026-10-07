// ─── Reminder / Cron Job ─────────────────────────────────
// Kirim notif harian otomatis ke semua wallet yang aktif
// Di-init setelah Telegram & WA bot ready
 
const cron = require('node-cron');
const fs = require('fs');
const { getDb, getDbPath } = require('./database');
const { getSaldo, processRecurring, getWeeklyAnalysis, fetchLiveRates } = require('./finance');
const { getGoals, getGoalProgress } = require('./goals');
const { formatRupiah, progressBar } = require('./formatter');
 
// Lazy-load sheets agar tidak crash kalau googleapis tidak diinstall
let sheetsModule = null;
function getSheets() {
  if (sheetsModule) return sheetsModule;
  try {
    sheetsModule = require('./sheets');
  } catch (_) {
    sheetsModule = null;
  }
  return sheetsModule;
}
 
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
  scheduleWeeklyTips();
  scheduleAutoBackup();
  scheduleRateFetch();
  scheduleSheetsSync();
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
 
/**
 * Jadwalkan weekly tips — setiap Senin jam 08:00 WIB
 */
function scheduleWeeklyTips() {
  cron.schedule('0 8 * * 1', async () => {
    console.log('[WeeklyTips] Mulai kirim analisis mingguan...');
    const db = getDb();
    try {
      const wallets = db.prepare(`SELECT * FROM wallets`).all();
 
      for (const wallet of wallets) {
        try {
          const { tips, thisWeekTotal, lastWeekTotal, thisWeekIncome } = getWeeklyAnalysis(wallet.id);
 
          if (thisWeekTotal === 0 && thisWeekIncome === 0) continue; // skip wallet kosong
 
          let msg = `💡 *Tips Mingguan*\n\n`;
          msg += `📊 Ringkasan 7 hari terakhir:\n`;
          msg += `• Pengeluaran: *${formatRupiah(thisWeekTotal)}*`;
          if (lastWeekTotal > 0) {
            const diff = Math.round(((thisWeekTotal - lastWeekTotal) / lastWeekTotal) * 100);
            const icon = diff > 0 ? '⬆️' : '⬇️';
            msg += ` (${icon}${Math.abs(diff)}% vs minggu lalu)`;
          }
          msg += `\n`;
          if (thisWeekIncome > 0) {
            msg += `• Pemasukan: *${formatRupiah(thisWeekIncome)}*\n`;
          }
          msg += `\n`;
          tips.forEach(t => { msg += `${t}\n`; });
          msg += `\nSemangat ngatur keuangan! 🔥`;
 
          if (wallet.platform === 'telegram' && telegramBot) {
            const chatId = wallet.id.replace('tg:', '');
            await telegramBot.telegram.sendMessage(chatId, msg, { parse_mode: 'Markdown' });
          } else if (wallet.platform === 'whatsapp' && waSock) {
            const chatId = wallet.id.replace('wa:', '');
            const plainMsg = msg.replace(/\*/g, '').replace(/_/g, '');
            await waSock.sendMessage(chatId, { text: plainMsg });
          }
        } catch (err) {
          console.error(`[WeeklyTips] Gagal kirim ke ${wallet.id}:`, err.message);
        }
      }
    } catch (err) {
      console.error('[WeeklyTips] Error:', err.message);
    }
  }, { timezone: 'Asia/Jakarta' });
 
  console.log('[WeeklyTips] Cron dijadwalkan (Senin 08:00 WIB)');
}
 
/**
 * Jadwalkan backup otomatis — setiap Minggu jam 22:00 WIB
 * Kirim file .db ke semua wallet aktif
 */
/**
 * Kirim backup DB ke satu chat Telegram
 */
async function sendTelegramBackup(chatId, dbPath, label) {
  label = label || 'Harian';
  const now = new Date().toLocaleDateString('id-ID', {
    day: '2-digit', month: 'long', year: 'numeric', timeZone: 'Asia/Jakarta'
  });
  const caption = `💾 *Backup Otomatis ${label}*\n\n📅 ${now}\nFile database keuangan kamu.\n\nSimpan baik-baik ya! 🔒`;
  await telegramBot.telegram.sendDocument(chatId, {
    source: dbPath,
    filename: `money-bot-backup-${new Date().toISOString().split('T')[0]}.db`,
  }, { caption, parse_mode: 'Markdown' });
}
 
/**
 * Jadwalkan backup otomatis:
 * - BACKUP_CHAT_ID diset -> kirim harian ke chat itu saja (22:00 WIB)
 * - Fallback: kirim mingguan (Minggu 22:00 WIB) ke semua wallet
 */
function scheduleAutoBackup() {
  const backupChatId = process.env.BACKUP_CHAT_ID;
 
  if (backupChatId) {
    cron.schedule('0 22 * * *', async () => {
      console.log('[Backup] Mulai backup harian ke BACKUP_CHAT_ID...');
      const dbPath = getDbPath();
      if (!fs.existsSync(dbPath)) {
        console.error('[Backup] File DB tidak ditemukan:', dbPath);
        return;
      }
      try {
        if (telegramBot) {
          await sendTelegramBackup(backupChatId, dbPath, 'Harian');
          console.log(`[Backup] Backup harian terkirim ke ${backupChatId} ✅`);
        }
      } catch (err) {
        console.error('[Backup] Gagal kirim backup harian:', err.message);
      }
    }, { timezone: 'Asia/Jakarta' });
    console.log('[Backup] Backup HARIAN ke BACKUP_CHAT_ID dijadwalkan (22:00 WIB)');
  } else {
    cron.schedule('0 22 * * 0', async () => {
      console.log('[Backup] Mulai kirim backup mingguan ke semua wallet...');
      const db = getDb();
      const dbPath = getDbPath();
      if (!fs.existsSync(dbPath)) {
        console.error('[Backup] File DB tidak ditemukan:', dbPath);
        return;
      }
      try {
        const wallets = db.prepare('SELECT * FROM wallets').all();
        let sent = 0;
        for (const wallet of wallets) {
          try {
            if (wallet.platform === 'telegram' && telegramBot) {
              await sendTelegramBackup(wallet.id.replace('tg:', ''), dbPath, 'Mingguan');
              sent++;
            } else if (wallet.platform === 'whatsapp' && waSock) {
              const chatId = wallet.id.replace('wa:', '');
              const fileBuffer = fs.readFileSync(dbPath);
              const now = new Date().toLocaleDateString('id-ID', { day: '2-digit', month: 'long', year: 'numeric', timeZone: 'Asia/Jakarta' });
              await waSock.sendMessage(chatId, {
                document: fileBuffer,
                fileName: `money-bot-backup-${new Date().toISOString().split('T')[0]}.db`,
                mimetype: 'application/octet-stream',
                caption: `Backup Otomatis Mingguan\n\n${now}\nFile database keuangan kamu. Simpan baik-baik ya!`,
              });
              sent++;
            }
          } catch (err) {
            console.error(`[Backup] Gagal kirim ke ${wallet.id}:`, err.message);
          }
        }
        console.log(`[Backup] Selesai - ${sent}/${wallets.length} wallet.`);
      } catch (err) {
        console.error('[Backup] Error:', err.message);
      }
    }, { timezone: 'Asia/Jakarta' });
    console.log('[Backup] Cron dijadwalkan (Minggu 22:00 WIB) - set BACKUP_CHAT_ID untuk backup harian pribadi');
  }
}
 
/**
 * Jadwalkan sinkronisasi Google Sheets setiap hari jam 23:00 WIB
 */
function scheduleSheetsSync() {
  const sheets = getSheets();
  if (!sheets) {
    console.log('[Sheets] googleapis tidak diinstall - Google Sheets sync dinonaktifkan.');
    return;
  }
  const ready = sheets.initSheets();
  if (!ready) return;
 
  sheets.syncToSheets()
    .then(r => console.log(`[Sheets] Startup sync: ${r.pushed} transaksi`))
    .catch(err => console.error('[Sheets] Startup sync gagal:', err.message));
 
  cron.schedule('0 23 * * *', async () => {
    console.log('[Sheets] Mulai sync harian ke Google Sheets...');
    try {
      const { pushed } = await sheets.syncToSheets();
      console.log(`[Sheets] Sync selesai - ${pushed} transaksi baru dikirim.`);
    } catch (err) {
      console.error('[Sheets] Sync gagal:', err.message);
    }
  }, { timezone: 'Asia/Jakarta' });
 
  console.log('[Sheets] Google Sheets sync dijadwalkan (23:00 WIB tiap hari)');
}
 
/**
 * Fetch live exchange rates saat startup + jadwalkan refresh harian jam 07:00 WIB
 */
function scheduleRateFetch() {
  // Fetch langsung saat bot start
  fetchLiveRates()
    .then(({ count, usdRate }) => {
      console.log(`[Kurs] Startup: ${count} mata uang siap (1 USD = Rp ${usdRate.toLocaleString('id-ID')})`);
    })
    .catch(err => {
      console.error('[Kurs] Gagal fetch saat startup:', err.message);
    });
 
  // Refresh harian jam 07:00 WIB
  cron.schedule('0 7 * * *', async () => {
    console.log('[Kurs] Auto-refresh live rates...');
    try {
      const { count, usdRate } = await fetchLiveRates();
      console.log(`[Kurs] Update ${count} mata uang (1 USD = Rp ${usdRate.toLocaleString('id-ID')})`);
    } catch (err) {
      console.error('[Kurs] Gagal refresh harian:', err.message);
    }
  }, { timezone: 'Asia/Jakarta' });
 
  console.log('[Kurs] Rate fetcher dijadwalkan (07:00 WIB tiap hari)');
}
 
module.exports = { initReminders, setReminder, disableReminder };
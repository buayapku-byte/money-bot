// ─── Laporan Bulanan Otomatis ─────────────────────────────
// Kirim ringkasan bulan lalu ke semua wallet aktif setiap tanggal 1

const { getDb } = require('./database');
const { getLaporanBulanLalu } = require('./finance');
const { formatLaporan } = require('./formatter');

/**
 * Hitung ms sampai tanggal 1 bulan berikutnya jam 08:00 WIB (UTC+7)
 */
function msUntilNextFirst() {
  const now = new Date();
  const wibOffset = 7 * 60 * 60 * 1000;
  const nowWib = new Date(now.getTime() + wibOffset);

  const nextYear  = nowWib.getUTCMonth() === 11
    ? nowWib.getUTCFullYear() + 1
    : nowWib.getUTCFullYear();
  const nextMonth = nowWib.getUTCMonth() === 11 ? 0 : nowWib.getUTCMonth() + 1;

  // Tanggal 1 bulan depan jam 08:00 WIB = 01:00 UTC
  const target = Date.UTC(nextYear, nextMonth, 1, 1, 0, 0, 0);
  const ms = target - now.getTime();
  // Kalau sudah lewat (mis. saat test), mundur 1 jam lagi
  return ms > 0 ? ms : ms + 31 * 24 * 60 * 60 * 1000;
}

/**
 * Kirim laporan bulanan ke semua wallet yang punya transaksi bulan lalu
 */
async function sendMonthlyReport(telegramBot, getWASocket) {
  console.log('[Scheduler] Mengirim laporan bulanan...');

  let wallets = [];
  try {
    const db = getDb();
    wallets = db.prepare('SELECT id, platform, platform_id, lang FROM wallets').all();
  } catch (err) {
    console.error('[Scheduler] Gagal ambil daftar wallet:', err);
    return;
  }

  for (const wallet of wallets) {
    try {
      const data = getLaporanBulanLalu(wallet.id);
      if (data.summary.jumlah_transaksi === 0) continue; // skip wallet tanpa transaksi

      const lang = wallet.lang || 'id';
      const text = formatLaporan(data, data.monthStr, lang);
      const header = lang === 'en'
        ? `📅 *Monthly Report — ${data.monthStr}*\n\n`
        : `📅 *Laporan Bulanan — ${data.monthStr}*\n\n`;
      const pesan = header + text;

      if (wallet.platform === 'telegram' && telegramBot) {
        await telegramBot.telegram
          .sendMessage(wallet.platform_id, pesan, { parse_mode: 'Markdown' })
          .catch(e => console.error(`[Scheduler TG] ${wallet.platform_id}:`, e.message));

      } else if (wallet.platform === 'whatsapp') {
        const sock = getWASocket ? getWASocket() : null;
        if (sock) {
          await sock
            .sendMessage(wallet.platform_id, { text: pesan })
            .catch(e => console.error(`[Scheduler WA] ${wallet.platform_id}:`, e.message));
        }
      }
    } catch (err) {
      console.error(`[Scheduler] wallet ${wallet.id}:`, err);
    }
  }

  console.log('[Scheduler] Laporan bulanan selesai dikirim.');
}

// ─── Internal refs ────────────────────────────────────────
let _telegramBot  = null;
let _getWASocket  = null;

function scheduleNext() {
  const delay = msUntilNextFirst();
  const hours  = Math.round(delay / 3_600_000);
  console.log(`[Scheduler] Laporan bulanan dijadwalkan dalam ~${hours} jam`);

  setTimeout(async () => {
    await sendMonthlyReport(_telegramBot, _getWASocket);
    scheduleNext(); // jadwalkan bulan berikutnya
  }, delay);
}

/**
 * Mulai scheduler laporan bulanan otomatis.
 * Panggil sekali saat aplikasi start.
 *
 * @param {import('telegraf').Telegraf} telegramBot
 * @param {() => import('@whiskeysockets/baileys').WASocket} getWASocket
 */
function startScheduler(telegramBot, getWASocket) {
  _telegramBot = telegramBot;
  _getWASocket = getWASocket;
  scheduleNext();
}

module.exports = { startScheduler };

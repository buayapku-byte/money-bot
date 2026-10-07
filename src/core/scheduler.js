// ─── Scheduler ────────────────────────────────────────────
// 1. Laporan Bulanan — tanggal 1 tiap bulan jam 08:00 WIB
// 2. Weekly Digest  — Senin pagi jam 08:00 WIB
 
const { getDb } = require('./database');
const { getLaporanBulanLalu, getLaporanMingguLalu } = require('./finance');
const { formatLaporan, formatRupiah } = require('./formatter');
 
// ─── Utils ────────────────────────────────────────────────
 
/** Hitung ms sampai tanggal 1 bulan berikutnya jam 08:00 WIB */
function msUntilNextFirst() {
  const now = new Date();
  const wib = new Date(now.getTime() + 7 * 3600_000); // UTC+7
  const nextYear  = wib.getUTCMonth() === 11 ? wib.getUTCFullYear() + 1 : wib.getUTCFullYear();
  const nextMonth = wib.getUTCMonth() === 11 ? 0 : wib.getUTCMonth() + 1;
  const target    = Date.UTC(nextYear, nextMonth, 1, 1, 0, 0, 0); // 01:00 UTC = 08:00 WIB
  const ms        = target - now.getTime();
  return ms > 0 ? ms : ms + 31 * 24 * 3600_000;
}
 
/** Hitung ms sampai Senin depan jam 08:00 WIB */
function msUntilNextMonday() {
  const now = new Date();
  const wib = new Date(now.getTime() + 7 * 3600_000); // UTC+7
  // 0=Sun 1=Mon … 6=Sat → hari ke-N sejak Senin = (dayOfWeek+6)%7
  const dayWib  = wib.getUTCDay();
  const daysUntilMon = dayWib === 1
    ? 7                       // sekarang Senin → Senin depan
    : (8 - dayWib) % 7 || 7; // hari lain
 
  const targetWib = new Date(Date.UTC(
    wib.getUTCFullYear(), wib.getUTCMonth(), wib.getUTCDate() + daysUntilMon,
    1, 0, 0, 0, // 01:00 UTC = 08:00 WIB
  ));
  const ms = targetWib.getTime() - now.getTime();
  return ms > 0 ? ms : ms + 7 * 24 * 3600_000;
}
 
/** Ambil semua wallet dari DB */
function getAllWallets() {
  return getDb().prepare('SELECT id, platform, platform_id, lang FROM wallets').all();
}
 
/** Kirim pesan ke semua wallet lewat platform masing-masing */
async function broadcast(telegramBot, getWASocket, wallets, buildMsg) {
  for (const wallet of wallets) {
    try {
      const pesan = buildMsg(wallet);
      if (!pesan) continue;
 
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
}
 
// ─── Laporan Bulanan ──────────────────────────────────────
 
async function sendMonthlyReport(telegramBot, getWASocket) {
  console.log('[Scheduler] Mengirim laporan bulanan...');
  const wallets = getAllWallets();
 
  await broadcast(telegramBot, getWASocket, wallets, (wallet) => {
    const data = getLaporanBulanLalu(wallet.id);
    if (data.summary.jumlah_transaksi === 0) return null;
 
    const lang = wallet.lang || 'id';
    const text = formatLaporan(data, data.monthStr, lang);
    const header = lang === 'en'
      ? `📅 *Monthly Report — ${data.monthStr}*\n\n`
      : `📅 *Laporan Bulanan — ${data.monthStr}*\n\n`;
    return header + text;
  });
 
  console.log('[Scheduler] Laporan bulanan selesai.');
}
 
// ─── Weekly Digest ────────────────────────────────────────
 
const NAMA_BULAN = ['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Ags','Sep','Okt','Nov','Des'];
 
function formatWeeklyDigest(data, lang) {
  const { summary, fromStr, toStr } = data;
  const from = fromStr.slice(5).split('-').reverse().join(' ');
  const toD  = toStr.slice(5).split('-').reverse().join(' ');
  const [, fromM] = fromStr.split('-').map(Number);
  const [, toM]   = toStr.split('-').map(Number);
  const range     = `${from} ${NAMA_BULAN[fromM-1]} – ${toD} ${NAMA_BULAN[toM-1]}`;
 
  if (lang === 'en') {
    return [
      `📆 *Weekly Digest*`,
      `_${range}_`,
      ``,
      `💸 Total expenses : *${formatRupiah(summary.total_keluar)}*`,
      `💰 Total income   : *${formatRupiah(summary.total_masuk)}*`,
      `📊 Balance        : *${formatRupiah(summary.selisih)}*`,
      `🔢 Transactions   : ${summary.jumlah_transaksi}`,
    ].join('\n');
  }
 
  return [
    `📆 *Weekly Digest*`,
    `_${range}_`,
    ``,
    `💸 Total pengeluaran : *${formatRupiah(summary.total_keluar)}*`,
    `💰 Total pemasukan   : *${formatRupiah(summary.total_masuk)}*`,
    `📊 Saldo bersih      : *${formatRupiah(summary.selisih)}*`,
    `🔢 Transaksi         : ${summary.jumlah_transaksi}`,
  ].join('\n');
}
 
async function sendWeeklyDigest(telegramBot, getWASocket) {
  console.log('[Scheduler] Mengirim weekly digest...');
  const wallets = getAllWallets();
 
  await broadcast(telegramBot, getWASocket, wallets, (wallet) => {
    const data = getLaporanMingguLalu(wallet.id);
    if (data.summary.jumlah_transaksi === 0) return null;
 
    const lang = wallet.lang || 'id';
    return formatWeeklyDigest(data, lang);
  });
 
  console.log('[Scheduler] Weekly digest selesai.');
}
 
// ─── Self-scheduling loops ────────────────────────────────
 
let _telegramBot = null;
let _getWASocket = null;
 
function scheduleMonthly() {
  const delay = msUntilNextFirst();
  console.log(`[Scheduler] Laporan bulanan ~${Math.round(delay / 3600_000)}j lagi`);
  setTimeout(async () => {
    await sendMonthlyReport(_telegramBot, _getWASocket);
    scheduleMonthly();
  }, delay);
}
 
function scheduleWeekly() {
  const delay = msUntilNextMonday();
  console.log(`[Scheduler] Weekly digest ~${Math.round(delay / 3600_000)}j lagi (Senin 08:00 WIB)`);
  setTimeout(async () => {
    await sendWeeklyDigest(_telegramBot, _getWASocket);
    scheduleWeekly();
  }, delay);
}
 
/**
 * Mulai semua scheduler.
 * Panggil sekali saat app start (lihat index.js).
 *
 * @param {import('telegraf').Telegraf} telegramBot
 * @param {() => any} getWASocket
 */
function startScheduler(telegramBot, getWASocket) {
  _telegramBot = telegramBot;
  _getWASocket = getWASocket;
  scheduleMonthly();
  scheduleWeekly();
}
 
module.exports = { startScheduler };
const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
} = require('@whiskeysockets/baileys');
const { Boom } = require('@hapi/boom');
const qrcode = require('qrcode-terminal');
const pino = require('pino');
const fs = require('fs');
 
const config = require('../../config');
const { getOrCreateWallet, resolveWalletId, createInviteCode, useInviteCode, unlinkWallet, getLang, setLang } = require('../core/database');
const { t } = require('../core/i18n');
const { setQR, clearQR } = require('../core/qr-server');
const { addTransaction, getSaldo, getHistory, getLaporan, undoLast, deleteTransaction, getLaporanKategori,
  setBudget, getBudgets, deleteBudget, checkBudgetAlert,
  editTransaction,
  addRecurring, getRecurring, deleteRecurring,
  setCurrency, getCurrencies, convertToIdr, CURRENCY_SYMBOLS,
  fetchLiveRates, getLiveRateUpdatedAt, POPULAR_CURRENCIES,
  getExportData, generateCsv, getAnalisis, getKekayaan,
  getSaldoMultiCurrency } = require('../core/finance');
const { parseNLP } = require('../core/nlp');
const { createGoal, getGoals, addToGoal, deleteGoal, getGoalProgress } = require('../core/goals');
const { setReminder, disableReminder } = require('../core/reminder');
const {
  formatRupiah,
  formatSaldo,
  formatTransaksi,
  formatHistory,
  formatLaporan,
  formatKategori,
  formatGoals,
  formatBudgets,
  formatRecurring,
  formatAnalisis,
  formatKekayaan,
} = require('../core/formatter');
const { buildChartConfig, fetchGrafikBuffer, buildGrafikCaption,
        buildTrendConfig, buildTrendCaption } = require('../core/grafik');
const { ocrImage, parseStruk } = require('../core/ocr');
const NAMA_BULAN = ['Januari','Februari','Maret','April','Mei','Juni',
  'Juli','Agustus','September','Oktober','November','Desember'];
 
/**
 * Format "2026-10" jadi "Oktober 2026 (1 - 31 Okt 2026)"
 * @param {string} monthStr - format YYYY-MM
 * @returns {string}
 */
function formatBulan(monthStr) {
  const [year, mon] = monthStr.split('-').map(Number);
  const lastDay = new Date(year, mon, 0).getDate();
  const nama = NAMA_BULAN[mon - 1];
  const singkat = nama.slice(0, 3);
  return nama + ' ' + year + ' (1 – ' + lastDay + ' ' + singkat + ' ' + year + ')';
}
 
 
 
// ─── State ────────────────────────────────────────────────
let waSocket = null;
 
// ─── Helper ───────────────────────────────────────────────
 
/**
 * Parse jumlah uang — sama seperti Telegram (500rb, 1.5jt, 1k, dll)
 */
function parseJumlah(str) {
  if (!str) return null;
  const s = str.toLowerCase().replace(/\./g, '').trim();
  if (/^\d+(\,\d+)?jt$/.test(s))  return parseFloat(s.replace(',', '.')) * 1_000_000;
  if (/^\d+(\.\d+)?jt$/.test(s))  return parseFloat(s) * 1_000_000;
  if (/^\d+(\.\d+)?rb$/.test(s))  return parseFloat(s) * 1_000;
  if (/^\d+(\.\d+)?k$/.test(s))   return parseFloat(s) * 1_000;
  if (/^\d+(\.\d+)?m$/.test(s))   return parseFloat(s) * 1_000_000;
  const n = parseFloat(s.replace(/[^\d.]/g, ''));
  return isNaN(n) ? null : n;
}
 
/**
 * Strip Markdown formatting untuk WA (WA punya format sendiri)
 * *bold* → *bold* (WA support)
 * _italic_ → _italic_ (WA support)
 * `code` → dihapus
 */
function stripForWA(text) {
  return text
    .replace(/`([^`]+)`/g, '$1')   // hapus backtick code
    .replace(/\n---+\n/g, '\n─────────────────\n'); // ganti HR
}
 
/**
 * Ambil wallet dari pesan WA — auto-resolve ke primary kalau linked
 * Attaches wallet.lang dari database
 */
function getWallet(chatId, chatName = '') {
  const wallet = getOrCreateWallet('whatsapp', chatId, chatName);
  const primaryId = resolveWalletId(wallet.id);
  let finalWallet;
  if (primaryId !== wallet.id) {
    const { getDb } = require('../core/database');
    finalWallet = getDb().prepare('SELECT * FROM wallets WHERE id = ?').get(primaryId) || wallet;
  } else {
    finalWallet = wallet;
  }
  finalWallet.lang = getLang(finalWallet.id);
  return finalWallet;
}
 
/**
 * Kirim pesan teks ke chat WA
 */
async function send(jid, text) {
  if (!waSocket) return;
  try {
    await waSocket.sendMessage(jid, { text: stripForWA(text) });
  } catch (err) {
    console.error('[WA send error]', err.message);
  }
}
 
/**
 * Kirim pesan reply (quote)
 */
async function reply(sock, msg, text) {
  try {
    await sock.sendMessage(msg.key.remoteJid, {
      text: stripForWA(text),
    }, { quoted: msg });
  } catch (err) {
    console.error('[WA reply error]', err.message);
  }
}
 
// ─── Command Handlers ─────────────────────────────────────
 
async function handleHelp(sock, msg) {
  const prefix = config.wa.prefix;
  await reply(sock, msg,
    `📋 *Daftar Perintah Bot Simpan Uang*\n\n` +
    `💰 *Transaksi*\n` +
    `${prefix}catat masuk 500rb gaji\n` +
    `${prefix}catat keluar 50rb makan\n` +
    `${prefix}saldo — lihat saldo\n` +
    `${prefix}history — 10 transaksi terakhir\n` +
    `${prefix}undo — batalkan transaksi terakhir\n` +
    `${prefix}hapus [id] — hapus transaksi by ID\n` +
    `${prefix}edit [id] [jumlah] [catatan] — edit transaksi\n\n` +
    `🎯 *Target Tabungan*\n` +
    `${prefix}target buat Liburan 3jt\n` +
    `${prefix}target buat HP 5jt 2026-12-31\n` +
    `${prefix}target lihat\n` +
    `${prefix}target hapus Liburan\n` +
    `${prefix}tabung 100rb Liburan\n\n` +
    `📊 *Laporan*\n` +
    `${prefix}laporan hari\n` +
    `${prefix}laporan minggu\n` +
    `${prefix}laporan bulan\n` +
    `${prefix}kategori [hari/minggu/bulan]\n\n` +
    `💡 *Budget*\n` +
    `${prefix}budget — lihat semua budget bulan ini\n` +
    `${prefix}budget makan 500rb — set budget kategori\n` +
    `${prefix}budget hapus makan — hapus budget\n\n` +
    `🔄 *Rutin (Berulang)*\n` +
    `${prefix}rutin — lihat daftar rutin\n` +
    `${prefix}rutin tambah keluar 150rb netflix 5 — tiap tgl 5\n` +
    `${prefix}rutin hapus [id]\n\n` +
    `⏰ *Reminder*\n` +
    `${prefix}reminder 20:00 — aktifkan notif harian\n` +
    `${prefix}reminder off — matikan notif\n\n` +
    `🔗 *Share Wallet*\n` +
    `${prefix}wallet share — buat kode undangan\n` +
    `${prefix}wallet gabung KODE — gabung ke wallet orang\n` +
    `${prefix}wallet pisah — berhenti berbagi\n\n` +
    `💱 *Multi-Kurs (160+ mata uang)*\n` +
    `${prefix}kurs — lihat kurs populer (live)\n` +
    `${prefix}kurs JPY — cek kurs spesifik\n` +
    `${prefix}kurs set THB 435 — set kurs manual\n` +
    `${prefix}kurs update — refresh dari server\n` +
    `${prefix}catat keluar 500THB makan — auto-konversi ke IDR\n\n` +
    `_Shorthand: 500rb · 1.5jt · 1k_`
  );
}
 
async function handleCatat(sock, msg, args, senderName) {
  const chatId = msg.key.remoteJid;
  const typeRaw = args[0]?.toLowerCase();
  let amountRaw = args[1];
  const note = args.slice(2).join(' ') || '';
 
  if (!typeRaw || !['masuk', 'keluar', 'in', 'out'].includes(typeRaw)) {
    return reply(sock, msg,
      `❌ Format salah!\nContoh:\n` +
      `${config.wa.prefix}catat masuk 500rb gaji\n` +
      `${config.wa.prefix}catat keluar 50rb makan\n` +
      `${config.wa.prefix}catat keluar 500THB makan (mata uang lain)`
    );
  }
 
  // Deteksi currency suffix: 500THB, 100USD, 50MYR, dll.
  let finalAmount = null;
  let currencyNote = '';
  const currencyMatch = amountRaw?.match(/^(\d+(?:[.,]\d+)?(?:rb|jt|k|m)?)([A-Z]{2,6})$/i);
  if (currencyMatch) {
    const rawNum = currencyMatch[1];
    const currCode = currencyMatch[2].toUpperCase();
    const numVal = parseJumlah(rawNum);
    if (numVal && numVal > 0) {
      try {
        const chatName = msg.key.remoteJid.endsWith('@g.us') ? '' : senderName;
        const walletTmp = getWallet(chatId, chatName);
        const converted = convertToIdr(walletTmp.id, numVal, currCode);
        finalAmount = converted;
        currencyNote = ` (${numVal} ${currCode} → ${formatRupiah(converted)})`;
      } catch (e) {
        return reply(sock, msg, `❌ ${e.message}`);
      }
    }
  } else {
    finalAmount = parseJumlah(amountRaw);
  }
 
  if (!finalAmount || finalAmount <= 0) {
    return reply(sock, msg,
      `❌ Jumlah tidak valid: *${amountRaw}*\nContoh: 500000 · 500rb · 1.5jt · 500THB`
    );
  }
 
  const type = ['masuk', 'in'].includes(typeRaw) ? 'in' : 'out';
 
  try {
    const chatName = msg.key.remoteJid.endsWith('@g.us')
      ? '' // nama group diambil saat socket ready, skip dulu
      : senderName;
    const wallet = getWallet(chatId, chatName);
    const fullNote = (note + currencyNote).trim();
    const trx = addTransaction(wallet.id, type, finalAmount, fullNote, 'umum', senderName);
    const { saldo } = getSaldo(wallet.id);
 
    let replyText = formatTransaksi(trx, wallet.lang) + `\n\n💰 Saldo sekarang: *${formatRupiah(saldo)}*`;
 
    // Cek budget alert kalau ini pengeluaran
    if (type === 'out') {
      const alert = checkBudgetAlert(wallet.id, trx.category);
      if (alert) {
        const icon = alert.level === 'danger' ? '🚨' : '⚠️';
        const label = alert.level === 'danger' ? 'Budget HABIS' : 'Budget hampir habis';
        replyText += `\n\n${icon} *${label}!*\n` +
          `Kategori: ${alert.category}\n` +
          `Terpakai: ${formatRupiah(alert.spent)} / ${formatRupiah(alert.budget)} (${alert.persen}%)`;
      }
    }
 
    await reply(sock, msg, replyText);
  } catch (err) {
    console.error('[WA /catat]', err);
    reply(sock, msg, '❌ Gagal catat transaksi. Coba lagi.');
  }
}
 
async function handleSaldo(sock, msg) {
  try {
    const chatId = msg.key.remoteJid;
    const wallet = getWallet(chatId);
    const data   = getSaldoMultiCurrency(wallet.id);
    let text     = formatSaldo(data, wallet.lang);
 
    // Tampilkan konversi currency jika user sudah set kurs
    if (data.conversions?.length) {
      const lines = data.conversions.map(c => {
        const val = Math.abs(c.value) >= 100
          ? Math.round(c.value).toLocaleString('id-ID')
          : c.value.toFixed(2);
        return `   ≈ ${c.symbol} ${val} (${c.code})`;
      });
      text += '\n' + lines.join('\n');
    }
 
    await reply(sock, msg, text);
  } catch (err) {
    console.error('[WA /saldo]', err);
    reply(sock, msg, '❌ Gagal ambil saldo.');
  }
}
 
async function handleHistory(sock, msg, args) {
  try {
    const limit = Math.min(parseInt(args[0]) || 10, 30);
    const wallet = getWallet(msg.key.remoteJid);
    const transactions = getHistory(wallet.id, limit);
    await reply(sock, msg, formatHistory(transactions, wallet.lang));
  } catch (err) {
    console.error('[WA /history]', err);
    reply(sock, msg, '❌ Gagal ambil history.');
  }
}
 
async function handleUndo(sock, msg) {
  try {
    const wallet = getWallet(msg.key.remoteJid);
    const deleted = undoLast(wallet.id);
 
    if (!deleted) {
      return reply(sock, msg, '📭 Tidak ada transaksi yang bisa dibatalkan.');
    }
 
    const icon = deleted.type === 'in' ? '📈' : '📉';
    const { saldo } = getSaldo(wallet.id);
    await reply(sock, msg,
      `✅ *Transaksi dibatalkan!*\n\n` +
      `${icon} ${formatRupiah(deleted.amount)}` +
      (deleted.note ? ` · ${deleted.note}` : '') +
      `\n\n💰 Saldo sekarang: *${formatRupiah(saldo)}*`
    );
  } catch (err) {
    console.error('[WA /undo]', err);
    reply(sock, msg, '❌ Gagal undo transaksi.');
  }
}
 
async function handleLaporan(sock, msg, args) {
  try {
    const period = args[0]?.toLowerCase() || 'bulan';
 
    if (!['hari', 'minggu', 'bulan'].includes(period)) {
      return reply(sock, msg,
        `❌ Period tidak valid.\nGunakan:\n` +
        `${config.wa.prefix}laporan hari\n` +
        `${config.wa.prefix}laporan minggu\n` +
        `${config.wa.prefix}laporan bulan`
      );
    }
 
    const wallet = getWallet(msg.key.remoteJid);
    const data = getLaporan(wallet.id, period);
    await reply(sock, msg, formatLaporan(data, period, wallet.lang));
  } catch (err) {
    console.error('[WA /laporan]', err);
    reply(sock, msg, '❌ Gagal buat laporan.');
  }
}
 
async function handleTarget(sock, msg, args) {
  const prefix = config.wa.prefix;
  const sub = args[0]?.toLowerCase();
 
  if (!sub || !['lihat', 'buat', 'hapus', 'setor'].includes(sub)) {
    return reply(sock, msg,
      `❌ Subcommand tidak valid.\nGunakan:\n` +
      `${prefix}target lihat\n` +
      `${prefix}target buat NamaGoal Jumlah [deadline]\n` +
      `${prefix}target setor NamaGoal Jumlah\n` +
      `${prefix}target hapus NamaGoal`
    );
  }
 
  try {
    const wallet = getWallet(msg.key.remoteJid);
 
    if (sub === 'lihat') {
      const goals = getGoals(wallet.id);
      // Ambil kurs USD live, fallback ke null (formatter pakai default 15750)
      let usdRate = null;
      try {
        const { getDb } = require('../core/database');
        const usdRow = getDb().prepare('SELECT rate_to_idr FROM live_rates WHERE code = ?').get('USD');
        if (usdRow) usdRate = usdRow.rate_to_idr;
      } catch (_) {}
      return reply(sock, msg, formatGoals(goals, getGoalProgress, usdRate, wallet.lang, config.wa.prefix));
    }
 
    if (sub === 'hapus') {
      const name = args.slice(1).join(' ');
      if (!name) return reply(sock, msg, `❌ Ketik nama goal.\nContoh: ${prefix}target hapus Liburan`);
      const deleted = deleteGoal(wallet.id, name);
      return reply(sock, msg,
        `✅ *Goal dihapus!*\n\n` +
        `🎯 ${deleted.name}\n` +
        `Dana terkumpul: ${formatRupiah(deleted.current_amount)}`
      );
    }
 
    if (sub === 'setor') {
      // !target setor NamaGoal Jumlah  — last arg = jumlah, rest = nama goal
      const amountRaw = args[args.length - 1];
      const amount = parseJumlah(amountRaw);
      if (!amount || amount <= 0 || args.length < 3) {
        return reply(sock, msg,
          `❌ Format salah!\nContoh: ${prefix}target setor Liburan Bali 500rb`
        );
      }
      const goalName = args.slice(1, args.length - 1).join(' ');
      if (!goalName) return reply(sock, msg, `❌ Ketik nama goal.\nContoh: ${prefix}target setor Liburan 500rb`);
 
      const { goal, isCompleted } = addToGoal(wallet.id, goalName, amount);
      const { persen } = getGoalProgress(goal);
      let text = `✅ *Setor berhasil!*\n\n`;
      text += `🎯 *${goal.name}*\n`;
      text += `Disetor: *${formatRupiah(amount)}*\n`;
      text += `Terkumpul: ${formatRupiah(goal.current_amount)} / ${formatRupiah(goal.target_amount)}\n`;
      text += `Progress: ${persen}%\n`;
      if (isCompleted) {
        text += `\n🎉 *GOAL TERCAPAI! Selamat!* 🎉`;
      } else {
        text += `Sisa: ${formatRupiah(goal.target_amount - goal.current_amount)}`;
      }
      return reply(sock, msg, text);
    }
 
    if (sub === 'buat') {
      const lastArg = args[args.length - 1];
      const isDeadline = /^\d{4}-\d{2}-\d{2}$/.test(lastArg);
      const deadline = isDeadline ? lastArg : null;
      const amountArg = isDeadline ? args[args.length - 2] : args[args.length - 1];
      const amount = parseJumlah(amountArg);
 
      if (!amount || amount <= 0) {
        return reply(sock, msg,
          `❌ Format salah!\nContoh: ${prefix}target buat Liburan 3jt`
        );
      }
 
      const nameEnd = isDeadline ? args.length - 2 : args.length - 1;
      const name = args.slice(1, nameEnd).join(' ');
      if (!name) return reply(sock, msg, `❌ Ketik nama goal.\nContoh: ${prefix}target buat Liburan Bali 3jt`);
 
      const goal = createGoal(wallet.id, name, amount, deadline);
      return reply(sock, msg,
        `✅ *Goal dibuat!*\n\n` +
        `🎯 *${goal.name}*\n` +
        `Target: ${formatRupiah(goal.target_amount)}\n` +
        (deadline ? `Deadline: ${deadline}\n` : '') +
        `\nGunakan \`${prefix}tabung jumlah ${goal.name}\` untuk mulai nabung!`
      );
    }
  } catch (err) {
    console.error('[WA /target]', err);
    reply(sock, msg, `❌ ${err.message || 'Terjadi error.'}`);
  }
}
 
async function handleTabung(sock, msg, args) {
  try {
    const amountRaw = args[0];
    const goalName = args.slice(1).join(' ');
    const amount = parseJumlah(amountRaw);
 
    if (!amount || amount <= 0) {
      return reply(sock, msg,
        `❌ Format salah!\nContoh: ${config.wa.prefix}tabung 100rb Liburan`
      );
    }
    if (!goalName) {
      return reply(sock, msg,
        `❌ Ketik nama goal tujuan.\nContoh: ${config.wa.prefix}tabung 100rb Liburan`
      );
    }
 
    const wallet = getWallet(msg.key.remoteJid);
    const { goal, isCompleted } = addToGoal(wallet.id, goalName, amount);
    const { persen } = getGoalProgress(goal);
 
    let text = `✅ *Tabungan bertambah!*\n\n`;
    text += `🎯 *${goal.name}*\n`;
    text += `Ditambah: *${formatRupiah(amount)}*\n`;
    text += `Terkumpul: ${formatRupiah(goal.current_amount)} / ${formatRupiah(goal.target_amount)}\n`;
    text += `Progress: ${persen}%\n`;
 
    if (isCompleted) {
      text += `\n🎉 *GOAL TERCAPAI! Selamat!* 🎉`;
    } else {
      text += `Sisa: ${formatRupiah(goal.target_amount - goal.current_amount)}`;
    }
 
    await reply(sock, msg, text);
  } catch (err) {
    console.error('[WA /tabung]', err);
    reply(sock, msg, `❌ ${err.message || 'Terjadi error.'}`);
  }
}
 
async function handleHapus(sock, msg, args) {
  try {
    const idRaw = args[0];
    const id = parseInt(idRaw);
 
    if (!idRaw || isNaN(id) || id <= 0) {
      return reply(sock, msg,
        `❌ Ketik ID transaksi yang mau dihapus.\n` +
        `Contoh: ${config.wa.prefix}hapus 42\n\n` +
        `Gunakan ${config.wa.prefix}history untuk lihat ID transaksi.`
      );
    }
 
    const wallet = getWallet(msg.key.remoteJid);
    const deleted = deleteTransaction(wallet.id, id);
    const { saldo } = getSaldo(wallet.id);
 
    const icon = deleted.type === 'in' ? '📈' : '📉';
    await reply(sock, msg,
      `🗑️ *Transaksi dihapus!*\n\n` +
      `${icon} #${deleted.id} ${formatRupiah(deleted.amount)}` +
      (deleted.note ? ` · ${deleted.note}` : '') +
      `\n\n💰 Saldo sekarang: *${formatRupiah(saldo)}*`
    );
  } catch (err) {
    console.error('[WA /hapus]', err);
    reply(sock, msg, `❌ ${err.message || 'Gagal hapus transaksi.'}`);
  }
}
 
async function handleKategori(sock, msg, args) {
  try {
    const period = args[0]?.toLowerCase() || 'bulan';
    if (!['hari', 'minggu', 'bulan'].includes(period)) {
      return reply(sock, msg,
        `❌ Period tidak valid.\nGunakan:\n` +
        `${config.wa.prefix}kategori hari\n` +
        `${config.wa.prefix}kategori minggu\n` +
        `${config.wa.prefix}kategori bulan`
      );
    }
    const wallet = getWallet(msg.key.remoteJid);
    const rows = getLaporanKategori(wallet.id, period);
    await reply(sock, msg, formatKategori(rows, period, wallet.lang, config.wa.prefix));
  } catch (err) {
    console.error('[WA /kategori]', err);
    reply(sock, msg, '❌ Gagal buat laporan kategori.');
  }
}
 
async function handleReminder(sock, msg, args) {
  try {
    const input = args[0]?.toLowerCase();
    if (!input) {
      return reply(sock, msg,
        `❌ Ketik jam atau "off".\nContoh:\n` +
        `${config.wa.prefix}reminder 20:00\n` +
        `${config.wa.prefix}reminder off`
      );
    }
 
    const wallet = getWallet(msg.key.remoteJid);
 
    if (input === 'off') {
      disableReminder(wallet.id);
      return reply(sock, msg, '🔕 Reminder dimatikan.');
    }
 
    const time = setReminder(wallet.id, 'whatsapp', input);
    return reply(sock, msg,
      `⏰ *Reminder diset!*\n\nKamu akan dapat notif harian jam *${time}* WIB.`
    );
  } catch (err) {
    console.error('[WA /reminder]', err);
    reply(sock, msg, `❌ ${err.message || 'Terjadi error.'}`);
  }
}
 
async function handleBudget(sock, msg, args) {
  const prefix = config.wa.prefix;
  try {
    const wallet = getWallet(msg.key.remoteJid);
 
    // Tanpa args — lihat semua budget
    if (!args.length) {
      const budgets = getBudgets(wallet.id);
      return reply(sock, msg, formatBudgets(budgets, wallet.lang));
    }
 
    const sub = args[0]?.toLowerCase();
 
    // !budget hapus [kategori bisa multi-kata]
    if (sub === 'hapus') {
      const category = args.slice(1).join(' ').toLowerCase();
      if (!category) return reply(sock, msg, `❌ Ketik nama kategori.\nContoh: ${prefix}budget hapus makan`);
      const deleted = deleteBudget(wallet.id, category);
      return reply(sock, msg,
        `✅ *Budget dihapus!*\n\nKategori: ${deleted.category}\nBudget: ${formatRupiah(deleted.amount)}`
      );
    }
 
    // !budget [kategori bisa multi-kata] [jumlah]
    // Jumlah selalu arg terakhir, sisanya = nama kategori
    const amountRaw = args[args.length - 1];
    const amount = parseJumlah(amountRaw);
    if (!amount || amount <= 0 || args.length < 2) {
      return reply(sock, msg,
        `❌ Format salah!\nContoh:\n` +
        `${prefix}budget makan 500rb\n` +
        `${prefix}budget belanja online 1jt\n` +
        `${prefix}budget transport 300rb`
      );
    }
 
    const category = args.slice(0, args.length - 1).join(' ').toLowerCase();
    const budget = setBudget(wallet.id, category, amount);
    return reply(sock, msg,
      `✅ *Budget diset!*\n\n` +
      `Kategori: *${budget.category}*\n` +
      `Budget: *${formatRupiah(budget.amount)}*\n` +
      `Periode: ${formatBulan(budget.month)}\n\n` +
      `_Kamu akan dapat peringatan saat mencapai 80% dan 100%._`
    );
  } catch (err) {
    console.error('[WA /budget]', err);
    reply(sock, msg, `❌ ${err.message || 'Gagal proses budget.'}`);
  }
}
 
async function handleRutin(sock, msg, args) {
  const prefix = config.wa.prefix;
  try {
    const wallet = getWallet(msg.key.remoteJid);
 
    // Tanpa args — lihat daftar rutin
    if (!args.length) {
      const list = getRecurring(wallet.id);
      return reply(sock, msg, formatRecurring(list, prefix, wallet.lang));
    }
 
    const sub = args[0]?.toLowerCase();
 
    // !rutin hapus [id]
    if (sub === 'hapus') {
      const id = parseInt(args[1]);
      if (!args[1] || isNaN(id) || id <= 0) {
        return reply(sock, msg, `❌ Ketik ID rutin.\nContoh: ${prefix}rutin hapus 3`);
      }
      const deleted = deleteRecurring(wallet.id, id);
      return reply(sock, msg,
        `✅ *Rutin dihapus!*\n\n` +
        `${deleted.type === 'in' ? '📈' : '📉'} ${formatRupiah(deleted.amount)}` +
        (deleted.note ? ` · ${deleted.note}` : '') +
        `\nTiap tgl ${deleted.day_of_month}`
      );
    }
 
    // !rutin tambah [masuk/keluar] [jumlah] [catatan...] [tgl]
    if (sub === 'tambah') {
      const typeRaw = args[1]?.toLowerCase();
      if (!typeRaw || !['masuk', 'keluar', 'in', 'out'].includes(typeRaw)) {
        return reply(sock, msg,
          `❌ Format salah!\nContoh:\n` +
          `${prefix}rutin tambah keluar 150rb netflix 5\n` +
          `${prefix}rutin tambah masuk 5jt gaji 25`
        );
      }
 
      const type = ['masuk', 'in'].includes(typeRaw) ? 'in' : 'out';
      const amount = parseJumlah(args[2]);
      if (!amount || amount <= 0) {
        return reply(sock, msg,
          `❌ Jumlah tidak valid.\nContoh: ${prefix}rutin tambah keluar 150rb netflix 5`
        );
      }
 
      // Arg terakhir harus angka 1-28 (tanggal)
      const lastArg = args[args.length - 1];
      const day = parseInt(lastArg);
      if (isNaN(day) || day < 1 || day > 28) {
        return reply(sock, msg,
          `❌ Tanggal tidak valid (1-28).\nContoh: ${prefix}rutin tambah keluar 150rb netflix 5`
        );
      }
 
      const note = args.slice(3, args.length - 1).join(' ') || '';
      const rec = addRecurring(wallet.id, type, amount, note, 'umum', day);
 
      return reply(sock, msg,
        `✅ *Transaksi rutin ditambah!*\n\n` +
        `${rec.type === 'in' ? '📈' : '📉'} *${formatRupiah(rec.amount)}*` +
        (rec.note ? ` · ${rec.note}` : '') + `\n` +
        `Kategori: ${rec.category}\n` +
        `Tiap tanggal: *${rec.day_of_month}*\n\n` +
        `_Akan dicatat otomatis setiap bulan._`
      );
    }
 
    // Subcommand tidak dikenal
    return reply(sock, msg,
      `❌ Subcommand tidak valid.\nGunakan:\n` +
      `${prefix}rutin\n` +
      `${prefix}rutin tambah keluar 150rb netflix 5\n` +
      `${prefix}rutin hapus [id]`
    );
  } catch (err) {
    console.error('[WA /rutin]', err);
    reply(sock, msg, `❌ ${err.message || 'Gagal proses rutin.'}`);
  }
}
 
async function handleEdit(sock, msg, args) {
  const prefix = config.wa.prefix;
  try {
    const id = parseInt(args[0]);
    if (!args[0] || isNaN(id) || id <= 0) {
      return reply(sock, msg,
        `❌ Format salah!\nContoh:\n` +
        `${prefix}edit 42 75rb — ubah jumlah\n` +
        `${prefix}edit 42 75rb kopi susu — ubah jumlah & catatan`
      );
    }
 
    const newAmount = args[1] ? parseJumlah(args[1]) : null;
    const newNote = args.length > 2 ? args.slice(2).join(' ') : null;
 
    if (newAmount === null && newNote === null) {
      return reply(sock, msg,
        `❌ Ketik jumlah atau catatan baru.\nContoh: ${prefix}edit 42 75rb kopi susu`
      );
    }
    if (args[1] && newAmount === null) {
      return reply(sock, msg, `❌ Jumlah tidak valid: *${args[1]}*\nContoh: 75000 · 75rb · 1.5jt`);
    }
 
    const wallet = getWallet(msg.key.remoteJid);
    const updated = editTransaction(wallet.id, id, newAmount, newNote);
 
    return reply(sock, msg,
      `✏️ *Transaksi diupdate!*\n\n` +
      `#${updated.id} ${updated.type === 'in' ? '📈' : '📉'} *${formatRupiah(updated.amount)}*` +
      (updated.note ? `\nCatatan: ${updated.note}` : '') +
      `\nKategori: ${updated.category}`
    );
  } catch (err) {
    console.error('[WA /edit]', err);
    reply(sock, msg, `❌ ${err.message || 'Gagal edit transaksi.'}`);
  }
}
 
async function handleWallet(sock, msg, args) {
  const prefix = config.wa.prefix;
  const sub = args[0]?.toLowerCase();
  const chatId = msg.key.remoteJid;
  const myWallet = getOrCreateWallet('whatsapp', chatId);
 
  try {
    if (sub === 'share' || sub === 'bagikan') {
      const code = createInviteCode(myWallet.id);
      return reply(sock, msg,
        `🔗 *Kode Share Wallet*\n\n` +
        `Kode: *${code}*\n` +
        `Berlaku: 24 jam\n\n` +
        `Kirim ke orang yang mau bergabung:\n` +
        `\`${prefix}wallet gabung ${code}\``
      );
    }
 
    if (sub === 'gabung') {
      const code = args[1];
      if (!code) return reply(sock, msg, `❌ Ketik kode undangan.\nContoh: ${prefix}wallet gabung ABC123`);
      const primary = useInviteCode(myWallet.id, code);
      return reply(sock, msg,
        `✅ *Berhasil bergabung!*\n\n` +
        `Sekarang kamu mengakses wallet: *${primary.name || primary.id}*\n` +
        `Semua transaksi akan dicatat ke wallet tersebut.\n\n` +
        `Gunakan \`${prefix}wallet pisah\` untuk berhenti berbagi.`
      );
    }
 
    if (sub === 'pisah') {
      const link = unlinkWallet(myWallet.id);
      return reply(sock, msg,
        `✅ *Wallet dipisah!*\n\nKamu sekarang kembali menggunakan wallet sendiri.`
      );
    }
 
    if (sub === 'info') {
      const { getDb } = require('../core/database');
      const link = getDb().prepare('SELECT * FROM wallet_links WHERE member_id = ?').get(myWallet.id);
      if (link) {
        const primary = getDb().prepare('SELECT * FROM wallets WHERE id = ?').get(link.primary_id);
        return reply(sock, msg,
          `🔗 *Status Wallet*\n\n` +
          `Kamu sedang berbagi wallet dengan:\n*${primary?.name || link.primary_id}*\n\n` +
          `Gunakan \`${prefix}wallet pisah\` untuk berhenti.`
        );
      }
      return reply(sock, msg,
        `👛 *Status Wallet*\n\nKamu menggunakan wallet sendiri.\n\n` +
        `Bagikan ke orang lain: \`${prefix}wallet share\``
      );
    }
 
    return reply(sock, msg,
      `❓ Subcommand wallet:\n` +
      `${prefix}wallet share — buat kode undangan\n` +
      `${prefix}wallet gabung KODE — gabung ke wallet orang lain\n` +
      `${prefix}wallet pisah — berhenti berbagi\n` +
      `${prefix}wallet info — cek status`
    );
  } catch (err) {
    reply(sock, msg, `❌ ${err.message}`);
  }
}
 
async function handleKurs(sock, msg, args) {
  const prefix = config.wa.prefix;
  const sub = args[0]?.toLowerCase();
  const wallet = getWallet(msg.key.remoteJid);
 
  try {
    // !kurs update — refresh dari API
    if (sub === 'update') {
      await reply(sock, msg, '🔄 Mengambil kurs terbaru dari server...');
      try {
        const { count, usdRate } = await fetchLiveRates();
        return reply(sock, msg,
          `✅ *Kurs berhasil diperbarui!*\n\n` +
          `📊 ${count} mata uang tersedia\n` +
          `💵 1 USD = Rp ${usdRate.toLocaleString('id-ID')}\n\n` +
          `Cek kurs: \`${prefix}kurs\``
        );
      } catch (e) {
        return reply(sock, msg, `❌ Gagal update kurs: ${e.message}\nCoba lagi nanti.`);
      }
    }
 
    // !kurs set CODE RATE — set kurs manual/custom
    if (sub === 'set') {
      const code = args[1]?.toUpperCase();
      const rate = parseFloat(args[2]);
      if (!code || !rate || rate <= 0) {
        return reply(sock, msg, `❌ Format: ${prefix}kurs set THB 435\n(1 THB = 435 IDR)`);
      }
      const result = setCurrency(wallet.id, code, rate);
      return reply(sock, msg,
        `✅ *Kurs custom disimpan!*\n\n1 ${result.code} = Rp ${rate.toLocaleString('id-ID')}\n` +
        `_(Override live rate — hanya berlaku di wallet ini)_\n\n` +
        `Contoh pakai: \`${prefix}catat keluar 500${result.code} makan\``
      );
    }
 
    // !kurs [CODE] — cek kurs mata uang spesifik
    if (sub && /^[a-z]{2,6}$/.test(sub)) {
      const code = sub.toUpperCase();
      const all = getCurrencies(wallet.id);
      const found = all.find(r => r.code === code);
      if (!found) {
        return reply(sock, msg,
          `❓ Kurs *${code}* tidak ditemukan.\n\n` +
          `Coba: \`${prefix}kurs update\` untuk refresh data\n` +
          `Atau: \`${prefix}kurs set ${code} [nilai]\` untuk set manual`
        );
      }
      const label = found.is_custom ? '*(custom)*' : '_(live rate)_';
      return reply(sock, msg,
        `💱 *Kurs ${code}*\n\n` +
        `1 ${code} = Rp ${Math.round(found.rate_to_idr).toLocaleString('id-ID')} ${label}\n\n` +
        `_Update: ${found.updated_at || '-'}_`
      );
    }
 
    // !kurs — tampilkan kurs populer + info
    const updatedAt = getLiveRateUpdatedAt();
    const all = getCurrencies(wallet.id);
    const customMap = new Map(all.filter(r => r.is_custom).map(r => [r.code, r]));
    const liveMap  = new Map(all.filter(r => !r.is_custom).map(r => [r.code, r]));
 
    let out = `💱 *Kurs Mata Uang*\n`;
    if (updatedAt) out += `_Update: ${updatedAt} WIB_\n`;
    out += `\n`;
 
    // Tampilkan custom rates kalau ada
    if (customMap.size > 0) {
      out += `🔧 *Custom (wallet kamu):*\n`;
      customMap.forEach(r => {
        out += `• ${r.code}: Rp ${Math.round(r.rate_to_idr).toLocaleString('id-ID')}\n`;
      });
      out += `\n`;
    }
 
    // Kurs populer dari live rates
    out += `📊 *Kurs Populer (live):*\n`;
    let shown = 0;
    for (const code of POPULAR_CURRENCIES) {
      if (customMap.has(code)) continue;
      const r = liveMap.get(code);
      if (r) {
        out += `• ${code}: Rp ${Math.round(r.rate_to_idr).toLocaleString('id-ID')}\n`;
        shown++;
      }
    }
 
    if (!updatedAt && shown === 0) {
      out += `_Data live belum tersedia._\n`;
    }
 
    out += `\n💡 *Perintah lain:*\n`;
    out += `• \`${prefix}kurs JPY\` — cek kurs spesifik\n`;
    out += `• \`${prefix}kurs set THB 435\` — set kurs manual\n`;
    out += `• \`${prefix}kurs update\` — refresh dari server\n`;
    out += `\n_160+ mata uang tersedia · auto-refresh tiap hari 07:00 WIB_`;
 
    return reply(sock, msg, out);
  } catch (err) {
    reply(sock, msg, `❌ ${err.message}`);
  }
}
 
// ─── Bahasa / Language ────────────────────────────────────
 
async function handleBahasa(sock, msg, args) {
  const prefix = config.wa.prefix;
  const chatId = msg.key.remoteJid;
  try {
    const langArg = args[0]?.toLowerCase();
    const myWallet = getOrCreateWallet('whatsapp', chatId, '');
 
    if (!langArg) {
      const currentLang = getLang(myWallet.id);
      return reply(sock, msg, t(currentLang, 'lang_current') + '\n\n' + t(currentLang, 'lang_usage').replace(/`\//g, `\`${prefix}`));
    }
 
    if (!['id', 'en'].includes(langArg)) {
      return reply(sock, msg, '❌ ' + t(getLang(myWallet.id), 'lang_usage').replace(/`\//g, `\`${prefix}`));
    }
 
    setLang(myWallet.id, langArg);
    return reply(sock, msg, t(langArg, 'lang_switched', langArg));
  } catch (err) {
    console.error('[WA !bahasa]', err);
    reply(sock, msg, '❌ Terjadi error.');
  }
}
 
// ─── Grafik / Chart ───────────────────────────────────────
 
async function handleGrafik(sock, msg, args) {
  const chatId = msg.key.remoteJid;
  try {
    const period = args[0]?.toLowerCase() || 'bulan';
 
    if (!['hari', 'minggu', 'bulan'].includes(period)) {
      const prefix = config.wa.prefix;
      return reply(sock, msg,
        `❌ Period tidak valid.\nGunakan:\n` +
        `${prefix}grafik\n` +
        `${prefix}grafik hari\n` +
        `${prefix}grafik minggu\n` +
        `${prefix}grafik bulan`
      );
    }
 
    const wallet = getWallet(chatId);
    const result = buildChartConfig(wallet.id, period, wallet.lang);
 
    if (!result) {
      return reply(sock, msg, wallet.lang === 'en'
        ? '📭 No expenses recorded for this period.'
        : '📭 Belum ada pengeluaran untuk periode ini.');
    }
 
    const buffer = await fetchGrafikBuffer(result.config);
    const caption = buildGrafikCaption(result.keluar, result.total, period, wallet.lang);
    await sock.sendMessage(chatId, { image: buffer, caption }, { quoted: msg });
  } catch (err) {
    console.error('[WA !grafik]', err);
    reply(sock, msg, '❌ Gagal buat grafik. Coba lagi.');
  }
}
 
// ─── Trend Bulanan ────────────────────────────────────────
 
async function handleTrend(sock, msg, args) {
  const chatId = msg.key.remoteJid;
  try {
    const months = parseInt(args[0]) || 6;
    if (![3, 6, 12].includes(months)) {
      const p = config.wa.prefix;
      return reply(sock, msg,
        `❌ Jumlah bulan tidak valid.\nGunakan:\n${p}trend 3\n${p}trend 6\n${p}trend 12`
      );
    }
    const wallet = getWallet(chatId);
    const result = buildTrendConfig(wallet.id, months, wallet.lang);
    if (!result) {
      return reply(sock, msg, wallet.lang === 'en'
        ? `📭 No data for the last ${months} months.`
        : `📭 Belum ada data untuk ${months} bulan terakhir.`);
    }
    const buffer  = await fetchGrafikBuffer(result.config);
    const caption = buildTrendCaption(result.rows, months, wallet.lang);
    await sock.sendMessage(chatId, { image: buffer, caption }, { quoted: msg });
  } catch (err) {
    console.error('[WA !trend]', err);
    reply(sock, msg, '❌ Gagal buat grafik trend. Coba lagi.');
  }
}
 
// ─── OCR Struk ────────────────────────────────────────────
 
/**
 * Handle pesan gambar yang dikirim dengan caption "struk"/"bon"/"receipt"
 * @param {object} sock - WA socket
 * @param {object} msg  - pesan WA lengkap (harus imageMessage)
 */
async function handleImageOcr(sock, msg) {
  const chatId  = msg.key.remoteJid;
  const caption = (msg.message?.imageMessage?.caption || '').toLowerCase().trim();
  const isOcr   = /\b(struk|bon|receipt|nota|catat)\b/.test(caption);
  if (!isOcr) return; // abaikan foto tanpa keyword
 
  const wallet = getWallet(chatId);
 
  try {
    reply(sock, msg, wallet.lang === 'en'
      ? '🔍 Reading receipt...'
      : '🔍 Memproses struk...');
 
    // Download gambar via baileys
    const { downloadMediaMessage } = require('@whiskeysockets/baileys');
    const imgBuffer = await downloadMediaMessage(msg, 'buffer', {}, { logger: pino({ level: 'silent' }) });
 
    const rawText = await ocrImage(imgBuffer, 'image/jpeg');
 
    if (!rawText.trim()) {
      return reply(sock, msg, wallet.lang === 'en'
        ? '❌ Could not read text from image. Try a clearer photo.'
        : '❌ Tidak bisa baca teks dari foto. Coba foto yang lebih jelas.');
    }
 
    const { jumlah, catatan } = parseStruk(rawText);
 
    if (!jumlah || jumlah < 100) {
      const preview = rawText.slice(0, 200).replace(/\n/g, ' ');
      return reply(sock, msg, wallet.lang === 'en'
        ? `❌ No total amount found.\n\nOCR preview: ${preview}`
        : `❌ Tidak ketemu jumlah total.\n\nHasil OCR: ${preview}`);
    }
 
    const tx = addTransaction(wallet.id, 'out', jumlah, catatan || 'Struk belanja', 'belanja', '');
 
    const budgetAlert = checkBudgetAlert(wallet.id, 'Belanja');
    const formatted   = formatTransaksi(tx, wallet.lang);
    let pesan = wallet.lang === 'en'
      ? `✅ *Receipt scanned & recorded!*\n\n${formatted}`
      : `✅ *Struk berhasil dibaca & dicatat!*\n\n${formatted}`;
    if (budgetAlert) pesan += `\n\n⚠️ ${budgetAlert}`;
 
    await sock.sendMessage(chatId, { text: pesan }, { quoted: msg });
  } catch (err) {
    console.error('[WA OCR]', err);
    reply(sock, msg, '❌ Gagal proses foto. Coba lagi.');
  }
}
 
// ─── Router ───────────────────────────────────────────────
 
/**
 * Dispatch pesan ke handler yang sesuai
 */
async function routeMessage(sock, msg, text, senderName) {
  const prefix = config.wa.prefix;
 
  // Pesan tanpa prefix → coba NLP catat cepat
  if (!text.startsWith(prefix)) {
    const nlp = parseNLP(text);
    if (!nlp) return; // bukan transaksi → abaikan
 
    try {
      const chatId = msg.key.remoteJid;
      const wallet = getWallet(chatId);
      const tx = addTransaction(wallet.id, nlp.type, nlp.amount, nlp.note, 'umum', senderName);
 
      const budgetAlert = checkBudgetAlert(wallet.id, tx.category);
      let pesan = formatTransaksi(tx, wallet.lang);
      if (budgetAlert) pesan += `\n\n⚠️ ${budgetAlert}`;
 
      const undoHint = wallet.lang === 'en'
        ? `\n\n_Reply ${prefix}undo to cancel_`
        : `\n\n_Balas ${prefix}undo untuk batalkan_`;
      pesan += undoHint;
 
      await sock.sendMessage(chatId, { text: pesan }, { quoted: msg });
    } catch (err) {
      console.error('[WA NLP]', err);
      // Diam saja kalau error — mungkin bukan transaksi
    }
    return;
  }
 
  // Split command dan args
  const parts = text.slice(prefix.length).trim().split(/\s+/);
  const command = parts[0]?.toLowerCase();
  const args = parts.slice(1);
 
  console.log(`[WA] ${senderName}: ${text}`);
 
  switch (command) {
    case 'help':
    case 'bantuan':
      return handleHelp(sock, msg);
 
    case 'catat':
      return handleCatat(sock, msg, args, senderName);
 
    case 'saldo':
      return handleSaldo(sock, msg);
 
    case 'history':
    case 'riwayat':
      return handleHistory(sock, msg, args);
 
    case 'undo':
    case 'batal':
      return handleUndo(sock, msg);
 
    case 'hapus':
    case 'delete':
      return handleHapus(sock, msg, args);
 
    case 'laporan':
    case 'report':
      return handleLaporan(sock, msg, args);
 
    case 'kategori':
    case 'category':
      return handleKategori(sock, msg, args);
 
    case 'target':
    case 'goal':
      return handleTarget(sock, msg, args);
 
    case 'tabung':
    case 'nabung':
      return handleTabung(sock, msg, args);
 
    case 'reminder':
    case 'notif':
      return handleReminder(sock, msg, args);
 
    case 'budget':
    case 'anggaran':
      return handleBudget(sock, msg, args);
 
    case 'rutin':
    case 'recurring':
      return handleRutin(sock, msg, args);
 
    case 'edit':
      return handleEdit(sock, msg, args);
 
    case 'wallet':
    case 'share':
      return handleWallet(sock, msg, args);
 
    case 'kurs':
    case 'currency':
      return handleKurs(sock, msg, args);
 
    case 'export':
      return handleExport(sock, msg, args);
 
    case 'analisis':
      return handleAnalisis(sock, msg, args);
 
    case 'kekayaan':
    case 'networth':
      return handleKekayaan(sock, msg, args);
 
    case 'bahasa':
    case 'language':
      return handleBahasa(sock, msg, args);
 
    case 'grafik':
    case 'chart':
      return handleGrafik(sock, msg, args);
 
    case 'trend':
      return handleTrend(sock, msg, args);
 
    default:
      // Command tidak dikenal — diam aja biar tidak spam grup
      break;
  }
}
 
// ─── Export CSV ───────────────────────────────────────────
 
async function handleExport(sock, msg, args) {
  const chatId = msg.key.remoteJid;
  const wallet = getOrCreateWallet('whatsapp', chatId, '');
  const walletId = resolveWalletId(wallet.id);
 
  const monthArg = args[0];
  let monthStr = null;
  if (monthArg && /^\d{4}-\d{2}$/.test(monthArg)) monthStr = monthArg;
 
  const rows = getExportData(walletId, monthStr);
  const month = monthStr || new Date().toISOString().slice(0, 7);
 
  if (!rows.length) {
    return sock.sendMessage(chatId, { text: `📭 Tidak ada transaksi untuk periode *${month}*` });
  }
 
  const csv = generateCsv(rows);
  // WA tidak support kirim file via Baileys dengan mudah — kirim teks ringkas
  const lines = csv.split('\n');
  const preview = lines.slice(0, Math.min(11, lines.length)).join('\n');
  const more = rows.length > 10 ? `\n_...dan ${rows.length - 10} baris lagi_\n\n_📌 Untuk file CSV lengkap, gunakan Telegram (@bot)_` : '';
 
  return sock.sendMessage(chatId, {
    text: `📊 *Export ${month}* — ${rows.length} transaksi\n\n\`\`\`\n${preview}\n\`\`\`${more}`,
  });
}
 
// ─── Analisis AI ──────────────────────────────────────────
 
async function handleAnalisis(sock, msg, args) {
  const chatId = msg.key.remoteJid;
  const wallet = getWallet(chatId);
 
  try {
    const data = getAnalisis(wallet.id);
    const text = formatAnalisis(data, wallet.lang);
    return sock.sendMessage(chatId, { text });
  } catch (err) {
    console.error('[WA !analisis]', err);
    return sock.sendMessage(chatId, { text: `❌ ${err.message || 'Terjadi error.'}` });
  }
}
 
// ─── Net Worth / Kekayaan ─────────────────────────────────
 
async function handleKekayaan(sock, msg, args) {
  const chatId = msg.key.remoteJid;
  const wallet = getWallet(chatId);
 
  try {
    const data = getKekayaan(wallet.id);
    const text = formatKekayaan(data, wallet.lang);
    return sock.sendMessage(chatId, { text });
  } catch (err) {
    console.error('[WA !kekayaan]', err);
    return sock.sendMessage(chatId, { text: `❌ ${err.message || 'Terjadi error.'}` });
  }
}
 
// ─── Bot Setup ────────────────────────────────────────────
 
async function createWhatsAppBot() {
  // Pastiin folder session ada
  if (!fs.existsSync(config.whatsapp.sessionPath)) {
    fs.mkdirSync(config.whatsapp.sessionPath, { recursive: true });
  }
 
  const { state, saveCreds } = await useMultiFileAuthState(config.whatsapp.sessionPath);
  const { version } = await fetchLatestBaileysVersion();
 
  const logger = config.whatsapp.silent
    ? pino({ level: 'silent' })
    : pino({ level: 'warn' });
 
  const sock = makeWASocket({
    version,
    auth: {
      creds: state.creds,
      keys: makeCacheableSignalKeyStore(state.keys, logger),
    },
    logger,
    printQRInTerminal: false,
    browser: ['Money Bot', 'Chrome', '1.0.0'],
    // Hanya receive teks — lebih efisien
    getMessage: async () => ({ conversation: '' }),
  });
 
  const usePhone = !state.creds.registered && config.whatsapp.phoneNumber;
  const pairingPhone = usePhone ? config.whatsapp.phoneNumber.replace(/[^0-9]/g, '') : null;
  let pairingCodeRequested = false;
  let pairingRenewInterval = null;
 
  async function printPairingCode() {
    try {
      const code = await sock.requestPairingCode(pairingPhone);
      console.log(`\n┌──────────────────────────────────┐`);
      console.log(`│  📱 WhatsApp Pairing Code         │`);
      console.log(`│                                  │`);
      console.log(`│       ${code}          │`);
      console.log(`│                                  │`);
      console.log(`│  WA → Setelan → Perangkat Tertaut│`);
      console.log(`│  → Tautkan dengan nomor telepon  │`);
      console.log(`└──────────────────────────────────┘\n`);
    } catch (err) {
      console.error('[WA] Gagal request pairing code:', err.message);
    }
  }
 
  // ─── Connection handler ──────────────────────────────
  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update;
 
    if (qr) {
      if (usePhone) {
        if (!pairingCodeRequested) {
          pairingCodeRequested = true;
          // Request kode pertama kali
          await printPairingCode();
          // Auto-renew tiap 45 detik sampai konek
          pairingRenewInterval = setInterval(async () => {
            console.log('[WA] Renew pairing code...');
            await printPairingCode();
          }, 45_000);
        }
      } else {
        // Mode QR biasa
        setQR(qr);
        console.log('\n📱 QR code tersedia! Buka URL Railway kamu di browser untuk scan.\n');
        qrcode.generate(qr, { small: true });
      }
    }
 
    if (connection === 'close') {
      const statusCode = lastDisconnect?.error instanceof Boom
        ? lastDisconnect.error.output?.statusCode
        : null;
 
      const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
 
      if (shouldReconnect) {
        console.log(`🔄 WA disconnected (${statusCode}), reconnecting in 5s...`);
        setTimeout(() => createWhatsAppBot(), 5000);
      } else {
        console.log('❌ WA logged out. Hapus folder session dan jalankan ulang:');
        console.log(`   rm -rf ${config.whatsapp.sessionPath} && node index.js`);
      }
    }
 
    if (connection === 'open') {
      clearQR();
      if (pairingRenewInterval) {
        clearInterval(pairingRenewInterval);
        pairingRenewInterval = null;
      }
      console.log('✅ WhatsApp bot aktif');
    }
  });
 
  // ─── Simpan credentials ──────────────────────────────
  sock.ev.on('creds.update', saveCreds);
 
  // ─── Handler pesan masuk ─────────────────────────────
  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    // Hanya proses notif baru — skip history
    if (type !== 'notify') return;
 
    for (const msg of messages) {
      // Skip pesan dari bot sendiri
      if (msg.key.fromMe) continue;
 
      // Skip WhatsApp system JIDs — newsletter, linked device, status broadcast
      const chatId = msg.key.remoteJid;
      if (
        chatId.endsWith('@newsletter') ||
        chatId.endsWith('@lid') ||
        chatId === 'status@broadcast'
      ) continue;
 
      // Auto-create wallet untuk chat ini
      getOrCreateWallet('whatsapp', chatId, '');
 
      // ── Pesan Gambar → coba OCR struk ─────────────────
      if (msg.message?.imageMessage) {
        try {
          await handleImageOcr(sock, msg);
        } catch (err) {
          console.error('[WA image route]', err);
        }
        continue;
      }
 
      // Ambil teks pesan
      const text = (
        msg.message?.conversation ||
        msg.message?.extendedTextMessage?.text ||
        msg.message?.ephemeralMessage?.message?.conversation ||
        ''
      ).trim();
 
      if (!text) continue;
 
      // Ambil nama pengirim
      const senderJid = msg.key.participant || msg.key.remoteJid;
      const senderName = msg.pushName || senderJid.split('@')[0] || 'Unknown';
 
      try {
        await routeMessage(sock, msg, text, senderName);
      } catch (err) {
        console.error('[WA route error]', err);
      }
    }
  });
 
  waSocket = sock;
  return sock;
}
 
function getWASocket() {
  return waSocket;
}
 
module.exports = { createWhatsAppBot, getWASocket };
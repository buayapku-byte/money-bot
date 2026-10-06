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
const { getOrCreateWallet } = require('../core/database');
const { setQR, clearQR } = require('../core/qr-server');
const { addTransaction, getSaldo, getHistory, getLaporan, undoLast, deleteTransaction, getLaporanKategori,
  setBudget, getBudgets, deleteBudget, checkBudgetAlert,
  editTransaction,
  addRecurring, getRecurring, deleteRecurring } = require('../core/finance');
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
} = require('../core/formatter');
 
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
 * Ambil wallet dari pesan WA
 */
function getWallet(chatId, chatName = '') {
  return getOrCreateWallet('whatsapp', chatId, chatName);
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
    `_Shorthand: 500rb · 1.5jt · 1k_`
  );
}
 
async function handleCatat(sock, msg, args, senderName) {
  const chatId = msg.key.remoteJid;
  const typeRaw = args[0]?.toLowerCase();
  const amountRaw = args[1];
  const note = args.slice(2).join(' ') || '';
 
  if (!typeRaw || !['masuk', 'keluar', 'in', 'out'].includes(typeRaw)) {
    return reply(sock, msg,
      `❌ Format salah!\nContoh:\n` +
      `${config.wa.prefix}catat masuk 500rb gaji\n` +
      `${config.wa.prefix}catat keluar 50rb makan`
    );
  }
 
  const amount = parseJumlah(amountRaw);
  if (!amount || amount <= 0) {
    return reply(sock, msg,
      `❌ Jumlah tidak valid: *${amountRaw}*\nContoh: 500000 · 500rb · 1.5jt · 1k`
    );
  }
 
  const type = ['masuk', 'in'].includes(typeRaw) ? 'in' : 'out';
 
  try {
    const chatName = msg.key.remoteJid.endsWith('@g.us')
      ? '' // nama group diambil saat socket ready, skip dulu
      : senderName;
    const wallet = getWallet(chatId, chatName);
    const trx = addTransaction(wallet.id, type, amount, note, 'umum', senderName);
    const { saldo } = getSaldo(wallet.id);
 
    let replyText = formatTransaksi(trx) + `\n\n💰 Saldo sekarang: *${formatRupiah(saldo)}*`;
 
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
    const wallet = getWallet(msg.key.remoteJid);
    const data = getSaldo(wallet.id);
    await reply(sock, msg, formatSaldo(data));
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
    await reply(sock, msg, formatHistory(transactions));
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
    await reply(sock, msg, formatLaporan(data, period));
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
      return reply(sock, msg, formatGoals(goals, getGoalProgress));
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
    await reply(sock, msg, formatKategori(rows, period));
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
      return reply(sock, msg, formatBudgets(budgets));
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
      `Bulan: ${budget.month}\n\n` +
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
      return reply(sock, msg, formatRecurring(list, prefix));
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
 
// ─── Router ───────────────────────────────────────────────
 
/**
 * Dispatch pesan ke handler yang sesuai
 */
async function routeMessage(sock, msg, text, senderName) {
  const prefix = config.wa.prefix;
 
  // Harus diawali prefix
  if (!text.startsWith(prefix)) return;
 
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
 
    default:
      // Command tidak dikenal — diam aja biar tidak spam grup
      break;
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
 
  // ─── Connection handler ──────────────────────────────
  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update;
 
    if (qr) {
      // Update QR untuk web server
      setQR(qr);
      // Tetap print di terminal juga (Railway logs)
      console.log('\n📱 QR code tersedia! Buka URL Railway kamu di browser untuk scan.\n');
      qrcode.generate(qr, { small: true });
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
      clearQR(); // Hapus QR dari web server — sudah terhubung
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
 
      // Auto-create wallet untuk chat ini
      const chatId = msg.key.remoteJid;
      getOrCreateWallet('whatsapp', chatId, '');
 
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
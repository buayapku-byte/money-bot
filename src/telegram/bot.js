const { Telegraf, Markup } = require('telegraf');
const config = require('../../config');
const { getOrCreateWallet, resolveWalletId, createInviteCode, useInviteCode, unlinkWallet } = require('../core/database');
const { addTransaction, getSaldo, getHistory, getLaporan, undoLast, deleteTransaction, getLaporanKategori,
  setBudget, getBudgets, deleteBudget, checkBudgetAlert,
  editTransaction,
  addRecurring, getRecurring, deleteRecurring,
  setCurrency, getCurrencies, convertToIdr, CURRENCY_SYMBOLS,
  fetchLiveRates, getLiveRateUpdatedAt, POPULAR_CURRENCIES } = require('../core/finance');
const { createGoal, getGoals, addToGoal, deleteGoal, getGoalProgress } = require('../core/goals');
const { setReminder, disableReminder } = require('../core/reminder');
const {
  formatRupiah, formatSaldo, formatTransaksi,
  formatHistory, formatLaporan, formatKategori, formatGoals,
  formatBudgets, formatRecurring,
} = require('../core/formatter');
 
// ─── Helper ───────────────────────────────────────────────
 
/**
 * Parse jumlah uang — support shorthand: 1.5jt, 500rb, 1k
 * @param {string} str
 * @returns {number|null}
 */
function parseJumlah(str) {
  if (!str) return null;
  const s = str.toLowerCase().replace(/\./g, '').trim();
 
  // Cek shorthand
  if (/^\d+(\.\d+)?jt$/.test(s))  return parseFloat(s) * 1_000_000;
  if (/^\d+(\.\d+)?rb$/.test(s))  return parseFloat(s) * 1_000;
  if (/^\d+(\.\d+)?k$/.test(s))   return parseFloat(s) * 1_000;
  if (/^\d+(\.\d+)?m$/.test(s))   return parseFloat(s) * 1_000_000;
 
  const n = parseFloat(s.replace(/[^\d.]/g, ''));
  return isNaN(n) ? null : n;
}
 
/**
 * Ambil wallet dari context Telegram — auto-resolve ke primary kalau linked
 */
function getWallet(ctx) {
  const chatId = ctx.chat.id;
  const name = ctx.chat.title || ctx.chat.first_name || 'Unknown';
  const wallet = getOrCreateWallet('telegram', chatId, name);
  const primaryId = resolveWalletId(wallet.id);
  if (primaryId !== wallet.id) {
    const { getDb } = require('../core/database');
    return getDb().prepare('SELECT * FROM wallets WHERE id = ?').get(primaryId) || wallet;
  }
  return wallet;
}
 
/**
 * Reply dengan pesan error yang rapi
 */
function replyError(ctx, msg) {
  return ctx.reply(`❌ ${msg}`, { parse_mode: 'Markdown' });
}
 
/**
 * Reply dengan Markdown
 */
function replyMd(ctx, msg) {
  return ctx.reply(msg, { parse_mode: 'Markdown' });
}
 
// ─── Bot Setup ────────────────────────────────────────────
 
function createTelegramBot() {
  if (!config.telegram.token) {
    console.warn('⚠️  TELEGRAM_TOKEN tidak ada di .env — Telegram bot dilewati.');
    return null;
  }
 
  const bot = new Telegraf(config.telegram.token);
 
  // ─── /start ───────────────────────────────────────────
  bot.start((ctx) => {
    getWallet(ctx); // auto-create wallet
    replyMd(ctx,
      `👋 *Bot Simpan Uang aktif!*\n\n` +
      `Bot ini bantu kamu & tim catat keuangan langsung di grup Telegram.\n\n` +
      `Ketik /help untuk lihat semua perintah.`
    );
  });
 
  // ─── /help ────────────────────────────────────────────
  bot.help((ctx) => {
    replyMd(ctx,
      `📋 *Daftar Perintah*\n\n` +
      `💰 *Transaksi*\n` +
      `\`/catat masuk 500000 gaji\` — catat pemasukan\n` +
      `\`/catat keluar 50rb makan\` — catat pengeluaran\n` +
      `\`/catat keluar 1.5jt belanja\` — support shorthand (rb/jt/k)\n` +
      `\`/saldo\` — lihat saldo sekarang\n` +
      `\`/history\` — 10 transaksi terakhir\n` +
      `\`/undo\` — batalkan transaksi terakhir\n` +
      `\`/hapus 42\` — hapus transaksi by ID\n` +
      `\`/edit 42 75rb kopi susu\` — edit jumlah & catatan\n\n` +
      `🎯 *Target Tabungan*\n` +
      `\`/target buat Liburan 3jt\` — buat goal baru\n` +
      `\`/target buat HP 5000000 2026-12-31\` — dengan deadline\n` +
      `\`/target lihat\` — lihat semua goal\n` +
      `\`/target hapus Liburan\` — hapus goal\n` +
      `\`/tabung 100rb Liburan\` — tambah dana ke goal\n\n` +
      `📊 *Laporan*\n` +
      `\`/laporan hari\` — laporan hari ini\n` +
      `\`/laporan minggu\` — laporan 7 hari terakhir\n` +
      `\`/laporan bulan\` — laporan bulan ini\n` +
      `\`/kategori [hari/minggu/bulan]\` — breakdown per kategori\n\n` +
      `💡 *Budget*\n` +
      `\`/budget\` — lihat budget bulan ini\n` +
      `\`/budget makan 500rb\` — set budget kategori\n` +
      `\`/budget hapus makan\` — hapus budget\n\n` +
      `🔄 *Rutin (Berulang)*\n` +
      `\`/rutin\` — lihat daftar rutin\n` +
      `\`/rutin tambah keluar 150rb netflix 5\` — tiap tgl 5\n` +
      `\`/rutin hapus [id]\` — hapus rutin\n\n` +
      `⏰ *Reminder*\n` +
      `\`/reminder 20:00\` — set notif harian jam 20:00\n` +
      `\`/reminder off\` — matiin reminder\n\n` +
      `🔗 *Share Wallet*\n` +
      `\`/wallet share\` — buat kode undangan\n` +
      `\`/wallet gabung KODE\` — gabung ke wallet orang\n` +
      `\`/wallet pisah\` — berhenti berbagi\n\n` +
      `💱 *Multi-Kurs (160+ mata uang)*\n` +
      `\`/kurs\` — lihat kurs populer (live)\n` +
      `\`/kurs JPY\` — cek kurs mata uang spesifik\n` +
      `\`/kurs set THB 435\` — set kurs manual\n` +
      `\`/kurs update\` — refresh dari server\n` +
      `\`/catat keluar 500THB makan\` — auto-konversi ke IDR\n`
    );
  });
 
  // ─── /catat ───────────────────────────────────────────
  // Usage: /catat masuk 500000 gaji bulan ini
  //        /catat keluar 50rb makan siang
  bot.command('catat', async (ctx) => {
    try {
      const args = ctx.message.text.split(/\s+/).slice(1);
      // args[0] = type (masuk/keluar), args[1] = amount, args[2..] = note
      const typeRaw = args[0]?.toLowerCase();
      const amountRaw = args[1];
      const note = args.slice(2).join(' ') || '';
 
      // Validasi type
      if (!typeRaw || !['masuk', 'keluar', 'in', 'out'].includes(typeRaw)) {
        return replyError(ctx,
          `Format salah!\nGunakan: \`/catat masuk 500000 catatan\` atau \`/catat keluar 50rb makan\`\nAtau dengan mata uang asing: \`/catat keluar 500THB makan\``
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
          const wallet = getWallet(ctx);
          const converted = convertToIdr(wallet.id, numVal, currCode);
          finalAmount = converted;
          currencyNote = ` (${numVal} ${currCode} → ${formatRupiah(converted)})`;
        }
      } else {
        finalAmount = parseJumlah(amountRaw);
      }
 
      if (!finalAmount || finalAmount <= 0) {
        return replyError(ctx,
          `Jumlah tidak valid: *${amountRaw}*\nContoh: \`500000\`, \`500rb\`, \`1.5jt\`, \`500THB\``
        );
      }
 
      const type = ['masuk', 'in'].includes(typeRaw) ? 'in' : 'out';
      const wallet = getWallet(ctx);
      const createdBy = ctx.from.first_name || ctx.from.username || 'Unknown';
      const fullNote = (note + currencyNote).trim();
 
      const trx = addTransaction(wallet.id, type, finalAmount, fullNote, 'umum', createdBy);
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
 
      await replyMd(ctx, replyText);
    } catch (err) {
      console.error('[TG /catat]', err);
      replyError(ctx, err.message || 'Terjadi error. Coba lagi.');
    }
  });
 
  // ─── /saldo ───────────────────────────────────────────
  bot.command('saldo', async (ctx) => {
    try {
      const wallet = getWallet(ctx);
      const data = getSaldo(wallet.id);
      await replyMd(ctx, formatSaldo(data));
    } catch (err) {
      console.error('[TG /saldo]', err);
      replyError(ctx, 'Gagal ambil saldo.');
    }
  });
 
  // ─── /history ─────────────────────────────────────────
  // Usage: /history        → 10 terakhir
  //        /history 20     → 20 terakhir
  bot.command('history', async (ctx) => {
    try {
      const args = ctx.message.text.split(/\s+/).slice(1);
      const limit = Math.min(parseInt(args[0]) || 10, 30);
 
      const wallet = getWallet(ctx);
      const transactions = getHistory(wallet.id, limit);
      await replyMd(ctx, formatHistory(transactions));
    } catch (err) {
      console.error('[TG /history]', err);
      replyError(ctx, 'Gagal ambil history.');
    }
  });
 
  // ─── /undo ────────────────────────────────────────────
  bot.command('undo', async (ctx) => {
    try {
      const wallet = getWallet(ctx);
      const deleted = undoLast(wallet.id);
 
      if (!deleted) {
        return replyMd(ctx, '📭 Tidak ada transaksi yang bisa dibatalkan.');
      }
 
      const icon = deleted.type === 'in' ? '📈' : '📉';
      const { saldo } = getSaldo(wallet.id);
      await replyMd(ctx,
        `✅ *Transaksi dibatalkan!*\n\n` +
        `${icon} ${formatRupiah(deleted.amount)}` +
        (deleted.note ? ` · ${deleted.note}` : '') + `\n\n` +
        `💰 Saldo sekarang: *${formatRupiah(saldo)}*`
      );
    } catch (err) {
      console.error('[TG /undo]', err);
      replyError(ctx, 'Gagal undo transaksi.');
    }
  });
 
  // ─── /laporan ─────────────────────────────────────────
  // Usage: /laporan hari | /laporan minggu | /laporan bulan
  bot.command('laporan', async (ctx) => {
    try {
      const args = ctx.message.text.split(/\s+/).slice(1);
      const period = args[0]?.toLowerCase() || 'bulan';
 
      if (!['hari', 'minggu', 'bulan'].includes(period)) {
        return replyError(ctx,
          `Period tidak valid.\nGunakan: \`/laporan hari\`, \`/laporan minggu\`, atau \`/laporan bulan\``
        );
      }
 
      const wallet = getWallet(ctx);
      const data = getLaporan(wallet.id, period);
      await replyMd(ctx, formatLaporan(data, period));
    } catch (err) {
      console.error('[TG /laporan]', err);
      replyError(ctx, 'Gagal buat laporan.');
    }
  });
 
  // ─── /target ──────────────────────────────────────────
  // Usage: /target lihat
  //        /target buat Liburan 3000000
  //        /target buat HP 5jt 2026-12-31
  //        /target hapus Liburan
  bot.command('target', async (ctx) => {
    try {
      const args = ctx.message.text.split(/\s+/).slice(1);
      const sub = args[0]?.toLowerCase();
 
      if (!sub || !['lihat', 'buat', 'hapus', 'setor'].includes(sub)) {
        return replyError(ctx,
          `Subcommand tidak valid.\nGunakan:\n` +
          `\`/target lihat\`\n` +
          `\`/target buat NamaGoal Jumlah [deadline]\`\n` +
          `\`/target setor NamaGoal Jumlah\`\n` +
          `\`/target hapus NamaGoal\``
        );
      }
 
      const wallet = getWallet(ctx);
 
      // /target lihat
      if (sub === 'lihat') {
        const goals = getGoals(wallet.id);
        return replyMd(ctx, formatGoals(goals, getGoalProgress));
      }
 
      // /target hapus NamaGoal
      if (sub === 'hapus') {
        const name = args.slice(1).join(' ');
        if (!name) return replyError(ctx, 'Ketik nama goal yang mau dihapus.\nContoh: `/target hapus Liburan`');
 
        const deleted = deleteGoal(wallet.id, name);
        return replyMd(ctx,
          `✅ *Goal dihapus!*\n\n` +
          `🎯 ${deleted.name}\n` +
          `Dana terkumpul: ${formatRupiah(deleted.current_amount)}`
        );
      }
 
      // /target setor NamaGoal Jumlah — last arg = jumlah, rest = nama goal
      if (sub === 'setor') {
        const amountRaw = args[args.length - 1];
        const amount = parseJumlah(amountRaw);
        if (!amount || amount <= 0 || args.length < 3) {
          return replyError(ctx,
            `Format salah!\nContoh: \`/target setor Liburan Bali 500rb\``
          );
        }
        const goalName = args.slice(1, args.length - 1).join(' ');
        if (!goalName) return replyError(ctx, 'Ketik nama goal.\nContoh: `/target setor Liburan 500rb`');
 
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
        return replyMd(ctx, text);
      }
 
      // /target buat NamaGoal Jumlah [deadline YYYY-MM-DD]
      if (sub === 'buat') {
        // Cek apakah arg terakhir adalah tanggal deadline
        const lastArg = args[args.length - 1];
        const isDeadline = /^\d{4}-\d{2}-\d{2}$/.test(lastArg);
        const deadline = isDeadline ? lastArg : null;
 
        // Amount adalah arg kedua dari belakang (atau dari belakang jika ada deadline)
        const amountArg = isDeadline ? args[args.length - 2] : args[args.length - 1];
        const amount = parseJumlah(amountArg);
 
        if (!amount || amount <= 0) {
          return replyError(ctx,
            `Format salah!\nGunakan: \`/target buat NamaGoal Jumlah\`\nContoh: \`/target buat Liburan 3jt\``
          );
        }
 
        // Nama goal = semua arg antara 'buat' dan amount (dan deadline jika ada)
        const nameEnd = isDeadline ? args.length - 2 : args.length - 1;
        const name = args.slice(1, nameEnd).join(' ');
 
        if (!name) {
          return replyError(ctx, 'Ketik nama goal.\nContoh: `/target buat Liburan Bali 3jt`');
        }
 
        const goal = createGoal(wallet.id, name, amount, deadline);
        return replyMd(ctx,
          `✅ *Goal dibuat!*\n\n` +
          `🎯 *${goal.name}*\n` +
          `Target: ${formatRupiah(goal.target_amount)}\n` +
          (deadline ? `Deadline: ${deadline}\n` : '') +
          `\nGunakan \`/tabung jumlah ${goal.name}\` untuk mulai nabung!`
        );
      }
    } catch (err) {
      console.error('[TG /target]', err);
      replyError(ctx, err.message || 'Terjadi error.');
    }
  });
 
  // ─── /tabung ──────────────────────────────────────────
  // Usage: /tabung 100rb Liburan
  //        /tabung 500000 Beli HP
  bot.command('tabung', async (ctx) => {
    try {
      const args = ctx.message.text.split(/\s+/).slice(1);
      const amountRaw = args[0];
      const goalName = args.slice(1).join(' ');
 
      const amount = parseJumlah(amountRaw);
      if (!amount || amount <= 0) {
        return replyError(ctx,
          `Format salah!\nGunakan: \`/tabung JumlahUang NamaGoal\`\nContoh: \`/tabung 100rb Liburan\``
        );
      }
 
      if (!goalName) {
        return replyError(ctx, 'Ketik nama goal tujuan.\nContoh: `/tabung 100rb Liburan`');
      }
 
      const wallet = getWallet(ctx);
      const { goal, isCompleted } = addToGoal(wallet.id, goalName, amount);
      const { persen } = getGoalProgress(goal);
 
      let msg = `✅ *Tabungan bertambah!*\n\n`;
      msg += `🎯 *${goal.name}*\n`;
      msg += `Ditambah: *${formatRupiah(amount)}*\n`;
      msg += `Terkumpul: ${formatRupiah(goal.current_amount)} / ${formatRupiah(goal.target_amount)}\n`;
      msg += `Progress: ${persen}%\n`;
 
      if (isCompleted) {
        msg += `\n🎉 *GOAL TERCAPAI! Selamat!* 🎉`;
      } else {
        const sisa = goal.target_amount - goal.current_amount;
        msg += `Sisa: ${formatRupiah(sisa)}`;
      }
 
      await replyMd(ctx, msg);
    } catch (err) {
      console.error('[TG /tabung]', err);
      replyError(ctx, err.message || 'Terjadi error.');
    }
  });
 
  // ─── /kategori ────────────────────────────────────────
  // Usage: /kategori | /kategori hari | /kategori minggu | /kategori bulan
  bot.command('kategori', async (ctx) => {
    try {
      const args = ctx.message.text.split(/\s+/).slice(1);
      const period = args[0]?.toLowerCase() || 'bulan';
 
      if (!['hari', 'minggu', 'bulan'].includes(period)) {
        return replyError(ctx,
          `Period tidak valid.\nGunakan: \`/kategori hari\`, \`/kategori minggu\`, atau \`/kategori bulan\``
        );
      }
 
      const wallet = getWallet(ctx);
      const rows = getLaporanKategori(wallet.id, period);
      await replyMd(ctx, formatKategori(rows, period));
    } catch (err) {
      console.error('[TG /kategori]', err);
      replyError(ctx, 'Gagal buat laporan kategori.');
    }
  });
 
  // ─── /hapus ───────────────────────────────────────────
  // Usage: /hapus 42
  bot.command('hapus', async (ctx) => {
    try {
      const args = ctx.message.text.split(/\s+/).slice(1);
      const id = parseInt(args[0]);
 
      if (!args[0] || isNaN(id) || id <= 0) {
        return replyError(ctx,
          `Ketik ID transaksi.\nContoh: \`/hapus 42\`\n\nGunakan \`/history\` untuk lihat ID transaksi.`
        );
      }
 
      const wallet = getWallet(ctx);
      const deleted = deleteTransaction(wallet.id, id);
      const { saldo } = getSaldo(wallet.id);
 
      const icon = deleted.type === 'in' ? '📈' : '📉';
      await replyMd(ctx,
        `🗑️ *Transaksi dihapus!*\n\n` +
        `${icon} #${deleted.id} ${formatRupiah(deleted.amount)}` +
        (deleted.note ? ` · ${deleted.note}` : '') +
        `\n\n💰 Saldo sekarang: *${formatRupiah(saldo)}*`
      );
    } catch (err) {
      console.error('[TG /hapus]', err);
      replyError(ctx, err.message || 'Gagal hapus transaksi.');
    }
  });
 
  // ─── /reminder ────────────────────────────────────────
  // Usage: /reminder 20:00
  //        /reminder off
  bot.command('reminder', async (ctx) => {
    try {
      const args = ctx.message.text.split(/\s+/).slice(1);
      const input = args[0]?.toLowerCase();
 
      if (!input) {
        return replyError(ctx,
          `Ketik jam atau "off".\nContoh: \`/reminder 20:00\` atau \`/reminder off\``
        );
      }
 
      const wallet = getWallet(ctx);
 
      if (input === 'off') {
        disableReminder(wallet.id);
        return replyMd(ctx, '🔕 Reminder dimatikan.');
      }
 
      const time = setReminder(wallet.id, 'telegram', input);
      return replyMd(ctx,
        `⏰ *Reminder diset!*\n\nKamu akan dapat notif harian jam *${time}* WIB.`
      );
    } catch (err) {
      console.error('[TG /reminder]', err);
      replyError(ctx, err.message || 'Terjadi error.');
    }
  });
 
  // ─── /budget ──────────────────────────────────────────
  // Usage: /budget
  //        /budget makan 500rb
  //        /budget hapus makan
  bot.command('budget', async (ctx) => {
    try {
      const args = ctx.message.text.split(/\s+/).slice(1);
      const wallet = getWallet(ctx);
 
      // Tanpa args — lihat budget
      if (!args.length) {
        const budgets = getBudgets(wallet.id);
        return replyMd(ctx, formatBudgets(budgets));
      }
 
      const sub = args[0]?.toLowerCase();
 
      // /budget hapus [kategori bisa multi-kata]
      if (sub === 'hapus') {
        const category = args.slice(1).join(' ').toLowerCase();
        if (!category) return replyError(ctx, 'Ketik nama kategori.\nContoh: `/budget hapus makan`');
        const deleted = deleteBudget(wallet.id, category);
        return replyMd(ctx,
          `✅ *Budget dihapus!*\n\nKategori: ${deleted.category}\nBudget: ${formatRupiah(deleted.amount)}`
        );
      }
 
      // /budget [kategori bisa multi-kata] [jumlah]
      // Jumlah selalu arg terakhir, sisanya = nama kategori
      const amountRaw = args[args.length - 1];
      const amount = parseJumlah(amountRaw);
      if (!amount || amount <= 0 || args.length < 2) {
        return replyError(ctx,
          `Format salah!\nContoh:\n\`/budget makan 500rb\`\n\`/budget belanja online 1jt\`\n\`/budget transport 300rb\``
        );
      }
      const category = args.slice(0, args.length - 1).join(' ').toLowerCase();
 
      const budget = setBudget(wallet.id, category, amount);
      return replyMd(ctx,
        `✅ *Budget diset!*\n\n` +
        `Kategori: *${budget.category}*\n` +
        `Budget: *${formatRupiah(budget.amount)}*\n` +
        `Bulan: ${budget.month}\n\n` +
        `_Kamu akan dapat peringatan saat mencapai 80% dan 100%._`
      );
    } catch (err) {
      console.error('[TG /budget]', err);
      replyError(ctx, err.message || 'Gagal proses budget.');
    }
  });
 
  // ─── /rutin ───────────────────────────────────────────
  // Usage: /rutin
  //        /rutin tambah keluar 150rb netflix 5
  //        /rutin hapus [id]
  bot.command('rutin', async (ctx) => {
    try {
      const args = ctx.message.text.split(/\s+/).slice(1);
      const wallet = getWallet(ctx);
 
      // Tanpa args — lihat daftar rutin
      if (!args.length) {
        const list = getRecurring(wallet.id);
        return replyMd(ctx, formatRecurring(list, '/'));
      }
 
      const sub = args[0]?.toLowerCase();
 
      // /rutin hapus [id]
      if (sub === 'hapus') {
        const id = parseInt(args[1]);
        if (!args[1] || isNaN(id) || id <= 0) {
          return replyError(ctx, 'Ketik ID rutin.\nContoh: `/rutin hapus 3`');
        }
        const deleted = deleteRecurring(wallet.id, id);
        return replyMd(ctx,
          `✅ *Rutin dihapus!*\n\n` +
          `${deleted.type === 'in' ? '📈' : '📉'} ${formatRupiah(deleted.amount)}` +
          (deleted.note ? ` · ${deleted.note}` : '') +
          `\nTiap tgl ${deleted.day_of_month}`
        );
      }
 
      // /rutin tambah [masuk/keluar] [jumlah] [catatan...] [tgl]
      if (sub === 'tambah') {
        const typeRaw = args[1]?.toLowerCase();
        if (!typeRaw || !['masuk', 'keluar', 'in', 'out'].includes(typeRaw)) {
          return replyError(ctx,
            `Format salah!\nContoh:\n\`/rutin tambah keluar 150rb netflix 5\`\n\`/rutin tambah masuk 5jt gaji 25\``
          );
        }
 
        const type = ['masuk', 'in'].includes(typeRaw) ? 'in' : 'out';
        const amount = parseJumlah(args[2]);
        if (!amount || amount <= 0) {
          return replyError(ctx,
            `Jumlah tidak valid.\nContoh: \`/rutin tambah keluar 150rb netflix 5\``
          );
        }
 
        // Arg terakhir harus angka 1-28 (tanggal)
        const lastArg = args[args.length - 1];
        const day = parseInt(lastArg);
        if (isNaN(day) || day < 1 || day > 28) {
          return replyError(ctx,
            `Tanggal tidak valid (1-28).\nContoh: \`/rutin tambah keluar 150rb netflix 5\``
          );
        }
 
        const note = args.slice(3, args.length - 1).join(' ') || '';
        const rec = addRecurring(wallet.id, type, amount, note, 'umum', day);
 
        return replyMd(ctx,
          `✅ *Transaksi rutin ditambah!*\n\n` +
          `${rec.type === 'in' ? '📈' : '📉'} *${formatRupiah(rec.amount)}*` +
          (rec.note ? ` · ${rec.note}` : '') + `\n` +
          `Kategori: ${rec.category}\n` +
          `Tiap tanggal: *${rec.day_of_month}*\n\n` +
          `_Akan dicatat otomatis setiap bulan._`
        );
      }
 
      return replyError(ctx,
        `Subcommand tidak valid.\nGunakan:\n\`/rutin\`\n\`/rutin tambah keluar 150rb netflix 5\`\n\`/rutin hapus [id]\``
      );
    } catch (err) {
      console.error('[TG /rutin]', err);
      replyError(ctx, err.message || 'Gagal proses rutin.');
    }
  });
 
  // ─── /edit ────────────────────────────────────────────
  // Usage: /edit 42 75rb
  //        /edit 42 75rb kopi susu
  //        /edit 42 - catatan baru (skip amount dengan -)
  bot.command('edit', async (ctx) => {
    try {
      const args = ctx.message.text.split(/\s+/).slice(1);
      const id = parseInt(args[0]);
 
      if (!args[0] || isNaN(id) || id <= 0) {
        return replyError(ctx,
          `Format salah!\nContoh:\n\`/edit 42 75rb\` — ubah jumlah\n\`/edit 42 75rb kopi susu\` — ubah jumlah & catatan`
        );
      }
 
      const newAmount = args[1] ? parseJumlah(args[1]) : null;
      const newNote = args.length > 2 ? args.slice(2).join(' ') : null;
 
      if (newAmount === null && newNote === null) {
        return replyError(ctx,
          `Ketik jumlah atau catatan baru.\nContoh: \`/edit 42 75rb kopi susu\``
        );
      }
      if (args[1] && newAmount === null) {
        return replyError(ctx,
          `Jumlah tidak valid: *${args[1]}*\nContoh: \`75000\`, \`75rb\`, \`1.5jt\``
        );
      }
 
      const wallet = getWallet(ctx);
      const updated = editTransaction(wallet.id, id, newAmount, newNote);
 
      return replyMd(ctx,
        `✏️ *Transaksi diupdate!*\n\n` +
        `#${updated.id} ${updated.type === 'in' ? '📈' : '📉'} *${formatRupiah(updated.amount)}*` +
        (updated.note ? `\nCatatan: ${updated.note}` : '') +
        `\nKategori: ${updated.category}`
      );
    } catch (err) {
      console.error('[TG /edit]', err);
      replyError(ctx, err.message || 'Gagal edit transaksi.');
    }
  });
 
  // ─── /wallet ──────────────────────────────────────────
  // Usage: /wallet share | /wallet gabung KODE | /wallet pisah | /wallet info
  bot.command('wallet', async (ctx) => {
    try {
      const args = ctx.message.text.split(/\s+/).slice(1);
      const sub = args[0]?.toLowerCase();
      const myWallet = getOrCreateWallet('telegram', ctx.chat.id, ctx.chat.title || ctx.chat.first_name || 'Unknown');
 
      if (sub === 'share' || sub === 'bagikan') {
        const code = createInviteCode(myWallet.id);
        return replyMd(ctx,
          `🔗 *Kode Share Wallet*\n\n` +
          `Kode: \`${code}\`\n` +
          `Berlaku: 24 jam\n\n` +
          `Kirim ke orang yang mau bergabung:\n` +
          `\`/wallet gabung ${code}\``
        );
      }
 
      if (sub === 'gabung') {
        const code = args[1];
        if (!code) return replyError(ctx, 'Ketik kode undangan.\nContoh: `/wallet gabung ABC123`');
        const primary = useInviteCode(myWallet.id, code);
        return replyMd(ctx,
          `✅ *Berhasil bergabung!*\n\n` +
          `Sekarang kamu mengakses wallet: *${primary.name || primary.id}*\n` +
          `Semua transaksi akan dicatat ke wallet tersebut.\n\n` +
          `Gunakan \`/wallet pisah\` untuk berhenti berbagi.`
        );
      }
 
      if (sub === 'pisah') {
        unlinkWallet(myWallet.id);
        return replyMd(ctx, `✅ *Wallet dipisah!*\n\nKamu sekarang kembali menggunakan wallet sendiri.`);
      }
 
      if (sub === 'info') {
        const { getDb } = require('../core/database');
        const link = getDb().prepare('SELECT * FROM wallet_links WHERE member_id = ?').get(myWallet.id);
        if (link) {
          const primary = getDb().prepare('SELECT * FROM wallets WHERE id = ?').get(link.primary_id);
          return replyMd(ctx,
            `🔗 *Status Wallet*\n\n` +
            `Kamu sedang berbagi wallet dengan:\n*${primary?.name || link.primary_id}*\n\n` +
            `Gunakan \`/wallet pisah\` untuk berhenti.`
          );
        }
        return replyMd(ctx,
          `👛 *Status Wallet*\n\nKamu menggunakan wallet sendiri.\n\n` +
          `Bagikan ke orang lain: \`/wallet share\``
        );
      }
 
      return replyMd(ctx,
        `❓ *Subcommand wallet:*\n` +
        `\`/wallet share\` — buat kode undangan\n` +
        `\`/wallet gabung KODE\` — gabung ke wallet orang lain\n` +
        `\`/wallet pisah\` — berhenti berbagi\n` +
        `\`/wallet info\` — cek status`
      );
    } catch (err) {
      console.error('[TG /wallet]', err);
      replyError(ctx, err.message || 'Terjadi error.');
    }
  });
 
  // ─── /kurs ────────────────────────────────────────────
  // Usage: /kurs | /kurs JPY | /kurs set THB 435 | /kurs update
  bot.command('kurs', async (ctx) => {
    try {
      const args = ctx.message.text.split(/\s+/).slice(1);
      const sub = args[0]?.toLowerCase();
      const wallet = getWallet(ctx);
 
      // /kurs update — refresh dari API
      if (sub === 'update') {
        await replyMd(ctx, '🔄 Mengambil kurs terbaru dari server...');
        try {
          const { count, usdRate } = await fetchLiveRates();
          return replyMd(ctx,
            `✅ *Kurs berhasil diperbarui!*\n\n` +
            `📊 ${count} mata uang tersedia\n` +
            `💵 1 USD = Rp ${usdRate.toLocaleString('id-ID')}\n\n` +
            `Cek kurs: \`/kurs\``
          );
        } catch (e) {
          return replyError(ctx, `Gagal update kurs: ${e.message}\nCoba lagi nanti.`);
        }
      }
 
      // /kurs set CODE RATE — set kurs manual/custom
      if (sub === 'set') {
        const code = args[1]?.toUpperCase();
        const rate = parseFloat(args[2]);
        if (!code || !rate || rate <= 0) {
          return replyError(ctx, `Format: \`/kurs set THB 435\`\n(1 THB = 435 IDR)`);
        }
        const result = setCurrency(wallet.id, code, rate);
        return replyMd(ctx,
          `✅ *Kurs custom disimpan!*\n\n1 ${result.code} = Rp ${rate.toLocaleString('id-ID')}\n` +
          `_(Override live rate — hanya berlaku di wallet ini)_\n\n` +
          `Contoh pakai: \`/catat keluar 500${result.code} makan\``
        );
      }
 
      // /kurs [CODE] — cek kurs mata uang spesifik
      if (sub && /^[a-z]{2,6}$/.test(sub)) {
        const code = sub.toUpperCase();
        const all = getCurrencies(wallet.id);
        const found = all.find(r => r.code === code);
        if (!found) {
          return replyError(ctx,
            `Kurs *${code}* tidak ditemukan.\n\n` +
            `Coba: \`/kurs update\` untuk refresh data\n` +
            `Atau: \`/kurs set ${code} [nilai]\` untuk set manual`
          );
        }
        const label = found.is_custom ? '*(custom)*' : '_(live rate)_';
        return replyMd(ctx,
          `💱 *Kurs ${code}*\n\n` +
          `1 ${code} = Rp ${Math.round(found.rate_to_idr).toLocaleString('id-ID')} ${label}\n\n` +
          `_Update: ${found.updated_at || '-'}_`
        );
      }
 
      // /kurs — tampilkan kurs populer + info
      const updatedAt = getLiveRateUpdatedAt();
      const all = getCurrencies(wallet.id);
      const customMap = new Map(all.filter(r => r.is_custom).map(r => [r.code, r]));
      const liveMap  = new Map(all.filter(r => !r.is_custom).map(r => [r.code, r]));
 
      let out = `💱 *Kurs Mata Uang*\n`;
      if (updatedAt) out += `_Update: ${updatedAt} WIB_\n`;
      out += `\n`;
 
      // Custom rates kalau ada
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
      out += `• \`/kurs JPY\` — cek kurs spesifik\n`;
      out += `• \`/kurs set THB 435\` — set kurs manual\n`;
      out += `• \`/kurs update\` — refresh dari server\n`;
      out += `\n_160+ mata uang tersedia · auto-refresh tiap hari 07:00 WIB_`;
 
      return replyMd(ctx, out);
    } catch (err) {
      console.error('[TG /kurs]', err);
      replyError(ctx, err.message || 'Terjadi error.');
    }
  });
 
  // ─── Error handler global ─────────────────────────────
  bot.catch((err, ctx) => {
    console.error(`[TG Error] ${ctx.updateType}:`, err);
    ctx.reply('❌ Terjadi error tak terduga. Coba lagi.').catch(() => {});
  });
 
  // ─── Launch ───────────────────────────────────────────
  bot.launch({
    allowedUpdates: ['message', 'callback_query'],
  });
 
  console.log('✅ Telegram bot aktif');
  return bot;
}
 
module.exports = { createTelegramBot };
const { Telegraf, Markup } = require('telegraf');
const config = require('../../config');
const { getOrCreateWallet } = require('../core/database');
const { addTransaction, getSaldo, getHistory, getLaporan, undoLast } = require('../core/finance');
const { createGoal, getGoals, addToGoal, deleteGoal, getGoalProgress } = require('../core/goals');
const { setReminder, disableReminder } = require('../core/reminder');
const {
  formatRupiah, formatSaldo, formatTransaksi,
  formatHistory, formatLaporan, formatGoals,
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
 * Ambil wallet dari context Telegram
 */
function getWallet(ctx) {
  const chatId = ctx.chat.id;
  const name = ctx.chat.title || ctx.chat.first_name || 'Unknown';
  return getOrCreateWallet('telegram', chatId, name);
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
      `\`/undo\` — batalkan transaksi terakhir\n\n` +
      `🎯 *Target Tabungan*\n` +
      `\`/target buat Liburan 3jt\` — buat goal baru\n` +
      `\`/target buat HP 5000000 2026-12-31\` — dengan deadline\n` +
      `\`/target lihat\` — lihat semua goal\n` +
      `\`/target hapus Liburan\` — hapus goal\n` +
      `\`/tabung 100rb Liburan\` — tambah dana ke goal\n\n` +
      `📊 *Laporan*\n` +
      `\`/laporan hari\` — laporan hari ini\n` +
      `\`/laporan minggu\` — laporan 7 hari terakhir\n` +
      `\`/laporan bulan\` — laporan bulan ini\n\n` +
      `⏰ *Reminder*\n` +
      `\`/reminder 20:00\` — set notif harian jam 20:00\n` +
      `\`/reminder off\` — matiin reminder\n`
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
          `Format salah!\nGunakan: \`/catat masuk 500000 catatan\` atau \`/catat keluar 50rb makan\``
        );
      }

      // Validasi amount
      const amount = parseJumlah(amountRaw);
      if (!amount || amount <= 0) {
        return replyError(ctx,
          `Jumlah tidak valid: *${amountRaw}*\nContoh: \`500000\`, \`500rb\`, \`1.5jt\`, \`1k\``
        );
      }

      const type = ['masuk', 'in'].includes(typeRaw) ? 'in' : 'out';
      const wallet = getWallet(ctx);
      const createdBy = ctx.from.first_name || ctx.from.username || 'Unknown';

      const trx = addTransaction(wallet.id, type, amount, note, 'umum', createdBy);
      const { saldo } = getSaldo(wallet.id);

      await replyMd(ctx,
        formatTransaksi(trx) +
        `\n\n💰 Saldo sekarang: *${formatRupiah(saldo)}*`
      );
    } catch (err) {
      console.error('[TG /catat]', err);
      replyError(ctx, 'Terjadi error. Coba lagi.');
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
  bot.command('hapus', async (ctx) => {
  try {
    const args = ctx.message.text.split(/\s+/).slice(1);
    const id = parseInt(args[0]);

    if (!args[0] || isNaN(id) || id <= 0) {
      return replyError(ctx,
        `Ketik ID transaksi.\nContoh: \`/hapus 42\`\n\nGunakan \`/history\` untuk lihat ID.`
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

      if (!sub || !['lihat', 'buat', 'hapus'].includes(sub)) {
        return replyError(ctx,
          `Subcommand tidak valid.\nGunakan:\n` +
          `\`/target lihat\`\n` +
          `\`/target buat NamaGoal Jumlah [deadline]\`\n` +
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

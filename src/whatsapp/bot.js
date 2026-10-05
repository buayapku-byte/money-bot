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
const { addTransaction, getSaldo, getHistory, getLaporan, undoLast } = require('../core/finance');
const { createGoal, getGoals, addToGoal, deleteGoal, getGoalProgress } = require('../core/goals');
const { setReminder, disableReminder } = require('../core/reminder');
const {
  formatRupiah,
  formatSaldo,
  formatTransaksi,
  formatHistory,
  formatLaporan,
  formatGoals,
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
    `${prefix}undo — batalkan transaksi terakhir\n\n` +
    `🎯 *Target Tabungan*\n` +
    `${prefix}target buat Liburan 3jt\n` +
    `${prefix}target buat HP 5jt 2026-12-31\n` +
    `${prefix}target lihat\n` +
    `${prefix}target hapus Liburan\n` +
    `${prefix}tabung 100rb Liburan\n\n` +
    `📊 *Laporan*\n` +
    `${prefix}laporan hari\n` +
    `${prefix}laporan minggu\n` +
    `${prefix}laporan bulan\n\n` +
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

    await reply(sock, msg,
      formatTransaksi(trx) + `\n\n💰 Saldo sekarang: *${formatRupiah(saldo)}*`
    );
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

  if (!sub || !['lihat', 'buat', 'hapus'].includes(sub)) {
    return reply(sock, msg,
      `❌ Subcommand tidak valid.\nGunakan:\n` +
      `${prefix}target lihat\n` +
      `${prefix}target buat NamaGoal Jumlah [deadline]\n` +
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

    case 'laporan':
    case 'report':
      return handleLaporan(sock, msg, args);

    case 'target':
    case 'goal':
      return handleTarget(sock, msg, args);

    case 'tabung':
    case 'nabung':
      return handleTabung(sock, msg, args);

    case 'reminder':
    case 'notif':
      return handleReminder(sock, msg, args);

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
      console.log('\n📱 Scan QR code ini di WhatsApp kamu:\n');
      qrcode.generate(qr, { small: true });
      console.log('\n(WhatsApp → Settings → Linked Devices → Link a Device)\n');
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

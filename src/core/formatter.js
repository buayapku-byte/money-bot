// ─── Message Formatter ───────────────────────────────────
// Format pesan yang konsisten untuk Telegram & WhatsApp
// Telegram support Markdown, WA pakai teks biasa
 
const { t } = require('./i18n');
 
/**
 * Format angka ke rupiah
 * @param {number} amount
 * @returns {string} e.g. "Rp 1.500.000"
 */
function formatRupiah(amount) {
  return 'Rp ' + Math.abs(amount).toLocaleString('id-ID');
}
 
/**
 * Format tanggal ke bahasa Indonesia
 * @param {string} dateStr - Format YYYY-MM-DD
 * @returns {string} e.g. "Senin, 5 Oktober 2026"
 */
function formatTanggal(dateStr) {
  const date = new Date(dateStr + 'T00:00:00');
  return date.toLocaleDateString('id-ID', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
  });
}
 
/**
 * Format datetime ke "Selasa, 6 Oktober 2026 · 15:29"
 * @param {string} datetimeStr
 * @param {string} lang - 'id' | 'en'
 */
function formatDatetime(datetimeStr, lang = 'id') {
  const d = new Date(datetimeStr);
  const pad = (n) => String(n).padStart(2, '0');
  const locale = lang === 'en' ? 'en-US' : 'id-ID';
  const tanggal = d.toLocaleDateString(locale, {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
  });
  return `${tanggal} · ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
 
/**
 * Progress bar teks
 * @param {number} persen - 0-100
 * @param {number} panjang - jumlah karakter bar
 * @returns {string} e.g. "████████░░ 80%"
 */
function progressBar(persen, panjang = 10) {
  const filled = Math.round((persen / 100) * panjang);
  const empty  = panjang - filled;
  return '█'.repeat(filled) + '░'.repeat(empty) + ` ${persen}%`;
}
 
/**
 * Format pesan saldo
 * @param {object} data
 * @param {string} lang - 'id' | 'en'
 */
function formatSaldo({ saldo, total_masuk, total_keluar }, lang = 'id') {
  const sign = saldo >= 0 ? '✅' : '⚠️';
  return (
    `${t(lang, 'saldo_title')}\n\n` +
    `${sign} ${t(lang, 'saldo_label')}: *${formatRupiah(saldo)}*\n` +
    `${t(lang, 'income_label')}: ${formatRupiah(total_masuk)}\n` +
    `${t(lang, 'expense_label')}: ${formatRupiah(total_keluar)}`
  );
}
 
/**
 * Format pesan konfirmasi transaksi
 * @param {object} trx
 * @param {string} lang - 'id' | 'en'
 */
function formatTransaksi(trx, lang = 'id') {
  const icon  = trx.type === 'in' ? '📈' : '📉';
  const label = t(lang, trx.type === 'in' ? 'type_in' : 'type_out');
  return (
    `${icon} *${label} ${t(lang, 'trx_saved')}*\n\n` +
    `${t(lang, 'trx_amount')}: *${formatRupiah(trx.amount)}*\n` +
    (trx.note     ? `${t(lang, 'trx_note')}: ${trx.note}\n`         : '') +
    (trx.category !== 'umum' ? `${t(lang, 'trx_category')}: ${trx.category}\n` : '') +
    `${t(lang, 'trx_time')}: ${formatDatetime(trx.created_at, lang)}`
  );
}
 
/**
 * Format daftar history transaksi
 * @param {Array}  transactions
 * @param {string} lang - 'id' | 'en'
 */
function formatHistory(transactions, lang = 'id') {
  if (!transactions.length) return t(lang, 'no_transaction');
 
  const rows = transactions.map((tx) => {
    const icon = tx.type === 'in' ? '📈' : '📉';
    const note = tx.note ? ` · ${tx.note}` : '';
    return `${icon} *#${tx.id}* ${formatRupiah(tx.amount)}${note}\n   _${tx.date}_`;
  });
 
  return (
    `${t(lang, 'history_title')}\n\n` +
    rows.join('\n') + `\n\n` +
    t(lang, 'showing_last', transactions.length)
  );
}
 
/**
 * Format laporan per periode
 * @param {object} data
 * @param {string} period - 'hari' | 'minggu' | 'bulan'
 * @param {string} lang   - 'id' | 'en'
 */
function formatLaporan({ transactions, summary }, period, lang = 'id') {
  const labelPeriod = {
    hari:   t(lang, 'period_hari'),
    minggu: t(lang, 'period_minggu'),
    bulan:  t(lang, 'period_bulan'),
  };
  const label = labelPeriod[period] || t(lang, 'period_label');
 
  let msg = `${t(lang, 'lap_title', label)}\n\n`;
  msg += `${t(lang, 'lap_income')}:  *${formatRupiah(summary.total_masuk)}*\n`;
  msg += `${t(lang, 'lap_expense')}: *${formatRupiah(summary.total_keluar)}*\n`;
  msg += `─────────────────\n`;
 
  const selisih = summary.selisih;
  msg += `${t(lang, selisih >= 0 ? 'surplus' : 'deficit')}: *${formatRupiah(selisih)}*\n`;
  msg += `\n${t(lang, 'lap_total', summary.jumlah_transaksi)}`;
 
  if (transactions.length > 0) {
    msg += `\n\n${t(lang, 'lap_detail')}\n`;
    transactions.slice(0, 8).forEach((tx) => {
      const icon = tx.type === 'in' ? '↑' : '↓';
      const note = tx.note ? ` ${tx.note}` : '';
      msg += `${icon} ${formatRupiah(tx.amount)}${note} _(${tx.date})_\n`;
    });
    if (transactions.length > 8) {
      msg += t(lang, 'lap_more', transactions.length - 8);
    }
  }
 
  return msg;
}
 
/**
 * Format laporan per kategori
 * @param {Array}  rows
 * @param {string} period  - 'hari' | 'minggu' | 'bulan'
 * @param {string} lang    - 'id' | 'en'
 * @param {string} prefix  - command prefix untuk link kosong
 */
function formatKategori(rows, period, lang = 'id', prefix = '/') {
  const labelPeriod = {
    hari:   t(lang, 'period_hari'),
    minggu: t(lang, 'period_minggu'),
    bulan:  t(lang, 'period_bulan'),
  };
  const label = labelPeriod[period] || t(lang, 'period_bulan');
 
  const ICON = {
    makan: '🍽️', jajan: '🧃', transport: '🚗', belanja: '🛍️', tagihan: '💡',
    hiburan: '🎮', kesehatan: '🏥', gaji: '💼', bonus: '🎁',
    transfer: '💸', umum: '📌',
  };
 
  const keluar = rows.filter(r => r.type === 'out').sort((a, b) => b.total - a.total);
  const masuk  = rows.filter(r => r.type === 'in').sort((a, b) => b.total - a.total);
  const totalKeluar = keluar.reduce((s, r) => s + r.total, 0);
  const totalMasuk  = masuk.reduce((s, r) => s + r.total, 0);
 
  let msg = `${t(lang, 'kat_title', label)}\n\n`;
 
  if (keluar.length) {
    msg += `${t(lang, 'kat_expense')}\n`;
    keluar.forEach(r => {
      const icon   = ICON[r.category] || '📌';
      const persen = totalKeluar > 0 ? Math.round((r.total / totalKeluar) * 100) : 0;
      const bar    = progressBar(persen, 8);
      msg += `${icon} *${r.category}*\n   ${bar}\n   ${formatRupiah(r.total)} · ${r.jumlah}x\n\n`;
    });
    msg += `─────────────────\n`;
    msg += `${t(lang, 'kat_total')}: *${formatRupiah(totalKeluar)}*\n\n`;
  }
 
  if (masuk.length) {
    msg += `${t(lang, 'kat_income')}\n`;
    masuk.forEach(r => {
      const icon   = ICON[r.category] || '📌';
      const persen = totalMasuk > 0 ? Math.round((r.total / totalMasuk) * 100) : 0;
      msg += `${icon} *${r.category}*: ${formatRupiah(r.total)} (${persen}%) · ${r.jumlah}x\n`;
    });
  }
 
  if (!keluar.length && !masuk.length) {
    msg += t(lang, 'kat_empty', prefix);
  }
 
  return msg.trim();
}
 
/**
 * Konversi IDR ke USD — pakai rate atau default 15750
 * @param {number} idr
 * @param {number|null} usdRate - 1 USD = X IDR
 * @returns {string} e.g. "$12.34"
 */
function toUsd(idr, usdRate) {
  const rate = usdRate || 15750;
  return '$' + (idr / rate).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
 
/**
 * Format daftar goals — dengan konversi USD opsional
 * @param {Array}    goals
 * @param {Function} getGoalProgress
 * @param {number|null} usdRate - 1 USD = X IDR (dari live_rates, null = pakai default)
 * @param {string}   lang   - 'id' | 'en'
 * @param {string}   prefix - command prefix untuk pesan kosong
 */
function formatGoals(goals, getGoalProgress, usdRate = null, lang = 'id', prefix = '/') {
  if (!goals.length) return t(lang, 'goals_empty', prefix);
 
  const rateLabel = usdRate
    ? `_Kurs: 1 USD = ${formatRupiah(Math.round(usdRate))}_`
    : `_Kurs: 1 USD = ${formatRupiah(15750)} (default)_`;
 
  let msg = `${t(lang, 'goals_title')}\n${rateLabel}\n\n`;
  goals.forEach((g, i) => {
    const { persen, sisaHari } = getGoalProgress(g);
    msg += `*${i + 1}. ${g.name}*\n`;
    msg += `   ${progressBar(persen)}\n`;
    msg += `   ${formatRupiah(g.current_amount)} _(${toUsd(g.current_amount, usdRate)})_\n`;
    msg += `   ${t(lang, 'goals_target')}: ${formatRupiah(g.target_amount)} _(${toUsd(g.target_amount, usdRate)})_\n`;
    if (sisaHari !== null) {
      const sisaLabel = sisaHari > 0
        ? t(lang, 'goals_days', sisaHari)
        : sisaHari === 0
        ? t(lang, 'goals_today')
        : t(lang, 'goals_overdue', sisaHari);
      msg += `   ⏰ ${sisaLabel} _(${g.deadline})_\n`;
    }
    msg += '\n';
  });
 
  return msg.trim();
}
 
/**
 * Format daftar budget bulan ini
 * @param {Array}  budgets
 * @param {string} lang - 'id' | 'en'
 */
function formatBudgets(budgets, lang = 'id') {
  if (!budgets.length) {
    return t(lang, 'budget_empty');
  }
 
  const ICON = {
    makan:'🍽️', jajan:'🧃', transport:'🚗', belanja:'🛍️', tagihan:'💡',
    hiburan:'🎮', kesehatan:'🏥', gaji:'💼', bonus:'🎁', transfer:'💸', umum:'📌',
  };
 
  let msg = `${t(lang, 'budget_title')}\n\n`;
  budgets.forEach(b => {
    const icon   = ICON[b.category] || '📌';
    const persen = Math.min(b.persen, 100);
    const bar    = progressBar(persen, 8);
    const level  = b.persen >= 100 ? '🚨' : b.persen >= 80 ? '⚠️' : '✅';
    msg += `${icon} *${b.category}*  ${level}\n`;
    msg += `   ${bar}\n`;
    msg += `   ${formatRupiah(b.spent)} / ${formatRupiah(b.amount)}\n\n`;
  });
 
  return msg.trim();
}
 
/**
 * Format daftar transaksi berulang
 * @param {Array}  list
 * @param {string} prefix - command prefix
 * @param {string} lang   - 'id' | 'en'
 */
function formatRecurring(list, prefix = '/', lang = 'id') {
  if (!list.length) {
    return t(lang, 'rec_empty', prefix);
  }
 
  const ICON = {
    makan:'🍽️', jajan:'🧃', transport:'🚗', belanja:'🛍️', tagihan:'💡',
    hiburan:'🎮', kesehatan:'🏥', gaji:'💼', bonus:'🎁', transfer:'💸', umum:'📌',
  };
 
  let msg = `${t(lang, 'rec_title')}\n\n`;
  list.forEach(r => {
    const dirIcon = r.type === 'in' ? '📈' : '📉';
    const catIcon = ICON[r.category] || '📌';
    msg += `*#${r.id}* ${dirIcon} *${formatRupiah(r.amount)}*`;
    if (r.note) msg += ` · ${r.note}`;
    msg += `\n   ${catIcon} ${r.category} · ${t(lang, 'rec_every')} *${r.day_of_month}*\n`;
  });
  msg += `\n${t(lang, 'rec_delete', prefix)}`;
 
  return msg;
}
 
/**
 * Format hasil analisis keuangan bulanan
 * @param {object} data
 * @param {string} lang - 'id' | 'en'
 */
function formatAnalisis(data, lang = 'id') {
  const { masukIni, keluarIni, savingsRate, trenKeluar, hariBoros,
    perKategori, hariUnik, rataHari, jumlahTransaksi, bulan } = data;
 
  const BULAN = t(lang, 'BULAN');
  const [year, month] = bulan.split('-');
  const bulanLabel = `${BULAN[parseInt(month) - 1]} ${year}`;
 
  let msg = `${t(lang, 'an_title', bulanLabel)}\n\n`;
 
  msg += `${t(lang, 'an_income')}:   *${formatRupiah(masukIni)}*\n`;
  msg += `${t(lang, 'an_expense')}: *${formatRupiah(keluarIni)}*\n`;
  msg += `${t(lang, 'an_savings')}: *${savingsRate}%*  ${savingsRate >= 30 ? '🟢' : savingsRate >= 10 ? '🟡' : '🔴'}\n`;
 
  if (trenKeluar !== null) {
    const str = trenKeluar > 0
      ? t(lang, 'an_up', trenKeluar)
      : t(lang, 'an_down', Math.abs(trenKeluar));
    msg += `${str}\n`;
  }
 
  msg += `\n${t(lang, 'an_txs', jumlahTransaksi, hariUnik)}\n`;
  if (rataHari > 0) msg += `${t(lang, 'an_avg')}: *${formatRupiah(rataHari)}*\n`;
  if (hariBoros)    msg += `${t(lang, 'an_busiest')}: *${hariBoros}*\n`;
 
  if (perKategori.length > 0) {
    msg += `\n${t(lang, 'an_top')}\n`;
    perKategori.slice(0, 5).forEach((k, i) => {
      const persen = keluarIni > 0 ? Math.round((k.total / keluarIni) * 100) : 0;
      msg += `${i + 1}. *${k.category}* — ${formatRupiah(k.total)} (${persen}%) · ${k.jumlah}x\n`;
    });
  }
 
  msg += `\n${t(lang, 'an_advice')}\n`;
  if (savingsRate < 0) {
    msg += `${t(lang, 'an_crit')}\n`;
  } else if (savingsRate < 20) {
    msg += `${t(lang, 'an_low', savingsRate)}\n`;
  } else if (savingsRate >= 50) {
    msg += `${t(lang, 'an_high', savingsRate)}\n`;
  } else {
    msg += `${t(lang, 'an_ok', savingsRate)}\n`;
  }
 
  if (trenKeluar !== null && trenKeluar >= 30) {
    msg += `${t(lang, 'an_twarn', trenKeluar)}\n`;
  } else if (trenKeluar !== null && trenKeluar <= -20) {
    msg += `${t(lang, 'an_tgood', Math.abs(trenKeluar))}\n`;
  }
 
  if (perKategori.length > 0) {
    const top = perKategori[0];
    const persen = keluarIni > 0 ? Math.round((top.total / keluarIni) * 100) : 0;
    if (persen >= 40) {
      msg += `${t(lang, 'an_topwarn', top.category, persen)}\n`;
    }
  }
 
  return msg.trim();
}
 
/**
 * Format snapshot net worth / kekayaan
 * @param {object} data
 * @param {string} lang - 'id' | 'en'
 */
function formatKekayaan(data, lang = 'id') {
  const { saldo, totalTabungan, totalKekayaan, goals, usdRate } = data;
 
  const toUsdStr = (idr) => {
    const rate = usdRate || 15750;
    return '$' + Math.round(idr / rate).toLocaleString('en-US');
  };
 
  const rateLabel = usdRate
    ? `_Kurs: 1 USD = ${formatRupiah(Math.round(usdRate))}_`
    : `_Kurs: 1 USD = ${formatRupiah(15750)} (default)_`;
 
  const locale  = lang === 'en' ? 'en-US' : 'id-ID';
  const tanggal = new Date().toLocaleDateString(locale, { day: 'numeric', month: 'long', year: 'numeric' });
 
  let msg = `${t(lang, 'kk_title')}\n${rateLabel}\n\n`;
 
  msg += `${t(lang, 'kk_balance')}:   *${formatRupiah(saldo)}* _(${toUsdStr(saldo)})_\n`;
  msg += `${t(lang, 'kk_savings')}: *${formatRupiah(totalTabungan)}* _(${toUsdStr(totalTabungan)})_\n`;
  msg += `─────────────────\n`;
 
  const netSign = totalKekayaan >= 0 ? '💎' : '⚠️';
  msg += `${netSign} *${t(lang, 'kk_net')}: ${formatRupiah(totalKekayaan)}* _(${toUsdStr(totalKekayaan)})_\n`;
 
  if (goals.length > 0) {
    msg += `\n${t(lang, 'kk_goals')}\n`;
    goals.forEach(g => {
      const persen = g.target_amount > 0 ? Math.min(100, Math.round((g.current_amount / g.target_amount) * 100)) : 0;
      const status = g.is_completed || persen >= 100 ? '✅' : '🎯';
      msg += `${status} *${g.name}*: ${formatRupiah(g.current_amount)} _(${persen}%)_\n`;
    });
  }
 
  msg += `\n${t(lang, 'kk_snap', tanggal)}`;
  return msg.trim();
}
 
module.exports = {
  formatRupiah,
  formatTanggal,
  formatDatetime,
  progressBar,
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
};
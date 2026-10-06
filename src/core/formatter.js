// ─── Message Formatter ───────────────────────────────────
// Format pesan yang konsisten untuk Telegram & WhatsApp
// Telegram support Markdown, WA pakai teks biasa
 
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
 * Format datetime ke HH:MM DD/MM/YYYY
 */
function formatDatetime(datetimeStr) {
  const d = new Date(datetimeStr);
  const pad = (n) => String(n).padStart(2, '0');
  return `${pad(d.getHours())}:${pad(d.getMinutes())} ${pad(d.getDate())}/${pad(d.getMonth()+1)}/${d.getFullYear()}`;
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
 */
function formatSaldo({ saldo, total_masuk, total_keluar }) {
  const sign = saldo >= 0 ? '✅' : '⚠️';
  return (
    `💰 *Saldo Sekarang*\n\n` +
    `${sign} Saldo: *${formatRupiah(saldo)}*\n` +
    `📈 Total masuk: ${formatRupiah(total_masuk)}\n` +
    `📉 Total keluar: ${formatRupiah(total_keluar)}`
  );
}
 
/**
 * Format pesan konfirmasi transaksi
 */
function formatTransaksi(trx) {
  const icon = trx.type === 'in' ? '📈' : '📉';
  const label = trx.type === 'in' ? 'Pemasukan' : 'Pengeluaran';
  return (
    `${icon} *${label} dicatat!*\n\n` +
    `Jumlah: *${formatRupiah(trx.amount)}*\n` +
    (trx.note ? `Catatan: ${trx.note}\n` : '') +
    (trx.category !== 'umum' ? `Kategori: ${trx.category}\n` : '') +
    `Waktu: ${formatDatetime(trx.created_at)}`
  );
}
 
/**
 * Format daftar history transaksi
 */
function formatHistory(transactions) {
  if (!transactions.length) return '📭 Belum ada transaksi.';
 
  const rows = transactions.map((t) => {
    const icon = t.type === 'in' ? '📈' : '📉';
    const note = t.note ? ` · ${t.note}` : '';
    return `${icon} *#${t.id}* ${formatRupiah(t.amount)}${note}\n   _${t.date}_`;
  });
 
  return `📋 *Riwayat Transaksi*\n\n` + rows.join('\n') + `\n\n_Menampilkan ${transactions.length} transaksi terakhir_\n_Gunakan /hapus [id] untuk hapus transaksi_`;
}
 
/**
 * Format laporan per periode
 */
function formatLaporan({ transactions, summary }, period) {
  const labelPeriod = { hari: 'Hari Ini', minggu: 'Minggu Ini', bulan: 'Bulan Ini' };
  const label = labelPeriod[period] || 'Periode';
 
  let msg = `📊 *Laporan ${label}*\n\n`;
  msg += `📈 Masuk:  *${formatRupiah(summary.total_masuk)}*\n`;
  msg += `📉 Keluar: *${formatRupiah(summary.total_keluar)}*\n`;
  msg += `─────────────────\n`;
 
  const selisih = summary.selisih;
  const sign = selisih >= 0 ? '✅ Surplus' : '⚠️ Defisit';
  msg += `${sign}: *${formatRupiah(selisih)}*\n`;
  msg += `\nTotal ${summary.jumlah_transaksi} transaksi`;
 
  if (transactions.length > 0) {
    msg += `\n\n*Detail:*\n`;
    transactions.slice(0, 8).forEach((t) => {
      const icon = t.type === 'in' ? '↑' : '↓';
      const note = t.note ? ` ${t.note}` : '';
      msg += `${icon} ${formatRupiah(t.amount)}${note} _(${t.date})_\n`;
    });
    if (transactions.length > 8) {
      msg += `_...dan ${transactions.length - 8} lainnya_`;
    }
  }
 
  return msg;
}
 
/**
 * Format laporan per kategori
 */
function formatKategori(rows, period) {
  const labelPeriod = { hari: 'Hari Ini', minggu: 'Minggu Ini', bulan: 'Bulan Ini' };
  const label = labelPeriod[period] || 'Bulan Ini';
 
  const ICON = {
    makan: '🍽️', jajan: '🧃', transport: '🚗', belanja: '🛍️', tagihan: '💡',
    hiburan: '🎮', kesehatan: '🏥', gaji: '💼', bonus: '🎁',
    transfer: '💸', umum: '📌',
  };
 
  const keluar = rows.filter(r => r.type === 'out').sort((a, b) => b.total - a.total);
  const masuk  = rows.filter(r => r.type === 'in').sort((a, b) => b.total - a.total);
  const totalKeluar = keluar.reduce((s, r) => s + r.total, 0);
  const totalMasuk  = masuk.reduce((s, r) => s + r.total, 0);
 
  let msg = `📊 *Laporan Kategori — ${label}*\n\n`;
 
  if (keluar.length) {
    msg += `📉 *Pengeluaran:*\n`;
    keluar.forEach(r => {
      const icon   = ICON[r.category] || '📌';
      const persen = totalKeluar > 0 ? Math.round((r.total / totalKeluar) * 100) : 0;
      const bar    = progressBar(persen, 8);
      msg += `${icon} *${r.category}*\n   ${bar}\n   ${formatRupiah(r.total)} · ${r.jumlah}x\n\n`;
    });
    msg += `─────────────────\n`;
    msg += `Total: *${formatRupiah(totalKeluar)}*\n\n`;
  }
 
  if (masuk.length) {
    msg += `📈 *Pemasukan:*\n`;
    masuk.forEach(r => {
      const icon   = ICON[r.category] || '📌';
      const persen = totalMasuk > 0 ? Math.round((r.total / totalMasuk) * 100) : 0;
      msg += `${icon} *${r.category}*: ${formatRupiah(r.total)} (${persen}%) · ${r.jumlah}x\n`;
    });
  }
 
  if (!keluar.length && !masuk.length) {
    msg += '_Belum ada transaksi di periode ini._\n\nCoba: `/kategori bulan`';
  }
 
  return msg.trim();
}
 
/**
 * Format daftar goals
 */
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
 * @param {Array} goals
 * @param {Function} getGoalProgress
 * @param {number|null} usdRate - 1 USD = X IDR (dari live_rates, null = pakai default)
 */
function formatGoals(goals, getGoalProgress, usdRate = null) {
  if (!goals.length) return '🎯 Belum ada target tabungan.\n\nGunakan `/target buat NamaGoal 1000000` untuk mulai.';
 
  const rateLabel = usdRate
    ? `_Kurs: 1 USD = ${formatRupiah(Math.round(usdRate))}_`
    : `_Kurs: 1 USD = ${formatRupiah(15750)} (default)_`;
 
  let msg = `🎯 *Target Tabungan*\n${rateLabel}\n\n`;
  goals.forEach((g, i) => {
    const { persen, sisaHari } = getGoalProgress(g);
    msg += `*${i + 1}. ${g.name}*\n`;
    msg += `   ${progressBar(persen)}\n`;
    msg += `   ${formatRupiah(g.current_amount)} _(${toUsd(g.current_amount, usdRate)})_\n`;
    msg += `   Target: ${formatRupiah(g.target_amount)} _(${toUsd(g.target_amount, usdRate)})_\n`;
    if (sisaHari !== null) {
      const sisaLabel = sisaHari > 0 ? `${sisaHari} hari lagi` : sisaHari === 0 ? 'Hari ini!' : `Terlewat ${Math.abs(sisaHari)} hari`;
      msg += `   ⏰ ${sisaLabel} _(${g.deadline})_\n`;
    }
    msg += '\n';
  });
 
  return msg.trim();
}
 
/**
 * Format daftar budget bulan ini
 */
function formatBudgets(budgets) {
  if (!budgets.length) {
    return (
      `💡 *Budget Bulan Ini*\n\n` +
      `_Belum ada budget.\n\n` +
      `Gunakan:\n` +
      `/budget makan 500rb\n` +
      `/budget transport 300rb_`
    );
  }
 
  const ICON = {
    makan:'🍽️', jajan:'🧃', transport:'🚗', belanja:'🛍️', tagihan:'💡',
    hiburan:'🎮', kesehatan:'🏥', gaji:'💼', bonus:'🎁', transfer:'💸', umum:'📌',
  };
 
  let msg = `💡 *Budget Bulan Ini*\n\n`;
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
 */
function formatRecurring(list, prefix = '/') {
  if (!list.length) {
    return (
      `🔄 *Transaksi Berulang*\n\n` +
      `_Belum ada.\n\n` +
      `Contoh:\n` +
      `${prefix}rutin tambah keluar 150rb netflix 5\n` +
      `(catat keluar 150rb "netflix" tiap tgl 5)_`
    );
  }
 
  const ICON = {
    makan:'🍽️', jajan:'🧃', transport:'🚗', belanja:'🛍️', tagihan:'💡',
    hiburan:'🎮', kesehatan:'🏥', gaji:'💼', bonus:'🎁', transfer:'💸', umum:'📌',
  };
 
  let msg = `🔄 *Transaksi Berulang*\n\n`;
  list.forEach(r => {
    const dirIcon = r.type === 'in' ? '📈' : '📉';
    const catIcon = ICON[r.category] || '📌';
    msg += `*#${r.id}* ${dirIcon} *${formatRupiah(r.amount)}*`;
    if (r.note) msg += ` · ${r.note}`;
    msg += `\n   ${catIcon} ${r.category} · tiap tgl *${r.day_of_month}*\n`;
  });
  msg += `\n_Gunakan ${prefix}rutin hapus [id] untuk hapus_`;
 
  return msg;
}
 
/**
 * Format hasil analisis keuangan bulanan
 */
function formatAnalisis(data) {
  const { masukIni, keluarIni, savingsRate, trenKeluar, hariBoros,
    perKategori, hariUnik, rataHari, jumlahTransaksi, bulan } = data;
 
  const NAMA_BULAN = ['Januari','Februari','Maret','April','Mei','Juni',
    'Juli','Agustus','September','Oktober','November','Desember'];
  const [year, month] = bulan.split('-');
  const bulanLabel = `${NAMA_BULAN[parseInt(month) - 1]} ${year}`;
 
  let msg = `🧠 *Analisis Keuangan — ${bulanLabel}*\n\n`;
 
  msg += `💰 Pemasukan:   *${formatRupiah(masukIni)}*\n`;
  msg += `💸 Pengeluaran: *${formatRupiah(keluarIni)}*\n`;
  msg += `📊 Savings Rate: *${savingsRate}%*  ${savingsRate >= 30 ? '🟢' : savingsRate >= 10 ? '🟡' : '🔴'}\n`;
 
  if (trenKeluar !== null) {
    const icon  = trenKeluar > 0 ? '📈' : '📉';
    const label = trenKeluar > 0 ? `naik ${trenKeluar}%` : `turun ${Math.abs(trenKeluar)}%`;
    msg += `${icon} Pengeluaran vs bulan lalu: *${label}*\n`;
  }
 
  msg += `\n📋 *${jumlahTransaksi} transaksi* dalam ${hariUnik} hari aktif\n`;
  if (rataHari > 0) msg += `📌 Rata-rata pengeluaran/hari: *${formatRupiah(rataHari)}*\n`;
  if (hariBoros)    msg += `📅 Hari paling boros: *${hariBoros}*\n`;
 
  if (perKategori.length > 0) {
    msg += `\n📊 *Top Pengeluaran:*\n`;
    perKategori.slice(0, 5).forEach((k, i) => {
      const persen = keluarIni > 0 ? Math.round((k.total / keluarIni) * 100) : 0;
      msg += `${i + 1}. *${k.category}* — ${formatRupiah(k.total)} (${persen}%) · ${k.jumlah}x\n`;
    });
  }
 
  msg += `\n💡 *Saran:*\n`;
  if (savingsRate < 0) {
    msg += `🚨 Pengeluaran melebihi pemasukan! Segera kurangi pengeluaran.\n`;
  } else if (savingsRate < 20) {
    msg += `⚠️ Savings rate ${savingsRate}% — targetkan minimal 20% dari pemasukan.\n`;
  } else if (savingsRate >= 50) {
    msg += `🎉 Savings rate ${savingsRate}% — luar biasa! Pertahankan terus.\n`;
  } else {
    msg += `✅ Savings rate ${savingsRate}% — sudah bagus!\n`;
  }
 
  if (trenKeluar !== null && trenKeluar >= 30) {
    msg += `⚠️ Pengeluaran naik *${trenKeluar}%* dari bulan lalu — perlu diwaspadai.\n`;
  } else if (trenKeluar !== null && trenKeluar <= -20) {
    msg += `🎉 Berhasil hemat *${Math.abs(trenKeluar)}%* dibanding bulan lalu!\n`;
  }
 
  if (perKategori.length > 0) {
    const top = perKategori[0];
    const persen = keluarIni > 0 ? Math.round((top.total / keluarIni) * 100) : 0;
    if (persen >= 40) {
      msg += `💡 *${top.category}* makan ${persen}% budget — coba batasi dengan /budget.\n`;
    }
  }
 
  return msg.trim();
}
 
/**
 * Format snapshot net worth / kekayaan
 */
function formatKekayaan(data) {
  const { saldo, totalTabungan, totalKekayaan, goals, usdRate } = data;
 
  const toUsdStr = (idr) => {
    const rate = usdRate || 15750;
    return '$' + Math.round(idr / rate).toLocaleString('en-US');
  };
 
  const rateLabel = usdRate
    ? `_Kurs: 1 USD = ${formatRupiah(Math.round(usdRate))}_`
    : `_Kurs: 1 USD = ${formatRupiah(15750)} (default)_`;
 
  const tanggal = new Date().toLocaleDateString('id-ID', { day: 'numeric', month: 'long', year: 'numeric' });
 
  let msg = `💎 *Net Worth Snapshot*\n${rateLabel}\n\n`;
 
  msg += `💰 Saldo Aktif:   *${formatRupiah(saldo)}* _(${toUsdStr(saldo)})_\n`;
  msg += `🎯 Total Tabungan: *${formatRupiah(totalTabungan)}* _(${toUsdStr(totalTabungan)})_\n`;
  msg += `─────────────────\n`;
 
  const netSign = totalKekayaan >= 0 ? '💎' : '⚠️';
  msg += `${netSign} *Net Worth: ${formatRupiah(totalKekayaan)}* _(${toUsdStr(totalKekayaan)})_\n`;
 
  if (goals.length > 0) {
    msg += `\n📊 *Rincian Goals:*\n`;
    goals.forEach(g => {
      const persen = g.target_amount > 0 ? Math.min(100, Math.round((g.current_amount / g.target_amount) * 100)) : 0;
      const status = g.is_completed || persen >= 100 ? '✅' : '🎯';
      msg += `${status} *${g.name}*: ${formatRupiah(g.current_amount)} _(${persen}%)_\n`;
    });
  }
 
  msg += `\n_Snapshot per ${tanggal}_`;
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
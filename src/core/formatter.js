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
 * Format daftar goals
 */
function formatGoals(goals, getGoalProgress) {
  if (!goals.length) return '🎯 Belum ada target tabungan.\n\nGunakan `/target buat NamaGoal 1000000` untuk mulai.';
 
  let msg = `🎯 *Target Tabungan*\n\n`;
  goals.forEach((g, i) => {
    const { persen, sisaHari } = getGoalProgress(g);
    msg += `*${i + 1}. ${g.name}*\n`;
    msg += `   ${progressBar(persen)}\n`;
    msg += `   ${formatRupiah(g.current_amount)} / ${formatRupiah(g.target_amount)}\n`;
    if (sisaHari !== null) {
      const sisaLabel = sisaHari > 0 ? `${sisaHari} hari lagi` : sisaHari === 0 ? 'Hari ini!' : `Terlewat ${Math.abs(sisaHari)} hari`;
      msg += `   ⏰ ${sisaLabel} _(${g.deadline})_\n`;
    }
    msg += '\n';
  });
 
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
  formatGoals,
};

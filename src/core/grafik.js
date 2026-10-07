// ─── Grafik / Chart Generator ────────────────────────────
// Pakai QuickChart.io API (no native deps) → return PNG Buffer
 
const https = require('https');
const { getLaporanKategori, getLaporanTrend } = require('./finance');
const { formatRupiah } = require('./formatter');
 
// ─── Palette ──────────────────────────────────────────────
const COLORS = [
  '#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0',
  '#9966FF', '#FF9F40', '#C9CBCF', '#7BC8A4',
  '#E8735A', '#B39DDB',
];
 
const PERIOD_LABEL_ID = { hari: 'Hari Ini', minggu: 'Minggu Ini', bulan: 'Bulan Ini' };
const PERIOD_LABEL_EN = { hari: 'Today',    minggu: 'This Week',  bulan: 'This Month' };
 
/**
 * Build Chart.js config dari data pengeluaran per kategori
 * @param {string} walletId
 * @param {string} period  - 'hari' | 'minggu' | 'bulan'
 * @param {string} lang    - 'id' | 'en'
 * @returns {{ config, total, keluar }} atau null kalau tidak ada data
 */
function buildChartConfig(walletId, period = 'bulan', lang = 'id') {
  const rows = getLaporanKategori(walletId, period);
  const keluar = rows
    .filter(r => r.type === 'out')
    .sort((a, b) => b.total - a.total)
    .slice(0, 8); // max 8 kategori
 
  if (!keluar.length) return null;
 
  const labels = keluar.map(r => r.category);
  const data   = keluar.map(r => Math.round(r.total));
  const bg     = keluar.map((_, i) => COLORS[i % COLORS.length]);
  const labelMap = lang === 'en' ? PERIOD_LABEL_EN : PERIOD_LABEL_ID;
  const periodLabel = labelMap[period] || labelMap.bulan;
  const total  = data.reduce((a, b) => a + b, 0);
 
  const config = {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data,
        backgroundColor: bg,
        borderRadius: 6,
      }],
    },
    options: {
      plugins: {
        title: {
          display: true,
          text: lang === 'en' ? `Expenses — ${periodLabel}` : `Pengeluaran — ${periodLabel}`,
          font: { size: 16, weight: 'bold' },
          padding: { bottom: 16 },
        },
        legend: { display: false },
      },
      scales: {
        y: {
          beginAtZero: true,
          ticks: { display: false },
          grid: { color: '#f0f0f0' },
        },
        x: {
          grid: { display: false },
          ticks: { font: { size: 13 } },
        },
      },
      layout: { padding: { top: 8, left: 8, right: 8, bottom: 8 } },
    },
  };
 
  return { config, total, keluar };
}
 
/**
 * POST ke QuickChart.io → return PNG Buffer
 * @param {object} chartConfig - Chart.js config object
 * @returns {Promise<Buffer>}
 */
function fetchGrafikBuffer(chartConfig) {
  return new Promise((resolve, reject) => {
    const payload = JSON.stringify({
      chart: chartConfig,
      width: 640,
      height: 400,
      backgroundColor: 'white',
      format: 'png',
      version: '4',
    });
 
    const options = {
      hostname: 'quickchart.io',
      path: '/chart',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(payload),
      },
      timeout: 15000,
    };
 
    const req = https.request(options, (res) => {
      const chunks = [];
      res.on('data', c => chunks.push(c));
      res.on('end', () => {
        const buf = Buffer.concat(chunks);
        // QuickChart returns error as JSON string if failed
        if (res.headers['content-type']?.includes('application/json')) {
          reject(new Error('QuickChart error: ' + buf.toString()));
        } else {
          resolve(buf);
        }
      });
    });
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(); reject(new Error('QuickChart timeout')); });
    req.write(payload);
    req.end();
  });
}
 
/**
 * Build caption teks untuk grafik
 * @param {Array} keluar - rows dari buildChartConfig
 * @param {number} total
 * @param {string} period
 * @param {string} lang
 * @returns {string}
 */
function buildGrafikCaption(keluar, total, period, lang = 'id') {
  const labelMap = lang === 'en' ? PERIOD_LABEL_EN : PERIOD_LABEL_ID;
  const periodLabel = labelMap[period] || labelMap.bulan;
  const title = lang === 'en'
    ? `📊 *Expenses — ${periodLabel}*`
    : `📊 *Pengeluaran — ${periodLabel}*`;
  const totalLabel = lang === 'en' ? 'Total' : 'Total';
 
  const lines = keluar.map((r, i) => {
    const pct = Math.round((r.total / total) * 100);
    return `${i + 1}. ${r.category}: *${formatRupiah(r.total)}* (${pct}%)`;
  });
 
  return `${title}\n${totalLabel}: *${formatRupiah(total)}*\n\n${lines.join('\n')}`;
}
 
// ─── Trend Bulanan ────────────────────────────────────────
 
const NAMA_BULAN_SHORT = [
  'Jan','Feb','Mar','Apr','Mei','Jun',
  'Jul','Ags','Sep','Okt','Nov','Des',
];
const MONTH_SHORT_EN = [
  'Jan','Feb','Mar','Apr','May','Jun',
  'Jul','Aug','Sep','Oct','Nov','Dec',
];
 
/**
 * Format 'YYYY-MM' jadi label singkat ('Okt 26')
 */
function shortMonthLabel(monthStr, lang = 'id') {
  const [y, m] = monthStr.split('-').map(Number);
  const names = lang === 'en' ? MONTH_SHORT_EN : NAMA_BULAN_SHORT;
  return `${names[m - 1]} '${String(y).slice(2)}`;
}
 
/**
 * Build Chart.js config untuk trend pengeluaran N bulan
 * @param {string} walletId
 * @param {number} months - 3 | 6 | 12
 * @param {string} lang   - 'id' | 'en'
 * @returns {{ config, rows, months }} atau null jika tidak ada data
 */
function buildTrendConfig(walletId, months = 6, lang = 'id') {
  const rows = getLaporanTrend(walletId, months);
  if (!rows.length) return null;
 
  const labels   = rows.map(r => shortMonthLabel(r.month, lang));
  const keluarData = rows.map(r => Math.round(r.keluar));
  const masukData  = rows.map(r => Math.round(r.masuk));
 
  const title = lang === 'en'
    ? `Income vs Expenses — Last ${months} Months`
    : `Tren Keuangan — ${months} Bulan Terakhir`;
 
  const config = {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label:           lang === 'en' ? 'Expenses'  : 'Pengeluaran',
          data:            keluarData,
          borderColor:     '#FF6384',
          backgroundColor: 'rgba(255,99,132,0.12)',
          fill:            true,
          tension:         0.35,
          pointRadius:     5,
          pointHoverRadius: 7,
        },
        {
          label:           lang === 'en' ? 'Income'    : 'Pemasukan',
          data:            masukData,
          borderColor:     '#36A2EB',
          backgroundColor: 'rgba(54,162,235,0.12)',
          fill:            true,
          tension:         0.35,
          pointRadius:     5,
          pointHoverRadius: 7,
        },
      ],
    },
    options: {
      plugins: {
        title: {
          display: true,
          text:    title,
          font:    { size: 15, weight: 'bold' },
          padding: { bottom: 14 },
        },
        legend: { display: true, position: 'bottom' },
      },
      scales: {
        y: {
          beginAtZero:  true,
          ticks:        { display: false },
          grid:         { color: '#f0f0f0' },
        },
        x: {
          grid: { display: false },
          ticks: { font: { size: 12 } },
        },
      },
      layout: { padding: { top: 8, left: 8, right: 8, bottom: 8 } },
    },
  };
 
  return { config, rows, months };
}
 
/**
 * Build caption untuk grafik trend
 * @param {Array} rows   - dari getLaporanTrend
 * @param {number} months
 * @param {string} lang
 * @returns {string}
 */
function buildTrendCaption(rows, months, lang = 'id') {
  if (!rows.length) return '';
 
  const totalKeluar = rows.reduce((s, r) => s + r.keluar, 0);
  const totalMasuk  = rows.reduce((s, r) => s + r.masuk, 0);
  const avgKeluar   = Math.round(totalKeluar / rows.length);
  const avgMasuk    = Math.round(totalMasuk  / rows.length);
 
  // Bulan dengan pengeluaran tertinggi
  const peak = rows.reduce((a, b) => b.keluar > a.keluar ? b : a, rows[0]);
  const peakLabel = shortMonthLabel(peak.month, lang);
 
  if (lang === 'en') {
    return [
      `📈 *Financial Trend — Last ${months} Months*`,
      ``,
      `💸 Total expenses: *${formatRupiah(totalKeluar)}*`,
      `💰 Total income:   *${formatRupiah(totalMasuk)}*`,
      `📊 Avg expenses/month: *${formatRupiah(avgKeluar)}*`,
      `📊 Avg income/month:   *${formatRupiah(avgMasuk)}*`,
      `📍 Peak spending: *${peakLabel}* (${formatRupiah(peak.keluar)})`,
    ].join('\n');
  }
 
  return [
    `📈 *Tren Keuangan — ${months} Bulan Terakhir*`,
    ``,
    `💸 Total pengeluaran: *${formatRupiah(totalKeluar)}*`,
    `💰 Total pemasukan:   *${formatRupiah(totalMasuk)}*`,
    `📊 Rata-rata keluar/bulan: *${formatRupiah(avgKeluar)}*`,
    `📊 Rata-rata masuk/bulan:  *${formatRupiah(avgMasuk)}*`,
    `📍 Pengeluaran tertinggi: *${peakLabel}* (${formatRupiah(peak.keluar)})`,
  ].join('\n');
}
 
module.exports = {
  buildChartConfig, fetchGrafikBuffer, buildGrafikCaption,
  buildTrendConfig, buildTrendCaption,
};
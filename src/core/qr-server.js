const http = require('http');
const { URL } = require('url');
 
let currentQR = null;
let isConnected = false;
let server = null;
 
// ─── QR State ─────────────────────────────────────────────
 
function setQR(qrData) {
  currentQR = qrData;
  isConnected = false;
}
 
function clearQR() {
  currentQR = null;
  isConnected = true;
}
 
// ─── Dashboard Data Helpers ───────────────────────────────
 
function safeGetDb() {
  try {
    return require('./database').getDb();
  } catch {
    return null;
  }
}
 
function getAllWallets() {
  const db = safeGetDb();
  if (!db) return [];
  try {
    const wallets = db.prepare('SELECT * FROM wallets ORDER BY created_at DESC').all();
    return wallets.map(w => {
      const masuk  = db.prepare(`SELECT COALESCE(SUM(amount),0) AS t FROM transactions WHERE wallet_id=? AND type='in'`).get(w.id);
      const keluar = db.prepare(`SELECT COALESCE(SUM(amount),0) AS t FROM transactions WHERE wallet_id=? AND type='out'`).get(w.id);
      return { id: w.id, name: w.name, platform: w.platform, saldo: masuk.t - keluar.t };
    });
  } catch { return []; }
}
 
function getWalletDashboard(walletId) {
  const db = safeGetDb();
  if (!db) throw new Error('Database belum siap');
 
  const masuk  = db.prepare(`SELECT COALESCE(SUM(amount),0) AS t FROM transactions WHERE wallet_id=? AND type='in'`).get(walletId);
  const keluar = db.prepare(`SELECT COALESCE(SUM(amount),0) AS t FROM transactions WHERE wallet_id=? AND type='out'`).get(walletId);
 
  const chartData = db.prepare(`
    SELECT date,
      SUM(CASE WHEN type='in'  THEN amount ELSE 0 END) AS masuk,
      SUM(CASE WHEN type='out' THEN amount ELSE 0 END) AS keluar
    FROM transactions
    WHERE wallet_id=? AND date >= date('now','localtime','-29 days')
    GROUP BY date ORDER BY date ASC
  `).all(walletId);
 
  const goals = db.prepare(`
    SELECT * FROM goals WHERE wallet_id=? AND is_completed=0 ORDER BY created_at ASC
  `).all(walletId);
 
  const goalsData = goals.map(g => ({
    name: g.name,
    target_amount: g.target_amount,
    current_amount: g.current_amount,
    deadline: g.deadline || null,
    persen: Math.min(Math.round((g.current_amount / g.target_amount) * 100), 100),
  }));
 
  const recent = db.prepare(`
    SELECT * FROM transactions WHERE wallet_id=? ORDER BY created_at DESC LIMIT 10
  `).all(walletId);
 
  const kategori = db.prepare(`
    SELECT category, type,
      SUM(amount) AS total,
      COUNT(*) AS jumlah
    FROM transactions
    WHERE wallet_id=? AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now', 'localtime')
    GROUP BY category, type
    ORDER BY total DESC
  `).all(walletId);
 
  return {
    saldo: masuk.t - keluar.t,
    total_masuk: masuk.t,
    total_keluar: keluar.t,
    chartData,
    goals: goalsData,
    recent,
    kategori,
  };
}
 
// ─── QR Page HTML ─────────────────────────────────────────
 
const QR_HTML = `<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Money Bot – WhatsApp QR</title>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #f7f7f7; min-height: 100vh;
      display: flex; flex-direction: column;
      align-items: center; justify-content: center; padding: 24px;
    }
    .card {
      background: white; border-radius: 16px; padding: 32px 40px;
      text-align: center; box-shadow: 0 4px 24px rgba(0,0,0,0.10);
      max-width: 380px; width: 100%;
    }
    h1 { font-size: 1.4rem; color: #111; margin-bottom: 4px; }
    .subtitle { color: #888; font-size: 0.9rem; margin-bottom: 16px; }
    .nav { margin-bottom: 20px; }
    .nav a {
      display: inline-block; padding: 6px 14px; border-radius: 999px;
      font-size: 0.82rem; text-decoration: none;
      background: #f0f0f0; color: #555; margin: 0 4px;
    }
    .nav a:hover { background: #e0e0e0; }
    .nav a.active { background: #dcfce7; color: #16a34a; }
    .status {
      display: inline-block; padding: 8px 18px; border-radius: 999px;
      font-size: 0.9rem; font-weight: 600; margin-bottom: 20px;
    }
    .waiting  { background: #fff3cd; color: #92680a; }
    .scanning { background: #e0f7e9; color: #1a7d3a; }
    .done     { background: #d4edda; color: #155724; }
    #qr-wrap {
      display: flex; justify-content: center;
      min-height: 180px; align-items: center; margin-bottom: 16px;
    }
    #qrcode canvas, #qrcode img { border-radius: 8px; }
    .hint { color: #666; font-size: 0.82rem; line-height: 1.5; }
    .loader {
      width: 44px; height: 44px;
      border: 4px solid #eee; border-top-color: #25D366;
      border-radius: 50%; animation: spin 0.8s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    .refresh { color: #aaa; font-size: 0.75rem; margin-top: 14px; }
  </style>
</head>
<body>
  <div class="card">
    <h1>💰 Money Bot</h1>
    <p class="subtitle">WhatsApp Setup</p>
    <div class="nav">
      <a href="/" class="active">🔗 QR Setup</a>
      <a href="/dashboard">📊 Dashboard</a>
    </div>
    <div id="status" class="status waiting">⏳ Menunggu QR code...</div>
    <div id="qr-wrap">
      <div class="loader" id="loader"></div>
      <div id="qrcode" style="display:none"></div>
    </div>
    <p class="hint" id="hint">
      Halaman ini otomatis refresh setiap 3 detik.<br>
      QR akan muncul sebentar lagi.
    </p>
    <p class="refresh" id="refresh-note"></p>
  </div>
  <script>
    let qrInstance = null;
    let lastQR = null;
    async function poll() {
      try {
        const res  = await fetch('/api/qr');
        const data = await res.json();
        if (data.connected) {
          document.getElementById('status').className = 'status done';
          document.getElementById('status').textContent = '✅ WhatsApp Terhubung!';
          document.getElementById('hint').textContent = 'Bot sudah aktif dan siap digunakan!';
          document.getElementById('loader').style.display = 'none';
          document.getElementById('qrcode').style.display = 'none';
          clearInterval(timer);
          return;
        }
        if (data.qr && data.qr !== lastQR) {
          lastQR = data.qr;
          document.getElementById('loader').style.display = 'none';
          document.getElementById('qrcode').style.display = 'block';
          document.getElementById('status').className = 'status scanning';
          document.getElementById('status').textContent = '📱 Scan QR dengan WhatsApp!';
          document.getElementById('hint').innerHTML =
            '<strong>WhatsApp</strong> → Settings → <strong>Linked Devices</strong><br>→ Link a Device → Scan QR ini';
          if (!qrInstance) {
            qrInstance = new QRCode(document.getElementById('qrcode'), {
              text: data.qr, width: 220, height: 220,
              colorDark: '#000000', colorLight: '#ffffff',
            });
          } else { qrInstance.clear(); qrInstance.makeCode(data.qr); }
        }
        document.getElementById('refresh-note').textContent =
          'Terakhir dicek: ' + new Date().toLocaleTimeString('id-ID');
      } catch (e) {
        document.getElementById('refresh-note').textContent = 'Reconnecting...';
      }
    }
    poll();
    const timer = setInterval(poll, 3000);
  </script>
</body>
</html>`;
 
// ─── Dashboard Page HTML ──────────────────────────────────
 
const DASHBOARD_HTML = `<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Money Bot – Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #f4f6f9; min-height: 100vh; color: #1a1a2e;
    }
    header {
      background: white; border-bottom: 1px solid #e5e7eb;
      padding: 14px 24px; display: flex; align-items: center;
      justify-content: space-between; position: sticky; top: 0;
      z-index: 100; box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    }
    .logo { font-size: 1.15rem; font-weight: 700; color: #111; }
    .logo span { color: #16a34a; }
    nav a {
      text-decoration: none; color: #555; font-size: 0.85rem;
      padding: 6px 14px; border-radius: 999px;
      background: #f0f0f0; margin-left: 8px; transition: background 0.15s;
    }
    nav a:hover { background: #e5e7eb; }
    nav a.active { background: #dcfce7; color: #16a34a; }
    .container { max-width: 960px; margin: 0 auto; padding: 24px 16px; }
 
    .wallet-bar {
      background: white; border-radius: 12px; padding: 14px 20px;
      margin-bottom: 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.06);
      display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
    }
    .wallet-bar label { font-size: 0.85rem; color: #666; font-weight: 500; white-space: nowrap; }
    .wallet-bar select {
      flex: 1; min-width: 200px; padding: 8px 12px;
      border: 1px solid #e5e7eb; border-radius: 8px;
      font-size: 0.9rem; background: #f9fafb; color: #111; cursor: pointer;
    }
    .wallet-bar select:focus { outline: none; border-color: #16a34a; }
 
    .stats-grid {
      display: grid; grid-template-columns: repeat(3, 1fr);
      gap: 16px; margin-bottom: 20px;
    }
    @media (max-width: 580px) { .stats-grid { grid-template-columns: 1fr; } }
    .stat-card {
      background: white; border-radius: 12px; padding: 18px 20px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.06);
      border-top: 3px solid transparent;
    }
    .stat-card.saldo  { border-top-color: #2563eb; }
    .stat-card.masuk  { border-top-color: #16a34a; }
    .stat-card.keluar { border-top-color: #dc2626; }
    .stat-label {
      font-size: 0.75rem; color: #9ca3af; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 8px;
    }
    .stat-value { font-size: 1.35rem; font-weight: 700; }
    .stat-card.saldo  .stat-value { color: #2563eb; }
    .stat-card.masuk  .stat-value { color: #16a34a; }
    .stat-card.keluar .stat-value { color: #dc2626; }
 
    .chart-card {
      background: white; border-radius: 12px; padding: 20px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.06); margin-bottom: 20px;
    }
    .section-title {
      font-size: 0.9rem; font-weight: 600; color: #374151; margin-bottom: 14px;
    }
    .chart-wrap { position: relative; height: 230px; }
 
    .goals-grid {
      display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
      gap: 14px; margin-bottom: 20px;
    }
    .goal-card {
      background: white; border-radius: 12px; padding: 16px 18px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    }
    .goal-name { font-weight: 600; font-size: 0.92rem; margin-bottom: 6px; color: #111; }
    .goal-amounts { font-size: 0.8rem; color: #6b7280; margin-bottom: 10px; }
    .progress-bg {
      background: #f0f0f0; border-radius: 999px; height: 8px; overflow: hidden; margin-bottom: 6px;
    }
    .progress-fill {
      height: 100%; border-radius: 999px;
      background: linear-gradient(90deg, #16a34a, #22c55e); transition: width 0.6s ease;
    }
    .progress-fill.done { background: linear-gradient(90deg, #2563eb, #60a5fa); }
    .goal-meta { font-size: 0.76rem; color: #9ca3af; display: flex; justify-content: space-between; }
 
    .txn-card {
      background: white; border-radius: 12px; padding: 20px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    }
    .txn-list { list-style: none; }
    .txn-item {
      display: flex; align-items: center; justify-content: space-between;
      padding: 10px 0; border-bottom: 1px solid #f3f4f6; font-size: 0.87rem;
    }
    .txn-item:last-child { border-bottom: none; }
    .txn-left { display: flex; align-items: center; gap: 10px; }
    .txn-icon {
      width: 34px; height: 34px; border-radius: 50%;
      display: flex; align-items: center; justify-content: center; font-size: 15px;
    }
    .txn-icon.in  { background: #dcfce7; }
    .txn-icon.out { background: #fee2e2; }
    .txn-note { color: #374151; font-weight: 500; }
    .txn-id { color: #d1d5db; font-size: 0.72rem; margin-left: 4px; }
    .txn-date { font-size: 0.74rem; color: #9ca3af; margin-top: 1px; }
    .txn-amount { font-weight: 700; }
    .txn-amount.in  { color: #16a34a; }
    .txn-amount.out { color: #dc2626; }
 
    .empty { text-align: center; padding: 28px; color: #9ca3af; font-size: 0.88rem; line-height: 1.6; }
    .goals-section-title { font-size: 0.9rem; font-weight: 600; color: #374151; margin-bottom: 12px; }
 
    .kategori-card {
      background: white; border-radius: 12px; padding: 20px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.06); margin-bottom: 20px;
    }
    .kat-grid {
      display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 4px;
    }
    @media (max-width: 580px) { .kat-grid { grid-template-columns: 1fr; } }
    .kat-group-title {
      font-size: 0.8rem; font-weight: 700; text-transform: uppercase;
      letter-spacing: 0.05em; margin-bottom: 10px;
    }
    .kat-group-title.out { color: #dc2626; }
    .kat-group-title.in  { color: #16a34a; }
    .kat-row { margin-bottom: 10px; }
    .kat-row-top {
      display: flex; justify-content: space-between;
      font-size: 0.82rem; margin-bottom: 4px; color: #374151;
    }
    .kat-name { font-weight: 600; }
    .kat-amount { color: #6b7280; }
    .kat-bar-bg { background: #f0f0f0; border-radius: 999px; height: 6px; overflow: hidden; }
    .kat-bar-fill { height: 100%; border-radius: 999px; transition: width 0.5s ease; }
    .kat-bar-fill.out { background: linear-gradient(90deg, #ef4444, #f87171); }
    .kat-bar-fill.in  { background: linear-gradient(90deg, #16a34a, #4ade80); }
    .kat-count { font-size: 0.7rem; color: #9ca3af; margin-top: 2px; }
  </style>
</head>
<body>
 
<header>
  <div class="logo">💰 Money<span>Bot</span></div>
  <nav>
    <a href="/">🔗 QR Setup</a>
    <a href="/dashboard" class="active">📊 Dashboard</a>
  </nav>
</header>
 
<div class="container">
 
  <div class="wallet-bar">
    <label>👛 Wallet:</label>
    <select id="wallet-select">
      <option value="">⏳ Memuat...</option>
    </select>
  </div>
 
  <div class="stats-grid">
    <div class="stat-card saldo">
      <div class="stat-label">💰 Saldo</div>
      <div class="stat-value" id="stat-saldo">–</div>
    </div>
    <div class="stat-card masuk">
      <div class="stat-label">📈 Total Masuk</div>
      <div class="stat-value" id="stat-masuk">–</div>
    </div>
    <div class="stat-card keluar">
      <div class="stat-label">📉 Total Keluar</div>
      <div class="stat-value" id="stat-keluar">–</div>
    </div>
  </div>
 
  <div class="chart-card">
    <div class="section-title">📅 Pemasukan vs Pengeluaran — 30 Hari Terakhir</div>
    <div class="chart-wrap"><canvas id="myChart"></canvas></div>
  </div>
 
  <div class="kategori-card">
    <div class="section-title">📊 Kategori Bulan Ini</div>
    <div class="kat-grid" id="kat-container">
      <div class="empty">Pilih wallet untuk lihat kategori</div>
    </div>
  </div>
 
  <div class="goals-section-title">🎯 Target Tabungan</div>
  <div class="goals-grid" id="goals-container">
    <div class="empty">Pilih wallet untuk lihat target tabungan</div>
  </div>
 
  <div class="txn-card">
    <div class="section-title">🕐 Transaksi Terakhir</div>
    <ul class="txn-list" id="txn-list">
      <li class="empty">Pilih wallet untuk lihat transaksi</li>
    </ul>
  </div>
 
</div>
 
<script>
  function formatRp(amount) {
    return 'Rp ' + Math.abs(amount).toLocaleString('id-ID');
  }
 
  let chartInstance = null;
 
  function renderChart(chartData) {
    const ctx = document.getElementById('myChart').getContext('2d');
 
    // Build keyed map from server data
    const masukMap = {}, keluarMap = {};
    chartData.forEach(d => { masukMap[d.date] = d.masuk; keluarMap[d.date] = d.keluar; });
 
    // Generate last 30 days
    const labels = [], masukVals = [], keluarVals = [];
    for (let i = 29; i >= 0; i--) {
      const d = new Date();
      d.setDate(d.getDate() - i);
      const key = d.toISOString().slice(0, 10);
      labels.push(key.slice(5).replace('-', '/'));  // MM/DD
      masukVals.push(masukMap[key] || 0);
      keluarVals.push(keluarMap[key] || 0);
    }
 
    if (chartInstance) chartInstance.destroy();
    chartInstance = new Chart(ctx, {
      type: 'bar',
      data: {
        labels,
        datasets: [
          { label: 'Masuk',  data: masukVals,  backgroundColor: 'rgba(22,163,74,0.75)',  borderRadius: 4 },
          { label: 'Keluar', data: keluarVals, backgroundColor: 'rgba(220,38,38,0.70)', borderRadius: 4 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { position: 'top', labels: { font: { size: 11 }, boxWidth: 12 } },
          tooltip: {
            callbacks: {
              label: (c) => c.dataset.label + ': ' + formatRp(c.parsed.y),
            },
          },
        },
        scales: {
          x: { grid: { display: false }, ticks: { maxRotation: 45, font: { size: 9 } } },
          y: {
            grid: { color: 'rgba(0,0,0,0.04)' },
            ticks: {
              font: { size: 10 },
              callback: (v) => {
                if (v >= 1_000_000) return (v/1_000_000).toFixed(1) + 'jt';
                if (v >= 1_000)     return (v/1_000).toFixed(0) + 'rb';
                return v;
              },
            },
          },
        },
      },
    });
  }
 
  function renderGoals(goals) {
    const el = document.getElementById('goals-container');
    if (!goals.length) {
      el.innerHTML = '<div class="empty">Belum ada target tabungan.<br>Gunakan /target buat NamaGoal Jumlah di bot.</div>';
      return;
    }
    el.innerHTML = goals.map(g => {
      const done = g.persen >= 100;
      return \`<div class="goal-card">
        <div class="goal-name">\${g.name}</div>
        <div class="goal-amounts">\${formatRp(g.current_amount)} / \${formatRp(g.target_amount)}</div>
        <div class="progress-bg">
          <div class="progress-fill \${done ? 'done' : ''}" style="width:\${g.persen}%"></div>
        </div>
        <div class="goal-meta">
          <span>\${g.persen}% tercapai\${done ? ' 🎉' : ''}</span>
          \${g.deadline ? '<span>⏰ ' + g.deadline + '</span>' : ''}
        </div>
      </div>\`;
    }).join('');
  }
 
  const KAT_ICON = {
    makan:'🍽️', transport:'🚗', belanja:'🛍️', tagihan:'💡',
    hiburan:'🎮', kesehatan:'🏥', gaji:'💼', bonus:'🎁',
    transfer:'💸', umum:'📌',
  };
 
  function renderKategori(kategori) {
    const el = document.getElementById('kat-container');
    const keluar = kategori.filter(r => r.type === 'out').sort((a,b) => b.total - a.total);
    const masuk  = kategori.filter(r => r.type === 'in').sort((a,b) => b.total - a.total);
    const totalKeluar = keluar.reduce((s,r) => s + r.total, 0);
    const totalMasuk  = masuk.reduce((s,r) => s + r.total, 0);
 
    if (!keluar.length && !masuk.length) {
      el.innerHTML = '<div class="empty" style="grid-column:1/-1">Belum ada transaksi bulan ini.</div>';
      return;
    }
 
    let html = '';
    if (keluar.length) {
      html += \`<div>
        <div class="kat-group-title out">📉 Pengeluaran</div>
        \${keluar.map(r => {
          const persen = totalKeluar > 0 ? Math.round((r.total / totalKeluar) * 100) : 0;
          const icon = KAT_ICON[r.category] || '📌';
          return \`<div class="kat-row">
            <div class="kat-row-top">
              <span class="kat-name">\${icon} \${r.category}</span>
              <span class="kat-amount">\${formatRp(r.total)}</span>
            </div>
            <div class="kat-bar-bg"><div class="kat-bar-fill out" style="width:\${persen}%"></div></div>
            <div class="kat-count">\${r.jumlah}x · \${persen}%</div>
          </div>\`;
        }).join('')}
      </div>\`;
    }
    if (masuk.length) {
      html += \`<div>
        <div class="kat-group-title in">📈 Pemasukan</div>
        \${masuk.map(r => {
          const persen = totalMasuk > 0 ? Math.round((r.total / totalMasuk) * 100) : 0;
          const icon = KAT_ICON[r.category] || '📌';
          return \`<div class="kat-row">
            <div class="kat-row-top">
              <span class="kat-name">\${icon} \${r.category}</span>
              <span class="kat-amount">\${formatRp(r.total)}</span>
            </div>
            <div class="kat-bar-bg"><div class="kat-bar-fill in" style="width:\${persen}%"></div></div>
            <div class="kat-count">\${r.jumlah}x · \${persen}%</div>
          </div>\`;
        }).join('')}
      </div>\`;
    }
    el.innerHTML = html;
  }
 
  function renderTransactions(recent) {
    const el = document.getElementById('txn-list');
    if (!recent.length) {
      el.innerHTML = '<li class="empty">Belum ada transaksi.</li>';
      return;
    }
    el.innerHTML = recent.map(t => {
      const isIn = t.type === 'in';
      return \`<li class="txn-item">
        <div class="txn-left">
          <div class="txn-icon \${t.type}">\${isIn ? '📈' : '📉'}</div>
          <div>
            <div class="txn-note">\${t.note || (isIn ? 'Pemasukan' : 'Pengeluaran')}<span class="txn-id">#\${t.id}</span></div>
            <div class="txn-date">\${t.date}</div>
          </div>
        </div>
        <div class="txn-amount \${t.type}">\${isIn ? '+' : '-'}\${formatRp(t.amount)}</div>
      </li>\`;
    }).join('');
  }
 
  async function loadDashboard(walletId) {
    document.getElementById('stat-saldo').textContent  = '...';
    document.getElementById('stat-masuk').textContent  = '...';
    document.getElementById('stat-keluar').textContent = '...';
    try {
      const res  = await fetch('/api/dashboard?wallet=' + encodeURIComponent(walletId));
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      document.getElementById('stat-saldo').textContent  = formatRp(data.saldo);
      document.getElementById('stat-masuk').textContent  = formatRp(data.total_masuk);
      document.getElementById('stat-keluar').textContent = formatRp(data.total_keluar);
      renderChart(data.chartData);
      renderKategori(data.kategori || []);
      renderGoals(data.goals);
      renderTransactions(data.recent);
    } catch (err) {
      document.getElementById('stat-saldo').textContent = 'Error';
      console.error(err);
    }
  }
 
  async function init() {
    try {
      const res     = await fetch('/api/wallets');
      const wallets = await res.json();
      const sel     = document.getElementById('wallet-select');
      if (!wallets.length) {
        sel.innerHTML = '<option value="">Belum ada wallet terdaftar</option>';
        return;
      }
      sel.innerHTML = wallets.map(w => {
        const icon = w.platform === 'telegram' ? '✈️' : '💬';
        return \`<option value="\${w.id}">\${icon} \${w.name || w.id} — \${formatRp(w.saldo)}</option>\`;
      }).join('');
      loadDashboard(wallets[0].id);
      sel.addEventListener('change', () => { if (sel.value) loadDashboard(sel.value); });
    } catch (err) {
      document.getElementById('wallet-select').innerHTML = '<option>Gagal memuat wallet</option>';
      console.error(err);
    }
  }
 
  init();
</script>
</body>
</html>`;
 
// ─── HTTP Server ──────────────────────────────────────────
 
function startQRServer(port) {
  server = http.createServer((req, res) => {
    const parsed   = new URL(req.url, 'http://localhost');
    const pathname = parsed.pathname;
 
    // /api/qr
    if (pathname === '/api/qr') {
      res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-cache' });
      res.end(JSON.stringify({ qr: currentQR, connected: isConnected }));
      return;
    }
 
    // /api/wallets
    if (pathname === '/api/wallets') {
      try {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(getAllWallets()));
      } catch (err) {
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: err.message }));
      }
      return;
    }
 
    // /api/dashboard?wallet=xxx
    if (pathname === '/api/dashboard') {
      const walletId = parsed.searchParams.get('wallet');
      if (!walletId) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'wallet param wajib ada' }));
        return;
      }
      try {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(getWalletDashboard(walletId)));
      } catch (err) {
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: err.message }));
      }
      return;
    }
 
    // /dashboard
    if (pathname === '/dashboard') {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end(DASHBOARD_HTML);
      return;
    }
 
    // Default → QR page
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(QR_HTML);
  });
 
  server.listen(port, '0.0.0.0', () => {
    console.log(`🌐 QR Server aktif di port ${port}`);
    console.log(`   Dashboard: [Railway URL]/dashboard`);
  });
}
 
module.exports = { startQRServer, setQR, clearQR };
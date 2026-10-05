const http = require('http');

let currentQR = null;
let isConnected = false;
let server = null;

/**
 * Simpan QR code baru (dipanggil dari WA bot saat QR digenerate)
 */
function setQR(qrData) {
  currentQR = qrData;
  isConnected = false;
}

/**
 * Hapus QR — dipanggil saat sudah terhubung
 */
function clearQR() {
  currentQR = null;
  isConnected = true;
}

/**
 * Mulai HTTP server yang serve QR code sebagai halaman web
 */
function startQRServer(port) {
  const HTML = `<!DOCTYPE html>
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
      background: #f7f7f7;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }
    .card {
      background: white;
      border-radius: 16px;
      padding: 32px 40px;
      text-align: center;
      box-shadow: 0 4px 24px rgba(0,0,0,0.10);
      max-width: 380px;
      width: 100%;
    }
    h1 { font-size: 1.4rem; color: #111; margin-bottom: 4px; }
    .subtitle { color: #888; font-size: 0.9rem; margin-bottom: 24px; }
    .status {
      display: inline-block;
      padding: 8px 18px;
      border-radius: 999px;
      font-size: 0.9rem;
      font-weight: 600;
      margin-bottom: 20px;
    }
    .waiting  { background: #fff3cd; color: #92680a; }
    .scanning { background: #e0f7e9; color: #1a7d3a; }
    .done     { background: #d4edda; color: #155724; }
    #qr-wrap {
      display: flex;
      justify-content: center;
      min-height: 180px;
      align-items: center;
      margin-bottom: 16px;
    }
    #qrcode canvas, #qrcode img { border-radius: 8px; }
    .hint { color: #666; font-size: 0.82rem; line-height: 1.5; }
    .loader {
      width: 44px; height: 44px;
      border: 4px solid #eee;
      border-top-color: #25D366;
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    .refresh { color: #aaa; font-size: 0.75rem; margin-top: 14px; }
  </style>
</head>
<body>
  <div class="card">
    <h1>💰 Money Bot</h1>
    <p class="subtitle">WhatsApp Setup</p>

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
          document.getElementById('hint').textContent = 'Bot sudah aktif dan siap digunakan di grup WhatsApp kamu!';
          document.getElementById('loader').style.display = 'none';
          document.getElementById('qrcode').style.display = 'none';
          document.getElementById('refresh-note').textContent = '';
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
              text: data.qr,
              width: 220,
              height: 220,
              colorDark: '#000000',
              colorLight: '#ffffff',
            });
          } else {
            qrInstance.clear();
            qrInstance.makeCode(data.qr);
          }
        }

        const now = new Date().toLocaleTimeString('id-ID');
        document.getElementById('refresh-note').textContent = 'Terakhir dicek: ' + now;
      } catch (e) {
        document.getElementById('refresh-note').textContent = 'Reconnecting...';
      }
    }

    poll();
    const timer = setInterval(poll, 3000);
  </script>
</body>
</html>`;

  server = http.createServer((req, res) => {
    if (req.url === '/api/qr') {
      res.writeHead(200, {
        'Content-Type': 'application/json',
        'Cache-Control': 'no-cache',
      });
      res.end(JSON.stringify({ qr: currentQR, connected: isConnected }));
      return;
    }

    // Semua path lain → HTML
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(HTML);
  });

  server.listen(port, '0.0.0.0', () => {
    console.log(`🌐 QR Server aktif di port ${port}`);
    console.log(`   Buka URL Railway kamu untuk scan QR WhatsApp`);
  });
}

module.exports = { startQRServer, setQR, clearQR };

// ─── OCR Struk / Bon ─────────────────────────────────────
// Pakai OCR.space API (free, no native deps) → extract jumlah + catatan

const https = require('https');

const OCR_API_KEY = process.env.OCR_API_KEY || 'helloworld'; // free tier: 500 calls/month

/**
 * Kirim image buffer ke OCR.space → return teks hasil OCR
 * @param {Buffer} imageBuffer
 * @param {string} [mimeType='image/jpeg']
 * @returns {Promise<string>} - raw OCR text
 */
function ocrImage(imageBuffer, mimeType = 'image/jpeg') {
  return new Promise((resolve, reject) => {
    const base64 = imageBuffer.toString('base64');
    const dataUrl = `data:${mimeType};base64,${base64}`;

    const body = new URLSearchParams({
      apikey:        OCR_API_KEY,
      base64Image:   dataUrl,
      language:      'ind',     // Bahasa Indonesia + angka
      isOverlayRequired: 'false',
      detectOrientation: 'true',
      scale:         'true',
      OCREngine:     '2',       // Engine 2 lebih akurat untuk struk
    }).toString();

    const options = {
      hostname: 'api.ocr.space',
      path:     '/parse/image',
      method:   'POST',
      headers: {
        'Content-Type':   'application/x-www-form-urlencoded',
        'Content-Length': Buffer.byteLength(body),
      },
      timeout: 20000,
    };

    const req = https.request(options, (res) => {
      const chunks = [];
      res.on('data', c => chunks.push(c));
      res.on('end', () => {
        try {
          const json = JSON.parse(Buffer.concat(chunks).toString());
          if (json.IsErroredOnProcessing) {
            reject(new Error('OCR error: ' + (json.ErrorMessage?.[0] || 'unknown')));
          } else {
            const text = json.ParsedResults?.[0]?.ParsedText || '';
            resolve(text);
          }
        } catch (e) {
          reject(new Error('OCR parse error: ' + e.message));
        }
      });
    });
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(); reject(new Error('OCR timeout')); });
    req.write(body);
    req.end();
  });
}

/**
 * Parse teks OCR → cari total/jumlah bayar terbesar dan baris deskripsi
 * @param {string} text - raw OCR text
 * @returns {{ jumlah: number|null, catatan: string }}
 */
function parseStruk(text) {
  if (!text?.trim()) return { jumlah: null, catatan: '' };

  const lines = text.split(/\r?\n/).map(l => l.trim()).filter(Boolean);

  // ── Cari jumlah uang ──────────────────────────────────────
  // Pattern angka: 150.000 / 150,000 / Rp 150000 / Total 150.000
  // Prioritas: baris dengan kata kunci "total" / "bayar" / "grand total"
  const priorityKw = /\b(total|grand total|bayar|payment|amount|jumlah|tagihan|harga)\b/i;
  const amountRe   = /(?:rp\.?\s*)?(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d{4,})/gi;

  let bestAmount = null;
  let bestLine   = '';

  // Pass 1: baris priority keyword
  for (const line of lines) {
    if (!priorityKw.test(line)) continue;
    const nums = [...line.matchAll(amountRe)].map(m => parseAmount(m[1]));
    if (nums.length) {
      const max = Math.max(...nums);
      if (!bestAmount || max > bestAmount) {
        bestAmount = max;
        bestLine   = line;
      }
    }
  }

  // Pass 2: ambil angka terbesar dari seluruh teks jika pass 1 gagal
  if (!bestAmount) {
    const allNums = [...text.matchAll(amountRe)].map(m => parseAmount(m[1]));
    if (allNums.length) bestAmount = Math.max(...allNums);
  }

  // ── Cari catatan deskripsi ────────────────────────────────
  // Ambil baris pertama non-kosong yang bukan angka murni sebagai catatan,
  // atau nama toko dari baris teratas struk
  const catatan = guessCatatan(lines, bestLine);

  return { jumlah: bestAmount, catatan };
}

/**
 * Konversi string angka (pakai titik/koma) ke number
 */
function parseAmount(str) {
  // "150.000" atau "150,000" → 150000
  // "1.500.000" → 1500000
  // "150.000,50" → 150000
  const s = str.replace(/[,.](\d{2})$/, '') // buang desimal
               .replace(/[.,]/g, '');        // buang separator
  return parseInt(s, 10) || 0;
}

/**
 * Tebak catatan dari baris struk
 */
function guessCatatan(lines, totalLine) {
  // Nama toko biasanya di baris atas
  const skipRe = /^\d[\d\s.,]*$|^rp|struk|bon|nota|receipt|invoice|kasir|cashier|tax|pajak|ppn|service/i;
  for (const line of lines) {
    if (line === totalLine) continue;
    if (skipRe.test(line)) continue;
    if (line.length < 3) continue;
    // Jika mengandung huruf → cocok sebagai catatan
    if (/[a-zA-Z]/.test(line)) {
      return line.slice(0, 80); // max 80 char
    }
  }
  return 'Struk belanja';
}

module.exports = { ocrImage, parseStruk };

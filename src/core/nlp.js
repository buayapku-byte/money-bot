// ─── NLP Parser ───────────────────────────────────────────
// Parse pesan biasa jadi transaksi tanpa command/prefix
// "makan siang 35rb"  → { type: 'out', amount: 35000, note: 'makan siang' }
// "gaji 5jt"          → { type: 'in',  amount: 5000000, note: 'gaji' }

// Kata-kata yang menandakan pemasukan
const INCOME_KEYWORDS = [
  'gaji', 'salary', 'dapat', 'terima', 'diterima', 'pendapatan', 'pemasukan',
  'bonus', 'thr', 'upah', 'honor', 'komisi', 'dividen', 'profit',
  'untung', 'hasil', 'income', 'fee', 'bayaran', 'transfer masuk',
  'cashback', 'refund', 'kembali', 'kembalian', 'jual', 'laku',
];

// Multiplier shorthand
const MULTIPLIERS = {
  rb: 1_000, ribu: 1_000,
  jt: 1_000_000, juta: 1_000_000,
  k: 1_000, m: 1_000_000,
};

// Pesan yang BUKAN transaksi — jangan parse
const IGNORE_RE = /^(oke|ok|ya|yep|yap|sip|siap|halo|hai|hi|hey|thanks|thx|makasih|mantap|done|selesai|test|coba|ping)/i;

/**
 * Parse teks natural language → data transaksi
 * @param {string} text - pesan dari user
 * @returns {{ type: 'in'|'out', amount: number, note: string } | null}
 */
function parseNLP(text) {
  if (!text) return null;
  const s = text.trim();

  // Abaikan pesan pendek / sapaan / satu kata
  if (IGNORE_RE.test(s)) return null;
  if (s.split(/\s+/).length < 2) return null; // minimal 2 kata

  // ── Cari jumlah uang ──────────────────────────────────────
  // Priority 1: angka + multiplier (mis. "35rb", "1.5jt", "5k")
  const mulRe = /(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?|\d+)\s*(rb|ribu|jt|juta|k|m)\b/i;
  // Priority 2: angka polos ≥ 1000 (mis. "35000", "150.000")
  const plainRe = /\b(\d{1,3}(?:[.,]\d{3})+|\d{4,})\b/;

  let amount   = null;
  let matchStr = '';

  const mulMatch = s.match(mulRe);
  if (mulMatch) {
    const rawNum = mulMatch[1].replace(/[.,]/g, '');
    const mul    = MULTIPLIERS[mulMatch[2].toLowerCase()] || 1;
    amount    = parseInt(rawNum) * mul;
    matchStr  = mulMatch[0];
  } else {
    const plainMatch = s.match(plainRe);
    if (plainMatch) {
      amount   = parseInt(plainMatch[1].replace(/[.,]/g, ''), 10);
      matchStr = plainMatch[0];
    }
  }

  // Tidak ada angka yang valid
  if (!amount || amount < 100) return null;

  // ── Ambil catatan (sisa teks) ─────────────────────────────
  const note = s.replace(matchStr, '').replace(/\s+/g, ' ').trim();
  if (!note || note.length < 2) return null; // harus ada keterangan

  // ── Tentukan type: masuk atau keluar ──────────────────────
  const lower    = note.toLowerCase();
  const isIncome = INCOME_KEYWORDS.some(kw => lower.includes(kw));

  return {
    type:   isIncome ? 'in' : 'out',
    amount,
    note:   note.slice(0, 100),
  };
}

module.exports = { parseNLP };

"""
NLP Parser — parse pesan natural language jadi data transaksi.
"makan siang 35rb"  → { type: 'out', amount: 35000, note: 'makan siang' }
"gaji 5jt"          → { type: 'in',  amount: 5000000, note: 'gaji' }
"""
import re
from typing import Optional

# Kata-kata yang menandakan pemasukan
INCOME_KEYWORDS = [
    'gaji', 'salary', 'dapat', 'terima', 'diterima', 'pendapatan', 'pemasukan',
    'bonus', 'thr', 'upah', 'honor', 'komisi', 'dividen', 'profit',
    'untung', 'hasil', 'income', 'fee', 'bayaran', 'transfer masuk',
    'cashback', 'refund', 'kembali', 'kembalian', 'jual', 'laku',
]

# Multiplier shorthand
MULTIPLIERS = {
    'rb': 1_000, 'ribu': 1_000,
    'jt': 1_000_000, 'juta': 1_000_000,
    'k': 1_000, 'm': 1_000_000,
}

# Pesan yang BUKAN transaksi — jangan parse
IGNORE_RE = re.compile(
    r'^(oke|ok|ya|yep|yap|sip|siap|halo|hai|hi|hey|thanks|thx|makasih|mantap|done|selesai|test|coba|ping)',
    re.IGNORECASE
)

# Priority 1: angka + multiplier (mis. "35rb", "1.5jt", "5k")
MUL_RE = re.compile(
    r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?|\d+)\s*(rb|ribu|jt|juta|k|m)\b',
    re.IGNORECASE
)
# Priority 2: angka polos ≥ 1000 (mis. "35000", "150.000")
PLAIN_RE = re.compile(r'\b(\d{1,3}(?:[.,]\d{3})+|\d{4,})\b')


def parse_nlp(text: str) -> Optional[dict]:
    """
    Parse teks natural language → data transaksi.
    Returns: { type: 'in'|'out', amount: int, note: str } or None
    """
    if not text:
        return None
    s = text.strip()

    # Abaikan pesan pendek / sapaan / satu kata
    if IGNORE_RE.match(s):
        return None
    if len(s.split()) < 2:  # minimal 2 kata
        return None

    # ── Cari jumlah uang ──────────────────────────────────────
    amount = None
    match_str = ''

    mul_match = MUL_RE.search(s)
    if mul_match:
        raw_num = mul_match.group(1).replace(',', '').replace('.', '')
        mul = MULTIPLIERS.get(mul_match.group(2).lower(), 1)
        amount = int(raw_num) * mul
        match_str = mul_match.group(0)
    else:
        plain_match = PLAIN_RE.search(s)
        if plain_match:
            amount = int(plain_match.group(1).replace(',', '').replace('.', ''))
            match_str = plain_match.group(0)

    # Tidak ada angka yang valid
    if not amount or amount < 100:
        return None

    # ── Ambil catatan (sisa teks) ─────────────────────────────
    note = re.sub(re.escape(match_str), '', s, count=1)
    note = re.sub(r'\s+', ' ', note).strip()
    if not note or len(note) < 2:
        return None  # harus ada keterangan

    # ── Tentukan type: masuk atau keluar ──────────────────────
    lower = note.lower()
    is_income = any(kw in lower for kw in INCOME_KEYWORDS)

    return {
        'type': 'in' if is_income else 'out',
        'amount': amount,
        'note': note[:100],
    }

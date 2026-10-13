"""
ocr.py — Scan struk / receipt via OCR (pytesseract + Pillow).
Graceful fallback jika Tesseract tidak terinstall.
"""
import re
import io
from typing import Optional

# Coba import pytesseract; fallback jika tidak tersedia
try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

from src.core.finance import detect_category

# ─── Regex patterns untuk ekstraksi data struk ────────────────

# Pola nominal — cocok dengan: 15.000, Rp15.000, 1.500.000, 15rb, 1jt, dll.
_NOMINAL_PATTERNS = [
    # Total / Grand Total
    re.compile(
        r'(?:total|grand\s+total|jumlah|bayar|pembayaran|charge|amount)\s*[:\-]?\s*'
        r'(?:Rp\.?\s*)?([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{2})?)',
        re.IGNORECASE
    ),
    # Nominal standalone besar (>= 4 digit, format ribuan)
    re.compile(
        r'(?:Rp\.?\s*)([0-9]{1,3}(?:[.,][0-9]{3})+)',
        re.IGNORECASE
    ),
]

# Pola merchant / nama toko untuk deteksi kategori
_MERCHANT_PATTERNS = [
    re.compile(r'^([A-Z][A-Za-z0-9\s&\'\-]{3,40})$', re.MULTILINE),
]

# Kata kunci tanggal
_DATE_PATTERN = re.compile(
    r'(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2,4})'
)


def _parse_nominal_str(s: str) -> Optional[float]:
    """Parse '15.000' atau '1,500,000' atau '1.500.000' → float."""
    s = s.strip()
    # Ambiguous: 1.500 bisa 1500 (ID) atau 1.5 (EN)
    # Heuristic: jika digit setelah titik/koma tepat 3 → ribuan
    # Jika digit setelah titik/koma 1-2 → desimal
    # Hapus titik/koma pemisah ribuan
    cleaned = s.replace('.', '').replace(',', '')
    try:
        val = float(cleaned)
        return val if val > 0 else None
    except ValueError:
        return None


def extract_text_from_image(image_bytes: bytes) -> str:
    """Jalankan OCR pada bytes gambar. Return teks mentah."""
    if not OCR_AVAILABLE:
        raise RuntimeError('pytesseract/Pillow belum terinstall')

    img = Image.open(io.BytesIO(image_bytes))

    # Preprocessing ringan: convert ke grayscale
    if img.mode != 'L':
        img = img.convert('L')

    # Tesseract config: PSM 6 = satu blok teks seragam (cocok untuk struk)
    custom_config = r'--oem 3 --psm 6 -l ind+eng'
    text = pytesseract.image_to_string(img, config=custom_config)
    return text


def parse_receipt(text: str) -> dict:
    """
    Parse teks struk OCR → dict:
      amount: float | None
      category: str
      note: str
      raw_lines: list[str]
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    amount = None
    # Coba pola "Total" dulu
    for pat in _NOMINAL_PATTERNS:
        for line in lines:
            m = pat.search(line)
            if m:
                val = _parse_nominal_str(m.group(1))
                if val and val >= 1000:  # minimum 1000 rupiah
                    amount = val
                    break
        if amount:
            break

    # Jika tidak ada, ambil nominal terbesar yang ditemukan
    if not amount:
        candidates = []
        for line in lines:
            for m in re.finditer(r'(?:Rp\.?\s*)?([0-9]{1,3}(?:[.,][0-9]{3})+)', line, re.IGNORECASE):
                val = _parse_nominal_str(m.group(1))
                if val and val >= 1000:
                    candidates.append(val)
        if candidates:
            amount = max(candidates)

    # Deteksi merchant/nama dari 3 baris pertama non-kosong
    merchant_hint = ' '.join(lines[:3]) if lines else ''
    category = detect_category(merchant_hint)

    # Buat catatan singkat dari baris terbaik
    note_candidates = [ln for ln in lines[:5] if len(ln) > 3 and not re.match(r'^[\d\s\.\,\:\-]+$', ln)]
    note = note_candidates[0] if note_candidates else 'struk'

    return {
        'amount':     amount,
        'category':   category,
        'note':       note[:60],  # potong panjang
        'raw_lines':  lines[:20],
    }


def scan_receipt(image_bytes: bytes) -> dict:
    """
    Gabungan: OCR + parse.
    Returns: {'amount', 'category', 'note', 'raw_lines', 'raw_text'}
    Raises RuntimeError jika OCR tidak tersedia.
    """
    raw_text = extract_text_from_image(image_bytes)
    result   = parse_receipt(raw_text)
    result['raw_text'] = raw_text
    return result

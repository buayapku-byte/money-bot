"""
csv_import.py — Import mutasi rekening dari CSV bank.
Support: BCA, Mandiri, BNI, BRI (format umum).
"""
import csv
import io
import re
from datetime import datetime
from typing import Optional

from src.core.finance import add_transaction, detect_category

# ─── Format Deteksi ───────────────────────────────────────────

def _clean_amount(s: str) -> Optional[float]:
    """'1.500.000,00' atau '1,500,000.00' atau '1.500.000' → 1500000.0"""
    if not s:
        return None
    s = s.strip().replace(' ', '').replace('"', '')
    # Hapus prefix Rp / Cr / Dr (tapi jangan hapus digit)
    s = re.sub(r'^[RrpPCcDd]+', '', s).strip()
    s = re.sub(r'[CcDd][Rr]$', '', s).strip()

    # Tentukan apakah titik atau koma adalah desimal
    # Heuristik:
    # - Jika ada koma diikuti 1-2 digit di akhir → koma = desimal (ID format: 1.500.000,00)
    # - Jika ada titik diikuti 1-2 digit di akhir → titik = desimal (EN format: 1,500,000.00)
    # - Jika hanya ada titik(s) dengan 3 digit setelahnya → titik = pemisah ribuan (1.500.000)

    if re.search(r',\d{1,2}$', s):
        # Indonesian: 1.500.000,00 → remove dots (thousands), replace comma with dot (decimal)
        s = s.replace('.', '').replace(',', '.')
    elif re.search(r'\.\d{1,2}$', s):
        # English: 1,500,000.00 → remove commas (thousands)
        s = s.replace(',', '')
    else:
        # No decimal → remove both dots and commas as thousands separators
        s = s.replace('.', '').replace(',', '')

    try:
        val = float(s)
        return val if val > 0 else None
    except ValueError:
        return None


def _parse_date(s: str) -> Optional[str]:
    """Parse berbagai format tanggal → 'YYYY-MM-DD'."""
    s = s.strip()
    fmts = [
        '%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d',
        '%d %b %Y', '%d %B %Y',
        '%d/%m/%y', '%d-%m-%y',
    ]
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None


# ─── Parser per bank ──────────────────────────────────────────

def _detect_bank_format(headers: list[str]) -> str:
    """Deteksi bank dari nama kolom header."""
    h = [col.lower().strip() for col in headers]
    joined = ' '.join(h)

    if 'keterangan' in joined and ('debit' in joined or 'kredit' in joined):
        return 'bca'
    if 'transaksi' in joined and ('nominal' in joined or 'mutasi' in joined):
        return 'mandiri'
    if 'kode' in joined and 'nominal' in joined:
        return 'bni'
    if 'uraian' in joined and ('debet' in joined or 'kredit' in joined):
        return 'bri'
    return 'generic'


def _parse_row_bca(row: dict) -> Optional[dict]:
    keys = {k.lower().strip(): v for k, v in row.items()}
    tanggal_raw = keys.get('tanggal', '') or keys.get('date', '')
    keterangan  = keys.get('keterangan', '') or keys.get('description', '')
    debit_raw   = keys.get('debit', '') or keys.get('mutasi debet', '')
    kredit_raw  = keys.get('kredit', '') or keys.get('mutasi kredit', '')

    tanggal = _parse_date(tanggal_raw)
    if not tanggal:
        return None

    debit  = _clean_amount(debit_raw)
    kredit = _clean_amount(kredit_raw)

    if debit and debit > 0:
        return {'date': tanggal, 'type': 'out', 'amount': debit, 'note': keterangan.strip()}
    if kredit and kredit > 0:
        return {'date': tanggal, 'type': 'in', 'amount': kredit, 'note': keterangan.strip()}
    return None


def _parse_row_mandiri(row: dict) -> Optional[dict]:
    keys = {k.lower().strip(): v for k, v in row.items()}
    tanggal_raw = keys.get('tanggal', '') or keys.get('date', '')
    keterangan  = keys.get('keterangan', '') or keys.get('transaksi', '')
    debit_raw   = keys.get('debit', '') or keys.get('nominal debet', '')
    kredit_raw  = keys.get('kredit', '') or keys.get('nominal kredit', '')

    tanggal = _parse_date(tanggal_raw)
    if not tanggal:
        return None

    debit  = _clean_amount(debit_raw)
    kredit = _clean_amount(kredit_raw)

    if debit and debit > 0:
        return {'date': tanggal, 'type': 'out', 'amount': debit, 'note': keterangan.strip()}
    if kredit and kredit > 0:
        return {'date': tanggal, 'type': 'in', 'amount': kredit, 'note': keterangan.strip()}
    return None


def _parse_row_generic(row: dict) -> Optional[dict]:
    """Fallback: coba tebak kolom mana yang tanggal, keterangan, debit/kredit."""
    keys = {k.lower().strip(): v for k, v in row.items()}

    # Cari tanggal
    tanggal = None
    for k in ['tanggal', 'date', 'tgl', 'waktu', 'time']:
        if k in keys:
            tanggal = _parse_date(keys[k])
            if tanggal:
                break
    if not tanggal:
        return None

    # Cari keterangan
    note = ''
    for k in ['keterangan', 'description', 'desc', 'uraian', 'remark', 'narasi']:
        if k in keys and keys[k]:
            note = keys[k].strip()
            break

    # Cari debit/kredit
    debit = None
    for k in ['debit', 'debet', 'dr', 'keluar']:
        if k in keys:
            debit = _clean_amount(keys[k])
            if debit:
                break

    kredit = None
    for k in ['kredit', 'kredit', 'cr', 'masuk']:
        if k in keys:
            kredit = _clean_amount(keys[k])
            if kredit:
                break

    # Cek kolom 'jumlah' + 'jenis'
    if not debit and not kredit:
        jml = _clean_amount(keys.get('jumlah', '') or keys.get('amount', '') or keys.get('nominal', ''))
        jenis = (keys.get('jenis', '') or keys.get('type', '') or '').lower()
        if jml:
            if 'kredit' in jenis or 'cr' in jenis or 'masuk' in jenis or 'in' in jenis:
                kredit = jml
            else:
                debit = jml

    if debit and debit > 0:
        return {'date': tanggal, 'type': 'out', 'amount': debit, 'note': note}
    if kredit and kredit > 0:
        return {'date': tanggal, 'type': 'in', 'amount': kredit, 'note': note}
    return None


# ─── Main import function ──────────────────────────────────────

def import_csv_mutasi(wallet_id: str, csv_bytes: bytes, created_by: str = 'csv-import') -> dict:
    """
    Parse CSV mutasi rekening dan masukkan ke database.

    Returns:
      {
        'imported': int,     # jumlah transaksi berhasil
        'skipped':  int,     # baris yang gagal/tidak valid
        'errors':   list,    # pesan error per baris
        'bank':     str,     # bank terdeteksi
      }
    """
    # Decode bytes — coba UTF-8, fallback ke latin-1
    try:
        text = csv_bytes.decode('utf-8-sig')  # utf-8 with BOM
    except UnicodeDecodeError:
        text = csv_bytes.decode('latin-1')

    # Cari baris header (skip baris kosong / header informasi di atas)
    lines = text.splitlines()
    header_idx = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        # Cari baris yang punya >= 3 kolom dan mengandung kata kunci
        cols = [c.strip().lower() for c in stripped.split(',')]
        if len(cols) >= 3 and any(k in cols for k in ['tanggal', 'date', 'tgl', 'keterangan', 'debit', 'kredit']):
            header_idx = i
            break

    data_text = '\n'.join(lines[header_idx:])
    reader = csv.DictReader(io.StringIO(data_text))

    if not reader.fieldnames:
        raise ValueError('Tidak bisa membaca header CSV. Pastikan format CSV benar.')

    bank = _detect_bank_format(list(reader.fieldnames))

    # Pilih parser
    parsers = {
        'bca':     _parse_row_bca,
        'mandiri': _parse_row_mandiri,
        'bni':     _parse_row_generic,
        'bri':     _parse_row_generic,
        'generic': _parse_row_generic,
    }
    parser = parsers.get(bank, _parse_row_generic)

    imported = 0
    skipped  = 0
    errors   = []

    for i, row in enumerate(reader, start=header_idx + 2):
        try:
            parsed = parser(row)
            if not parsed:
                skipped += 1
                continue
            if not parsed.get('amount') or parsed['amount'] <= 0:
                skipped += 1
                continue

            category = detect_category(parsed.get('note', ''))
            add_transaction(
                wallet_id  = wallet_id,
                type_      = parsed['type'],
                amount     = parsed['amount'],
                note       = parsed.get('note', '')[:100],
                category   = category,
                created_by = created_by,
            )

            # Override tanggal langsung ke DB jika berbeda dari hari ini
            if parsed.get('date'):
                from src.core.database import get_db
                db = get_db()
                db.execute(
                    "UPDATE transactions SET date=? WHERE wallet_id=? AND created_by=? "
                    "ORDER BY id DESC LIMIT 1",
                    (parsed['date'], wallet_id, created_by)
                )
                db.commit()

            imported += 1
        except Exception as e:
            errors.append(f'Baris {i}: {e}')
            skipped += 1

    return {
        'imported': imported,
        'skipped':  skipped,
        'errors':   errors[:10],  # max 10 error ditampilkan
        'bank':     bank.upper(),
    }

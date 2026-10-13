"""
pdf_report.py — Generate laporan PDF bulanan menggunakan fpdf2.
Graceful fallback dengan pesan error jika fpdf2 tidak terinstall.
"""
import io
from datetime import datetime
from typing import Optional

try:
    from fpdf import FPDF
    FPDF_AVAILABLE = True
except ImportError:
    FPDF_AVAILABLE = False

from src.core.finance import get_laporan, get_laporan_kategori, get_proyeksi_bulan, get_saldo

NAMA_BULAN = [
    'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
    'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember',
]


def _fmt_rp(amount: float) -> str:
    """Format angka ke 'Rp 1.500.000'."""
    return f"Rp {int(round(abs(amount))):,}".replace(',', '.')


class MoneyBotPDF(FPDF):
    def __init__(self, wallet_name: str, month_str: str):
        super().__init__()
        self.wallet_name = wallet_name
        self.month_str   = month_str
        try:
            y, m = map(int, month_str.split('-'))
            self.bulan_label = f'{NAMA_BULAN[m-1]} {y}'
        except Exception:
            self.bulan_label = month_str

    def header(self):
        self.set_font('Helvetica', 'B', 15)
        self.set_fill_color(34, 197, 94)   # green-500
        self.set_text_color(255, 255, 255)
        self.cell(0, 12, f'  Laporan Keuangan — {self.bulan_label}', fill=True, ln=True)
        self.set_text_color(100, 100, 100)
        self.set_font('Helvetica', '', 9)
        self.cell(0, 6, f'  Wallet: {self.wallet_name}  |  Dibuat: {datetime.now().strftime("%d/%m/%Y %H:%M")}', ln=True)
        self.ln(4)
        self.set_text_color(0, 0, 0)

    def footer(self):
        self.set_y(-12)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 6, f'Halaman {self.page_no()} | Bot Simpan Uang', align='C')

    def section_title(self, title: str):
        self.set_font('Helvetica', 'B', 11)
        self.set_fill_color(240, 240, 240)
        self.cell(0, 8, f'  {title}', fill=True, ln=True)
        self.ln(2)

    def summary_row(self, label: str, value: str, bold: bool = False, color=None):
        style = 'B' if bold else ''
        self.set_font('Helvetica', style, 10)
        if color:
            self.set_text_color(*color)
        self.cell(90, 7, label)
        self.cell(0, 7, value, ln=True)
        if color:
            self.set_text_color(0, 0, 0)

    def table_header(self, cols: list[tuple]):
        """cols: [(label, width), ...]"""
        self.set_font('Helvetica', 'B', 9)
        self.set_fill_color(55, 65, 81)
        self.set_text_color(255, 255, 255)
        for label, width in cols:
            self.cell(width, 7, label, border=0, fill=True)
        self.ln()
        self.set_text_color(0, 0, 0)

    def table_row(self, values: list[tuple], fill: bool = False):
        """values: [(text, width, align?), ...]"""
        self.set_font('Helvetica', '', 8)
        if fill:
            self.set_fill_color(248, 248, 248)
        for item in values:
            text  = item[0]
            width = item[1]
            align = item[2] if len(item) > 2 else 'L'
            self.cell(width, 6, str(text), border=0, fill=fill, align=align)
        self.ln()


def generate_monthly_pdf(
    wallet_id: str,
    wallet_name: str,
    month_str: Optional[str] = None,
) -> bytes:
    """
    Generate laporan PDF untuk satu bulan.
    Returns: bytes PDF
    Raises: RuntimeError jika fpdf2 belum terinstall
    """
    if not FPDF_AVAILABLE:
        raise RuntimeError(
            'Library `fpdf2` belum terinstall.\n'
            'Jalankan: pip install fpdf2'
        )

    month_str = month_str or datetime.now().strftime('%Y-%m')
    lap       = get_laporan(wallet_id, 'bulan')
    kategori  = get_laporan_kategori(wallet_id, 'bulan')
    saldo_now = get_saldo(wallet_id)
    proj      = get_proyeksi_bulan(wallet_id)
    summary   = lap.get('summary', {})
    trans     = lap.get('transactions', [])

    masuk   = summary.get('total_masuk', 0)
    keluar  = summary.get('total_keluar', 0)
    selisih = masuk - keluar

    pdf = MoneyBotPDF(wallet_name=wallet_name, month_str=month_str)
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()

    # ── Ringkasan ──────────────────────────────────────────────
    pdf.section_title('Ringkasan Bulan Ini')
    pdf.summary_row('Total Pemasukan',   _fmt_rp(masuk),   bold=True,  color=(22, 163, 74))
    pdf.summary_row('Total Pengeluaran', _fmt_rp(keluar),  bold=True,  color=(220, 38, 38))
    net_color = (22, 163, 74) if selisih >= 0 else (220, 38, 38)
    pdf.summary_row('Net (Selisih)',      _fmt_rp(selisih), bold=True,  color=net_color)
    pdf.summary_row('Saldo Sekarang',    _fmt_rp(saldo_now['saldo']), bold=True)
    pdf.summary_row('Jumlah Transaksi',  str(summary.get('jumlah_transaksi', 0)))
    pdf.ln(4)

    # ── Proyeksi ──────────────────────────────────────────────
    pdf.section_title('Proyeksi Akhir Bulan')
    proj_color = (220, 38, 38) if proj['is_defisit'] else (22, 163, 74)
    pdf.summary_row('Hari Berlalu / Total', f'{proj["hari_berlalu"]} / {proj["hari_total"]} hari')
    pdf.summary_row('Rata Pengeluaran/Hari', _fmt_rp(proj['rata_keluar_harian']))
    pdf.summary_row('Estimasi Saldo Akhir Bulan', _fmt_rp(proj['proyeksi_saldo_akhir_bulan']),
                    bold=True, color=proj_color)
    pdf.ln(4)

    # ── Pengeluaran per Kategori ───────────────────────────────
    keluar_kategori = [k for k in kategori if k['type'] == 'out']
    if keluar_kategori:
        pdf.section_title('Pengeluaran per Kategori')
        total_kat = sum(k['total'] for k in keluar_kategori) or 1
        cols = [('Kategori', 60), ('Jumlah', 35), ('Total', 45), ('Porsi', 30)]
        pdf.table_header(cols)
        for i, k in enumerate(keluar_kategori[:20]):
            pct = round(k['total'] / total_kat * 100)
            pdf.table_row([
                (k['category'].title(), 60),
                (str(k['jumlah']), 35, 'C'),
                (_fmt_rp(k['total']), 45, 'R'),
                (f'{pct}%', 30, 'C'),
            ], fill=i % 2 == 0)
        pdf.ln(4)

    # ── Riwayat Transaksi ─────────────────────────────────────
    if trans:
        pdf.section_title(f'Riwayat Transaksi ({len(trans)} transaksi)')
        cols = [('Tanggal', 25), ('Tipe', 20), ('Jumlah', 40), ('Kategori', 35), ('Catatan', 50)]
        pdf.table_header(cols)
        for i, t in enumerate(trans[:100]):  # max 100 baris
            tipe_label = 'Masuk' if t['type'] == 'in' else 'Keluar'
            note = (t.get('note') or '')[:30]
            pdf.table_row([
                (t.get('date', '')[:10],    25),
                (tipe_label,                20),
                (_fmt_rp(t['amount']),       40, 'R'),
                ((t.get('category') or '').title(), 35),
                (note,                      50),
            ], fill=i % 2 == 0)
        if len(trans) > 100:
            pdf.set_font('Helvetica', 'I', 8)
            pdf.cell(0, 6, f'  ... dan {len(trans) - 100} transaksi lainnya', ln=True)
        pdf.ln(2)

    output = io.BytesIO()
    pdf.output(output)
    return output.getvalue()

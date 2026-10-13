"""
Grafik module — chart generation via QuickChart.io.
Bar chart untuk kategori, line chart untuk trend.
"""
import json
import requests
from typing import Optional

from src.core.finance import get_laporan_kategori, get_laporan_trend
from src.core.formatter import format_rupiah

COLORS = [
    'rgba(255, 99, 132, 0.8)',
    'rgba(54, 162, 235, 0.8)',
    'rgba(255, 206, 86, 0.8)',
    'rgba(75, 192, 192, 0.8)',
    'rgba(153, 102, 255, 0.8)',
    'rgba(255, 159, 64, 0.8)',
    'rgba(199, 199, 199, 0.8)',
    'rgba(83, 102, 255, 0.8)',
    'rgba(255, 99, 255, 0.8)',
    'rgba(99, 255, 132, 0.8)',
]

QUICKCHART_URL = 'https://quickchart.io/chart'


def short_month_label(month_str: str, lang: str) -> str:
    """Ubah '2026-10' → 'Okt \'26' (id) atau 'Oct \'26' (en)."""
    BULAN_ID = ['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Agt','Sep','Okt','Nov','Des']
    BULAN_EN = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    try:
        parts = month_str.split('-')
        year = parts[0][-2:]
        month_idx = int(parts[1]) - 1
        names = BULAN_EN if lang == 'en' else BULAN_ID
        return f"{names[month_idx]} '{year}"
    except Exception:
        return month_str


def build_chart_config(wallet_id: str, period: str, lang: str) -> Optional[dict]:
    """
    Buat konfigurasi bar chart QuickChart untuk kategori pengeluaran.
    Returns None jika tidak ada data.
    """
    rows = get_laporan_kategori(wallet_id, period)

    # Filter hanya pengeluaran (keluar)
    keluar_rows = [r for r in rows if r.get('type') == 'out']
    if not keluar_rows:
        return None

    # Ambil max 8 kategori (sort by total desc)
    keluar_rows = sorted(keluar_rows, key=lambda r: r.get('total', 0), reverse=True)[:8]

    total = sum(r.get('total', 0) for r in keluar_rows)
    labels = [r.get('category', 'umum').capitalize() for r in keluar_rows]
    data = [r.get('total', 0) for r in keluar_rows]
    colors = COLORS[:len(labels)]

    config = {
        'type': 'bar',
        'data': {
            'labels': labels,
            'datasets': [{
                'label': 'Pengeluaran' if lang == 'id' else 'Expenses',
                'data': data,
                'backgroundColor': colors,
                'borderColor': [c.replace('0.8', '1') for c in colors],
                'borderWidth': 1,
            }]
        },
        'options': {
            'plugins': {
                'legend': {'display': False},
                'title': {
                    'display': True,
                    'text': ('Pengeluaran per Kategori' if lang == 'id' else 'Expenses by Category'),
                    'font': {'size': 16},
                }
            },
            'scales': {
                'y': {
                    'beginAtZero': True,
                    'ticks': {
                        'callback': '(v) => "Rp " + v.toLocaleString("id-ID")',
                    }
                }
            }
        }
    }

    return {'config': config, 'total': total, 'keluar': keluar_rows}


def fetch_grafik_buffer(chart_config: dict) -> Optional[bytes]:
    """POST ke QuickChart.io, returns PNG bytes."""
    payload = {
        'chart': chart_config,
        'width': 600,
        'height': 400,
        'format': 'png',
        'backgroundColor': 'white',
    }
    try:
        resp = requests.post(
            QUICKCHART_URL,
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        print(f'[GRAFIK] Error fetching chart: {e}')
        return None


def build_grafik_caption(keluar: list, total: float, period: str, lang: str) -> str:
    """Buat caption teks untuk bar chart."""
    if lang == 'en':
        period_labels = {'hari': 'Today', 'minggu': 'This Week', 'bulan': 'This Month'}
        period_label = period_labels.get(period, period)
        lines = [f'📊 *Expenses by Category — {period_label}*\n']
        for i, row in enumerate(keluar[:8]):
            cat = row.get('category', 'umum').capitalize()
            amt = format_rupiah(row.get('total', 0))
            pct = round((row.get('total', 0) / total * 100)) if total else 0
            lines.append(f'{i+1}. {cat}: {amt} ({pct}%)')
        lines.append(f'\n💸 *Total: {format_rupiah(total)}*')
    else:
        period_labels = {'hari': 'Hari Ini', 'minggu': 'Minggu Ini', 'bulan': 'Bulan Ini'}
        period_label = period_labels.get(period, period)
        lines = [f'📊 *Pengeluaran per Kategori — {period_label}*\n']
        for i, row in enumerate(keluar[:8]):
            cat = row.get('category', 'umum').capitalize()
            amt = format_rupiah(row.get('total', 0))
            pct = round((row.get('total', 0) / total * 100)) if total else 0
            lines.append(f'{i+1}. {cat}: {amt} ({pct}%)')
        lines.append(f'\n💸 *Total: {format_rupiah(total)}*')

    return '\n'.join(lines)


def build_trend_config(wallet_id: str, months: int, lang: str) -> Optional[dict]:
    """
    Buat konfigurasi line chart QuickChart untuk trend bulanan (income vs expenses).
    Returns None jika tidak ada data.
    """
    rows = get_laporan_trend(wallet_id, months)
    if not rows:
        return None

    labels = [short_month_label(r['month'], lang) for r in rows]
    masuk_data = [r.get('masuk', 0) for r in rows]
    keluar_data = [r.get('keluar', 0) for r in rows]

    income_label = 'Pemasukan' if lang == 'id' else 'Income'
    expense_label = 'Pengeluaran' if lang == 'id' else 'Expenses'
    title = 'Trend Keuangan' if lang == 'id' else 'Financial Trend'

    config = {
        'type': 'line',
        'data': {
            'labels': labels,
            'datasets': [
                {
                    'label': income_label,
                    'data': masuk_data,
                    'borderColor': 'rgba(75, 192, 192, 1)',
                    'backgroundColor': 'rgba(75, 192, 192, 0.1)',
                    'tension': 0.3,
                    'fill': True,
                },
                {
                    'label': expense_label,
                    'data': keluar_data,
                    'borderColor': 'rgba(255, 99, 132, 1)',
                    'backgroundColor': 'rgba(255, 99, 132, 0.1)',
                    'tension': 0.3,
                    'fill': True,
                }
            ]
        },
        'options': {
            'plugins': {
                'title': {
                    'display': True,
                    'text': f'{title} ({months} bulan terakhir)' if lang == 'id' else f'{title} (Last {months} months)',
                    'font': {'size': 16},
                }
            },
            'scales': {
                'y': {
                    'beginAtZero': True,
                }
            }
        }
    }

    return {'config': config, 'rows': rows, 'months': months}


def build_trend_caption(rows: list, months: int, lang: str) -> str:
    """Buat caption teks untuk line chart trend."""
    if not rows:
        return ''

    total_masuk = sum(r.get('masuk', 0) for r in rows)
    total_keluar = sum(r.get('keluar', 0) for r in rows)
    avg_masuk = total_masuk / len(rows) if rows else 0
    avg_keluar = total_keluar / len(rows) if rows else 0

    if lang == 'en':
        lines = [
            f'📈 *Financial Trend — Last {months} months*\n',
            f'💰 Avg. Income/month: {format_rupiah(avg_masuk)}',
            f'💸 Avg. Expenses/month: {format_rupiah(avg_keluar)}',
        ]
        balance = total_masuk - total_keluar
        if balance >= 0:
            lines.append(f'✅ Net {months}m: +{format_rupiah(balance)}')
        else:
            lines.append(f'⚠️ Net {months}m: -{format_rupiah(abs(balance))}')
    else:
        lines = [
            f'📈 *Trend Keuangan — {months} bulan terakhir*\n',
            f'💰 Rata-rata masuk/bulan: {format_rupiah(avg_masuk)}',
            f'💸 Rata-rata keluar/bulan: {format_rupiah(avg_keluar)}',
        ]
        balance = total_masuk - total_keluar
        if balance >= 0:
            lines.append(f'✅ Net {months}bl: +{format_rupiah(balance)}')
        else:
            lines.append(f'⚠️ Net {months}bl: -{format_rupiah(abs(balance))}')

    return '\n'.join(lines)

"""
Goals module — tabungan/savings goals.
"""
import math
from datetime import datetime

from src.core.database import get_db, _row, _rows


def create_goal(wallet_id: str, name: str, target_amount: float, deadline: str = None) -> dict:
    """Buat goal baru. Raises ValueError jika nama sudah ada."""
    db = get_db()

    existing = _row(db.execute(
        'SELECT id FROM goals WHERE wallet_id = ? AND LOWER(name) = LOWER(?) AND is_completed = 0',
        (wallet_id, name)
    ))
    if existing:
        raise ValueError(f'Goal "{name}" sudah ada.')

    cur = db.execute(
        'INSERT INTO goals (wallet_id, name, target_amount, current_amount, deadline) VALUES (?, ?, ?, 0, ?)',
        (wallet_id, name, target_amount, deadline)
    )
    db.commit()

    return _row(db.execute('SELECT * FROM goals WHERE id = ?', (cur.lastrowid,)))


def get_goals(wallet_id: str) -> list:
    """Ambil semua active goals, ORDER BY created_at ASC."""
    db = get_db()
    return _rows(db.execute(
        'SELECT * FROM goals WHERE wallet_id = ? AND is_completed = 0 ORDER BY created_at ASC',
        (wallet_id,)
    ))


def add_to_goal(wallet_id: str, goal_name: str, amount: float) -> dict:
    """
    Tambah tabungan ke goal.
    Returns updated goal. Raises ValueError jika goal tidak ditemukan.
    """
    db = get_db()

    # Exact match dulu
    goal = _row(db.execute(
        'SELECT * FROM goals WHERE wallet_id = ? AND LOWER(name) = LOWER(?) AND is_completed = 0',
        (wallet_id, goal_name)
    ))

    # Fuzzy match jika tidak ketemu
    if not goal:
        goal = _row(db.execute(
            'SELECT * FROM goals WHERE wallet_id = ? AND LOWER(name) LIKE LOWER(?) AND is_completed = 0',
            (wallet_id, f'%{goal_name}%')
        ))

    if not goal:
        raise ValueError(f'Goal "{goal_name}" tidak ditemukan.')

    new_amount = (goal['current_amount'] or 0) + amount
    is_completed = 1 if new_amount >= goal['target_amount'] else 0

    db.execute(
        'UPDATE goals SET current_amount = ?, is_completed = ? WHERE id = ?',
        (new_amount, is_completed, goal['id'])
    )
    db.commit()

    return _row(db.execute('SELECT * FROM goals WHERE id = ?', (goal['id'],)))


def delete_goal(wallet_id: str, goal_name: str) -> dict:
    """Hapus goal. LIKE fuzzy match. Raises ValueError jika tidak ditemukan."""
    db = get_db()

    goal = _row(db.execute(
        'SELECT * FROM goals WHERE wallet_id = ? AND LOWER(name) LIKE LOWER(?) AND is_completed = 0',
        (wallet_id, f'%{goal_name}%')
    ))

    if not goal:
        raise ValueError(f'Goal "{goal_name}" tidak ditemukan.')

    db.execute('DELETE FROM goals WHERE id = ?', (goal['id'],))
    db.commit()

    return goal


def get_goal_progress(goal: dict) -> dict:
    """Hitung progress untuk satu goal. Returns {persen, sisaHari}."""
    current = goal.get('current_amount') or 0
    target = goal.get('target_amount') or 1
    deadline = goal.get('deadline')

    persen = min(100, round((current / target) * 100))

    sisa_hari = None
    if deadline:
        try:
            deadline_dt = datetime.strptime(deadline[:10], '%Y-%m-%d')
            now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            delta = deadline_dt - now
            sisa_hari = math.ceil(delta.total_seconds() / 86400)
        except (ValueError, TypeError):
            sisa_hari = None

    return {
        'persen': persen,
        'sisaHari': sisa_hari,
    }

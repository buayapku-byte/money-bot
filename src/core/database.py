"""
Database module — SQLite via sqlite3 bawaan Python.
Semua tabel dan operasi core wallet ada di sini.
"""
import sqlite3
import os
import string
import secrets
from datetime import datetime, timedelta

import config

_db: sqlite3.Connection | None = None


def init_database() -> sqlite3.Connection:
    global _db

    db_dir = os.path.dirname(config.DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    _db = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    _db.row_factory = sqlite3.Row
    _db.execute('PRAGMA journal_mode = WAL')
    _db.execute('PRAGMA foreign_keys = ON')

    _create_tables()
    _run_migrations()

    print(f'✅ Database ready: {config.DB_PATH}')
    return _db


def _run_migrations():
    """Jalankan migration schema yang mungkin belum ada di DB lama."""
    try:
        _db.execute("ALTER TABLE wallets ADD COLUMN lang TEXT DEFAULT 'id'")
        _db.commit()
        print('[DB] Kolom lang ditambahkan ke wallets')
    except sqlite3.OperationalError:
        pass  # kolom sudah ada

    try:
        _db.execute("ALTER TABLE transactions ADD COLUMN receipt_path TEXT")
        _db.commit()
        print('[DB] Kolom receipt_path ditambahkan ke transactions')
    except sqlite3.OperationalError:
        pass

    try:
        _db.execute("ALTER TABLE transactions ADD COLUMN bank_id INTEGER")
        _db.commit()
        print('[DB] Kolom bank_id ditambahkan ke transactions')
    except sqlite3.OperationalError:
        pass

    # Wave 3 tables — sudah di _create_tables via IF NOT EXISTS, tapi pastikan
    for sql in [
        """CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, wallet_id TEXT NOT NULL,
            name TEXT NOT NULL, amount REAL NOT NULL, billing_day INTEGER NOT NULL,
            category TEXT DEFAULT 'hiburan', currency TEXT DEFAULT 'IDR',
            is_active INTEGER DEFAULT 1, last_billed TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')))""",
        """CREATE TABLE IF NOT EXISTS savings_challenges (
            id INTEGER PRIMARY KEY AUTOINCREMENT, wallet_id TEXT NOT NULL,
            type TEXT NOT NULL, started_at TEXT NOT NULL,
            completed_weeks INTEGER DEFAULT 0, is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now','localtime')))""",
        """CREATE TABLE IF NOT EXISTS group_wallets (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            owner_id TEXT NOT NULL, invite_code TEXT UNIQUE,
            created_at TEXT DEFAULT (datetime('now','localtime')))""",
        """CREATE TABLE IF NOT EXISTS group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT, group_id INTEGER NOT NULL,
            wallet_id TEXT NOT NULL, role TEXT DEFAULT 'member',
            joined_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(group_id, wallet_id))""",
    ]:
        try:
            _db.execute(sql)
            _db.commit()
        except sqlite3.OperationalError:
            pass


def _create_tables():
    _db.executescript("""
        CREATE TABLE IF NOT EXISTS wallets (
            id          TEXT PRIMARY KEY,
            platform    TEXT NOT NULL CHECK(platform IN ('telegram', 'whatsapp')),
            name        TEXT,
            lang        TEXT DEFAULT 'id',
            created_at  TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id   TEXT NOT NULL,
            type        TEXT NOT NULL CHECK(type IN ('in', 'out')),
            amount      REAL NOT NULL CHECK(amount > 0),
            category    TEXT DEFAULT 'umum',
            note        TEXT,
            created_by  TEXT,
            date        TEXT DEFAULT (date('now', 'localtime')),
            created_at  TEXT DEFAULT (datetime('now', 'localtime')),
            receipt_path TEXT,
            FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_transactions_wallet_date
            ON transactions(wallet_id, date);

        CREATE TABLE IF NOT EXISTS goals (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id       TEXT NOT NULL,
            name            TEXT NOT NULL,
            target_amount   REAL NOT NULL CHECK(target_amount > 0),
            current_amount  REAL DEFAULT 0,
            deadline        TEXT,
            is_completed    INTEGER DEFAULT 0,
            created_at      TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS reminders (
            wallet_id   TEXT PRIMARY KEY,
            time        TEXT DEFAULT '20:00',
            is_active   INTEGER DEFAULT 1,
            FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS budgets (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id   TEXT NOT NULL,
            category    TEXT NOT NULL,
            amount      REAL NOT NULL CHECK(amount > 0),
            month       TEXT NOT NULL,
            created_at  TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(wallet_id, category, month),
            FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS recurring (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id     TEXT NOT NULL,
            type          TEXT NOT NULL CHECK(type IN ('in', 'out')),
            amount        REAL NOT NULL CHECK(amount > 0),
            note          TEXT,
            category      TEXT DEFAULT 'umum',
            day_of_month  INTEGER NOT NULL CHECK(day_of_month BETWEEN 1 AND 28),
            last_run      TEXT,
            is_active     INTEGER DEFAULT 1,
            created_at    TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS wallet_links (
            member_id   TEXT PRIMARY KEY,
            primary_id  TEXT NOT NULL,
            linked_at   TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (member_id)  REFERENCES wallets(id) ON DELETE CASCADE,
            FOREIGN KEY (primary_id) REFERENCES wallets(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS invite_codes (
            code        TEXT PRIMARY KEY,
            wallet_id   TEXT NOT NULL,
            expires_at  TEXT NOT NULL,
            used        INTEGER DEFAULT 0,
            created_at  TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS live_rates (
            code          TEXT PRIMARY KEY,
            rate_to_idr   REAL NOT NULL,
            updated_at    TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS currencies (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id     TEXT NOT NULL,
            code          TEXT NOT NULL,
            rate_to_idr   REAL NOT NULL,
            updated_at    TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(wallet_id, code),
            FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS wishlists (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id  TEXT NOT NULL,
            name       TEXT NOT NULL,
            price      REAL NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS bank_accounts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id       TEXT NOT NULL,
            name            TEXT NOT NULL,
            initial_balance REAL DEFAULT 0,
            color           TEXT DEFAULT 'blue',
            created_at      TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS auto_savings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id   TEXT NOT NULL,
            goal_name   TEXT NOT NULL,
            percentage  REAL NOT NULL,
            created_at  TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(wallet_id, goal_name),
            FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS debts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id   TEXT NOT NULL,
            type        TEXT NOT NULL CHECK(type IN ('utang','piutang')),
            person      TEXT NOT NULL,
            amount      REAL NOT NULL,
            note        TEXT DEFAULT '',
            is_paid     INTEGER DEFAULT 0,
            due_date    TEXT,
            paid_at     TEXT,
            created_at  TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS installments (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id       TEXT NOT NULL,
            name            TEXT NOT NULL,
            total_months    INTEGER NOT NULL,
            paid_months     INTEGER DEFAULT 0,
            monthly_amount  REAL NOT NULL,
            start_date      TEXT NOT NULL,
            due_day         INTEGER DEFAULT 1,
            note            TEXT DEFAULT '',
            is_done         INTEGER DEFAULT 0,
            created_at      TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS bills (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id   TEXT NOT NULL,
            name        TEXT NOT NULL,
            due_day     INTEGER NOT NULL,
            amount      REAL DEFAULT 0,
            note        TEXT DEFAULT '',
            is_active   INTEGER DEFAULT 1,
            created_at  TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS split_bills (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id   TEXT NOT NULL,
            title       TEXT NOT NULL,
            total       REAL DEFAULT 0,
            note        TEXT DEFAULT '',
            is_settled  INTEGER DEFAULT 0,
            created_at  TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS split_items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            split_id    INTEGER NOT NULL,
            person      TEXT NOT NULL,
            amount      REAL NOT NULL,
            is_paid     INTEGER DEFAULT 0,
            paid_at     TEXT,
            FOREIGN KEY (split_id) REFERENCES split_bills(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS investments (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id   TEXT NOT NULL,
            name        TEXT NOT NULL,
            ticker      TEXT,
            type        TEXT DEFAULT 'saham',
            buy_price   REAL NOT NULL,
            quantity    REAL NOT NULL,
            buy_date    TEXT NOT NULL,
            note        TEXT DEFAULT '',
            is_sold     INTEGER DEFAULT 0,
            sell_price  REAL,
            created_at  TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS achievements (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id   TEXT NOT NULL,
            code        TEXT NOT NULL,
            earned_at   TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(wallet_id, code),
            FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS dana_darurat_config (
            wallet_id   TEXT PRIMARY KEY,
            months      INTEGER DEFAULT 3,
            goal_id     INTEGER,
            updated_at  TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS subscriptions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id   TEXT NOT NULL,
            name        TEXT NOT NULL,
            amount      REAL NOT NULL CHECK(amount > 0),
            billing_day INTEGER NOT NULL CHECK(billing_day BETWEEN 1 AND 28),
            category    TEXT DEFAULT 'hiburan',
            currency    TEXT DEFAULT 'IDR',
            is_active   INTEGER DEFAULT 1,
            last_billed TEXT,
            created_at  TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS savings_challenges (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id   TEXT NOT NULL,
            type        TEXT NOT NULL,
            started_at  TEXT NOT NULL,
            completed_weeks INTEGER DEFAULT 0,
            is_active   INTEGER DEFAULT 1,
            created_at  TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS group_wallets (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            owner_id    TEXT NOT NULL,
            invite_code TEXT UNIQUE,
            created_at  TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (owner_id) REFERENCES wallets(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS group_members (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id    INTEGER NOT NULL,
            wallet_id   TEXT NOT NULL,
            role        TEXT DEFAULT 'member',
            joined_at   TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(group_id, wallet_id),
            FOREIGN KEY (group_id)  REFERENCES group_wallets(id) ON DELETE CASCADE,
            FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
        );
    """)
    _db.commit()


def get_db() -> sqlite3.Connection:
    if _db is None:
        raise RuntimeError('Database belum diinisialisasi. Panggil init_database() dulu.')
    return _db


def get_db_path() -> str:
    return os.path.abspath(config.DB_PATH)


def _row(cursor) -> dict | None:
    row = cursor.fetchone()
    return dict(row) if row else None


def _rows(cursor) -> list[dict]:
    return [dict(r) for r in cursor.fetchall()]


# ─── Wallet ───────────────────────────────────────────────

def get_or_create_wallet(platform: str, chat_id, name: str = None) -> dict:
    db = get_db()
    prefix = 'tg' if platform == 'telegram' else 'wa'
    wallet_id = f'{prefix}:{chat_id}'

    row = _row(db.execute('SELECT * FROM wallets WHERE id = ?', (wallet_id,)))
    if not row:
        db.execute(
            'INSERT INTO wallets (id, platform, name) VALUES (?, ?, ?)',
            (wallet_id, platform, name)
        )
        db.execute(
            'INSERT OR IGNORE INTO reminders (wallet_id, time) VALUES (?, ?)',
            (wallet_id, '20:00')
        )
        db.commit()
        row = _row(db.execute('SELECT * FROM wallets WHERE id = ?', (wallet_id,)))
        print(f'[DB] Wallet baru: {wallet_id} ({name or "unknown"})')

    return row


def resolve_wallet_id(wallet_id: str) -> str:
    """Return primary wallet_id jika sedang linked, atau wallet_id itu sendiri."""
    db = get_db()
    row = _row(db.execute('SELECT primary_id FROM wallet_links WHERE member_id = ?', (wallet_id,)))
    return row['primary_id'] if row else wallet_id


def get_lang(wallet_id: str) -> str:
    db = get_db()
    row = _row(db.execute('SELECT lang FROM wallets WHERE id = ?', (wallet_id,)))
    return (row.get('lang') or 'id') if row else 'id'


def set_lang(wallet_id: str, lang: str):
    db = get_db()
    db.execute('UPDATE wallets SET lang = ? WHERE id = ?', (lang, wallet_id))
    db.commit()


# ─── Invite Codes ─────────────────────────────────────────

def create_invite_code(wallet_id: str) -> str:
    db = get_db()
    db.execute(
        "DELETE FROM invite_codes WHERE wallet_id = ? AND (used = 1 OR expires_at < datetime('now', 'localtime'))",
        (wallet_id,)
    )

    charset = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    while True:
        code = ''.join(secrets.choice(charset) for _ in range(6))
        exists = _row(db.execute('SELECT 1 FROM invite_codes WHERE code = ?', (code,)))
        if not exists:
            break

    expires_at = (datetime.now() + timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
    db.execute(
        'INSERT INTO invite_codes (code, wallet_id, expires_at) VALUES (?, ?, ?)',
        (code, wallet_id, expires_at)
    )
    db.commit()
    return code


def use_invite_code(member_wallet_id: str, code: str) -> dict:
    db = get_db()
    invite = _row(db.execute(
        "SELECT * FROM invite_codes WHERE code = ? AND used = 0 AND expires_at > datetime('now', 'localtime')",
        (code.upper(),)
    ))
    if not invite:
        raise ValueError('Kode tidak valid atau sudah kadaluarsa.')
    if invite['wallet_id'] == member_wallet_id:
        raise ValueError('Tidak bisa bergabung ke wallet sendiri.')

    db.execute('UPDATE invite_codes SET used = 1 WHERE code = ?', (code.upper(),))
    db.execute(
        'INSERT OR REPLACE INTO wallet_links (member_id, primary_id) VALUES (?, ?)',
        (member_wallet_id, invite['wallet_id'])
    )
    db.commit()

    primary = _row(db.execute('SELECT * FROM wallets WHERE id = ?', (invite['wallet_id'],)))
    print(f'[DB] Wallet {member_wallet_id} linked ke {invite["wallet_id"]}')
    return primary


def unlink_wallet(member_wallet_id: str) -> dict | None:
    db = get_db()
    link = _row(db.execute('SELECT * FROM wallet_links WHERE member_id = ?', (member_wallet_id,)))
    if not link:
        return None
    db.execute('DELETE FROM wallet_links WHERE member_id = ?', (member_wallet_id,))
    db.commit()
    print(f'[DB] Wallet {member_wallet_id} unlinked dari {link["primary_id"]}')
    return link

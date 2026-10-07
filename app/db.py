"""Small local database. SQL is parameterized; every order read is customer scoped."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path


@contextmanager
def connection():
    path = Path(os.getenv('DATABASE_PATH', 'data/agent.db'))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def initialize():
    with connection() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS orders (
          id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, product TEXT NOT NULL,
          delivered_on TEXT, status TEXT NOT NULL, final_sale INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS conversations (
          id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, last_order TEXT
        );
        CREATE TABLE IF NOT EXISTS messages (
          id INTEGER PRIMARY KEY, conversation_id TEXT NOT NULL,
          role TEXT NOT NULL, content TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS proposals (
          id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, order_id TEXT NOT NULL,
          created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS returns (
          id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, order_id TEXT NOT NULL UNIQUE,
          status TEXT NOT NULL, created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS handoffs (
          id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, summary TEXT NOT NULL
        );
        ''')
        # Relative dates keep a freshly seeded demo useful. Existing orders are preserved.
        today = date.today()
        rows = [
            ('ORD-1001', 'customer-1', 'Headphones', str(today-timedelta(days=7)), 'delivered', 0),
            ('ORD-1002', 'customer-1', 'Shoes', str(today-timedelta(days=45)), 'delivered', 0),
            ('ORD-1003', 'customer-1', 'Jacket', None, 'in_transit', 0),
            ('ORD-1004', 'customer-1', 'Clearance bag', str(today-timedelta(days=3)), 'delivered', 1),
            ('ORD-2001', 'customer-2', 'Watch', str(today-timedelta(days=2)), 'delivered', 0),
        ]
        db.executemany('INSERT OR IGNORE INTO orders VALUES (?,?,?,?,?,?)', rows)

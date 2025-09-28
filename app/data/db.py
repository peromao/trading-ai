import os
import sqlite3
from typing import Iterable, Optional, Dict, Any

import pandas as pd


DB_PATH = os.getenv("DB_PATH", "db.sqlite3")


def get_connection(path: Optional[str] = None) -> sqlite3.Connection:
    """Return a sqlite3 connection with sensible defaults."""
    db_path = path or DB_PATH
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables if they do not exist."""
    cur = conn.cursor()
    # Cash snapshots (one row per date)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS cash (
            date TEXT PRIMARY KEY,
            amount REAL,
            total_portfolio_amount REAL
        );
        """
    )
    # Positions (latest holdings per day/ticker)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS positions (
            date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            qty REAL,
            avg_price REAL,
            UNIQUE(date, ticker)
        );
        """
    )
    # Executed orders (can have multiple per date/ticker)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            qty REAL,
            price REAL
        );
        """
    )
    # Market daily info per ticker (one row per date/ticker)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS stocks_info (
            date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            dividends REAL DEFAULT 0.0,
            stock_splits REAL DEFAULT 0.0,
            PRIMARY KEY (date, ticker)
        );
        """
    )
    conn.commit()


def table_is_empty(conn: sqlite3.Connection, table: str) -> bool:
    try:
        cur = conn.execute(f"SELECT 1 FROM {table} LIMIT 1")
        return cur.fetchone() is None
    except sqlite3.Error:
        return True


def bootstrap_db(path: Optional[str] = None) -> None:
    """Ensure the SQLite database exists with the expected schema."""
    conn = get_connection(path)
    try:
        init_db(conn)
    finally:
        conn.close()


def df_from_query(sql: str, params: Iterable[Any] | None = None) -> pd.DataFrame:
    conn = get_connection()
    try:
        df = pd.read_sql_query(sql, conn, params=params or [])
        return df
    finally:
        conn.close()

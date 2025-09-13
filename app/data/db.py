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


def _clean_ticker(t: Any) -> str:
    return str(t).strip().strip('"').strip("'")


def _to_date_str(val: Any) -> str:
    try:
        return pd.to_datetime(val, errors="coerce").date().strftime("%Y-%m-%d")
    except Exception:
        # Fallback to string
        return str(val)[:10]


def table_is_empty(conn: sqlite3.Connection, table: str) -> bool:
    try:
        cur = conn.execute(f"SELECT 1 FROM {table} LIMIT 1")
        return cur.fetchone() is None
    except sqlite3.Error:
        return True


def _csv_exists(path: str) -> bool:
    return os.path.exists(path) and os.path.getsize(path) > 0


def migrate_csv_to_sqlite(conn: sqlite3.Connection) -> None:
    """Import existing CSV files into SQLite if tables are empty.

    This is idempotent and only runs for tables that have no rows.
    """
    cur = conn.cursor()

    # cash.csv
    if table_is_empty(conn, "cash") and _csv_exists("data/cash.csv"):
        df = pd.read_csv("data/cash.csv")
        df.columns = [c.strip() for c in df.columns]
        if "date" in df.columns:
            df["date"] = df["date"].map(_to_date_str)
        rows = [
            (r.get("date"), r.get("amount"), r.get("total_portfolio_amount"))
            for r in df.to_dict(orient="records")
        ]
        cur.executemany(
            "INSERT OR REPLACE INTO cash(date, amount, total_portfolio_amount) VALUES (?, ?, ?)",
            rows,
        )

    # positions.csv
    if table_is_empty(conn, "positions") and _csv_exists("data/positions.csv"):
        df = pd.read_csv("data/positions.csv")
        df.columns = [c.strip() for c in df.columns]
        if "date" in df.columns:
            df["date"] = df["date"].map(_to_date_str)
        if "ticker" in df.columns:
            df["ticker"] = df["ticker"] = df["ticker"].map(_clean_ticker)
        rows = [
            (r.get("date"), r.get("ticker"), r.get("qty"), r.get("avg_price"))
            for r in df.to_dict(orient="records")
        ]
        cur.executemany(
            "INSERT OR REPLACE INTO positions(date, ticker, qty, avg_price) VALUES (?, ?, ?, ?)",
            rows,
        )

    # orders.csv
    if table_is_empty(conn, "orders") and _csv_exists("data/orders.csv"):
        df = pd.read_csv("data/orders.csv")
        df.columns = [c.strip() for c in df.columns]
        if "date" in df.columns:
            df["date"] = df["date"].map(_to_date_str)
        if "ticker" in df.columns:
            df["ticker"] = df["ticker"].map(_clean_ticker)
        rows = [
            (r.get("date"), r.get("ticker"), r.get("qty"), r.get("price"))
            for r in df.to_dict(orient="records")
        ]
        cur.executemany(
            "INSERT INTO orders(date, ticker, qty, price) VALUES (?, ?, ?, ?)",
            rows,
        )

    # stocks_info.csv
    if table_is_empty(conn, "stocks_info") and _csv_exists("data/stocks_info.csv"):
        df = pd.read_csv("data/stocks_info.csv")
        df.columns = [c.strip() for c in df.columns]
        if "date" in df.columns:
            df["date"] = df["date"].map(_to_date_str)
        if "ticker" in df.columns:
            df["ticker"] = df["ticker"].map(_clean_ticker)
        # Ensure missing optional columns exist
        for col, default in ("dividends", 0.0), ("stock_splits", 0.0):
            if col not in df.columns:
                df[col] = default
        rows = [
            (
                r.get("date"),
                r.get("ticker"),
                r.get("open"),
                r.get("high"),
                r.get("low"),
                r.get("close"),
                r.get("volume"),
                r.get("dividends"),
                r.get("stock_splits"),
            )
            for r in df.to_dict(orient="records")
        ]
        cur.executemany(
            """
            INSERT OR REPLACE INTO stocks_info(
                date, ticker, open, high, low, close, volume, dividends, stock_splits
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    conn.commit()


def bootstrap_db(path: Optional[str] = None) -> None:
    """Ensure DB exists with schema and import CSVs on first run."""
    conn = get_connection(path)
    try:
        init_db(conn)
        migrate_csv_to_sqlite(conn)
    finally:
        conn.close()


def df_from_query(sql: str, params: Iterable[Any] | None = None) -> pd.DataFrame:
    conn = get_connection()
    try:
        df = pd.read_sql_query(sql, conn, params=params or [])
        return df
    finally:
        conn.close()


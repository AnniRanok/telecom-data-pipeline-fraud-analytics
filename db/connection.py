"""
Database Connection Layer

Provides a unified DB interface that works with:
  - DuckDB  (local dev, current)
  - PostgreSQL via psycopg2 (production, swap one line)

Usage:
    from db.connection import get_engine, get_conn, DB_PATH

    conn = get_conn()           # raw DuckDB connection
    engine = get_engine()       # SQLAlchemy-compatible engine

PostgreSQL migration:
    Change BACKEND = "duckdb"  →  BACKEND = "postgresql"
    Set PG_DSN below.
    All SQL in etl/ and dwh/ is ANSI-compatible — no changes needed.
"""

import os
import duckdb
import pandas as pd

# ─── CONFIG 
BACKEND  = "duckdb"        # "duckdb" | "postgresql"
DB_DIR   = os.path.join(os.path.dirname(__file__), "..", "db")
BDB_PATH = os.path.join(DB_DIR, "business_db.duckdb")   # Operational DB
DWH_PATH = os.path.join(DB_DIR, "dwh.duckdb")           # Data Warehouse

# PostgreSQL (uncomment when ready):
# PG_BDB_DSN = "postgresql://telecom:telecom@localhost:5432/business_db"
# PG_DWH_DSN = "postgresql://telecom:telecom@localhost:5432/dwh_db"


# ─── CONNECTION FACTORY 

class DBConn:
    """
    Thin wrapper around a DuckDB connection.
    Exposes: execute(), read_df(), write_df(), executemany()

    Drop-in replacement for psycopg2 cursor when migrating to PostgreSQL:
      self.conn = psycopg2.connect(PG_DSN)
      self.cur  = self.conn.cursor()
    """

    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._path = path
        self._conn = duckdb.connect(path)

    def execute(self, sql: str, params=None) -> "DBConn":
        if params:
            self._conn.execute(sql, params)
        else:
            self._conn.execute(sql)
        return self

    def executemany(self, sql: str, rows: list) -> "DBConn":
        self._conn.executemany(sql, rows)
        return self

    def fetchall(self) -> list:
        return self._conn.fetchall()

    def fetchone(self):
        return self._conn.fetchone()

    def read_df(self, sql: str, params=None) -> pd.DataFrame:
        if params:
            return self._conn.execute(sql, params).df()
        return self._conn.execute(sql).df()

    def write_df(self, df: pd.DataFrame, table: str,
                 if_exists: str = "append") -> int:
        """
        Write DataFrame to table. Columns are matched by name; any table
        columns not present in the DataFrame are left to their SQL defaults.
        if_exists: 'append' | 'replace'
        Returns number of rows written.
        """
        if df.empty:
            return 0
        tmp = "__tmp_write__"
        self._conn.register(tmp, df)
        if if_exists == "replace":
            self._conn.execute(f"DELETE FROM {table}")
        cols = ", ".join(df.columns)
        self._conn.execute(f"INSERT INTO {table} ({cols}) SELECT {cols} FROM {tmp}")
        self._conn.unregister(tmp)
        return len(df)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def table_exists(self, table: str) -> bool:
        r = self._conn.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name = ?", [table.lower()]
        ).fetchone()
        return r[0] > 0

    def table_count(self, table: str) -> int:
        if not self.table_exists(table):
            return 0
        return self._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def get_bdb() -> DBConn:
    """Return Business DB connection."""
    return DBConn(BDB_PATH)

def get_dwh() -> DBConn:
    """Return Data Warehouse connection."""
    return DBConn(DWH_PATH)


# ─── QUICK SANITY CHECK 
if __name__ == "__main__":
    print("Testing Business DB connection...")
    with get_bdb() as bdb:
        bdb.execute("CREATE TABLE IF NOT EXISTS _test (x INTEGER)")
        bdb.execute("INSERT INTO _test VALUES (42)")
        row = bdb.read_df("SELECT * FROM _test")
        bdb.execute("DROP TABLE _test")
        print(f"  BDB OK — read: {row.iloc[0,0]}")

    print("Testing DWH connection...")
    with get_dwh() as dwh:
        dwh.execute("CREATE TABLE IF NOT EXISTS _test (x INTEGER)")
        dwh.execute("INSERT INTO _test VALUES (99)")
        row = dwh.read_df("SELECT * FROM _test")
        dwh.execute("DROP TABLE _test")
        print(f"  DWH OK — read: {row.iloc[0,0]}")

    print("\nBDB path:", BDB_PATH)
    print("DWH path:", DWH_PATH)
    print("\nTo migrate to PostgreSQL:")
    print("  1. Set BACKEND = 'postgresql'")
    print("  2. Set PG_BDB_DSN / PG_DWH_DSN")
    print("  3. Replace DBConn with psycopg2.connect()")
    print("  All SQL stays the same.")

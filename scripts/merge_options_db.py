"""Merge data/options_intraday.db into /mnt/Data/EVA/options_intraday.db.

Usage:
  .venv/bin/python scripts/merge_options_db.py

Usage (dry-run):
  .venv/bin/python scripts/merge_options_db.py --dry-run
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

SRC = Path("data/options_intraday.db")
DST = Path("/mnt/Data/EVA/options_intraday.db")


def get_pragma_info(conn: sqlite3.Connection, table: str) -> list[dict]:
    cur = conn.execute(f"PRAGMA table_info('{table}')")
    cols = []
    for row in cur.fetchall():
        cid, name, col_type, notnull, default, pk = row
        cols.append({
            "cid": cid,
            "name": name,
            "type": col_type,
            "pk": pk,
        })
    return cols


def is_generated(conn: sqlite3.Connection, table: str, col_name: str) -> bool:
    cur = conn.execute(
        f"SELECT hidden FROM pragma_table_xinfo('{table}') WHERE name='{col_name}'",
    )
    row = cur.fetchone()
    return row is not None and row[0] == 2


def merge_table(
    dst_conn: sqlite3.Connection,
    src_conn: sqlite3.Connection,
    table: str,
    *,
    dry_run: bool = False,
) -> int:
    src_cols = get_pragma_info(src_conn, table)

    # Exclude INTEGER PRIMARY KEY AUTOINCREMENT (let dst assign new ids)
    # and GENERATED STORED columns (read-only in SQLite 3.45+)
    insert_cols = []
    for c in src_cols:
        if c["pk"] == 1 and c["type"] == "INTEGER":
            continue
        if is_generated(src_conn, table, c["name"]):
            continue
        insert_cols.append(c["name"])

    col_list = ", ".join(insert_cols)
    sql = f"INSERT OR IGNORE INTO {table} ({col_list}) SELECT {col_list} FROM src.{table}"

    if dry_run:
        print(f"[DRY-RUN] {sql}")
        src_count = src_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        return src_count

    dst_conn.execute(sql)
    inserted = dst_conn.total_changes
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge source DB into destination DB using INSERT OR IGNORE."
    )
    parser.add_argument("--dry-run", action="store_true", help="Print SQL without executing.")
    args = parser.parse_args()

    if not SRC.exists():
        print(f"ERROR: Source DB not found: {SRC}", file=sys.stderr)
        sys.exit(1)
    if not DST.exists():
        print(f"ERROR: Destination DB not found: {DST}", file=sys.stderr)
        sys.exit(1)

    src_conn = sqlite3.connect(str(SRC))
    dst_conn = sqlite3.connect(str(DST))

    try:
        tables = [
            row[0]
            for row in src_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            if row[0] != "sqlite_sequence"
        ]

        print(f"Tables to merge ({len(tables)}): {', '.join(tables)}")

        if not args.dry_run:
            dst_conn.execute("PRAGMA journal_mode=WAL")
            dst_conn.execute("BEGIN")

        total_rows = 0
        for table in tables:
            src_count = src_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if src_count == 0:
                print(f"  {table}: 0 rows (skip)")
                continue

            before = dst_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            n = merge_table(dst_conn, src_conn, table, dry_run=args.dry_run)

            if args.dry_run:
                print(f"  {table}: {src_count} rows ready to merge")
                total_rows += src_count
            else:
                after = dst_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                actual = after - before
                skipped = src_count - actual
                total_rows += actual
                print(f"  {table}: {actual} merged ({skipped} skipped by UNIQUE)")

        if not args.dry_run:
            dst_conn.execute("COMMIT")
            dst_conn.execute("PRAGMA journal_mode=DELETE")
            dst_conn.execute("ANALYZE")

        print(f"\nTotal: {total_rows} rows merged")
    finally:
        src_conn.close()
        dst_conn.close()


if __name__ == "__main__":
    main()

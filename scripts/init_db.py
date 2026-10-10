"""Create the SQLite tables and load the sample data.

Usage (from the repo root, with the virtual environment active):

    python scripts/init_db.py           # create tables; load sample data only if empty
    python scripts/init_db.py --reset   # delete the database file, then start fresh

Uses the same settings as the app:
    TICKETS_DB_PATH    SQLite file (default data/tickets.db)
    TICKETS_DATA_FILE  sample data JSON (default data/sample_data.json)

Safe to run more than once: without --reset it never removes existing tickets.
Stop the server before using --reset so it is not holding the file open.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import db
from tickets.app import DEFAULT_DATA_FILE, DEFAULT_DB_FILE


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create tables and load sample data.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete the existing database file first (removes all saved tickets)",
    )
    args = parser.parse_args(argv)

    db_path = Path(os.environ.get("TICKETS_DB_PATH", str(DEFAULT_DB_FILE)))
    data_file = Path(os.environ.get("TICKETS_DATA_FILE", str(DEFAULT_DATA_FILE)))

    if args.reset and db_path.exists():
        db_path.unlink()
        print(f"Deleted {db_path}")

    with open(data_file, encoding="utf-8") as f:
        data = json.load(f)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = db.connect(db_path)
    try:
        db.init_db(conn)
        db.seed_if_empty(conn, data)
        count = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
    finally:
        conn.close()

    print(f"Database ready at {db_path} ({count} tickets)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Create the MySQL tables and load the sample data.

Usage (from the repo root, with the virtual environment active):

    python scripts/init_db.py           # create tables; load sample data only if empty
    python scripts/init_db.py --reset   # drop the tables, then start fresh

Uses the same settings as the app:
    MYSQL_HOST         MySQL host (default 127.0.0.1)
    MYSQL_PORT         MySQL port (default 3306)
    MYSQL_USER         MySQL user (default tickets)
    MYSQL_PASSWORD     MySQL password (no default)
    MYSQL_DATABASE     database name (default tickets)
    TICKETS_DATA_FILE  sample data JSON (default data/sample_data.json)

Safe to run more than once: without --reset it never removes existing tickets.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import db
from tickets.app import DEFAULT_DATA_FILE


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create tables and load sample data.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="drop the tables first (removes all saved tickets)",
    )
    args = parser.parse_args(argv)

    config = db.config_from_env()
    data_file = Path(os.environ.get("TICKETS_DATA_FILE", str(DEFAULT_DATA_FILE)))

    with open(data_file, encoding="utf-8") as f:
        data = json.load(f)

    conn = db.connect(config)
    try:
        if args.reset:
            db.reset_db(conn)
            print(f"Reset database {config.database}")
        else:
            db.init_db(conn)
        db.seed_if_empty(conn, data)
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS ticket_count FROM tickets")
            count = cur.fetchone()["ticket_count"]
    finally:
        conn.close()

    print(f"Database ready ({count} tickets)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

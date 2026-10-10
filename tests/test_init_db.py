import json
import os
import subprocess
import sys
from pathlib import Path

import db
from tickets.app import DEFAULT_DATA_FILE

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "init_db.py"


def _run(db_path, *args):
    env = {**os.environ, "TICKETS_DB_PATH": str(db_path)}
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )


def _ticket_count(db_path):
    conn = db.connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
    finally:
        conn.close()


def _sample_count():
    with open(DEFAULT_DATA_FILE, encoding="utf-8") as f:
        return len(json.load(f)["tickets"])


def test_creates_tables_and_loads_sample_data(tmp_path):
    path = tmp_path / "tickets.db"
    _run(path)
    assert _ticket_count(path) == _sample_count()


def test_running_again_keeps_existing_tickets(tmp_path):
    path = tmp_path / "tickets.db"
    _run(path)
    conn = db.connect(path)
    try:
        conn.execute("DELETE FROM notes WHERE ticket_id = 'HD-1042'")
        conn.execute("DELETE FROM tickets WHERE ticket_id = 'HD-1042'")
        conn.commit()
    finally:
        conn.close()

    _run(path)
    assert _ticket_count(path) == _sample_count() - 1


def test_reset_starts_fresh(tmp_path):
    path = tmp_path / "tickets.db"
    _run(path)
    conn = db.connect(path)
    try:
        conn.execute("DELETE FROM notes")
        conn.execute("DELETE FROM tickets")
        conn.commit()
    finally:
        conn.close()

    result = _run(path, "--reset")
    assert "Deleted" in result.stdout
    assert _ticket_count(path) == _sample_count()

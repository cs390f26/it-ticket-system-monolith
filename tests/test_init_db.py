import json
import os
import subprocess
import sys
from pathlib import Path

import db
from tickets.app import DEFAULT_DATA_FILE

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "init_db.py"


def _run(config, *args):
    env = {
        **os.environ,
        "MYSQL_HOST": config.host,
        "MYSQL_PORT": str(config.port),
        "MYSQL_USER": config.user,
        "MYSQL_PASSWORD": config.password,
        "MYSQL_DATABASE": config.database,
    }
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )


def _ticket_count(config):
    conn = db.connect(config)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS ticket_count FROM tickets")
            return cur.fetchone()["ticket_count"]
    finally:
        conn.close()


def _sample_count():
    with open(DEFAULT_DATA_FILE, encoding="utf-8") as f:
        return len(json.load(f)["tickets"])


def test_creates_tables_and_loads_sample_data(mysql_config):
    _run(mysql_config)
    assert _ticket_count(mysql_config) == _sample_count()


def test_running_again_keeps_existing_tickets(mysql_config):
    _run(mysql_config)
    conn = db.connect(mysql_config)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM notes WHERE ticket_id = %s", ("HD-1042",))
            cur.execute("DELETE FROM tickets WHERE ticket_id = %s", ("HD-1042",))
        conn.commit()
    finally:
        conn.close()

    _run(mysql_config)
    assert _ticket_count(mysql_config) == _sample_count() - 1


def test_reset_starts_fresh(mysql_config):
    _run(mysql_config)
    conn = db.connect(mysql_config)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM notes")
            cur.execute("DELETE FROM tickets")
        conn.commit()
    finally:
        conn.close()

    result = _run(mysql_config, "--reset")
    assert "Reset" in result.stdout
    assert _ticket_count(mysql_config) == _sample_count()

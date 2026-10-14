"""MySQL schema and queries for tickets and notes.

Connection setup and SQL stay in this module so ticket rules and HTTP routes
do not depend on the database.
"""

import os
import re
from dataclasses import dataclass

import pymysql
from pymysql.cursors import DictCursor

# Spec schema (it-ticket-system-specs/db.md). IF NOT EXISTS keeps a restart
# from dropping an existing database. Indexes live on the CREATE TABLE so a
# second startup does not try to add them again.
_TICKETS_TABLE = """
CREATE TABLE IF NOT EXISTS tickets (
  ticket_id VARCHAR(32) PRIMARY KEY,
  title VARCHAR(120) NOT NULL,
  description VARCHAR(2000) NOT NULL,
  requester_name VARCHAR(80) NOT NULL,
  requester_email VARCHAR(120) NOT NULL,
  category VARCHAR(16) NOT NULL CHECK (category IN ('Hardware', 'Software', 'Network', 'Account', 'Other')),
  priority VARCHAR(16) NOT NULL CHECK (priority IN ('Low', 'Medium', 'High', 'Urgent')),
  status VARCHAR(16) NOT NULL CHECK (status IN ('Open', 'In progress', 'Resolved')),
  created_at VARCHAR(32) NOT NULL,
  updated_at VARCHAR(32) NOT NULL,
  INDEX idx_tickets_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

_NOTES_TABLE = """
CREATE TABLE IF NOT EXISTS notes (
  note_id INT AUTO_INCREMENT PRIMARY KEY,
  ticket_id VARCHAR(32) NOT NULL,
  author VARCHAR(16) NOT NULL CHECK (author IN ('System', 'IT staff')),
  body VARCHAR(1000) NOT NULL,
  created_at VARCHAR(32) NOT NULL,
  INDEX idx_notes_ticket_created (ticket_id, created_at),
  CONSTRAINT fk_notes_ticket FOREIGN KEY (ticket_id) REFERENCES tickets (ticket_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

TICKET_FIELDS = (
    "ticket_id",
    "title",
    "description",
    "requester_name",
    "requester_email",
    "category",
    "priority",
    "status",
    "created_at",
    "updated_at",
)

NOTE_FIELDS = ("note_id", "ticket_id", "author", "body", "created_at")

_TICKET_COLUMNS = ", ".join(TICKET_FIELDS)
_NOTE_COLUMNS = ", ".join(NOTE_FIELDS)

_INSERT_TICKET = f"""
INSERT INTO tickets ({_TICKET_COLUMNS})
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

_INSERT_NOTE = """
INSERT INTO notes (ticket_id, author, body, created_at)
VALUES (%s, %s, %s, %s)
"""

_INSERT_NOTE_WITH_ID = f"""
INSERT INTO notes ({_NOTE_COLUMNS})
VALUES (%s, %s, %s, %s, %s)
"""

_DB_NAME = re.compile(r"^[A-Za-z0-9_]+$")


class UnavailableError(Exception):
    """Raised when the database cannot be reached or a statement fails."""


@dataclass(frozen=True)
class DbConfig:
    """How to reach the MySQL server and which database to use."""

    host: str
    port: int
    user: str
    password: str
    database: str


def config_from_env(database: str | None = None) -> DbConfig:
    """Read MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE.

    Host defaults to 127.0.0.1, port to 3306, user to tickets, and the
    database name to tickets. The password has no default. Pass database to
    use a different name (tests do this) while keeping the other settings.
    """
    return DbConfig(
        host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ.get("MYSQL_USER", "tickets"),
        password=os.environ.get("MYSQL_PASSWORD", ""),
        database=database if database is not None else os.environ.get("MYSQL_DATABASE", "tickets"),
    )


def connect(config: DbConfig) -> pymysql.Connection:
    """Open the MySQL database, creating it first when it is missing."""
    _ensure_database(config)
    try:
        return pymysql.connect(
            host=config.host,
            port=config.port,
            user=config.user,
            password=config.password,
            database=config.database,
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=False,
            connect_timeout=5,
        )
    except pymysql.Error as exc:
        raise UnavailableError("Service unavailable") from exc


def drop_database(config: DbConfig) -> None:
    """Remove a database. Tests use this to clean up."""
    name = _quote_db(config.database)
    try:
        conn = _server_connect(config)
    except pymysql.Error as exc:
        raise UnavailableError("Service unavailable") from exc
    try:
        with conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {name}")
    except pymysql.Error as exc:
        raise UnavailableError("Service unavailable") from exc
    finally:
        conn.close()


def init_db(conn: pymysql.Connection) -> None:
    """Create the tables and indexes if they are not already there."""
    try:
        with conn.cursor() as cur:
            cur.execute(_TICKETS_TABLE)
            cur.execute(_NOTES_TABLE)
    except pymysql.Error as exc:
        raise UnavailableError("Service unavailable") from exc


def reset_db(conn: pymysql.Connection) -> None:
    """Drop both tables and create them again. Notes go first (foreign key)."""
    try:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS notes")
            cur.execute("DROP TABLE IF EXISTS tickets")
    except pymysql.Error as exc:
        raise UnavailableError("Service unavailable") from exc
    init_db(conn)


def seed_if_empty(conn: pymysql.Connection, data: dict) -> None:
    """Insert sample tickets and notes when the tickets table has no rows."""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS ticket_count FROM tickets")
            count = cur.fetchone()["ticket_count"]
            if count:
                return
            for ticket in data.get("tickets") or []:
                updated_at = ticket.get("updated_at", ticket["created_at"])
                cur.execute(
                    _INSERT_TICKET,
                    (
                        ticket["ticket_id"],
                        ticket["title"],
                        ticket["description"],
                        ticket["requester_name"],
                        ticket["requester_email"],
                        ticket["category"],
                        ticket["priority"],
                        ticket["status"],
                        ticket["created_at"],
                        updated_at,
                    ),
                )
            for note in data.get("notes") or []:
                cur.execute(
                    _INSERT_NOTE_WITH_ID,
                    (
                        note["note_id"],
                        note["ticket_id"],
                        note["author"],
                        note["body"],
                        note["created_at"],
                    ),
                )
        conn.commit()
    except pymysql.Error as exc:
        conn.rollback()
        raise UnavailableError("Service unavailable") from exc


def ping(conn: pymysql.Connection) -> None:
    """Confirm the database accepts a query."""
    _read(conn, "SELECT 1")


def list_tickets(
    conn: pymysql.Connection,
    status: str | None,
    priority: str | None,
) -> list[dict]:
    """Ticket rows, highest priority first, then newest."""
    rows = _read(
        conn,
        f"""
        SELECT {_TICKET_COLUMNS}
        FROM tickets
        WHERE (%s IS NULL OR status = %s)
          AND (%s IS NULL OR priority = %s)
        ORDER BY
          CASE priority
            WHEN 'Urgent' THEN 1
            WHEN 'High' THEN 2
            WHEN 'Medium' THEN 3
            WHEN 'Low' THEN 4
          END,
          created_at DESC
        """,
        (status, status, priority, priority),
    )
    return [_row_dict(row, TICKET_FIELDS) for row in rows]


def list_ticket_ids(conn: pymysql.Connection) -> list[str]:
    """Every ticket id, used to choose the next HD- number."""
    rows = _read(conn, "SELECT ticket_id FROM tickets")
    return [row["ticket_id"] for row in rows]


def get_ticket(conn: pymysql.Connection, ticket_id: str) -> dict | None:
    """One ticket plus its notes, oldest first. None when the id is missing."""
    rows = _read(
        conn,
        f"SELECT {_TICKET_COLUMNS} FROM tickets WHERE ticket_id = %s",
        (ticket_id,),
    )
    if not rows:
        return None
    ticket = _row_dict(rows[0], TICKET_FIELDS)
    notes = _read(
        conn,
        f"""
        SELECT {_NOTE_COLUMNS}
        FROM notes
        WHERE ticket_id = %s
        ORDER BY created_at ASC, note_id ASC
        """,
        (ticket_id,),
    )
    ticket["notes"] = [_row_dict(note, NOTE_FIELDS) for note in notes]
    return ticket


def insert_ticket_with_note(conn: pymysql.Connection, ticket: dict, note: dict) -> None:
    """Insert a ticket and its opening note in one transaction."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                _INSERT_TICKET,
                tuple(ticket[field] for field in TICKET_FIELDS),
            )
            cur.execute(
                _INSERT_NOTE,
                (note["ticket_id"], note["author"], note["body"], note["created_at"]),
            )
        conn.commit()
    except pymysql.Error as exc:
        conn.rollback()
        raise UnavailableError("Service unavailable") from exc


def save_status(
    conn: pymysql.Connection,
    ticket_id: str,
    status: str,
    updated_at: str,
) -> bool:
    """Update status and updated_at. False when the ticket does not exist."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM tickets WHERE ticket_id = %s",
                (ticket_id,),
            )
            found = cur.fetchone()
            if found is None:
                return False
            cur.execute(
                "UPDATE tickets SET status = %s, updated_at = %s WHERE ticket_id = %s",
                (status, updated_at, ticket_id),
            )
        conn.commit()
        return True
    except pymysql.Error as exc:
        conn.rollback()
        raise UnavailableError("Service unavailable") from exc


def insert_note(
    conn: pymysql.Connection,
    ticket_id: str,
    author: str,
    body: str,
    created_at: str,
) -> dict:
    """Append a note and return it, including the id MySQL assigned."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                _INSERT_NOTE,
                (ticket_id, author, body, created_at),
            )
            note_id = cur.lastrowid
        conn.commit()
    except pymysql.Error as exc:
        conn.rollback()
        raise UnavailableError("Service unavailable") from exc
    return {
        "note_id": note_id,
        "ticket_id": ticket_id,
        "author": author,
        "body": body,
        "created_at": created_at,
    }


def _server_connect(config: DbConfig) -> pymysql.Connection:
    """Connect without selecting a database, so it can be created or dropped."""
    return pymysql.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=True,
        connect_timeout=5,
    )


def _ensure_database(config: DbConfig) -> None:
    name = _quote_db(config.database)
    try:
        conn = _server_connect(config)
    except pymysql.Error as exc:
        raise UnavailableError("Service unavailable") from exc
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS {name} "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    except pymysql.Error as exc:
        raise UnavailableError("Service unavailable") from exc
    finally:
        conn.close()


def _quote_db(name: str) -> str:
    if not _DB_NAME.match(name):
        raise UnavailableError("Service unavailable")
    return f"`{name}`"


def _read(conn: pymysql.Connection, sql: str, params: tuple = ()) -> list[dict]:
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())
    except pymysql.Error as exc:
        raise UnavailableError("Service unavailable") from exc


def _row_dict(row: dict, fields: tuple[str, ...]) -> dict:
    return {field: row[field] for field in fields}

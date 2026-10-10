"""SQLite schema and queries for tickets and notes.

Connection setup and SQL stay in this module so a later hosted database can
replace them without changing ticket rules or HTTP routes.
"""

import sqlite3
from pathlib import Path

# Spec schema (it-ticket-system-specs/db.md). IF NOT EXISTS keeps a restart
# from wiping an existing file.
SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
  ticket_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  requester_name TEXT NOT NULL,
  requester_email TEXT NOT NULL,
  category TEXT NOT NULL CHECK (category IN ('Hardware', 'Software', 'Network', 'Account', 'Other')),
  priority TEXT NOT NULL CHECK (priority IN ('Low', 'Medium', 'High', 'Urgent')),
  status TEXT NOT NULL CHECK (status IN ('Open', 'In progress', 'Resolved')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notes (
  note_id INTEGER PRIMARY KEY,
  ticket_id TEXT NOT NULL REFERENCES tickets (ticket_id),
  author TEXT NOT NULL CHECK (author IN ('System', 'IT staff')),
  body TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tickets_created_at ON tickets (created_at);
CREATE INDEX IF NOT EXISTS idx_notes_ticket_created ON notes (ticket_id, created_at);
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
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_INSERT_NOTE = """
INSERT INTO notes (ticket_id, author, body, created_at)
VALUES (?, ?, ?, ?)
"""

_INSERT_NOTE_WITH_ID = f"""
INSERT INTO notes ({_NOTE_COLUMNS})
VALUES (?, ?, ?, ?, ?)
"""


class UnavailableError(Exception):
    """Raised when the database cannot be reached or a statement fails."""


def connect(path: str | Path) -> sqlite3.Connection:
    """Open the SQLite file. Foreign keys are enforced on this connection."""
    try:
        conn = sqlite3.connect(path, timeout=5)
    except sqlite3.Error as exc:
        raise UnavailableError("Service unavailable") from exc
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
    except sqlite3.Error as exc:
        conn.close()
        raise UnavailableError("Service unavailable") from exc
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create the tables and indexes if they are not already there."""
    try:
        conn.executescript(SCHEMA)
    except sqlite3.Error as exc:
        raise UnavailableError("Service unavailable") from exc


def seed_if_empty(conn: sqlite3.Connection, data: dict) -> None:
    """Insert sample tickets and notes when the tickets table has no rows."""
    try:
        count = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        if count:
            return
        for ticket in data.get("tickets") or []:
            updated_at = ticket.get("updated_at", ticket["created_at"])
            conn.execute(
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
            conn.execute(
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
    except sqlite3.Error as exc:
        conn.rollback()
        raise UnavailableError("Service unavailable") from exc


def ping(conn: sqlite3.Connection) -> None:
    """Confirm the database accepts a query."""
    _read(conn, "SELECT 1")


def list_tickets(
    conn: sqlite3.Connection,
    status: str | None,
    priority: str | None,
) -> list[dict]:
    """Ticket rows, highest priority first, then newest."""
    rows = _read(
        conn,
        f"""
        SELECT {_TICKET_COLUMNS}
        FROM tickets
        WHERE (? IS NULL OR status = ?)
          AND (? IS NULL OR priority = ?)
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


def list_ticket_ids(conn: sqlite3.Connection) -> list[str]:
    """Every ticket id, used to choose the next HD- number."""
    rows = _read(conn, "SELECT ticket_id FROM tickets")
    return [row["ticket_id"] for row in rows]


def get_ticket(conn: sqlite3.Connection, ticket_id: str) -> dict | None:
    """One ticket plus its notes, oldest first. None when the id is missing."""
    rows = _read(
        conn,
        f"SELECT {_TICKET_COLUMNS} FROM tickets WHERE ticket_id = ?",
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
        WHERE ticket_id = ?
        ORDER BY created_at ASC, note_id ASC
        """,
        (ticket_id,),
    )
    ticket["notes"] = [_row_dict(note, NOTE_FIELDS) for note in notes]
    return ticket


def insert_ticket_with_note(conn: sqlite3.Connection, ticket: dict, note: dict) -> None:
    """Insert a ticket and its opening note in one transaction."""
    try:
        conn.execute(
            _INSERT_TICKET,
            tuple(ticket[field] for field in TICKET_FIELDS),
        )
        conn.execute(
            _INSERT_NOTE,
            (note["ticket_id"], note["author"], note["body"], note["created_at"]),
        )
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        raise UnavailableError("Service unavailable") from exc


def save_status(
    conn: sqlite3.Connection,
    ticket_id: str,
    status: str,
    updated_at: str,
) -> bool:
    """Update status and updated_at. False when the ticket does not exist."""
    try:
        found = conn.execute(
            "SELECT 1 FROM tickets WHERE ticket_id = ?",
            (ticket_id,),
        ).fetchone()
        if found is None:
            return False
        conn.execute(
            "UPDATE tickets SET status = ?, updated_at = ? WHERE ticket_id = ?",
            (status, updated_at, ticket_id),
        )
        conn.commit()
        return True
    except sqlite3.Error as exc:
        conn.rollback()
        raise UnavailableError("Service unavailable") from exc


def insert_note(
    conn: sqlite3.Connection,
    ticket_id: str,
    author: str,
    body: str,
    created_at: str,
) -> dict:
    """Append a note and return it, including the id SQLite assigned."""
    try:
        cursor = conn.execute(
            _INSERT_NOTE,
            (ticket_id, author, body, created_at),
        )
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        raise UnavailableError("Service unavailable") from exc
    return {
        "note_id": cursor.lastrowid,
        "ticket_id": ticket_id,
        "author": author,
        "body": body,
        "created_at": created_at,
    }


def _read(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.Error as exc:
        raise UnavailableError("Service unavailable") from exc


def _row_dict(row: sqlite3.Row, fields: tuple[str, ...]) -> dict:
    return {field: row[field] for field in fields}

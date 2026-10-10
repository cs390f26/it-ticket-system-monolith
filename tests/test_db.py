import pytest

import db
from db import UnavailableError


def test_failed_opening_note_does_not_leave_a_ticket(tmp_path):
    path = tmp_path / "tickets.db"
    conn = db.connect(path)
    try:
        db.init_db(conn)
        with pytest.raises(UnavailableError):
            db.insert_ticket_with_note(
                conn,
                {
                    "ticket_id": "HD-1001",
                    "title": "Seed ticket",
                    "description": "Used to check rollback.",
                    "requester_name": "Ada",
                    "requester_email": "ada@college.edu",
                    "category": "Other",
                    "priority": "Low",
                    "status": "Open",
                    "created_at": "2026-09-01T10:00:00.000Z",
                    "updated_at": "2026-09-01T10:00:00.000Z",
                },
                {
                    "ticket_id": "HD-1001",
                    "author": "Nobody",
                    "body": "Ticket opened by requester.",
                    "created_at": "2026-09-01T10:00:00.000Z",
                },
            )
        assert db.list_tickets(conn, None, None) == []
    finally:
        conn.close()

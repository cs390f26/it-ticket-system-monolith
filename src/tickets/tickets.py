import json
import re
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import db
from db import UnavailableError

CATEGORIES = ("Hardware", "Software", "Network", "Account", "Other")
PRIORITIES = ("Low", "Medium", "High", "Urgent")
STATUSES = ("Open", "In progress", "Resolved")

DEFAULT_PRIORITY = "Medium"
OPENING_NOTE = "Ticket opened by requester."

# "name@domain": one @, no spaces, something on each side.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+$")

TICKET_ID_PREFIX = "HD-"
FIRST_TICKET_NUMBER = 1001


class ValidationError(Exception):
    """Raised when input breaks a ticket rule (blank title, bad status, etc.)."""


class NotFoundError(Exception):
    """Raised when a ticket id does not exist."""


def _now() -> str:
    """Current UTC time in the spec's format, e.g. 2026-09-11T09:14:00.000Z."""
    stamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    return stamp.replace("+00:00", "Z")


def _clean_text(data: dict, field: str, label: str, min_len: int, max_len: int) -> str:
    """Trim a required text field and check its length."""
    value = data.get(field)
    if value is None:
        raise ValidationError(f"{label} is required")
    if not isinstance(value, str):
        raise ValidationError(f"{label} must be text")
    value = value.strip()
    if not value:
        raise ValidationError(f"{label} is required")
    if len(value) < min_len:
        raise ValidationError(f"{label} must be at least {min_len} characters")
    if len(value) > max_len:
        raise ValidationError(f"{label} must be at most {max_len} characters")
    return value


def _check_choice(value, choices: tuple, message: str) -> str:
    if value not in choices:
        raise ValidationError(message)
    return value


def _next_ticket_id(ticket_ids: list[str]) -> str:
    numbers = [
        int(ticket_id[len(TICKET_ID_PREFIX):])
        for ticket_id in ticket_ids
        if ticket_id.startswith(TICKET_ID_PREFIX)
        and ticket_id[len(TICKET_ID_PREFIX):].isdigit()
    ]
    next_number = max(numbers) + 1 if numbers else FIRST_TICKET_NUMBER
    return f"{TICKET_ID_PREFIX}{next_number}"


CATEGORY_MESSAGE = "Category must be Hardware, Software, Network, Account, or Other"
PRIORITY_MESSAGE = "Priority must be Low, Medium, High, or Urgent"
STATUS_MESSAGE = "Status must be Open, In progress, or Resolved"


class TicketApp:
    """Ticket rules for the help desk.

    Rows live in MySQL. Validation stays here; queries stay in db.py.
    updated_at starts equal to created_at and changes only when the status
    is saved.
    """

    def __init__(self, config: db.DbConfig):
        self._config = config
        self._lock = threading.Lock()

    @classmethod
    def from_file(cls, data_path: str | Path, config: db.DbConfig | None = None) -> "TicketApp":
        """Create the schema and seed an empty database from a JSON file."""
        with open(data_path, encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_data(data, config)

    @classmethod
    def from_data(cls, data: dict, config: db.DbConfig | None = None) -> "TicketApp":
        """Create the schema and seed an empty database from ticket and note rows."""
        config = config or db.config_from_env()
        conn = db.connect(config)
        try:
            db.init_db(conn)
            db.seed_if_empty(conn, data)
        finally:
            conn.close()
        return cls(config)

    @classmethod
    def empty(cls, config: db.DbConfig | None = None) -> "TicketApp":
        """Create the schema with no tickets."""
        return cls.from_data({"tickets": [], "notes": []}, config)

    @contextmanager
    def _connection(self):
        conn = db.connect(self._config)
        try:
            yield conn
        finally:
            conn.close()

    def health(self) -> None:
        """Raise UnavailableError when the database cannot be queried."""
        with self._connection() as conn:
            db.ping(conn)

    def list_tickets(self, status: str | None = None, priority: str | None = None) -> list[dict]:
        """Ticket rows, highest priority first, then newest. Filters are optional."""
        if status is not None:
            _check_choice(status, STATUSES, STATUS_MESSAGE)
        if priority is not None:
            _check_choice(priority, PRIORITIES, PRIORITY_MESSAGE)

        with self._lock, self._connection() as conn:
            return db.list_tickets(conn, status, priority)

    def create_ticket(self, data: dict) -> str:
        """Validate a submit, store it as Open with the opening note, return its id."""
        requester_name = _clean_text(data, "requesterName", "Name", 1, 80)
        requester_email = _clean_text(data, "requesterEmail", "Email", 3, 120)
        if not EMAIL_PATTERN.match(requester_email):
            raise ValidationError("Email must look like name@domain")
        category = _check_choice(data.get("category"), CATEGORIES, CATEGORY_MESSAGE)
        priority = data.get("priority")
        if priority is None:
            priority = DEFAULT_PRIORITY
        _check_choice(priority, PRIORITIES, PRIORITY_MESSAGE)
        title = _clean_text(data, "title", "Title", 1, 120)
        description = _clean_text(data, "description", "Description", 1, 2000)

        with self._lock, self._connection() as conn:
            ticket_id = _next_ticket_id(db.list_ticket_ids(conn))
            created_at = _now()
            db.insert_ticket_with_note(
                conn,
                {
                    "ticket_id": ticket_id,
                    "title": title,
                    "description": description,
                    "requester_name": requester_name,
                    "requester_email": requester_email,
                    "category": category,
                    "priority": priority,
                    "status": "Open",
                    "created_at": created_at,
                    "updated_at": created_at,
                },
                {
                    "ticket_id": ticket_id,
                    "author": "System",
                    "body": OPENING_NOTE,
                    "created_at": created_at,
                },
            )
        return ticket_id

    def get_ticket(self, ticket_id: str) -> dict:
        """One ticket row plus updated_at and its notes (oldest first)."""
        with self._lock, self._connection() as conn:
            ticket = db.get_ticket(conn, ticket_id)
        if ticket is None:
            raise NotFoundError(f"ticket {ticket_id!r} not found")
        return ticket

    def update_status(self, ticket_id: str, status) -> dict:
        """Save a new status and return the full ticket."""
        _check_choice(status, STATUSES, STATUS_MESSAGE)
        with self._lock, self._connection() as conn:
            saved = db.save_status(conn, ticket_id, status, _now())
            if not saved:
                raise NotFoundError(f"ticket {ticket_id!r} not found")
            return db.get_ticket(conn, ticket_id)

    def add_note(self, ticket_id: str, data: dict) -> dict:
        """Append an IT staff note and return it."""
        body = _clean_text(data, "body", "Note", 1, 1000)
        with self._lock, self._connection() as conn:
            if db.get_ticket(conn, ticket_id) is None:
                raise NotFoundError(f"ticket {ticket_id!r} not found")
            return db.insert_note(conn, ticket_id, "IT staff", body, _now())

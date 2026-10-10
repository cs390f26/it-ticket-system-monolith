import json
import re
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

CATEGORIES = ("Hardware", "Software", "Network", "Account", "Other")
PRIORITIES = ("Low", "Medium", "High", "Urgent")
STATUSES = ("Open", "In progress", "Resolved")

DEFAULT_PRIORITY = "Medium"
OPENING_NOTE = "Ticket opened by requester."

# Queue order: Urgent first, Low last.
PRIORITY_RANK = {"Urgent": 1, "High": 2, "Medium": 3, "Low": 4}

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


CATEGORY_MESSAGE = "Category must be Hardware, Software, Network, Account, or Other"
PRIORITY_MESSAGE = "Priority must be Low, Medium, High, or Urgent"
STATUS_MESSAGE = "Status must be Open, In progress, or Resolved"


class TicketApp:
    """Ticket rules for the help desk.

    Tickets and notes are kept in plain in-memory lists for now and reset on
    every restart. Rows use the column names from the specs (ticket_id,
    created_at, updated_at, ...). updated_at starts equal to created_at and
    changes only when the status is saved.
    """

    def __init__(self, tickets: list[dict] | None = None, notes: list[dict] | None = None):
        self._tickets = deepcopy(tickets or [])
        self._notes = deepcopy(notes or [])
        for ticket in self._tickets:
            ticket.setdefault("updated_at", ticket["created_at"])
        self._lock = threading.Lock()

    @classmethod
    def from_file(cls, path: str | Path) -> "TicketApp":
        """Build a TicketApp seeded from a sample data JSON file."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls(data.get("tickets", []), data.get("notes", []))

    def health(self) -> None:
        """Nothing can be unavailable while data lives in memory."""

    def list_tickets(self, status: str | None = None, priority: str | None = None) -> list[dict]:
        """Ticket rows, highest priority first, then newest. Filters are optional."""
        if status is not None:
            _check_choice(status, STATUSES, STATUS_MESSAGE)
        if priority is not None:
            _check_choice(priority, PRIORITIES, PRIORITY_MESSAGE)

        with self._lock:
            rows = [
                deepcopy(t)
                for t in self._tickets
                if (status is None or t["status"] == status)
                and (priority is None or t["priority"] == priority)
            ]

        rows.sort(key=lambda t: t["created_at"], reverse=True)
        rows.sort(key=lambda t: PRIORITY_RANK[t["priority"]])
        return rows

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

        with self._lock:
            ticket_id = self._next_ticket_id()
            created_at = _now()
            self._tickets.append(
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
                }
            )
            self._notes.append(self._new_note(ticket_id, "System", OPENING_NOTE, created_at))
        return ticket_id

    def get_ticket(self, ticket_id: str) -> dict:
        """One ticket row plus updated_at and its notes (oldest first)."""
        with self._lock:
            return self._ticket_with_notes(ticket_id)

    def update_status(self, ticket_id: str, status) -> dict:
        """Save a new status and return the full ticket."""
        _check_choice(status, STATUSES, STATUS_MESSAGE)
        with self._lock:
            ticket = self._find(ticket_id)
            ticket["status"] = status
            ticket["updated_at"] = _now()
            return self._ticket_with_notes(ticket_id)

    def add_note(self, ticket_id: str, data: dict) -> dict:
        """Append an IT staff note and return it."""
        body = _clean_text(data, "body", "Note", 1, 1000)
        with self._lock:
            self._find(ticket_id)
            note = self._new_note(ticket_id, "IT staff", body, _now())
            self._notes.append(note)
            return deepcopy(note)

    def _find(self, ticket_id: str) -> dict:
        for ticket in self._tickets:
            if ticket["ticket_id"] == ticket_id:
                return ticket
        raise NotFoundError(f"ticket {ticket_id!r} not found")

    def _ticket_with_notes(self, ticket_id: str) -> dict:
        ticket = deepcopy(self._find(ticket_id))
        notes = [deepcopy(n) for n in self._notes if n["ticket_id"] == ticket_id]
        notes.sort(key=lambda n: (n["created_at"], n["note_id"]))
        ticket["notes"] = notes
        return ticket

    def _next_ticket_id(self) -> str:
        numbers = [
            int(t["ticket_id"][len(TICKET_ID_PREFIX):])
            for t in self._tickets
            if t["ticket_id"].startswith(TICKET_ID_PREFIX)
            and t["ticket_id"][len(TICKET_ID_PREFIX):].isdigit()
        ]
        next_number = max(numbers) + 1 if numbers else FIRST_TICKET_NUMBER
        return f"{TICKET_ID_PREFIX}{next_number}"

    def _new_note(self, ticket_id: str, author: str, body: str, created_at: str) -> dict:
        next_id = max((n["note_id"] for n in self._notes), default=0) + 1
        return {
            "note_id": next_id,
            "ticket_id": ticket_id,
            "author": author,
            "body": body,
            "created_at": created_at,
        }

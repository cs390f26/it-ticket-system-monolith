import pytest

from tickets.tickets import NotFoundError, TicketApp, ValidationError

SAMPLE_QUEUE_ORDER = ["HD-1043", "HD-1046", "HD-1042", "HD-1044", "HD-1047", "HD-1045"]


def test_queue_order_priority_then_newest(ticket_app):
    ids = [t["ticket_id"] for t in ticket_app.list_tickets()]
    assert ids == SAMPLE_QUEUE_ORDER


def test_filter_by_status(ticket_app):
    rows = ticket_app.list_tickets(status="In progress")
    assert [t["ticket_id"] for t in rows] == ["HD-1043", "HD-1047"]


def test_filter_by_status_and_priority(ticket_app):
    rows = ticket_app.list_tickets(status="Open", priority="High")
    assert [t["ticket_id"] for t in rows] == ["HD-1046", "HD-1042"]


def test_filter_no_matches_is_empty(ticket_app):
    assert ticket_app.list_tickets(status="Resolved", priority="Urgent") == []


def test_bad_filter_rejected(ticket_app):
    with pytest.raises(ValidationError):
        ticket_app.list_tickets(status="Waiting for user info")


def test_create_trims_defaults_and_adds_opening_note(ticket_app, valid_submit):
    del valid_submit["priority"]
    ticket_id = ticket_app.create_ticket(valid_submit)

    assert ticket_id == "HD-1048"
    ticket = ticket_app.get_ticket(ticket_id)
    assert ticket["requester_name"] == "Sam Ortiz"
    assert ticket["title"] == "Zoom crashes on launch"
    assert ticket["priority"] == "Medium"
    assert ticket["status"] == "Open"
    assert ticket["updated_at"] == ticket["created_at"]
    assert [(n["author"], n["body"]) for n in ticket["notes"]] == [
        ("System", "Ticket opened by requester.")
    ]


def test_first_ticket_id_when_empty(empty_app, valid_submit):
    assert empty_app.create_ticket(valid_submit) == "HD-1001"


@pytest.mark.parametrize(
    "field, value, message",
    [
        ("title", "   ", "Title is required"),
        ("title", "x" * 121, "Title must be at most 120 characters"),
        ("requesterName", None, "Name is required"),
        ("requesterEmail", "not-an-email", "Email must look like name@domain"),
        ("description", "x" * 2001, "Description must be at most 2000 characters"),
        ("category", "Printer", "Category must be"),
        ("priority", "Critical", "Priority must be"),
    ],
)
def test_create_validation(ticket_app, valid_submit, field, value, message):
    valid_submit[field] = value
    with pytest.raises(ValidationError, match=message):
        ticket_app.create_ticket(valid_submit)


def test_update_status_sets_updated_at(ticket_app):
    ticket = ticket_app.update_status("HD-1042", "In progress")
    assert ticket["status"] == "In progress"
    assert ticket["updated_at"] > ticket["created_at"]
    assert ticket_app.get_ticket("HD-1042")["updated_at"] == ticket["updated_at"]


def test_update_status_does_not_add_note(ticket_app):
    before = len(ticket_app.get_ticket("HD-1042")["notes"])
    ticket_app.update_status("HD-1042", "Resolved")
    assert len(ticket_app.get_ticket("HD-1042")["notes"]) == before


def test_update_status_invalid(ticket_app):
    with pytest.raises(ValidationError, match="Status must be"):
        ticket_app.update_status("HD-1042", "Closed")


def test_add_note_keeps_status_and_updated_at(ticket_app):
    before = ticket_app.get_ticket("HD-1042")
    note = ticket_app.add_note("HD-1042", {"body": "  Checked the access point.  "})
    after = ticket_app.get_ticket("HD-1042")

    assert note["author"] == "IT staff"
    assert note["body"] == "Checked the access point."
    assert note["note_id"] == 11
    assert after["status"] == before["status"]
    assert after["updated_at"] == before["updated_at"]
    assert after["notes"][-1]["note_id"] == 11


def test_blank_note_rejected(ticket_app):
    with pytest.raises(ValidationError, match="Note is required"):
        ticket_app.add_note("HD-1042", {"body": "   "})


def test_notes_oldest_first(ticket_app):
    notes = ticket_app.get_ticket("HD-1047")["notes"]
    assert [n["note_id"] for n in notes] == [6, 7, 8]


@pytest.mark.parametrize("call", ["get", "status", "note"])
def test_unknown_ticket(ticket_app, call):
    with pytest.raises(NotFoundError):
        if call == "get":
            ticket_app.get_ticket("HD-0000")
        elif call == "status":
            ticket_app.update_status("HD-0000", "Open")
        else:
            ticket_app.add_note("HD-0000", {"body": "hello"})


def test_returned_rows_are_copies(ticket_app):
    ticket_app.get_ticket("HD-1042")["status"] = "Resolved"
    assert ticket_app.get_ticket("HD-1042")["status"] == "Open"


def test_seed_keeps_stored_updated_at():
    tickets = [
        {
            "ticket_id": "HD-1",
            "priority": "Low",
            "status": "Resolved",
            "created_at": "2026-09-01T10:00:00.000Z",
            "updated_at": "2026-09-02T15:30:00.000Z",
        }
    ]
    assert TicketApp(tickets).get_ticket("HD-1")["updated_at"] == "2026-09-02T15:30:00.000Z"


def test_seed_data_is_not_shared():
    tickets = [{"ticket_id": "HD-1", "priority": "Low", "status": "Open", "created_at": "x"}]
    TicketApp(tickets).update_status("HD-1", "Resolved")
    assert tickets[0]["status"] == "Open"

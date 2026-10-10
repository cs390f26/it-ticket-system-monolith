import pytest

from tickets.app import DEFAULT_DATA_FILE, create_app
from tickets.tickets import TicketApp


@pytest.fixture
def ticket_app(tmp_path):
    """A fresh TicketApp seeded with the sample data for every test."""
    return TicketApp.from_file(DEFAULT_DATA_FILE, tmp_path / "tickets.db")


@pytest.fixture
def empty_app(tmp_path):
    return TicketApp.empty(tmp_path / "empty.db")


@pytest.fixture
def client(ticket_app):
    flask_app = create_app(ticket_app)
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


@pytest.fixture
def valid_submit():
    return {
        "requesterName": "  Sam Ortiz  ",
        "requesterEmail": "sam.ortiz@college.edu",
        "category": "Software",
        "priority": "High",
        "title": "  Zoom crashes on launch  ",
        "description": "Zoom closes right after the splash screen.",
    }

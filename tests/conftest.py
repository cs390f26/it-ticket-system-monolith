import uuid

import pytest

import db
from tickets.app import DEFAULT_DATA_FILE, create_app
from tickets.tickets import TicketApp


@pytest.fixture
def mysql_config():
    """A private database for one test, dropped when the test ends."""
    config = db.config_from_env(database=f"tickets_test_{uuid.uuid4().hex}")
    yield config
    db.drop_database(config)


@pytest.fixture
def ticket_app(mysql_config):
    """A fresh TicketApp seeded with the sample data for every test."""
    return TicketApp.from_file(DEFAULT_DATA_FILE, mysql_config)


@pytest.fixture
def empty_app(mysql_config):
    return TicketApp.empty(mysql_config)


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

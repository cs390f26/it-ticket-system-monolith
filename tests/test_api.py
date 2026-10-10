import pytest

from db import UnavailableError


def test_health_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_list_tickets(client):
    response = client.get("/tickets")
    assert response.status_code == 200
    tickets = response.get_json()["tickets"]
    assert len(tickets) == 6
    assert tickets[0] == {
        "id": "HD-1043",
        "title": "Laptop will not boot after update",
        "requesterName": "Jordan Lee",
        "category": "Hardware",
        "priority": "Urgent",
        "status": "In progress",
        "createdAt": "2026-09-10T15:40:00.000Z",
    }


def test_list_tickets_with_filters(client):
    response = client.get("/tickets", query_string={"status": "Open", "priority": "High"})
    assert response.status_code == 200
    assert [t["id"] for t in response.get_json()["tickets"]] == ["HD-1046", "HD-1042"]


def test_list_tickets_empty_filter_value_ignored(client):
    response = client.get("/tickets?status=&priority=")
    assert response.status_code == 200
    assert len(response.get_json()["tickets"]) == 6


def test_list_tickets_no_matches(client):
    response = client.get("/tickets", query_string={"status": "Resolved", "priority": "Urgent"})
    assert response.status_code == 200
    assert response.get_json() == {"tickets": []}


def test_list_tickets_bad_filter(client):
    response = client.get("/tickets", query_string={"priority": "Critical"})
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "BAD_REQUEST"


def test_list_tickets_empty_store(empty_app):
    from tickets.app import create_app

    response = create_app(empty_app).test_client().get("/tickets")
    assert response.get_json() == {"tickets": []}


def test_create_then_get(client, valid_submit):
    response = client.post("/tickets", json=valid_submit)
    assert response.status_code == 201
    assert response.get_json() == {"id": "HD-1048"}

    ticket = client.get("/tickets/HD-1048").get_json()
    assert ticket["title"] == "Zoom crashes on launch"
    assert ticket["requesterName"] == "Sam Ortiz"
    assert ticket["priority"] == "High"
    assert ticket["status"] == "Open"
    assert ticket["updatedAt"] == ticket["createdAt"]
    assert ticket["notes"][0]["author"] == "System"


def test_create_missing_title(client, valid_submit):
    del valid_submit["title"]
    response = client.post("/tickets", json=valid_submit)
    assert response.status_code == 400
    assert response.get_json() == {
        "error": {"code": "BAD_REQUEST", "message": "Title is required"}
    }


def test_create_bad_email(client, valid_submit):
    valid_submit["requesterEmail"] = "sam"
    response = client.post("/tickets", json=valid_submit)
    assert response.status_code == 400
    assert response.get_json()["error"]["message"] == "Email must look like name@domain"


@pytest.mark.parametrize("data", [None, "not json", "[1, 2]"])
def test_create_requires_json_object(client, data):
    response = client.post("/tickets", data=data, content_type="application/json")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "BAD_REQUEST"


def test_get_ticket(client):
    response = client.get("/tickets/HD-1042")
    assert response.status_code == 200
    ticket = response.get_json()
    assert ticket["id"] == "HD-1042"
    assert ticket["requesterEmail"] == "maya.chen@college.edu"
    assert ticket["updatedAt"] == "2026-09-11T09:14:00.000Z"
    assert ticket["notes"] == [
        {
            "id": 4,
            "author": "System",
            "body": "Ticket opened by requester.",
            "createdAt": "2026-09-11T09:14:00.000Z",
        }
    ]


def test_get_ticket_not_found(client):
    response = client.get("/tickets/HD-0000")
    assert response.status_code == 404
    assert response.get_json() == {
        "error": {"code": "TICKET_NOT_FOUND", "message": "Ticket not found"}
    }


def test_update_status(client):
    response = client.patch("/tickets/HD-1042", json={"status": "In progress"})
    assert response.status_code == 200
    ticket = response.get_json()
    assert ticket["status"] == "In progress"
    assert ticket["updatedAt"] > ticket["createdAt"]
    assert len(ticket["notes"]) == 1


def test_update_status_invalid(client):
    response = client.patch("/tickets/HD-1042", json={"status": "Closed"})
    assert response.status_code == 400
    assert response.get_json()["error"]["message"] == (
        "Status must be Open, In progress, or Resolved"
    )


def test_update_status_missing(client):
    response = client.patch("/tickets/HD-1042", json={})
    assert response.status_code == 400


def test_update_status_not_found(client):
    response = client.patch("/tickets/HD-0000", json={"status": "Open"})
    assert response.status_code == 404


def test_add_note(client):
    response = client.post("/tickets/HD-1042/notes", json={"body": "Checked the access point."})
    assert response.status_code == 201
    note = response.get_json()
    assert note["id"] == 11
    assert note["author"] == "IT staff"
    assert note["body"] == "Checked the access point."
    assert "createdAt" in note

    ticket = client.get("/tickets/HD-1042").get_json()
    assert ticket["notes"][-1]["id"] == 11
    assert ticket["status"] == "Open"


def test_add_note_blank(client):
    response = client.post("/tickets/HD-1042/notes", json={"body": "  "})
    assert response.status_code == 400
    assert response.get_json()["error"]["message"] == "Note is required"


def test_add_note_not_found(client):
    response = client.post("/tickets/HD-0000/notes", json={"body": "hello"})
    assert response.status_code == 404


def test_health_when_database_down(client, monkeypatch):
    def fail(path):
        raise UnavailableError("Service unavailable")

    monkeypatch.setattr("db.connect", fail)
    response = client.get("/health")
    assert response.status_code == 503
    assert response.get_json() == {"status": "unavailable"}


@pytest.mark.parametrize(
    "method, path, kwargs",
    [
        ("get", "/tickets", {}),
        ("post", "/tickets", {"json": {
            "requesterName": "Sam",
            "requesterEmail": "sam@college.edu",
            "category": "Other",
            "title": "Test",
            "description": "Testing",
        }}),
        ("get", "/tickets/HD-1042", {}),
        ("patch", "/tickets/HD-1042", {"json": {"status": "Open"}}),
        ("post", "/tickets/HD-1042/notes", {"json": {"body": "hello"}}),
    ],
)
def test_routes_when_database_down(client, monkeypatch, method, path, kwargs):
    def fail(db_path):
        raise UnavailableError("Service unavailable")

    monkeypatch.setattr("db.connect", fail)
    response = getattr(client, method)(path, **kwargs)
    assert response.status_code == 503
    assert response.get_json() == {
        "error": {"code": "SERVICE_UNAVAILABLE", "message": "Service unavailable"}
    }

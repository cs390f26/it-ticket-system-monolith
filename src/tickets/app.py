import os
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from tickets.tickets import NotFoundError, TicketApp, UnavailableError, ValidationError

DEFAULT_DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "sample_data.json"
DEFAULT_DB_FILE = Path(__file__).resolve().parents[2] / "data" / "tickets.db"


def _error(code: str, message: str, status: int):
    return jsonify({"error": {"code": code, "message": message}}), status


def _not_found():
    return _error("TICKET_NOT_FOUND", "Ticket not found", 404)


def _unavailable():
    return _error("SERVICE_UNAVAILABLE", "Service unavailable", 503)


def _summary_json(row: dict) -> dict:
    return {
        "id": row["ticket_id"],
        "title": row["title"],
        "requesterName": row["requester_name"],
        "category": row["category"],
        "priority": row["priority"],
        "status": row["status"],
        "createdAt": row["created_at"],
    }


def _note_json(row: dict) -> dict:
    return {
        "id": row["note_id"],
        "author": row["author"],
        "body": row["body"],
        "createdAt": row["created_at"],
    }


def _ticket_json(row: dict) -> dict:
    return {
        "id": row["ticket_id"],
        "title": row["title"],
        "description": row["description"],
        "requesterName": row["requester_name"],
        "requesterEmail": row["requester_email"],
        "category": row["category"],
        "priority": row["priority"],
        "status": row["status"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "notes": [_note_json(n) for n in row["notes"]],
    }


def _json_body():
    """The request's JSON object, or None if the body is missing or not an object."""
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else None


def create_app(ticket_app: TicketApp, show_ads: bool = True) -> Flask:
    """Build the Flask app and add routes."""
    app = Flask(__name__)

    @app.context_processor
    def page_settings():
        return {"show_ads": show_ads}

    @app.errorhandler(500)
    def internal_error(_exc):
        return _error("INTERNAL_ERROR", "Something went wrong on the server", 500)

    @app.get("/")
    def index_page():
        return render_template("index.html")

    @app.get("/submit")
    def submit_page():
        return render_template("submit.html", active="submit")

    @app.get("/queue")
    def queue_page():
        return render_template("queue.html", active="queue")

    @app.get("/ticket")
    def ticket_page():
        return render_template("ticket.html", active="queue")

    @app.get("/health")
    def health():
        try:
            ticket_app.health()
        except UnavailableError:
            return jsonify({"status": "unavailable"}), 503
        return jsonify({"status": "ok"}), 200

    @app.get("/tickets")
    def list_tickets():
        # An empty value (?status=) is treated the same as leaving the filter off.
        status = request.args.get("status") or None
        priority = request.args.get("priority") or None
        try:
            rows = ticket_app.list_tickets(status=status, priority=priority)
        except ValidationError as exc:
            return _error("BAD_REQUEST", str(exc), 400)
        except UnavailableError:
            return _unavailable()
        return jsonify({"tickets": [_summary_json(r) for r in rows]}), 200

    @app.post("/tickets")
    def create_ticket():
        body = _json_body()
        if body is None:
            return _error("BAD_REQUEST", "JSON body required", 400)
        try:
            ticket_id = ticket_app.create_ticket(body)
        except ValidationError as exc:
            return _error("BAD_REQUEST", str(exc), 400)
        except UnavailableError:
            return _unavailable()
        return jsonify({"id": ticket_id}), 201

    @app.get("/tickets/<ticket_id>")
    def get_ticket(ticket_id):
        try:
            row = ticket_app.get_ticket(ticket_id)
        except NotFoundError:
            return _not_found()
        except UnavailableError:
            return _unavailable()
        return jsonify(_ticket_json(row)), 200

    @app.patch("/tickets/<ticket_id>")
    def update_status(ticket_id):
        body = _json_body()
        if body is None:
            return _error("BAD_REQUEST", "JSON body required", 400)
        if "status" not in body:
            return _error("BAD_REQUEST", "Status is required", 400)
        try:
            row = ticket_app.update_status(ticket_id, body["status"])
        except ValidationError as exc:
            return _error("BAD_REQUEST", str(exc), 400)
        except NotFoundError:
            return _not_found()
        except UnavailableError:
            return _unavailable()
        return jsonify(_ticket_json(row)), 200

    @app.post("/tickets/<ticket_id>/notes")
    def add_note(ticket_id):
        body = _json_body()
        if body is None:
            return _error("BAD_REQUEST", "JSON body required", 400)
        try:
            note = ticket_app.add_note(ticket_id, body)
        except ValidationError as exc:
            return _error("BAD_REQUEST", str(exc), 400)
        except NotFoundError:
            return _not_found()
        except UnavailableError:
            return _unavailable()
        return jsonify(_note_json(note)), 201

    return app


def launch() -> Flask:
    """Build TicketApp + Flask app from environment settings (for gunicorn too).

    TICKETS_DB_PATH: SQLite file on this machine (defaults to data/tickets.db).
    TICKETS_DATA_FILE: sample data JSON used only when that database is empty
    (defaults to data/sample_data.json in this repo).
    TICKETS_SHOW_ADS: set to 0 to hide the just-for-fun ad strip.
    """
    db_path = os.environ.get("TICKETS_DB_PATH", str(DEFAULT_DB_FILE))
    data_file = os.environ.get("TICKETS_DATA_FILE", str(DEFAULT_DATA_FILE))
    show_ads = os.environ.get("TICKETS_SHOW_ADS", "1") != "0"
    return create_app(TicketApp.from_file(data_file, db_path), show_ads=show_ads)


if __name__ == "__main__":
    launch().run(debug=True, port=int(os.environ.get("PORT", "5000")))

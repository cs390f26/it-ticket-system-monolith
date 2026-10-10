# Development

## Setup

From the repo root (Python 3.12 or newer):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Run the server

```bash
python -m tickets.app
```

Open http://127.0.0.1:5000. Set `PORT` to use a different port.

Tickets are stored in a SQLite file on this machine. `TICKETS_DB_PATH` sets that file (default `data/tickets.db`). On startup the app creates the tables if needed and, when the database is empty, seeds it from `TICKETS_DATA_FILE` (default `data/sample_data.json`). A restart keeps saved tickets. `/health` checks that the database can be queried.

To serve it the way it will run on EC2 (one worker, SQLite file beside the app):

```bash
gunicorn --workers 1 --bind 0.0.0.0:8000 "tickets.app:launch()"
```

## Run the tests

```bash
pytest
```

## Layout

- `src/tickets/app.py`: Flask routes. Page routes (`/`, `/submit`, `/queue`, `/ticket?id=`) render templates; API routes (`/tickets`, `/tickets/<id>`, `/tickets/<id>/notes`, `/health`) return JSON matching `it-ticket-system-specs/openapi.yaml`.
- `src/tickets/tickets.py`: `TicketApp`, all ticket rules and validation.
- `src/tickets/templates/`: Jinja pages. Each extends `base.html`.
- `src/tickets/static/`: `styles.css` and `app.js` (shared fetch and formatting helpers).
- `src/db.py`: SQLite schema, connection, and queries.

## API quick check

```bash
curl localhost:5000/tickets
curl "localhost:5000/tickets?status=Open&priority=High"
curl localhost:5000/tickets/HD-1042
curl -X POST localhost:5000/tickets -H "Content-Type: application/json" \
  -d '{"requesterName":"Sam","requesterEmail":"sam@college.edu","category":"Other","title":"Test","description":"Testing"}'
curl -X PATCH localhost:5000/tickets/HD-1042 -H "Content-Type: application/json" -d '{"status":"In progress"}'
curl -X POST localhost:5000/tickets/HD-1042/notes -H "Content-Type: application/json" -d '{"body":"Checked the access point."}'
```

# Development

## Setup

From the repo root (Python 3.12 or newer):

```bash
python3 -m venv .venv          # create a private Python environment in .venv/
source .venv/bin/activate      # use it in this terminal (run again in each new terminal)
pip install -r requirements.txt
pip install -e .               # install this project as the "tickets" package; -e picks up code edits without reinstalling
```

## Create the database

Install MySQL 8 and start it. On macOS with Homebrew:

```bash
brew install mysql
brew services start mysql
```

Create the app user. The app connects over TCP to `127.0.0.1`, so the account is `'tickets'@'127.0.0.1'`. It needs `CREATE` so the app can create the database on first use.

```bash
mysql -u root <<'SQL'
CREATE USER IF NOT EXISTS 'tickets'@'127.0.0.1' IDENTIFIED BY 'Tickets-390!';
CREATE USER IF NOT EXISTS 'tickets'@'localhost' IDENTIFIED BY 'Tickets-390!';
GRANT ALL PRIVILEGES ON tickets.* TO 'tickets'@'127.0.0.1';
GRANT ALL PRIVILEGES ON tickets.* TO 'tickets'@'localhost';
GRANT CREATE ON *.* TO 'tickets'@'127.0.0.1';
GRANT CREATE ON *.* TO 'tickets'@'localhost';
FLUSH PRIVILEGES;
SQL
```

Use the same settings the app reads:

```bash
export MYSQL_HOST=127.0.0.1
export MYSQL_PORT=3306
export MYSQL_USER=tickets
export MYSQL_PASSWORD='Tickets-390!'
export MYSQL_DATABASE=tickets
```

Then:

```bash
python scripts/init_db.py
```

This creates the `tickets` database if needed, creates the `tickets` and `notes` tables, and loads the sample tickets from `data/sample_data.json`. Running it again is safe: it never removes tickets that are already saved.

The app also does this on startup, so this step is optional locally. On EC2, the web instance runs it against the database instance during setup.

### Reset the data

To throw away every saved ticket and go back to just the sample data, stop the server (Ctrl+C) and run:

```bash
python scripts/init_db.py --reset
```

`--reset` drops the `notes` and `tickets` tables and builds them again from the sample data.

## Run the server

```bash
python -m tickets.app
```

Open http://127.0.0.1:5000. Set `PORT` to use a different port, for example `PORT=5001 python -m tickets.app`.

On macOS, AirPlay Receiver also listens on port 5000 and answers with "403 Access denied". If you see that page, either turn off AirPlay Receiver (System Settings → General → AirDrop & Handoff) or use `PORT=5001`.

On your own machine, tickets are stored in a local MySQL server. `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, and `MYSQL_DATABASE` set that server (defaults `127.0.0.1`, `3306`, user `tickets`, database `tickets`; the password has no default). On startup the app creates the tables if needed and, when the database is empty, seeds it from `TICKETS_DATA_FILE` (default `data/sample_data.json`). A restart keeps saved tickets. `/health` checks that the database can be queried.

In production, `MYSQL_HOST` on the web instance is the database instance's private IP. See [Deploy on EC2](deploy.md).

Set `TICKETS_SHOW_ADS=0` to hide the just-for-fun ad slot.

To serve it with one gunicorn worker, the same process model as the web instance:

```bash
gunicorn --workers 1 --bind 0.0.0.0:8000 "tickets.app:launch()"
```

`gunicorn` is the production web server. `--workers 1` runs a single process, `--bind 0.0.0.0:8000` listens on port 8000 on every network address, and `"tickets.app:launch()"` tells it to call `launch()` in `src/tickets/app.py` to build the Flask app. Open http://127.0.0.1:8000.

## Run the tests

Tests use the same MySQL server and `MYSQL_*` settings as the app. Each test creates its own database and drops it when the test ends.

```bash
pytest
```

To also see how much of the code the tests cover (the same check GitHub Actions runs on every push):

```bash
pytest --cov=tickets --cov=db --cov-report=term-missing --cov-fail-under=90
```

`--cov-report=term-missing` lists the line numbers no test runs, and `--cov-fail-under=90` fails if coverage is below 90%.

## Layout

- `src/tickets/app.py`: Flask routes. Page routes (`/`, `/submit`, `/queue`, `/ticket?id=`) render templates; API routes (`/tickets`, `/tickets/<id>`, `/tickets/<id>/notes`, `/health`) return JSON matching `it-ticket-system-specs/openapi.yaml`.
- `src/tickets/tickets.py`: `TicketApp`, all ticket rules and validation.
- `src/tickets/templates/`: Jinja pages. Each extends `base.html`.
- `src/tickets/static/`: `styles.css` and `app.js` (shared fetch and formatting helpers).
- `src/db.py`: MySQL schema, connection, and queries.
- `scripts/init_db.py`: creates the tables and loads the sample data (`--reset` starts over).

## API quick check

```bash
curl 127.0.0.1:5000/tickets
curl "127.0.0.1:5000/tickets?status=Open&priority=High"
curl 127.0.0.1:5000/tickets/HD-1042
curl -X POST 127.0.0.1:5000/tickets -H "Content-Type: application/json" \
  -d '{"requesterName":"Sam","requesterEmail":"sam@college.edu","category":"Other","title":"Test","description":"Testing"}'
curl -X PATCH 127.0.0.1:5000/tickets/HD-1042 -H "Content-Type: application/json" -d '{"status":"In progress"}'
curl -X POST 127.0.0.1:5000/tickets/HD-1042/notes -H "Content-Type: application/json" -d '{"body":"Checked the access point."}'
```

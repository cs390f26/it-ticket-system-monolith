# Design

This document describes the design of the Flask server and how data moves through its layers. The web pages and the database are *delivery mechanisms* for the core application, and each one has its own layer:

1. **Browser** (`templates/*.html`, `static/app.js`): HTML pages whose JavaScript calls the JSON API with `fetch()` and draws the results.
2. **API** (`src/tickets/app.py`): handles HTTP. Parses requests, calls the application, turns results and errors into JSON responses.
3. **Application** (`src/tickets/tickets.py`, class `TicketApp`): the ticket rules. Validation, default priority, the opening note, ticket ids, timestamps.
4. **DB** (`src/db.py`): the only code that knows about SQLite. Turns application requests into SQL and SQL rows into plain Python dicts.

```
Browser  --fetch /tickets-->  app.py  --list_tickets()-->  TicketApp  --list_tickets()-->  db.py  --SQL-->  SQLite (data/tickets.db)
Browser  <--JSON-----------  app.py  <--list of dicts---  TicketApp  <--list of dicts---  db.py  <--rows--
```

Each layer only calls the one below it. The page routes (`/`, `/submit`, `/queue`, `/ticket`) return HTML with **no ticket data in it**; the page's JavaScript asks the API for the data after it loads. This is the same pattern as the voting app.

Because SQL lives only in `db.py`, a later phase can move to a hosted database by rewriting `db.py` without touching the ticket rules or the routes.

## Data representations

The data for this application is a collection of tickets, each with a list of notes.

### Database

Two tables (full schema in `it-ticket-system-specs/db.md` and `SCHEMA` in `src/db.py`):

- **`tickets`**: `ticket_id` (primary key, e.g. `HD-1042`), `title`, `description`, `requester_name`, `requester_email`, `category`, `priority`, `status`, `created_at`, `updated_at`
- **`notes`**: `note_id` (primary key), `ticket_id` (references `tickets`), `author` (`System` or `IT staff`), `body`, `created_at`

Timestamps are UTC text in the form `2026-09-11T09:14:00.000Z`. `updated_at` starts equal to `created_at` and changes only when a status is saved.

### Rows inside the server

`db.py` returns plain dicts whose keys match the column names exactly (snake_case). The application layer passes these through. For example, one ticket from `db.list_tickets()`:

```python
{
    "ticket_id": "HD-1042",
    "title": "Cannot connect to campus Wi-Fi",
    "description": "I can see Campus-Secure in the Wi-Fi list, ...",
    "requester_name": "Maya Chen",
    "requester_email": "maya.chen@college.edu",
    "category": "Network",
    "priority": "High",
    "status": "Open",
    "created_at": "2026-09-11T09:14:00.000Z",
    "updated_at": "2026-09-11T09:14:00.000Z",
}
```

`db.get_ticket()` returns the same dict plus a `"notes"` list of note dicts.

### API responses

`app.py` converts rows to the camelCase JSON in `it-ticket-system-specs/openapi.yaml`, and only includes the fields each view needs.

**Ticket summary** (`GET /tickets`, used by the queue). No description, email, or notes:

```json
{
  "tickets": [
    {
      "id": "HD-1042",
      "title": "Cannot connect to campus Wi-Fi",
      "requesterName": "Maya Chen",
      "category": "Network",
      "priority": "High",
      "status": "Open",
      "createdAt": "2026-09-11T09:14:00.000Z"
    }
  ]
}
```

**Full ticket** (`GET /tickets/<id>` and `PATCH /tickets/<id>`, used by the ticket page): every field, plus `updatedAt` and the `notes` list.

**Errors** always use one shape, for example a 404:

```json
{ "error": { "code": "TICKET_NOT_FOUND", "message": "Ticket not found" } }
```

| Exception from the application | HTTP status | `code` |
|---|---|---|
| `ValidationError` (bad input) | 400 | `BAD_REQUEST` |
| `NotFoundError` (unknown id) | 404 | `TICKET_NOT_FOUND` |
| `UnavailableError` (database failed) | 503 | `SERVICE_UNAVAILABLE` |
| Any other unexpected exception (a bug) | 500 | `INTERNAL_ERROR` |

## HTTP status codes

Which common status codes the API returns, and why the others are not used.

**Successful (2xx)**

| Code | Used? | Where |
|---|---|---|
| 200 OK | Yes | `GET /tickets`, `GET /tickets/<id>`, `PATCH /tickets/<id>`, `GET /health`, and every page route |
| 201 Created | Yes | `POST /tickets` (returns the new id) and `POST /tickets/<id>/notes` (returns the new note) |
| 204 No Content | No | Every successful call returns data the page needs (the new id, the updated ticket, or the new note), so there is nothing to send with an empty body |

**Client errors (4xx)**

| Code | Used? | Where |
|---|---|---|
| 400 Bad Request | Yes | Missing or non-JSON body, a missing or invalid field (blank title, bad email, unknown status, note too long), or an invalid queue filter |
| 401 Unauthorized | No | The app has no sign-in (a project requirement), so there are no credentials to be missing |
| 403 Forbidden | No | Without sign-in there are no users or permissions to refuse |
| 404 Not Found | Yes | A ticket id that does not exist (`TICKET_NOT_FOUND`). A URL that is not a route at all gets Flask's default 404 page |

**Server errors (5xx)**

| Code | Used? | Where |
|---|---|---|
| 500 Internal Server Error | Yes | Any unexpected exception, i.e. a bug. Returned as JSON (`INTERNAL_ERROR`) so the page can show the message. When running with `debug=True` locally, Flask shows its debugger page instead |
| 502 Bad Gateway | No | Only happens when a proxy (for example nginx or a load balancer) sits in front of gunicorn and gunicorn does not answer. On one EC2 instance, gunicorn serves requests directly |
| 503 Service Unavailable | Yes | The database cannot be opened or a query fails (`SERVICE_UNAVAILABLE`). `/health` returns `{"status": "unavailable"}` with 503 |

## Walkthrough: loading the Ticket Queue

What happens when a user opens `/queue?status=Open`:

1. **Browser requests the page.** `GET /queue?status=Open` hits `queue_page()` in `app.py`, which renders `queue.html` (extending `base.html`). The HTML has the filter dropdowns and an empty table body (`<tbody id="ticket-rows">`) showing "Loading tickets...".
2. **JavaScript reads the filters.** The script at the bottom of `queue.html` copies `status=Open` from the address bar into the Status dropdown, then calls `loadQueue()`.
3. **JavaScript calls the API.** `loadQueue()` builds the query string and calls `api("/tickets?status=Open")`, the shared `fetch()` helper in `static/app.js`.
4. **API layer.** `list_tickets()` in `app.py` reads `status` and `priority` from the query string (an empty value counts as "no filter") and calls `ticket_app.list_tickets(status="Open", priority=None)`.
5. **Application layer.** `TicketApp.list_tickets()` checks that `Open` is one of `Open`, `In progress`, `Resolved`; a bad value raises `ValidationError`. It then opens a database connection and calls `db.list_tickets(conn, "Open", None)`.
6. **DB layer.** `db.list_tickets()` runs one `SELECT` on the `tickets` table. `WHERE (? IS NULL OR status = ?)` applies only the filters that were given. `ORDER BY CASE priority ... END, created_at DESC` sorts Urgent → High → Medium → Low, newest first within each priority. Each row becomes a dict.
7. **Back up through the layers.** The list of dicts returns to `app.py`, where `_summary_json()` renames fields to camelCase and drops the ones the queue does not show. Flask sends `200` with `{"tickets": [...]}`.
8. **Browser draws the table.** `loadQueue()` turns each ticket into a table row: the ID becomes a link to `/ticket?id=HD-1042`, priority and status become colored badges (`priorityBadge`, `statusBadge`), and `createdAt` is formatted as a date. If the list is empty it shows "No tickets match these filters."

Changing a dropdown runs `loadQueue()` again (steps 3–8) and updates the address bar, so the page itself is never reloaded.

**If something goes wrong:** an invalid filter returns `400`, and a database failure returns `503`. In both cases `loadQueue()` shows the error message from the response in a red banner. If the server cannot be reached at all, `api()` returns "Could not reach the server. Try again."

## Other pages

The other pages follow the same path through the layers:

| Page | Browser call | Application method | What it does |
|---|---|---|---|
| Submit Ticket (`/submit`) | `POST /tickets` | `create_ticket()` | Trims and validates fields, defaults priority to Medium, picks the next `HD-` id, sets status Open and both timestamps, and saves the ticket with a System "Ticket opened by requester." note in one transaction. Returns `201 {"id": "HD-1047"}`. |
| Ticket page (`/ticket?id=`) | `GET /tickets/<id>` | `get_ticket()` | Loads one ticket with its notes, oldest first. Unknown id → 404. |
| Ticket page: Save changes | `PATCH /tickets/<id>` | `update_status()` | Validates the status and saves it with a new `updated_at`, even if the status did not change. Returns the full ticket. |
| Ticket page: Add Note | `POST /tickets/<id>/notes` | `add_note()` | Validates the note body and saves it with author `IT staff`. Does not change `updated_at`. Returns `201` with the note. |

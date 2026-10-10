# Campus IT Help Desk

Author: Ryan Demarest, Andrew Kelleman
Course: CSCI 390 Cloud Computing
Institution: Moravian University

## CI/CD Status

| Workflow | Status |
|----------|--------|
| Tests | [![Tests](https://github.com/cs390f26/it-ticket-system-monolith/actions/workflows/run_tests.yml/badge.svg)](https://github.com/cs390f26/it-ticket-system-monolith/actions/workflows/run_tests.yml) |
| Deploy | [![Deploy](https://github.com/cs390f26/it-ticket-system-monolith/actions/workflows/deploy.yml/badge.svg)](https://github.com/cs390f26/it-ticket-system-monolith/actions/workflows/deploy.yml) |

## Project Overview

This is the monolithic implementation of the IT ticket system. See the [specs repository](https://github.com/cs390f26/it-ticket-system-specs) for the use cases, API, database schema, sample data, and UI mockups.

**Monolithic** here means the Flask web server and the SQLite database run together on a single machine (one EC2 instance in production).

Users can:

- Submit a ticket describing an IT problem
- View the ticket queue, filtered by status and priority
- Open a ticket to update its status
- Add internal notes for the IT team

## Documentation

| Doc | Contents |
|-----|----------|
| [Development setup](docs/development.md) | Virtual environment, install, run the app, run the tests |
| [Deploy on EC2](docs/deploy.md) | Launching the app on an EC2 instance |
| [Design](docs/design.md) | Layers, data representations, and how data flows for each page |
| [Flask API plan](docs/flask-api-plan.md) | Routes, layers, and how they map to the specs |

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
python -m tickets.app
```

Then open [http://127.0.0.1:5000](http://127.0.0.1:5000). See [Development setup](docs/development.md) for full steps.

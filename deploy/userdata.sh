#!/bin/bash
# Paste this file into the EC2 User data field. Cloud-init runs it once as root
# on first boot. Output is written to /var/log/cloud-init-output.log.

# Stop on the first failed command, unset variable, or failed command in a pipeline.
set -euo pipefail

# Change this if the instance should clone a fork, and push that change before launch.
REPO_URL="https://github.com/cs390f26/it-ticket-system-monolith.git"

APP_DIR=/home/ec2-user/it-ticket-system-monolith

# Amazon Linux 2023. python3.12 is the version this app requires.
yum install -y python3.12 git

git clone "$REPO_URL" "$APP_DIR"
cd "$APP_DIR"

# Install into a virtualenv so the app does not use the system Python.
python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .

mkdir -p "$APP_DIR/data"

# gunicorn and init_db run as ec2-user, so that user must own the app tree.
chown -R ec2-user:ec2-user "$APP_DIR"

# Create the tables and load sample data before the web server starts.
# Running as ec2-user makes data/tickets.db owned by the same user as gunicorn.
sudo -u ec2-user "$APP_DIR/.venv/bin/python" "$APP_DIR/scripts/init_db.py"

cp deploy/it-ticket-system.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now it-ticket-system.service

#!/bin/bash
# Paste this file into the web instance User data field. Cloud-init runs it
# once as root on first boot. Output is written to /var/log/cloud-init-output.log.
#
# Launch the database instance first. For a console launch, set DB_HOST below
# to that instance's private IP. CloudFormation exports DB_HOST before it runs
# this script.

# Stop on the first failed command, unset variable, or failed command in a pipeline.
set -euo pipefail

# Console launch: set this to the database instance private IP.
# CloudFormation sets DB_HOST in the environment, which wins over this default.
DB_HOST="${DB_HOST:-}"
if [ -z "$DB_HOST" ]; then
  echo "DB_HOST is required (database instance private IP)" >&2
  exit 1
fi

# Change this if the instance should clone a fork, and push that change before launch.
REPO_URL="https://github.com/cs390f26/it-ticket-system-monolith.git"

APP_DIR=/home/ec2-user/it-ticket-system-monolith

# Keep this password the same as deploy/userdata-db.sh and deploy/it-ticket-system.service.
MYSQL_APP_PASSWORD='Tickets-390!'

# Amazon Linux 2023. python3.12 is the version this app requires.
yum install -y python3.12 git

git clone "$REPO_URL" "$APP_DIR"
cd "$APP_DIR"

# Install into a virtualenv so the app does not use the system Python.
python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .

# gunicorn and init_db run as ec2-user, so that user must own the app tree.
chown -R ec2-user:ec2-user "$APP_DIR"

# The database instance is up before this one, but MySQL may still be starting.
ok=0
for _ in $(seq 1 60); do
  if sudo -u ec2-user env \
    MYSQL_HOST="$DB_HOST" \
    MYSQL_PORT=3306 \
    MYSQL_USER=tickets \
    MYSQL_PASSWORD="${MYSQL_APP_PASSWORD}" \
    MYSQL_DATABASE=tickets \
    "$APP_DIR/.venv/bin/python" "$APP_DIR/scripts/init_db.py"
  then
    ok=1
    break
  fi
  sleep 10
done
if [ "$ok" != 1 ]; then
  echo "MySQL at ${DB_HOST} did not become ready" >&2
  exit 1
fi

sed -i "s/^Environment=MYSQL_HOST=.*/Environment=MYSQL_HOST=${DB_HOST}/" deploy/it-ticket-system.service
cp deploy/it-ticket-system.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now it-ticket-system.service

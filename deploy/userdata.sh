#!/bin/bash
set -euo pipefail

# Change REPO_URL if the instance should clone a fork instead of this repo.
REPO_URL="https://github.com/cs390f26/it-ticket-system-monolith.git"

APP_DIR=/home/ec2-user/it-ticket-system-monolith

yum install -y python3.12 git

git clone "$REPO_URL" "$APP_DIR"
cd "$APP_DIR"

python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .

mkdir -p "$APP_DIR/data"

chown -R ec2-user:ec2-user "$APP_DIR"

cp deploy/it-ticket-system.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now it-ticket-system.service

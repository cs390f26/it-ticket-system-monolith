#!/bin/bash
# Paste this file into the database instance User data field. Cloud-init runs
# it once as root on first boot. Output is written to /var/log/cloud-init-output.log.

# Stop on the first failed command, unset variable, or failed command in a pipeline.
set -euo pipefail

# Keep this password the same as deploy/userdata-web.sh and deploy/it-ticket-system.service.
MYSQL_APP_PASSWORD='Tickets-390!'

# MySQL 8 is not in the Amazon Linux 2023 default repos.
rpm --import https://repo.mysql.com/RPM-GPG-KEY-mysql-2023
rpm --import https://repo.mysql.com/RPM-GPG-KEY-mysql-2025 || true
yum install -y https://dev.mysql.com/get/mysql80-community-release-el9-1.noarch.rpm
yum install -y mysql-community-server

# Listen on the private network interface. The security group allows port 3306
# only from the web instance.
mkdir -p /etc/my.cnf.d
cat > /etc/my.cnf.d/tickets.cnf <<'EOF'
[mysqld]
bind-address = 0.0.0.0
mysqlx = 0
EOF

systemctl stop mysqld || true
rm -rf /var/lib/mysql
mkdir -p /var/lib/mysql
chown mysql:mysql /var/lib/mysql
chmod 750 /var/lib/mysql
mysqld --initialize-insecure --user=mysql
systemctl enable --now mysqld

for _ in $(seq 1 30); do
  if mysqladmin --user=root ping --silent; then
    break
  fi
  sleep 2
done
mysqladmin --user=root ping --silent

# '%' matches the web instance. Its private IP is not a fixed MySQL account host.
mysql --user=root <<SQL
ALTER USER 'root'@'localhost' IDENTIFIED BY '${MYSQL_APP_PASSWORD}';
CREATE DATABASE IF NOT EXISTS tickets CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'tickets'@'%' IDENTIFIED BY '${MYSQL_APP_PASSWORD}';
GRANT ALL PRIVILEGES ON tickets.* TO 'tickets'@'%';
GRANT CREATE ON *.* TO 'tickets'@'%';
FLUSH PRIVILEGES;
SQL

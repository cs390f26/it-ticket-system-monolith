# Deploy on EC2

The Flask app and MySQL 8 run on **two EC2 instances** in the same VPC. The web instance runs gunicorn. The database instance runs MySQL and accepts connections on its private IP. Port 3306 is open only to the web instance.

`deploy/userdata-db.sh` sets up MySQL. `deploy/userdata-web.sh` sets up the app. `deploy/it-ticket-system.service` keeps gunicorn running on the web instance.


## Before you launch

`deploy/userdata-web.sh` clones this repository:

```
REPO_URL="https://github.com/cs390f26/it-ticket-system-monolith.git"
```

That URL is already this repo. Change it only if the web instance should clone a fork, then commit and push before you launch. The instance clones whatever is on GitHub at boot, so unpushed commits are not deployed.

Confirm the remote if a push fails:

```bash
git remote -v
```

Launch both instances in the **same VPC** (the learner lab default VPC). The web instance reaches MySQL at the database instance's **private** IP, not its public IP.


## What userdata-db.sh does

Cloud-init runs the script once, as root, on first boot of the database instance. The steps are:

1. Install MySQL 8 from the MySQL community repo.
2. Bind MySQL to `0.0.0.0` so the private network interface accepts connections. The security group is what blocks the internet.
3. Create the `tickets` database and the `tickets`@`%` user.

The database instance does not run the Flask app.

`set -euo pipefail` at the top stops the script at the first failed command. A later step does not run after an earlier one fails.


## What userdata-web.sh does

Cloud-init runs the script once, as root, on first boot of the web instance. The steps are:

1. Read `DB_HOST`, the database instance's private IP.
2. Install `python3.12` and `git` with `yum`.
3. Clone `REPO_URL` into `/home/ec2-user/it-ticket-system-monolith`.
4. Create a virtualenv and install `requirements.txt` plus this project (`pip install -e .`).
5. Give the whole app directory to `ec2-user`.
6. Retry `scripts/init_db.py` as `ec2-user` with `MYSQL_HOST` set to `DB_HOST`. MySQL may still be starting. The script creates the tables and loads `data/sample_data.json` when the database is empty.
7. Write `DB_HOST` into `deploy/it-ticket-system.service` and start it. gunicorn listens on port 80 with one worker and calls `tickets.app:launch()`.


## Launch in the AWS console

Use an AWS Academy Learner Lab session that is started, with the console open in that session. Launch the **database instance first**.

### Database instance

* Name the instance `IT ticket system database`.
* AMI: **Amazon Linux 2023**.
* Instance type: `t3.micro`.
* Key pair: `vockey`, so you can SSH if something fails.
* Network settings: the same VPC as the web instance. Allow **SSH (port 22)** from anywhere 
* Then click 'Edit' next to network, scroll down, then click 'Add security group rule'
* The type is MySQL/aurora, port: 3306, only from the web instance's security group. Do not open 3306 to `0.0.0.0/0`.
* Storage: keep the default volume.
* Advanced details, at the bottom: paste the full contents of `deploy/userdata-db.sh` into **User data**.
* Make sure to get the private IP for the Web Instance's 'User data'

Launch it. On the instance details page, copy the **private** IPv4 address.

### Web instance

* Name the instance `IT ticket system web`.
* AMI: **Amazon Linux 2023**. The script uses `yum`, `python3.12`, and the `ec2-user` account from that image.
* Instance type: `t3.micro`.
* Key pair: `vockey`.
* Network settings: the same VPC. Allow **SSH (port 22)** and **HTTP (port 80)**. The app listens on port 80. Leave HTTPS off unless you add a certificate.
* Storage: keep the default volume.
* Advanced details: paste `deploy/userdata-web.sh` into **User data**. Replace `DB_HOST="${DB_HOST:-}"` near the top with the database private IP you copied:

```bash
DB_HOST="10.0.1.25"
```

Boot finishes before the scripts do. Wait a few minutes, then open `http://WEB_PUBLIC_IP/` in a browser. You should see the help desk without using SSH. `http://WEB_PUBLIC_IP/health` returns `{"status":"ok"}` when the app can query the database.

The public IP is on the web instance details page. It changes if you stop and start the instance. The private IP of the database instance can change too. If it does, update `MYSQL_HOST` in the web unit and restart gunicorn.


## If it does not come up

SSH in with `vockey` and read the script output on the instance that failed:

```bash
sudo cat /var/log/cloud-init-output.log
```

Checks on the **web** instance:

* `systemctl status it-ticket-system` — gunicorn status
* `curl -s http://localhost/health` — the app and the database
* `sudo journalctl -u it-ticket-system -f` — gunicorn logs
* `sudo systemctl restart it-ticket-system` — restart after a code or config change

On the **database** instance, `systemctl status mysqld` shows whether MySQL is running.


## CloudFormation

`deploy/cloudformation.yaml` builds both instances: a web security group for SSH and HTTP, a database security group for SSH and MySQL from the web group only, Amazon Linux 2023, and user data that downloads the two scripts from GitHub. It passes the database private IP to the web instance as `DB_HOST`. Push `userdata-db.sh` and `userdata-web.sh` to `main` before you create the stack.

From the repo root, with the AWS CLI using your Learner Lab credentials:

```bash
aws cloudformation create-stack \
  --stack-name it-ticket-system \
  --template-body file://deploy/cloudformation.yaml \
  --parameters ParameterKey=GitHubUsername,ParameterValue=cs390f26
```

Wait for the instances, then read their addresses. **CREATE_COMPLETE means the instances exist, not that user data has finished.**

```bash
aws cloudformation wait stack-create-complete --stack-name it-ticket-system
aws cloudformation describe-stacks \
  --stack-name it-ticket-system \
  --query 'Stacks[0].Outputs' \
  --output table
```

`WebPublicIP` is the site. `DatabasePrivateIP` is the address the app uses for MySQL.

Delete the stack when you are done with it:

```bash
aws cloudformation delete-stack --stack-name it-ticket-system
aws cloudformation wait stack-delete-complete --stack-name it-ticket-system
```

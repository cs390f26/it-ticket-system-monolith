# Deploy on EC2

The Flask app and the SQLite database run on one EC2 instance. `deploy/userdata.sh` does the setup at launch, and `deploy/it-ticket-system.service` keeps gunicorn running.


## Before you launch

`deploy/userdata.sh` clones this repository:

```
REPO_URL="https://github.com/cs390f26/it-ticket-system-monolith.git"
```

That URL is already this repo. Change it only if the instance should clone a fork, then commit and push before you launch. The instance clones whatever is on GitHub at boot, so unpushed commits are not deployed.

Confirm the remote if a push fails:

```bash
git remote -v
```


## What userdata.sh does

Cloud-init runs the script once, as root, on first boot. The steps are:

1. Install `python3.12` and `git` with `yum`.
2. Clone `REPO_URL` into `/home/ec2-user/it-ticket-system-monolith`.
3. Create a virtualenv and install `requirements.txt` plus this project (`pip install -e .`).
4. Create `data/` and give the whole app directory to `ec2-user`.
5. Run `scripts/init_db.py` as `ec2-user`. That creates `data/tickets.db`, creates the tables, and loads `data/sample_data.json` when the database is empty.
6. Install `deploy/it-ticket-system.service` and start it. gunicorn listens on port 80 with one worker and calls `tickets.app:launch()`.

`set -euo pipefail` at the top stops the script at the first failed command. A later step does not run after an earlier one fails.


## Launch in the AWS console

Use an AWS Academy Learner Lab session that is started, with the console open in that session.

* Name the instance `IT ticket system`.
* AMI: **Amazon Linux 2023**. The script uses `yum`, `python3.12`, and the `ec2-user` account from that image.
* Instance type: `t3.micro`.
* Key pair: `vockey`, so you can SSH if something fails.
* Network settings: allow **SSH (port 22)** and **HTTP (port 80)**. The app listens on port 80. Leave HTTPS off unless you add a certificate.
* Storage: keep the default volume.
* Advanced details, at the bottom: paste the full contents of `deploy/userdata.sh` into **User data**.

Launch the instance. Boot finishes before the script does. Wait a few minutes, then open `http://PUBLIC_IP/` in a browser. You should see the help desk without using SSH. `http://PUBLIC_IP/health` returns `{"status":"ok"}` when the app can query the database.

The public IP is on the instance details page. It changes if you stop and start the instance.


## If it does not come up

SSH in with `vockey` and read the script output:

```bash
sudo cat /var/log/cloud-init-output.log
```

Other checks on the instance:

* `systemctl status it-ticket-system` — gunicorn status
* `curl -s http://localhost/health` — the app and the database
* `sudo journalctl -u it-ticket-system -f` — gunicorn logs
* `sudo systemctl restart it-ticket-system` — restart after a code or config change


## CloudFormation

`deploy/cloudformation.yaml` builds the same instance: a security group for SSH and HTTP, Amazon Linux 2023, and user data that downloads `deploy/userdata.sh` from GitHub and runs it. Push the script to `main` before you create the stack.

From the repo root, with the AWS CLI using your Learner Lab credentials:

```bash
aws cloudformation create-stack \
  --stack-name it-ticket-system \
  --template-body file://deploy/cloudformation.yaml \
  --parameters ParameterKey=GitHubUsername,ParameterValue=cs390f26
```

Wait for the instance, then read its address. **CREATE_COMPLETE means the instance exists, not that user data has finished.**

```bash
aws cloudformation wait stack-create-complete --stack-name it-ticket-system
aws cloudformation describe-stacks \
  --stack-name it-ticket-system \
  --query 'Stacks[0].Outputs' \
  --output table
```

Delete the stack when you are done with it:

```bash
aws cloudformation delete-stack --stack-name it-ticket-system
aws cloudformation wait stack-delete-complete --stack-name it-ticket-system
```

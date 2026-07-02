# CarTracker Backend — VPS Deployment Guide
Ubuntu 22.04 LTS · No Docker · Gunicorn + Nginx

---

## 1. Server prerequisites

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.12 python3.12-venv python3-pip postgresql postgresql-contrib nginx certbot python3-certbot-nginx git
```

---

## 2. PostgreSQL database

```bash
sudo -u postgres psql <<'SQL'
CREATE USER cartracker_user WITH PASSWORD 'STRONG_PASSWORD';
CREATE DATABASE cartracker OWNER cartracker_user;
GRANT ALL PRIVILEGES ON DATABASE cartracker TO cartracker_user;
SQL
```

---

## 3. App user and code

```bash
sudo useradd -m -s /bin/bash cartracker
sudo -u cartracker bash

# As cartracker user:
cd ~
git clone <your-repo-url> car-tracking-platform
cd car-tracking-platform/backend

python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## 4. Environment file

```bash
cp deploy/env.production .env
nano .env           # fill in every value

# Generate secrets:
python3 -c "import secrets; print(secrets.token_hex(32))"
# Run twice — one value for SECRET_KEY, a different one for JWT_SECRET_KEY
```

Place `serviceAccountKey.json` (from Firebase Console → Project Settings → Service Accounts)
at the path you set in `FIREBASE_CREDENTIALS`.

---

## 5. Log directory

```bash
sudo mkdir -p /var/log/cartracker
sudo chown cartracker:cartracker /var/log/cartracker
```

---

## 6. Initialize the database

```bash
# As cartracker user, inside venv:
source venv/bin/activate
python - <<'PY'
from api import create_app
app = create_app('production')
with app.app_context():
    from api.models.models import db
    db.create_all()
    print("Tables created.")
PY

# Seed initial data (creates org, vehicles, devices):
python seed.py
```

---

## 7. systemd service

```bash
sudo cp deploy/cartracker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable cartracker
sudo systemctl start cartracker
sudo systemctl status cartracker   # should show: active (running)
```

Check logs:
```bash
sudo journalctl -u cartracker -f
tail -f /var/log/cartracker/error.log
```

---

## 8. Nginx + TLS

```bash
# Replace api.yourdomain.com in the config first:
sudo cp deploy/nginx-cartracker.conf /etc/nginx/sites-available/cartracker
sudo ln -s /etc/nginx/sites-available/cartracker /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# Free TLS certificate:
sudo certbot --nginx -d api.yourdomain.com
sudo systemctl reload nginx
```

---

## 9. Smoke test

```bash
curl https://api.yourdomain.com/api/v1/health
# Expected: {"status":"success","data":{"status":"ok"}}

curl -X POST https://api.yourdomain.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"manager@tieftechnologiesltd.com","password":"YourPassword"}'
```

---

## 10. Updates (zero-downtime reload)

```bash
cd ~/car-tracking-platform
git pull
source backend/venv/bin/activate
pip install -r backend/requirements.txt
sudo systemctl reload cartracker    # sends SIGHUP — Gunicorn restarts workers gracefully
```

---

## Firewall (UFW)

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
# Port 8000 (Gunicorn) is NOT opened — only Nginx talks to it on localhost.
```

---

## What's running where

| Component | Address |
|---|---|
| Gunicorn (Flask) | 127.0.0.1:8000 (internal only) |
| Nginx (HTTPS) | 0.0.0.0:443 |
| PostgreSQL | 127.0.0.1:5432 (local only) |
| Swagger UI | https://api.yourdomain.com/api/v1/docs/ |
| Health check | https://api.yourdomain.com/api/v1/health |

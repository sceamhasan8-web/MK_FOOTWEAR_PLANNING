# Central Production Deployment & Company Database Setup

## 1. Architectural Strategy

The Footwear Manufacturing Production Planning ERP uses a **client-server centralized topology**.
All desktop planning stations, mobile shop-floor devices, and management web browsers connect to one authoritative central FastAPI backend and PostgreSQL database.

```text
Office Windows Desktops            Factory Shop-Floor Androids           Web Browsers
   (Compose Desktop)                 (Compose Android)                 (Management)
           │                                 │                              │
           └─────────────────────────┬───────┴──────────────────────────────┘
                                     │
                             REST API over HTTPS
                                     │
                                     ▼
                     FastAPI Application Server (Python 3.12)
                        ├── Calculation & Scheduling Engine
                        ├── Route & Operation Progress Tracking
                        ├── JWT RBAC Authorization Guard
                        └── OpenPyXL / CSV Reporting Engine
                                     │
                                     ▼
                    Authoritative PostgreSQL Database (v15+)
```

---

## 2. Central PostgreSQL Database Installation & Configuration

### A. Installing PostgreSQL
On your central Linux (Ubuntu/Debian) or Windows Server:
```bash
# Ubuntu / Debian
sudo apt update
sudo apt install postgresql postgresql-contrib -y

# Start and enable service
sudo systemctl enable postgresql
sudo systemctl start postgresql
```

### B. Creating Database and User
```bash
sudo -u postgres psql
```
In the PostgreSQL prompt:
```sql
CREATE DATABASE footwear_erp;
CREATE USER erp_user WITH ENCRYPTED PASSWORD 'StrongProductionSecret2026!';
GRANT ALL PRIVILEGES ON DATABASE footwear_erp TO erp_user;
ALTER DATABASE footwear_erp OWNER TO erp_user;
\q
```

### C. Configuring Remote Access (Internal Company Subnet)
Edit `postgresql.conf`:
```text
listen_addresses = '*'
```
Edit `pg_hba.conf` to allow factory office and Wi-Fi subnets (e.g. `192.168.1.0/24`):
```text
# TYPE  DATABASE        USER            ADDRESS                 METHOD
host    footwear_erp    erp_user        192.168.1.0/24          scram-sha-256
```
Restart PostgreSQL:
```bash
sudo systemctl restart postgresql
```

---

## 3. Production Backend Setup (FastAPI + Gunicorn / Uvicorn)

### A. Environment Configuration
Create `/opt/footwear-erp/backend/.env`:
```ini
ENVIRONMENT=production
DEBUG=False
PROJECT_NAME="Footwear Manufacturing Production Planning ERP"
DATABASE_URL=postgresql://erp_user:StrongProductionSecret2026!@localhost:5432/footwear_erp
SECRET_KEY=generate-a-cryptographically-secure-random-token-here-minimum-64-chars
ACCESS_TOKEN_EXPIRE_MINUTES=480
CORS_ORIGINS=["*"]
DEFAULT_TIMEZONE=Asia/Dhaka
DEFAULT_CUTOFF_HOUR=18
DEFAULT_CUTOFF_MINUTE=0
```

### B. Python Virtual Environment & Migrations
```bash
cd /opt/footwear-erp/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Seed initial factory data (if fresh deployment)
python -m app.seed.demo_data
```

### C. Systemd Service Definition
Create `/etc/systemd/system/footwear-erp.service`:
```ini
[Unit]
Description=Footwear Manufacturing ERP Backend Service
After=network.target postgresql.service

[Service]
Type=simple
User=erp
WorkingDirectory=/opt/footwear-erp/backend
EnvironmentFile=/opt/footwear-erp/backend/.env
ExecStart=/opt/footwear-erp/backend/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable footwear-erp
sudo systemctl start footwear-erp
```

---

## 4. Reverse Proxy Setup (Nginx with SSL)

Install Nginx:
```bash
sudo apt install nginx -y
```
Create `/etc/nginx/sites-available/footwear-erp`:
```nginx
server {
    listen 80;
    server_name erp.factory.internal;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
Enable site and restart Nginx:
```bash
sudo ln -s /etc/nginx/sites-available/footwear-erp /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

---

## 5. Client Connection Configuration

### Windows Desktop Application:
Configure the endpoint URL in the desktop settings or launch with environment variable:
```bash
set ERP_API_BASE=http://erp.factory.internal/api/v1
FootwearManufacturingERP.exe
```

### Android Mobile Devices:
On the initial login screen, enter the company server IP or domain:
```text
Server Host: erp.factory.internal (or 192.168.1.100:8000)
```
Ensure Android devices are connected to the internal factory Wi-Fi SSID with route to the server.

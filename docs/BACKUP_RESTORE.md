# Database Backup and Disaster Recovery Guide

## 1. Automated PostgreSQL Daily Backup Routine

Footwear manufacturing production transactions (cutting outputs, lasting counts, deadline revisions) must be safeguarded with daily snapshots and point-in-time recovery.

### A. Dedicated Backup Directory
```bash
sudo mkdir -p /var/backups/footwear_erp
sudo chown -R postgres:postgres /var/backups/footwear_erp
sudo chmod 700 /var/backups/footwear_erp
```

### B. Daily Snapshot Script (`backup_footwear_erp.sh`)
Create `/usr/local/bin/backup_footwear_erp.sh`:
```bash
#!/usr/bin/env bash
set -e

BACKUP_DIR="/var/backups/footwear_erp"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/footwear_erp_${TIMESTAMP}.dump"
LOG_FILE="/var/log/footwear_erp_backup.log"

echo "[$(date)] Starting backup of footwear_erp..." >> "${LOG_FILE}"

# Custom-format dump (compressed, supporting parallel restore)
pg_dump -U postgres -Fc -b -v -f "${BACKUP_FILE}" footwear_erp 2>> "${LOG_FILE}"

echo "[$(date)] Backup completed: ${BACKUP_FILE}" >> "${LOG_FILE}"

# Delete backups older than 30 days
find "${BACKUP_DIR}" -type f -name "footwear_erp_*.dump" -mtime +30 -exec rm {} \;
echo "[$(date)] Pruned backups older than 30 days." >> "${LOG_FILE}"
```
Make executable:
```bash
sudo chmod +x /usr/local/bin/backup_footwear_erp.sh
```

### C. Schedule via Crontab (Daily at 02:00 AM)
Add to postgres user crontab (`sudo crontab -u postgres -e`):
```cron
0 2 * * * /usr/local/bin/backup_footwear_erp.sh
```

---

## 2. Disaster Recovery & Database Restoration

### A. Full Restoration from `.dump` file

If a hardware failure occurs or data rollback is required:

1. Stop application backend to prevent concurrent transactions:
   ```bash
   sudo systemctl stop footwear-erp
   ```

2. Terminate existing connections to target database:
   ```bash
   sudo -u postgres psql -c "
   SELECT pg_terminate_backend(pid) 
   FROM pg_stat_activity 
   WHERE datname = 'footwear_erp' AND pid <> pg_backend_pid();"
   ```

3. Drop and recreate database:
   ```bash
   sudo -u postgres dropdb footwear_erp
   sudo -u postgres createdb -O erp_user footwear_erp
   ```

4. Restore using `pg_restore`:
   ```bash
   sudo -u postgres pg_restore --clean --if-exists -d footwear_erp -v /var/backups/footwear_erp/footwear_erp_20261007_020000.dump
   ```

5. Restart application backend:
   ```bash
   sudo systemctl start footwear-erp
   ```

6. Verify restoration integrity:
   ```bash
   sudo -u postgres psql -d footwear_erp -c "SELECT count(*) FROM orders;"
   sudo -u postgres psql -d footwear_erp -c "SELECT count(*) FROM daily_production_entries;"
   ```

---

## 3. SQLite Development / Standalone Backup

For standalone office development or testing deployments using SQLite (`footwear_erp.db`):

### Backup:
```powershell
# Windows PowerShell
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
Copy-Item "d:\ErpPlanning\backend\footwear_erp.db" -Destination "d:\ErpPlanning\backups\footwear_erp_$timestamp.db"
```

### Restore:
```powershell
# Windows PowerShell
Stop-Process -Name "python" -ErrorAction SilentlyContinue
Copy-Item "d:\ErpPlanning\backups\footwear_erp_TARGET.db" -Destination "d:\ErpPlanning\backend\footwear_erp.db" -Force
```

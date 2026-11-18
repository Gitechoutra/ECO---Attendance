"""Create a MySQL backup of the ECHOUTRA ONE database and prune old ones.

Usage (from backend/):  .venv\\Scripts\\python -m scripts.backup [--keep 14] [--dir backups]
Schedule it daily with Windows Task Scheduler or cron. The DB password is passed via the
MYSQL_PWD environment variable, never on the command line.
"""
import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from app.core.config import BASE_DIR, settings


def find_mysqldump() -> str | None:
    for c in [shutil.which("mysqldump"), r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe", "/usr/bin/mysqldump"]:
        if c and Path(c).exists():
            return c
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(BASE_DIR / "backups"))
    ap.add_argument("--keep", type=int, default=14, help="number of most recent backups to keep")
    args = ap.parse_args()
    tool = find_mysqldump()
    if not tool:
        print("mysqldump not found")
        return 1
    out = Path(args.dir)
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"{settings.DB_NAME}-{datetime.now():%Y%m%d-%H%M%S}.sql"
    proc = subprocess.run(
        [tool, "-h", settings.DB_HOST, "-P", str(settings.DB_PORT), "-u", settings.DB_USER, "--single-transaction",
         "--routines", "--triggers", "--set-gtid-purged=OFF", f"--result-file={target}", settings.DB_NAME],
        env={**os.environ, "MYSQL_PWD": settings.DB_PASSWORD}, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr)
        target.unlink(missing_ok=True)
        return proc.returncode
    print(f"Backup written: {target} ({target.stat().st_size // 1024} KB)")
    backups = sorted(out.glob(f"{settings.DB_NAME}-*.sql"))
    for old in backups[:-args.keep]:
        old.unlink()
        print(f"Pruned {old.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

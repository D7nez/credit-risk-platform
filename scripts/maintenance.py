"""Online SQLite backup and optional retention cleanup."""
import argparse
import os
from pathlib import Path
from datetime import datetime, timezone

from app.server import load_local_env
from app.store import Store

load_local_env()
root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--backup", action="store_true")
parser.add_argument("--purge-older-than", type=int, metavar="DAYS")
args = parser.parse_args()
if not args.backup and args.purge_older_than is None:
    parser.error("Specify --backup and/or --purge-older-than DAYS")
store = Store(os.environ.get("DB_PATH", str(root / "state/predictions.sqlite3")))
if args.backup:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = root / "backups" / f"predictions-{stamp}.sqlite3"
    store.backup(str(destination))
    print(f"Backup: {destination}")
if args.purge_older_than is not None:
    if args.purge_older_than < 1:
        parser.error("Retention must be at least 1 day")
    print(f"Deleted {store.purge(args.purge_older_than)} old prediction records")

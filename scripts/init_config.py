"""Generate distinct local API secrets; rerunning preserves existing config."""
import os
from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1]
target = root / ".env"
if target.exists():
    raise SystemExit(f"Already exists: {target}. Keep the existing keys; rotate deliberately if needed.")
content = (f"APP_API_KEY={secrets.token_urlsafe(32)}\n"
           f"APP_ADMIN_KEY={secrets.token_urlsafe(32)}\n"
           "APP_HOST=127.0.0.1\nAPP_PORT=8000\n"
           "DB_PATH=state/predictions.sqlite3\nMODEL_PATH=models/credit_default_model.joblib\n")
descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w", encoding="utf-8") as file:
    file.write(content)
print(f"Created {target}. Open it locally to copy the API and admin keys into the app settings.")

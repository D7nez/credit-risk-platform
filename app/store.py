"""SQLite storage; no raw financial inputs or personal identifiers are retained."""

import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS predictions (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                score REAL NOT NULL CHECK (score >= 0 AND score <= 1),
                model_version TEXT NOT NULL,
                batch_id TEXT,
                outcome INTEGER CHECK (outcome IN (0,1)),
                outcome_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_predictions_created ON predictions(created_at);
            CREATE INDEX IF NOT EXISTS idx_predictions_batch ON predictions(batch_id);
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=10000")
        return db

    def add_scores(self, scores: list[float], version: str, batch_id: str | None = None):
        now = utc_now()
        ids = [str(uuid.uuid4()) for _ in scores]
        with self.connect() as db:
            db.executemany(
                "INSERT INTO predictions(id,created_at,score,model_version,batch_id) VALUES (?,?,?,?,?)",
                [(item, now, float(score), version, batch_id) for item, score in zip(ids, scores)]
            )
        return ids

    def add_outcome(self, prediction_id: str, outcome: int):
        with self.connect() as db:
            cur = db.execute("UPDATE predictions SET outcome=?,outcome_at=? "
                             "WHERE id=? AND outcome IS NULL",
                             (outcome, utc_now(), prediction_id))
            if cur.rowcount != 1:
                exists = db.execute("SELECT outcome FROM predictions WHERE id=?", (prediction_id,)).fetchone()
                if exists is None:
                    raise KeyError("Prediction ID not found")
                raise ValueError("Outcome already recorded; corrections need a reviewed workflow")

    def recent(self, days: int):
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
        with self.connect() as db:
            return [dict(r) for r in db.execute(
                "SELECT id,created_at,score,model_version,batch_id,outcome FROM predictions "
                "WHERE created_at >= ? ORDER BY created_at DESC", (since,))]

    def counts(self):
        with self.connect() as db:
            row = db.execute("SELECT COUNT(*) total, COUNT(outcome) labeled, AVG(score) mean_score "
                             "FROM predictions").fetchone()
            return dict(row)

    def purge(self, older_than_days: int):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat(timespec="seconds")
        with self.connect() as db:
            cur = db.execute("DELETE FROM predictions WHERE created_at < ?", (cutoff,))
            return cur.rowcount

    def backup(self, destination: str):
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as source, sqlite3.connect(target) as backup_db:
            source.backup(backup_db)

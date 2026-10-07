"""SQLite review history + daily usage counter (SRS 4.4, 5.5). Raw code is stored only if the user opts in (SRS 5.3)."""
import json
import sqlite3
import threading
from datetime import datetime, timezone

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  snippet_hash TEXT NOT NULL,
  language TEXT NOT NULL,
  summary_json TEXT NOT NULL,
  report_json TEXT NOT NULL,
  code TEXT
);
CREATE INDEX IF NOT EXISTS idx_reviews_session ON reviews(session_id, id DESC);
CREATE TABLE IF NOT EXISTS usage (session_id TEXT NOT NULL, day TEXT NOT NULL, n INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (session_id, day));
"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Database:
    def __init__(self, path: str):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)

    def _run(self, sql, args=(), fetch=None):
        with self._lock:
            cur = self._conn.execute(sql, args)
            self._conn.commit()
            if fetch == "one":
                return cur.fetchone()
            if fetch == "all":
                return cur.fetchall()
            return cur

    def add_review(self, session_id, snippet_hash, language, report: dict, code=None) -> int:
        cur = self._run(
            "INSERT INTO reviews(session_id, created_at, snippet_hash, language, summary_json, report_json, code)"
            " VALUES (?,?,?,?,?,?,?)",
            (session_id, _now().isoformat(timespec="seconds"), snippet_hash, language,
             json.dumps(report["summary"]), json.dumps(report), code))
        return cur.lastrowid

    def list_reviews(self, session_id, limit=20):
        rows = self._run("SELECT id, created_at, snippet_hash, language, summary_json FROM reviews "
                         "WHERE session_id=? ORDER BY id DESC LIMIT ?", (session_id, limit), "all")
        return [{"id": r["id"], "created_at": r["created_at"], "snippet_hash": r["snippet_hash"][:8],
                 "language": r["language"], "summary": json.loads(r["summary_json"])} for r in rows]

    def get_review(self, session_id, review_id):
        r = self._run("SELECT * FROM reviews WHERE id=? AND session_id=?", (review_id, session_id), "one")
        if not r:
            return None
        return {"id": r["id"], "created_at": r["created_at"], "language": r["language"],
                "report": json.loads(r["report_json"]), "code": r["code"]}

    def delete_review(self, session_id, review_id) -> bool:
        return self._run("DELETE FROM reviews WHERE id=? AND session_id=?", (review_id, session_id)).rowcount > 0

    def used_today(self, session_id) -> int:
        r = self._run("SELECT n FROM usage WHERE session_id=? AND day=?",
                      (session_id, _now().date().isoformat()), "one")
        return r["n"] if r else 0

    def bump_usage(self, session_id):
        self._run("INSERT INTO usage(session_id, day, n) VALUES (?,?,1) "
                  "ON CONFLICT(session_id, day) DO UPDATE SET n = n + 1",
                  (session_id, _now().date().isoformat()))

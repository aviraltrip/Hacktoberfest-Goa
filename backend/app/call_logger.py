"""
Call Logger for Gemma 4 Invocations.
Stores detailed LLM telemetry for the Gemma Call Inspector frontend drawer.
Persists calls to both an in-memory buffer and a SQLite database.
"""

import sqlite3
import json
import uuid
from datetime import datetime, timezone
from typing import Optional, Any
from pathlib import Path

from app.models import GemmaCallLog
from app.config import DB_PATH


class GemmaCallLogger:
    """Thread-safe and async-friendly logger for LLM invocations."""

    def __init__(self, db_path: Path = DB_PATH, max_in_memory: int = 100):
        self.db_path = db_path
        self.max_in_memory = max_in_memory
        self._memory_logs: list[GemmaCallLog] = []
        self._init_sqlite()

    def _init_sqlite(self):
        """Initializes the gemma_calls SQLite table."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS gemma_calls (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    model TEXT NOT NULL,
                    prompt_summary TEXT NOT NULL,
                    image_paths TEXT NOT NULL,
                    response_raw TEXT NOT NULL,
                    parsed_json TEXT,
                    latency_ms REAL NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT
                )
            """)
            conn.commit()

    def log(
        self,
        endpoint: str,
        model: str,
        prompt_summary: str,
        response_raw: str,
        latency_ms: float,
        status: str = "success",
        image_paths: Optional[list[str]] = None,
        parsed_json: Optional[dict[str, Any]] = None,
        error: Optional[str] = None,
        call_id: Optional[str] = None
    ) -> GemmaCallLog:
        """Records a new Gemma 4 call entry."""
        cid = call_id or f"call_{uuid.uuid4().hex[:10]}"
        iso_ts = datetime.now(timezone.utc).isoformat()
        img_paths = image_paths or []

        log_entry = GemmaCallLog(
            id=cid,
            timestamp=iso_ts,
            endpoint=endpoint,
            model=model,
            prompt_summary=prompt_summary,
            image_paths=img_paths,
            response_raw=response_raw,
            parsed_json=parsed_json,
            latency_ms=latency_ms,
            status=status,
            error=error
        )

        # Store in-memory
        self._memory_logs.insert(0, log_entry)
        if len(self._memory_logs) > self.max_in_memory:
            self._memory_logs.pop()

        # Persist to SQLite
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO gemma_calls
                    (id, timestamp, endpoint, model, prompt_summary, image_paths, response_raw, parsed_json, latency_ms, status, error)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        log_entry.id,
                        log_entry.timestamp,
                        log_entry.endpoint,
                        log_entry.model,
                        log_entry.prompt_summary,
                        json.dumps(log_entry.image_paths),
                        log_entry.response_raw,
                        json.dumps(log_entry.parsed_json) if log_entry.parsed_json is not None else None,
                        log_entry.latency_ms,
                        log_entry.status,
                        log_entry.error
                    )
                )
                conn.commit()
        except Exception as e:
            # Non-blocking log failure
            print(f"[CallLogger] SQLite write warning: {e}")

        return log_entry

    def get_recent_calls(self, limit: int = 50) -> list[GemmaCallLog]:
        """Returns the most recent calls, combining in-memory and SQLite cache."""
        if self._memory_logs:
            return self._memory_logs[:limit]

        results: list[GemmaCallLog] = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM gemma_calls ORDER BY timestamp DESC LIMIT ?", (limit,)
                )
                for row in cursor.fetchall():
                    results.append(
                        GemmaCallLog(
                            id=row["id"],
                            timestamp=row["timestamp"],
                            endpoint=row["endpoint"],
                            model=row["model"],
                            prompt_summary=row["prompt_summary"],
                            image_paths=json.loads(row["image_paths"]) if row["image_paths"] else [],
                            response_raw=row["response_raw"],
                            parsed_json=json.loads(row["parsed_json"]) if row["parsed_json"] else None,
                            latency_ms=row["latency_ms"],
                            status=row["status"],
                            error=row["error"]
                        )
                    )
        except Exception as e:
            print(f"[CallLogger] SQLite read warning: {e}")

        return results

    def clear(self):
        """Clears memory and database call logs."""
        self._memory_logs.clear()
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM gemma_calls")
                conn.commit()
        except Exception:
            pass


# Global singleton instance
call_logger = GemmaCallLogger()

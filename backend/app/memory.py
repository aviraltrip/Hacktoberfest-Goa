"""
SQLite FTS5 Heal Memory subsystem for DemoToSkill.
Provides vectorless retrieval over past repair events.
Indexes repairs by step intent using SQLite FTS5 to supply historical
healing hints to Gemma 4 during Set-of-Marks visual reasoning.
"""

import sqlite3
import re
from pathlib import Path
from typing import Optional
from app.config import DB_PATH


def _clean_fts_query(text: str) -> str:
    """Sanitizes text into safe FTS5 tokens joined by OR."""
    tokens = re.findall(r"\w+", text)
    if not tokens:
        return ""
    # Filter short stop words
    significant = [t for t in tokens if len(t) > 2]
    return " OR ".join(significant[:8]) if significant else " OR ".join(tokens[:5])


class HealMemory:
    """Manages persistent storage and FTS5 retrieval of past healing solutions."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_tables()

    def _init_tables(self):
        """Initializes heals table and FTS5 full-text index with sync triggers."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS heals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    old_locator TEXT NOT NULL,
                    new_locator TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create FTS5 virtual table if supported
            try:
                conn.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS heals_fts USING fts5(
                        intent,
                        content='heals',
                        content_rowid='id'
                    )
                """)
                # Synchronization triggers
                conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS heals_ai AFTER INSERT ON heals BEGIN
                        INSERT INTO heals_fts(rowid, intent) VALUES (new.id, new.intent);
                    END;
                """)
                conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS heals_ad AFTER DELETE ON heals BEGIN
                        INSERT INTO heals_fts(heals_fts, rowid, intent) VALUES('delete', old.id, old.intent);
                    END;
                """)
            except Exception as e:
                print(f"[HealMemory] Note: SQLite FTS5 setup note: {e}")

            conn.commit()

    def save_heal(
        self,
        site: str,
        intent: str,
        old_locator: str,
        new_locator: str
    ) -> int:
        """Records a successful repair into heal memory."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO heals (site, intent, old_locator, new_locator)
                VALUES (?, ?, ?, ?)
                """,
                (site, intent, old_locator, new_locator)
            )
            conn.commit()
            return cursor.lastrowid

    def lookup_hints(
        self,
        site: str,
        intent: str,
        limit: int = 3
    ) -> list[str]:
        """
        Retrieves relevant past healing hints using FTS5 lexical match or LIKE fallback.
        Returns formatted strings describing previous locator migrations.
        """
        hints: list[str] = []
        fts_query = _clean_fts_query(intent)

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row

                # 1. Try FTS5 search
                if fts_query:
                    try:
                        cursor = conn.execute(
                            """
                            SELECT h.intent, h.old_locator, h.new_locator
                            FROM heals_fts f
                            JOIN heals h ON f.rowid = h.id
                            WHERE heals_fts MATCH ?
                            ORDER BY rank
                            LIMIT ?
                            """,
                            (fts_query, limit)
                        )
                        for row in cursor.fetchall():
                            hints.append(
                                f"Similar intent '{row['intent']}': previous broken locator '{row['old_locator']}' "
                                f"was healed to '{row['new_locator']}'"
                            )
                    except Exception:
                        pass

                # 2. Fallback to LIKE query if no FTS matches
                if not hints:
                    words = [w for w in intent.split() if len(w) > 3]
                    if words:
                        pattern = f"%{words[0]}%"
                        cursor = conn.execute(
                            """
                            SELECT intent, old_locator, new_locator
                            FROM heals
                            WHERE intent LIKE ?
                            ORDER BY timestamp DESC
                            LIMIT ?
                            """,
                            (pattern, limit)
                        )
                        for row in cursor.fetchall():
                            hints.append(
                                f"Past repair for '{row['intent']}': '{row['old_locator']}' "
                                f"-> '{row['new_locator']}'"
                            )

        except Exception as e:
            print(f"[HealMemory] Lookup error: {e}")

        return hints

    def clear(self):
        """Clears all heal memory records."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM heals")
            try:
                conn.execute("DELETE FROM heals_fts")
            except Exception:
                pass
            conn.commit()


# Global singleton instance
heal_memory = HealMemory()

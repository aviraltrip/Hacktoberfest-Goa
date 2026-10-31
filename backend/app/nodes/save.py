"""
Save Node for DemoToSkill Compile Graph.
Persists the verified WorkflowSpec and trial run execution logs to disk and SQLite.
"""

import json
import sqlite3
from typing import Any
from pathlib import Path

from app.config import SPECS_DIR, DB_PATH
from app.models import CompileState, WorkflowSpec, RowResult
from app.nodes.compile_spec import save_spec_to_file, persist_spec_to_sqlite


def persist_run_results_to_sqlite(
    run_id: str,
    spec_id: str,
    status: str,
    results: list[RowResult],
    db_path: Path = DB_PATH
):
    """Saves execution run records to SQLite runs table."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                spec_id TEXT NOT NULL,
                status TEXT NOT NULL,
                results_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(spec_id) REFERENCES specs(id)
            )
        """)
        conn.execute(
            """
            INSERT OR REPLACE INTO runs (id, spec_id, status, results_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                run_id,
                spec_id,
                status,
                json.dumps([r.model_dump() for r in results], indent=2)
            )
        )
        conn.commit()


def save_node(state: CompileState) -> dict[str, Any]:
    """
    LangGraph Compile Graph node: 'save'.
    Finalizes and saves WorkflowSpec and trial execution traces.
    """
    spec: WorkflowSpec = state.get("spec")
    results: list[RowResult] = state.get("results") or []
    rec_id = state.get("recording_id", "run")

    if spec:
        # Save spec to specs/{id}.json and SQLite specs table
        save_spec_to_file(spec)
        persist_spec_to_sqlite(spec)

        # Save run results to SQLite runs table
        run_status = "passed" if all(r.success for r in results) else "failed"
        persist_run_results_to_sqlite(
            run_id=f"run_trial_{rec_id}",
            spec_id=spec.id,
            status=run_status,
            results=results
        )

    return {
        "status": "saved"
    }

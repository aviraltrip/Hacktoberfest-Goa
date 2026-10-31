"""
Compile Spec Node for DemoToSkill Compile Graph.
Finalizes the validated WorkflowSpec, generates synthetic trial rows for testing,
and saves the specification to disk and SQLite.
"""

import json
import sqlite3
import uuid
from typing import Any
from pathlib import Path

from app.config import SPECS_DIR, DB_PATH
from app.models import CompileState, WorkflowSpec, Variable


def generate_trial_rows(variables: list[Variable]) -> list[dict[str, Any]]:
    """
    Generates 2 distinct synthetic test rows to prove generalization.
    Ensures different select options and variations are tested.
    """
    if not variables:
        return [{}]

    row1: dict[str, Any] = {}
    row2: dict[str, Any] = {}

    for var in variables:
        if var.type == "select" and var.options:
            # Use 1st option for row 1, 2nd option for row 2 (if available)
            row1[var.name] = var.options[0]
            row2[var.name] = var.options[1] if len(var.options) > 1 else var.options[0]
        elif var.type == "number":
            base = int(var.example) if var.example.isdigit() else 2026
            row1[var.name] = base
            row2[var.name] = base + 1
        else:
            # Text fields
            row1[var.name] = var.example or "Alice Smith"
            row2[var.name] = f"Test {var.example or 'Bob Jones'}"

    return [row1, row2]


def persist_spec_to_sqlite(spec: WorkflowSpec, db_path: Path = DB_PATH):
    """Persists finalized spec to SQLite specs table."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS specs (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                start_url TEXT NOT NULL,
                spec_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute(
            """
            INSERT OR REPLACE INTO specs (id, name, start_url, spec_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                spec.id,
                spec.name,
                spec.start_url,
                json.dumps(spec.model_dump(), indent=2)
            )
        )
        conn.commit()


def save_spec_to_file(spec: WorkflowSpec, specs_dir: Path = SPECS_DIR) -> Path:
    """Saves WorkflowSpec as a standalone JSON file in specs/."""
    specs_dir.mkdir(parents=True, exist_ok=True)
    spec_path = specs_dir / f"{spec.id}.json"
    with open(spec_path, "w", encoding="utf-8") as f:
        json.dump(spec.model_dump(), f, indent=2)
    return spec_path


def compile_spec_node(state: CompileState) -> dict[str, Any]:
    """
    LangGraph node: 'compile_spec'.
    Finalizes WorkflowSpec, writes to filesystem and SQLite,
    and initializes trial run rows.
    """
    spec: WorkflowSpec = state.get("spec")
    if not spec:
        return {"status": "failed", "error": "No draft spec provided to compile"}

    # Assign persistent ID if not present
    if not spec.id or spec.id.startswith("spec_draft"):
        spec.id = f"spec_{uuid.uuid4().hex[:8]}"

    # Save to disk and database
    save_spec_to_file(spec)
    persist_spec_to_sqlite(spec)

    # Generate synthetic trial rows to test generalization in Phase 4
    trial_rows = generate_trial_rows(spec.variables)

    return {
        "spec": spec,
        "trial_rows": trial_rows,
        "status": "testing"
    }

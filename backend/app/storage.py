"""SQLite storage using only the standard library (no ORM).

Schema:
  runs(id TEXT PK, agent TEXT, created_at TEXT)
  results(id INTEGER PK, run_id TEXT, task_id TEXT, score REAL,
          output TEXT, details TEXT (JSON), latency_ms REAL,
          tool_calls TEXT (JSON), error TEXT)
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                agent TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL REFERENCES runs(id),
                task_id TEXT NOT NULL,
                score REAL NOT NULL,
                output TEXT NOT NULL,
                details TEXT NOT NULL,
                latency_ms REAL NOT NULL,
                tool_calls TEXT NOT NULL,
                error TEXT
            )"""
        )
        conn.commit()


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def create_run(db_path: Path, agent: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    run_id = uuid.uuid4().hex[:12]
    created_at = datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO runs (id, agent, created_at) VALUES (?, ?, ?)",
            (run_id, agent, created_at),
        )
        for r in results:
            conn.execute(
                """INSERT INTO results
                   (run_id, task_id, score, output, details, latency_ms, tool_calls, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    r["task_id"],
                    r["score"],
                    r["output"],
                    json.dumps(r["details"]),
                    r["latency_ms"],
                    json.dumps(r["tool_calls"]),
                    r["error"],
                ),
            )
        conn.commit()
    return get_run(db_path, run_id)  # type: ignore[return-value]


def get_run(db_path: Path, run_id: str) -> dict[str, Any] | None:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        result_rows = conn.execute(
            "SELECT * FROM results WHERE run_id = ? ORDER BY id", (run_id,)
        ).fetchall()
    return {
        "id": row["id"],
        "agent": row["agent"],
        "created_at": row["created_at"],
        "results": [
            {
                "task_id": r["task_id"],
                "score": r["score"],
                "output": r["output"],
                "details": json.loads(r["details"]),
                "latency_ms": r["latency_ms"],
                "tool_calls": json.loads(r["tool_calls"]),
                "error": r["error"],
            }
            for r in result_rows
        ],
    }


def list_runs(db_path: Path) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM runs ORDER BY created_at DESC, id DESC").fetchall()
        summaries = []
        for row in rows:
            agg = conn.execute(
                "SELECT COUNT(*) AS n, AVG(score) AS avg_score FROM results WHERE run_id = ?",
                (row["id"],),
            ).fetchone()
            summaries.append(
                {
                    "id": row["id"],
                    "agent": row["agent"],
                    "created_at": row["created_at"],
                    "task_count": agg["n"],
                    "avg_score": agg["avg_score"],
                }
            )
    return summaries


def leaderboard(db_path: Path) -> list[dict[str, Any]]:
    """Aggregated ONLY from stored runs. Empty list when no runs exist."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            """SELECT r.agent AS agent,
                      COUNT(DISTINCT r.id) AS runs,
                      COUNT(res.id) AS tasks,
                      AVG(res.score) AS avg_score,
                      AVG(res.latency_ms) AS avg_latency_ms
               FROM runs r JOIN results res ON res.run_id = r.id
               GROUP BY r.agent
               ORDER BY avg_score DESC, agent ASC"""
        ).fetchall()
    return [
        {
            "agent": row["agent"],
            "runs": row["runs"],
            "tasks": row["tasks"],
            "avg_score": row["avg_score"],
            "avg_latency_ms": row["avg_latency_ms"],
        }
        for row in rows
    ]

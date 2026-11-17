"""casano-agentbench backend: FastAPI app over deterministic tasks + agents."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

BACKEND_DIR = Path(__file__).resolve().parent.parent

# Load .env files (repo root, then backend/ which wins). No .env file is
# required; plain environment variables work the same way.
try:
    from dotenv import load_dotenv

    load_dotenv(BACKEND_DIR.parent / ".env")
    load_dotenv(BACKEND_DIR / ".env", override=True)
except ImportError:  # pragma: no cover - python-dotenv is in requirements.txt
    pass

from . import storage
from .agents import AGENT_NAMES, bifrost_configured, get_agent
from .tasks import TASK_BY_ID, TASKS


def get_db_path() -> Path:
    override = os.environ.get("AGENTBENCH_DB")
    if override:
        return Path(override)
    return BACKEND_DIR / "data" / "agentbench.db"


def get_cors_origins() -> list[str]:
    raw = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    return [o.strip() for o in raw.split(",") if o.strip()]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    storage.init_db(get_db_path())
    yield


app = FastAPI(title="casano-agentbench", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def _db() -> Path:
    path = get_db_path()
    storage.init_db(path)
    return path


class RunRequest(BaseModel):
    agent: str = Field(..., min_length=1, max_length=32)
    task_ids: list[str] | None = Field(default=None, max_length=20)

    model_config = {"extra": "forbid"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/tasks")
def list_tasks() -> list[dict[str, str]]:
    return [t.public_dict() for t in TASKS]


@app.get("/agents")
def list_agents() -> dict:
    # Configured-ness comes from env presence ONLY. Keys are never read
    # into a response, logged, or otherwise exposed here.
    configured = bifrost_configured()
    return {
        "bifrost_configured": configured,
        "agents": [
            {
                "name": "echo",
                "description": "Deterministic baseline that returns fixed text.",
                "available": True,
            },
            {
                "name": "rule",
                "description": "Deterministic solver for the built-in tasks.",
                "available": True,
            },
            {
                "name": "bifrost",
                "description": "LLM agent via a Bifrost gateway (OpenAI-compatible).",
                "available": True,
                "bifrost_configured": configured,
            },
        ],
    }


@app.post("/runs", status_code=201)
def create_run(req: RunRequest) -> dict:
    if req.agent not in AGENT_NAMES:
        raise HTTPException(status_code=422, detail=f"unknown agent: {req.agent}")
    if req.task_ids is None:
        selected = TASKS
    else:
        if len(req.task_ids) == 0:
            raise HTTPException(status_code=422, detail="task_ids must not be empty")
        selected = []
        for task_id in req.task_ids:
            if len(task_id) > 64:
                raise HTTPException(status_code=422, detail=f"task id too long: {task_id[:32]}")
            task = TASK_BY_ID.get(task_id)
            if task is None:
                raise HTTPException(status_code=422, detail=f"unknown task id: {task_id}")
            selected.append(task)
    agent = get_agent(req.agent)
    results = []
    for task in selected:
        outcome = agent.run(task)
        score, details = task.checker(outcome.output, outcome.tool_calls)
        results.append(
            {
                "task_id": task.id,
                "score": score,
                "output": outcome.output[:4000],
                "details": details,
                "latency_ms": outcome.latency_ms,
                "tool_calls": outcome.tool_calls,
                "error": outcome.error,
            }
        )
    return storage.create_run(_db(), req.agent, results)


@app.get("/runs")
def list_runs() -> list[dict]:
    return storage.list_runs(_db())


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    if len(run_id) > 64:
        raise HTTPException(status_code=404, detail="run not found")
    run = storage.get_run(_db(), run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@app.get("/leaderboard")
def get_leaderboard() -> list[dict]:
    return storage.leaderboard(_db())

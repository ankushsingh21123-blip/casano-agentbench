"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  API_URL,
  createRun,
  fetchAgents,
  fetchLeaderboard,
  fetchRuns,
  fetchTasks,
  type AgentsResponse,
  type LeaderboardRow,
  type RunDetail,
  type RunSummary,
  type Task,
} from "../lib/api";

function ResultsTable({ run }: { run: RunDetail }) {
  return (
    <table>
      <thead>
        <tr>
          <th>Task</th>
          <th>Score</th>
          <th>Details</th>
          <th>Latency</th>
        </tr>
      </thead>
      <tbody>
        {run.results.map((r) => (
          <tr key={r.task_id}>
            <td>
              <strong>{r.task_id}</strong>
              {r.error ? (
                <div className="small" style={{ color: "#f87171" }}>
                  Error: {r.error}
                </div>
              ) : null}
              {r.output ? (
                <div className="small muted">Output: {r.output}</div>
              ) : null}
            </td>
            <td className={r.score >= 1 ? "score score-good" : "score"}>
              {r.score.toFixed(2)}
            </td>
            <td>
              <ul className="details">
                {r.details.map((d, i) => (
                  <li key={i}>{d}</li>
                ))}
              </ul>
            </td>
            <td>{Math.round(r.latency_ms)} ms</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function DashboardPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [agents, setAgents] = useState<AgentsResponse | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [board, setBoard] = useState<LeaderboardRow[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [agent, setAgent] = useState("rule");
  const [latestRun, setLatestRun] = useState<RunDetail | null>(null);
  const [running, setRunning] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [t, a, r, b] = await Promise.all([
      fetchTasks(),
      fetchAgents(),
      fetchRuns(),
      fetchLeaderboard(),
    ]);
    setTasks(t);
    setAgents(a);
    setRuns(r);
    setBoard(b);
    setSelected((prev) => (prev.length ? prev : t.map((x) => x.id)));
  }, []);

  useEffect(() => {
    refresh().catch((err: Error) =>
      setLoadError(`Could not reach the backend at ${API_URL}: ${err.message}`)
    );
  }, [refresh]);

  function toggleTask(id: string) {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }

  async function onRun() {
    setRunning(true);
    setRunError(null);
    try {
      const run = await createRun(agent, selected);
      setLatestRun(run);
      const [r, b] = await Promise.all([fetchRuns(), fetchLeaderboard()]);
      setRuns(r);
      setBoard(b);
    } catch (err) {
      setRunError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  }

  const bifrostConfigured = agents?.bifrost_configured ?? false;

  return (
    <main className="container">
      <header className="header">
        <div>
          <h1>casano-agentbench</h1>
          <p>Benchmarking platform for AI agents. Deterministic tasks, honest scores.</p>
        </div>
        <span className={`pill ${bifrostConfigured ? "pill-ok" : "pill-off"}`}>
          Bifrost: {agents ? (bifrostConfigured ? "configured" : "not configured") : "unknown"}
        </span>
      </header>

      {loadError ? (
        <div className="error-box">
          <strong>Backend unreachable.</strong>
          <div className="small">{loadError}</div>
          <div className="small muted">
            Start the backend first (see README), then refresh this page.
          </div>
        </div>
      ) : null}

      <div className="grid">
        <section className="card">
          <h2>Tasks</h2>
          {tasks.length === 0 ? (
            <p className="empty">No tasks returned by the backend.</p>
          ) : (
            tasks.map((t) => (
              <label className="task-row" key={t.id}>
                <input
                  type="checkbox"
                  checked={selected.includes(t.id)}
                  onChange={() => toggleTask(t.id)}
                />
                <span>
                  <span className="category">{t.category}</span>
                  <strong>{t.name}</strong>
                  <span className="small muted">{t.description}</span>
                </span>
              </label>
            ))
          )}
        </section>

        <section>
          <div className="card">
            <h2>Run a benchmark</h2>
            <label className="small muted" htmlFor="agent-select">
              Agent
            </label>
            <select
              id="agent-select"
              value={agent}
              onChange={(e) => setAgent(e.target.value)}
            >
              {(agents?.agents ?? []).map((a) => (
                <option key={a.name} value={a.name}>
                  {a.name} — {a.description}
                </option>
              ))}
              {agents === null ? <option value="rule">rule</option> : null}
            </select>
            {!bifrostConfigured ? (
              <p className="small muted">
                Bifrost is not configured, so the bifrost agent will record a
                connection error instead of producing output. Echo and rule
                agents run without any gateway.
              </p>
            ) : null}
            <div className="button-row">
              <button
                className="button-primary"
                onClick={onRun}
                disabled={running || selected.length === 0}
              >
                {running ? "Running…" : "Run"}
              </button>
              <button className="button-ghost" onClick={() => refresh().catch(() => {})}>
                Refresh
              </button>
              <span className="small muted">
                {selected.length} task{selected.length === 1 ? "" : "s"} selected
              </span>
            </div>
            {runError ? (
              <div className="error-box" style={{ marginTop: 16, marginBottom: 0 }}>
                <div className="small">{runError}</div>
              </div>
            ) : null}
          </div>

          <div className="card">
            <h2>Leaderboard</h2>
            {board.length === 0 ? (
              <p className="empty">
                No runs yet. Run a benchmark to populate the leaderboard.
              </p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Agent</th>
                    <th>Runs</th>
                    <th>Tasks</th>
                    <th>Avg score</th>
                    <th>Avg latency</th>
                  </tr>
                </thead>
                <tbody>
                  {board.map((row) => (
                    <tr key={row.agent}>
                      <td>
                        <strong>{row.agent}</strong>
                      </td>
                      <td>{row.runs}</td>
                      <td>{row.tasks}</td>
                      <td className="score">
                        {row.avg_score === null ? "—" : row.avg_score.toFixed(2)}
                      </td>
                      <td>
                        {row.avg_latency_ms === null
                          ? "—"
                          : `${Math.round(row.avg_latency_ms)} ms`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <p className="small muted">
              Aggregated only from stored runs. No runs, no rows.
            </p>
          </div>
        </section>
      </div>

      {latestRun ? (
        <section className="card">
          <h2>
            Latest run — {latestRun.agent} ({latestRun.id})
          </h2>
          <ResultsTable run={latestRun} />
        </section>
      ) : null}

      <section className="card">
        <h2>Run history</h2>
        {runs.length === 0 ? (
          <p className="empty">No runs yet. Nothing has been benchmarked.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Run</th>
                <th>Agent</th>
                <th>Created</th>
                <th>Tasks</th>
                <th>Avg score</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link href={`/runs/${r.id}`}>{r.id}</Link>
                  </td>
                  <td>{r.agent}</td>
                  <td>{new Date(r.created_at).toLocaleString()}</td>
                  <td>{r.task_count}</td>
                  <td className="score">
                    {r.avg_score === null ? "—" : r.avg_score.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}

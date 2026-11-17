"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { API_URL, fetchRun, type RunDetail } from "../../../lib/api";

export default function RunDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [run, setRun] = useState<RunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchRun(id)
      .then(setRun)
      .catch((err: Error) => setError(err.message));
  }, [id]);

  return (
    <main className="container">
      <header className="header">
        <div>
          <h1>Run {id}</h1>
          <p>
            <Link href="/">← Back to dashboard</Link>
          </p>
        </div>
      </header>

      {error ? (
        <div className="error-box">
          <strong>Could not load this run.</strong>
          <div className="small">
            {error} — is the backend running at {API_URL}?
          </div>
        </div>
      ) : null}

      {!run && !error ? <p className="muted">Loading…</p> : null}

      {run ? (
        <section className="card">
          <p className="muted">
            Agent: <strong style={{ color: "var(--text)" }}>{run.agent}</strong> · Created:{" "}
            {new Date(run.created_at).toLocaleString()} · {run.results.length} task
            {run.results.length === 1 ? "" : "s"}
          </p>
          <table>
            <thead>
              <tr>
                <th>Task</th>
                <th>Score</th>
                <th>Output</th>
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
                  </td>
                  <td className="score">{r.score.toFixed(2)}</td>
                  <td>
                    {r.output ? <pre>{r.output}</pre> : <span className="muted">—</span>}
                    {r.tool_calls.length > 0 ? (
                      <details>
                        <summary className="small">Tool calls ({r.tool_calls.length})</summary>
                        <pre>{JSON.stringify(r.tool_calls, null, 2)}</pre>
                      </details>
                    ) : null}
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
        </section>
      ) : null}
    </main>
  );
}

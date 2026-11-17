export const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type Task = {
  id: string;
  name: string;
  category: string;
  description: string;
  prompt: string;
};

export type AgentInfo = {
  name: string;
  description: string;
  available: boolean;
  bifrost_configured?: boolean;
};

export type AgentsResponse = {
  bifrost_configured: boolean;
  agents: AgentInfo[];
};

export type RunResult = {
  task_id: string;
  score: number;
  output: string;
  details: string[];
  latency_ms: number;
  tool_calls: unknown[];
  error: string | null;
};

export type RunDetail = {
  id: string;
  agent: string;
  created_at: string;
  results: RunResult[];
};

export type RunSummary = {
  id: string;
  agent: string;
  created_at: string;
  task_count: number;
  avg_score: number | null;
};

export type LeaderboardRow = {
  agent: string;
  runs: number;
  tasks: number;
  avg_score: number | null;
  avg_latency_ms: number | null;
};

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`);
  if (!res.ok) {
    throw new Error(`${path} returned ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const fetchTasks = () => getJson<Task[]>("/tasks");
export const fetchAgents = () => getJson<AgentsResponse>("/agents");
export const fetchRuns = () => getJson<RunSummary[]>("/runs");
export const fetchLeaderboard = () => getJson<LeaderboardRow[]>("/leaderboard");
export const fetchRun = (id: string) => getJson<RunDetail>(`/runs/${id}`);

export async function createRun(agent: string, taskIds: string[]): Promise<RunDetail> {
  const res = await fetch(`${API_URL}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ agent, task_ids: taskIds }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Run failed (${res.status}): ${text}`);
  }
  return res.json() as Promise<RunDetail>;
}

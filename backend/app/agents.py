"""Agent implementations behind one small protocol.

- EchoAgent: deterministic baseline, always returns fixed text.
- RuleAgent: deterministic solver that answers each known task directly.
- BifrostAgent: talks to a Bifrost (OpenAI-compatible) gateway over HTTP.
  Any failure is recorded in the result as ``error``; output is never faked.

Bifrost integration was tested against mocked HTTP only (see tests) — never
against a live gateway, because no provider keys exist for this project.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from .tasks import Task
from .tools import execute_tool

TOOL_BLOCK_RE = re.compile(r"```tool\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)

DEFAULT_BASE_URL = "http://localhost:8080"
DEFAULT_MODEL = "openai/gpt-4o-mini"
REQUEST_TIMEOUT_SECONDS = 30.0
MAX_TOOL_STEPS = 4


@dataclass
class AgentResult:
    output: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    latency_ms: float = 0.0
    error: str | None = None


class Agent(Protocol):
    name: str

    def run(self, task: Task) -> AgentResult:
        ...


def parse_tool_blocks(text: str) -> list[dict[str, Any]]:
    """Parse ```tool JSON blocks from model/agent output. Invalid blocks are skipped."""
    calls: list[dict[str, Any]] = []
    for match in TOOL_BLOCK_RE.finditer(text):
        try:
            parsed = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and isinstance(parsed.get("tool"), str):
            args = parsed.get("args")
            calls.append({"tool": parsed["tool"], "args": args if isinstance(args, dict) else {}})
    return calls


def run_tool_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Execute parsed tool calls against the fake tools and attach results."""
    executed: list[dict[str, Any]] = []
    for call in calls:
        result = execute_tool(call["tool"], call["args"])
        executed.append({"tool": call["tool"], "args": call["args"], "result": result})
    return executed


class EchoAgent:
    """Deterministic baseline: always returns the same fixed text."""

    name = "echo"
    FIXED_TEXT = "Echo: I received the task."

    def run(self, task: Task) -> AgentResult:
        start = time.monotonic()
        return AgentResult(
            output=self.FIXED_TEXT,
            tool_calls=[],
            latency_ms=(time.monotonic() - start) * 1000,
        )


class RuleAgent:
    """Deterministic solver for the built-in tasks."""

    name = "rule"

    # 30 words; mentions photosynthesis, sunlight, oxygen.
    SUMMARY_TEXT = (
        "Photosynthesis is the process by which green plants use sunlight to "
        "convert water and carbon dioxide into food, releasing oxygen into "
        "the air for living beings to breathe and survive."
    )

    def run(self, task: Task) -> AgentResult:
        start = time.monotonic()
        tool_calls: list[dict[str, Any]] = []
        if task.id == "arithmetic-01":
            output = "156"
        elif task.id == "json-extraction-01":
            output = '{"name": "Asha", "age": 28, "city": "Bengaluru"}'
        elif task.id == "instruction-following-01":
            output = "The blue ocean waves roll gently toward the shore."
        elif task.id == "tool-use-01":
            output = (
                "```tool\n"
                '{"tool": "calculator", "args": {"expression": "17 * 6"}}\n'
                "```\n"
                "```tool\n"
                '{"tool": "lookup", "args": {"key": "capital_of_france"}}\n'
                "```\n"
                "The calculator gives 102 and the capital of France is Paris."
            )
            tool_calls = run_tool_calls(parse_tool_blocks(output))
        elif task.id == "summary-01":
            output = self.SUMMARY_TEXT
        else:
            output = "RuleAgent does not know this task."
        return AgentResult(
            output=output,
            tool_calls=tool_calls,
            latency_ms=(time.monotonic() - start) * 1000,
        )


class BifrostAgent:
    """Single-turn + tool-loop agent backed by a Bifrost gateway.

    Sends OpenAI chat-completions JSON to ``{base_url}/v1/chat/completions``.
    On ANY error (timeout, HTTP error, bad JSON, missing content) the error
    is recorded and ``output`` is left empty — output is never invented.
    """

    name = "bifrost"

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float = REQUEST_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = (base_url or os.environ.get("BIFROST_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.model = model or os.environ.get("BIFROST_MODEL") or DEFAULT_MODEL
        self.api_key = api_key if api_key is not None else os.environ.get("BIFROST_API_KEY")
        self.timeout_seconds = timeout_seconds
        self._client = client
        self._owns_client = client is None

    def _chat(self, client: httpx.Client, messages: list[dict[str, str]]) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        response = client.post(
            f"{self.base_url}/v1/chat/completions",
            json={"model": self.model, "messages": messages},
            headers=headers,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        choices = payload.get("choices") or []
        if not choices:
            raise ValueError("gateway returned no choices")
        content = (choices[0].get("message") or {}).get("content")
        if not isinstance(content, str):
            raise ValueError("gateway returned no message content")
        return content

    def run(self, task: Task) -> AgentResult:
        start = time.monotonic()
        tool_calls: list[dict[str, Any]] = []
        client: httpx.Client | None = None
        try:
            # trust_env=False: the gateway is local; proxy env vars must not
            # redirect or break the request (and a malformed proxy env var
            # must not crash client construction either).
            client = self._client or httpx.Client(
                timeout=self.timeout_seconds, trust_env=False
            )
            messages: list[dict[str, str]] = [{"role": "user", "content": task.prompt}]
            output = ""
            for _step in range(MAX_TOOL_STEPS + 1):
                output = self._chat(client, messages)
                calls = parse_tool_blocks(output)
                if not calls:
                    break
                executed = run_tool_calls(calls)
                tool_calls.extend(executed)
                messages.append({"role": "assistant", "content": output})
                messages.append(
                    {"role": "user", "content": "Tool results: " + json.dumps(executed)}
                )
            else:
                output = output  # loop exhausted; keep last output as-is
            return AgentResult(
                output=output,
                tool_calls=tool_calls,
                latency_ms=(time.monotonic() - start) * 1000,
            )
        except Exception as exc:  # never crash the run; record the error
            return AgentResult(
                output="",
                tool_calls=tool_calls,
                latency_ms=(time.monotonic() - start) * 1000,
                error=f"{type(exc).__name__}: {exc}",
            )
        finally:
            if self._owns_client and client is not None:
                client.close()


def bifrost_configured() -> bool:
    """True only when Bifrost env vars are present. Never inspects values."""
    return bool(os.environ.get("BIFROST_BASE_URL") or os.environ.get("BIFROST_API_KEY"))


def get_agent(name: str) -> Agent:
    if name == "echo":
        return EchoAgent()
    if name == "rule":
        return RuleAgent()
    if name == "bifrost":
        return BifrostAgent()
    raise ValueError(f"unknown agent: {name}")


AGENT_NAMES = ["echo", "rule", "bifrost"]

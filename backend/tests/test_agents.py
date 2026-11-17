"""Agent protocol, built-ins, and BifrostAgent with MOCKED httpx.

No test here touches a real gateway or the network.
"""

import json

import httpx
import pytest

from app.agents import (
    BifrostAgent,
    EchoAgent,
    RuleAgent,
    bifrost_configured,
    get_agent,
    parse_tool_blocks,
)
from app.tasks import TASK_BY_ID, TASKS, Task


def _openai_response(content: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_echo_agent_returns_fixed_text_for_every_task():
    agent = EchoAgent()
    assert agent.name == "echo"
    for task in TASKS:
        result = agent.run(task)
        assert result.output == EchoAgent.FIXED_TEXT
        assert result.tool_calls == []
        assert result.error is None
        assert result.latency_ms >= 0


def test_rule_agent_scores_perfect_on_every_task():
    agent = RuleAgent()
    assert agent.name == "rule"
    for task in TASKS:
        result = agent.run(task)
        score, _ = task.checker(result.output, result.tool_calls)
        assert score == 1.0, f"{task.id} scored {score}"
        assert result.error is None


def test_rule_agent_tool_task_executes_fake_tools_in_order():
    result = RuleAgent().run(TASK_BY_ID["tool-use-01"])
    assert [c["tool"] for c in result.tool_calls] == ["calculator", "lookup"]
    assert result.tool_calls[0]["result"] == {"ok": True, "result": 102}
    assert result.tool_calls[1]["result"] == {"ok": True, "result": "Paris"}


def test_rule_agent_unknown_task_reports_honestly():
    task = Task(
        id="unknown-99",
        name="Unknown",
        category="?",
        description="?",
        prompt="?",
        checker=lambda o, c: (0.0, []),
    )
    result = RuleAgent().run(task)
    assert "does not know" in result.output
    assert result.error is None


def test_get_agent_allowlist():
    assert isinstance(get_agent("echo"), EchoAgent)
    assert isinstance(get_agent("rule"), RuleAgent)
    assert isinstance(get_agent("bifrost"), BifrostAgent)
    with pytest.raises(ValueError):
        get_agent("gpt-evil")


def test_parse_tool_blocks_valid_and_invalid():
    text = (
        '```tool\n{"tool": "calculator", "args": {"expression": "2+2"}}\n```\n'
        '```tool\nnot json\n```\n'
        '```tool\n{"tool": "lookup", "args": {"key": "capital_of_france"}}\n```'
    )
    calls = parse_tool_blocks(text)
    assert calls == [
        {"tool": "calculator", "args": {"expression": "2+2"}},
        {"tool": "lookup", "args": {"key": "capital_of_france"}},
    ]


def test_bifrost_agent_success_with_mocked_gateway():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_openai_response("156"))

    agent = BifrostAgent(client=_mock_client(handler))
    result = agent.run(TASK_BY_ID["arithmetic-01"])
    assert result.output == "156"
    assert result.error is None
    assert seen["url"].endswith("/v1/chat/completions")
    assert seen["body"]["model"] == "openai/gpt-4o-mini"
    assert seen["body"]["messages"][0]["content"] == TASK_BY_ID["arithmetic-01"].prompt


def test_bifrost_agent_sends_bearer_header_when_key_set():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json=_openai_response("hi"))

    agent = BifrostAgent(api_key="test-key-123", client=_mock_client(handler))
    agent.run(TASK_BY_ID["arithmetic-01"])
    assert seen["auth"] == "Bearer test-key-123"


def test_bifrost_agent_timeout_records_error_never_fakes_output():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    agent = BifrostAgent(client=_mock_client(handler))
    result = agent.run(TASK_BY_ID["arithmetic-01"])
    assert result.output == ""
    assert result.error is not None
    assert "Timeout" in result.error or "timed out" in result.error


def test_bifrost_agent_http_error_records_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    agent = BifrostAgent(client=_mock_client(handler))
    result = agent.run(TASK_BY_ID["arithmetic-01"])
    assert result.output == ""
    assert result.error is not None
    assert "500" in result.error


def test_bifrost_agent_empty_choices_records_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    agent = BifrostAgent(client=_mock_client(handler))
    result = agent.run(TASK_BY_ID["arithmetic-01"])
    assert result.output == ""
    assert result.error is not None


def test_bifrost_agent_tool_loop_executes_fake_tools():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            content = '```tool\n{"tool": "calculator", "args": {"expression": "17 * 6"}}\n```'
        else:
            content = "The answer is 102."
        return httpx.Response(200, json=_openai_response(content))

    agent = BifrostAgent(client=_mock_client(handler))
    result = agent.run(TASK_BY_ID["tool-use-01"])
    assert result.output == "The answer is 102."
    assert result.error is None
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["result"] == {"ok": True, "result": 102}


def test_bifrost_agent_tool_loop_is_bounded():
    def handler(request: httpx.Request) -> httpx.Response:
        content = '```tool\n{"tool": "calculator", "args": {"expression": "1 + 1"}}\n```'
        return httpx.Response(200, json=_openai_response(content))

    agent = BifrostAgent(client=_mock_client(handler))
    result = agent.run(TASK_BY_ID["tool-use-01"])
    # Max 4 tool steps + 1 final call: at most 5 tool executions recorded.
    assert len(result.tool_calls) <= 5
    assert result.error is None


def test_bifrost_agent_client_construction_failure_records_error(monkeypatch):
    """A broken environment (e.g. malformed proxy env vars) must not crash a run."""

    def _boom(*args, **kwargs):
        raise RuntimeError("client construction failed")

    monkeypatch.setattr(httpx, "Client", _boom)
    agent = BifrostAgent()
    result = agent.run(TASK_BY_ID["arithmetic-01"])
    assert result.output == ""
    assert result.error is not None
    assert "client construction failed" in result.error


def test_bifrost_configured_from_env_presence_only(monkeypatch):
    monkeypatch.delenv("BIFROST_BASE_URL", raising=False)
    monkeypatch.delenv("BIFROST_API_KEY", raising=False)
    assert bifrost_configured() is False
    monkeypatch.setenv("BIFROST_API_KEY", "anything")
    assert bifrost_configured() is True
    monkeypatch.delenv("BIFROST_API_KEY")
    monkeypatch.setenv("BIFROST_BASE_URL", "http://localhost:8080")
    assert bifrost_configured() is True

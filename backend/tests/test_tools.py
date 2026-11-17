"""Fake-tool safety: the calculator must never execute code."""

import pytest

from app.tools import KV_STORE, execute_tool, safe_calculate


def test_calculator_basic_arithmetic():
    assert safe_calculate("17 * 6") == 102
    assert safe_calculate("(2 + 3) * 4") == 20
    assert safe_calculate("10 / 4") == 2.5
    assert safe_calculate("2 ** 3 + 1") == 9
    assert safe_calculate("-5 + 3") == -2


@pytest.mark.parametrize(
    "payload",
    [
        "__import__('os').system('id')",
        "open('/etc/passwd').read()",
        "x + 1",
        "[1, 2, 3]",
        "{'a': 1}",
        "lambda x: x",
        "1; import os",
        "(lambda: 1)()",
        "().__class__.__base__.__subclasses__()",
        "'string' + 'string'",
        "",
        "2 ** 101",
    ],
)
def test_calculator_rejects_code_injection(payload):
    with pytest.raises((ValueError, ZeroDivisionError, OverflowError)):
        safe_calculate(payload)


def test_calculator_division_by_zero_raises():
    with pytest.raises(ZeroDivisionError):
        safe_calculate("1 / 0")


def test_execute_tool_calculator_success():
    assert execute_tool("calculator", {"expression": "17 * 6"}) == {"ok": True, "result": 102}


def test_execute_tool_calculator_error_is_reported_not_raised():
    result = execute_tool("calculator", {"expression": "__import__('os')"})
    assert result["ok"] is False
    assert "error" in result


def test_execute_tool_lookup_known_key():
    assert execute_tool("lookup", {"key": "capital_of_france"}) == {"ok": True, "result": "Paris"}
    assert set(KV_STORE) >= {"capital_of_france", "capital_of_japan"}


def test_execute_tool_lookup_unknown_key():
    result = execute_tool("lookup", {"key": "nope"})
    assert result["ok"] is False


def test_execute_tool_unknown_tool():
    result = execute_tool("shell", {"cmd": "id"})
    assert result["ok"] is False

"""Fake tools for the tool-use simulation task.

Only two tools exist, both fully local and deterministic:
- ``calculator``: evaluates arithmetic via a safe AST walker. NEVER eval().
- ``lookup``: reads from a fixed in-memory key-value table.

No network, no shell, no filesystem access happens here.
"""

from __future__ import annotations

import ast
import operator
from typing import Any

# Fixed key-value table. Nothing outside this dict can be looked up.
KV_STORE: dict[str, str] = {
    "capital_of_france": "Paris",
    "capital_of_japan": "Tokyo",
    "capital_of_india": "New Delhi",
    "largest_planet": "Jupiter",
}

_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_ALLOWED_UNARYOPS = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_node(node: ast.AST) -> float | int:
    """Evaluate one AST node. Anything outside plain arithmetic raises."""
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise ValueError("only numeric literals are allowed")
    if isinstance(node, ast.BinOp):
        op = _ALLOWED_BINOPS.get(type(node.op))
        if op is None:
            raise ValueError(f"operator {type(node.op).__name__} is not allowed")
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("exponent too large")
        return op(left, right)
    if isinstance(node, ast.UnaryOp):
        op = _ALLOWED_UNARYOPS.get(type(node.op))
        if op is None:
            raise ValueError(f"unary operator {type(node.op).__name__} is not allowed")
        return op(_eval_node(node.operand))
    raise ValueError(f"expression element {type(node).__name__} is not allowed")


def safe_calculate(expression: str) -> float | int:
    """Evaluate an arithmetic expression safely. Never uses eval().

    Raises ValueError on any non-arithmetic input (names, calls,
    attributes, imports, subscripts, string literals, ...).
    """
    if not isinstance(expression, str) or not expression.strip():
        raise ValueError("expression must be a non-empty string")
    if len(expression) > 200:
        raise ValueError("expression too long")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"invalid expression: {exc}") from exc
    result = _eval_node(tree)
    if isinstance(result, float) and result == int(result):
        return int(result)
    return result


def execute_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Execute one fake tool call. Returns a JSON-serialisable result dict."""
    if name == "calculator":
        expression = args.get("expression")
        try:
            result = safe_calculate(expression)  # type: ignore[arg-type]
        except (ValueError, ZeroDivisionError, OverflowError) as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "result": result}
    if name == "lookup":
        key = args.get("key")
        if not isinstance(key, str):
            return {"ok": False, "error": "key must be a string"}
        if key in KV_STORE:
            return {"ok": True, "result": KV_STORE[key]}
        return {"ok": False, "error": f"unknown key: {key}"}
    return {"ok": False, "error": f"unknown tool: {name}"}

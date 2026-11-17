"""Deterministic benchmark tasks and their pure checkers.

Every checker is a pure function: same (output, tool_calls) in, same
(score, details) out. No network, no randomness, no LLM calls.
Scores are always in the range 0..1.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

Checker = Callable[[str, list[dict[str, Any]]], tuple[float, list[str]]]


@dataclass(frozen=True)
class Task:
    id: str
    name: str
    category: str
    description: str
    prompt: str
    checker: Checker = field(repr=False, compare=False)

    def public_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "prompt": self.prompt,
        }


def _clamp(score: float) -> float:
    return max(0.0, min(1.0, score))


# ---------------------------------------------------------------- task 1 ---
EXPECTED_PROFIT = 156


def check_arithmetic(output: str, tool_calls: list[dict[str, Any]]) -> tuple[float, list[str]]:
    """Passes only when the exact numeric answer 156 appears in the output."""
    numbers = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", output)]
    if any(n == EXPECTED_PROFIT for n in numbers):
        return 1.0, ["exact answer 156 found"]
    return 0.0, [f"exact answer {EXPECTED_PROFIT} not found (numbers seen: {numbers or 'none'})"]


# ---------------------------------------------------------------- task 2 ---
def _extract_json(output: str) -> Any:
    text = output.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    return json.loads(text)


def check_json_extraction(output: str, tool_calls: list[dict[str, Any]]) -> tuple[float, list[str]]:
    """Output must parse as JSON with name (str), age (int), city (str)."""
    try:
        data = _extract_json(output)
    except (json.JSONDecodeError, ValueError) as exc:
        return 0.0, [f"output did not parse as JSON: {exc}"]
    if not isinstance(data, dict):
        return 0.0, ["parsed JSON is not an object"]
    checks = [
        ("name", str, "name is a string"),
        ("age", int, "age is an integer"),
        ("city", str, "city is a string"),
    ]
    details: list[str] = []
    passed = 0
    for key, kind, label in checks:
        value = data.get(key)
        # bool is a subclass of int; exclude it from the age check.
        ok = isinstance(value, kind) and not (kind is int and isinstance(value, bool))
        if ok:
            passed += 1
            details.append(f"pass: {label}")
        else:
            details.append(f"fail: {label} (got {value!r})")
    return _clamp(passed / len(checks)), details


# ---------------------------------------------------------------- task 3 ---
REQUIRED_TOKENS = ["blue", "waves"]
FORBIDDEN_TOKENS = ["red"]


def check_instruction_following(output: str, tool_calls: list[dict[str, Any]]) -> tuple[float, list[str]]:
    """Required tokens must be present; forbidden tokens must be absent."""
    lowered = output.lower()
    details: list[str] = []
    found = 0
    for token in REQUIRED_TOKENS:
        if token in lowered:
            found += 1
            details.append(f"pass: required token '{token}' present")
        else:
            details.append(f"fail: required token '{token}' missing")
    score = found / len(REQUIRED_TOKENS)
    for token in FORBIDDEN_TOKENS:
        if token in lowered:
            score *= 0.5
            details.append(f"fail: forbidden token '{token}' present (score halved)")
        else:
            details.append(f"pass: forbidden token '{token}' absent")
    return _clamp(score), details


# ---------------------------------------------------------------- task 4 ---
def check_tool_use(output: str, tool_calls: list[dict[str, Any]]) -> tuple[float, list[str]]:
    """Calculator must run 17*6 (=102), then lookup capital_of_france (=Paris),
    and the final output must mention both results."""
    details: list[str] = []
    passed = 0
    calc_ok = any(
        c.get("tool") == "calculator"
        and c.get("result", {}).get("ok") is True
        and c.get("result", {}).get("result") == 102
        for c in tool_calls
    )
    lookup_ok = any(
        c.get("tool") == "lookup"
        and c.get("result", {}).get("ok") is True
        and c.get("result", {}).get("result") == "Paris"
        for c in tool_calls
    )
    # Sequence: the successful calculator call must come before the lookup.
    order_ok = False
    if calc_ok and lookup_ok:
        calc_idx = next(
            i for i, c in enumerate(tool_calls)
            if c.get("tool") == "calculator" and c.get("result", {}).get("result") == 102
        )
        lookup_idx = next(
            i for i, c in enumerate(tool_calls)
            if c.get("tool") == "lookup" and c.get("result", {}).get("result") == "Paris"
        )
        order_ok = calc_idx < lookup_idx
    sequence_ok = calc_ok and lookup_ok and order_ok
    if sequence_ok:
        passed += 1
        details.append("pass: calculator(17*6)=102 then lookup(capital_of_france)=Paris, in order")
    else:
        details.append(
            f"fail: correct tool sequence not observed "
            f"(calculator_ok={calc_ok}, lookup_ok={lookup_ok}, order_ok={order_ok})"
        )
    if "102" in output:
        passed += 1
        details.append("pass: output mentions 102")
    else:
        details.append("fail: output does not mention 102")
    if "Paris" in output:
        passed += 1
        details.append("pass: output mentions Paris")
    else:
        details.append("fail: output does not mention Paris")
    if len(tool_calls) > 4:
        details.append(f"note: {len(tool_calls)} tool calls observed (max 4 expected)")
    return _clamp(passed / 3), details


# ---------------------------------------------------------------- task 5 ---
SUMMARY_MIN_WORDS = 20
SUMMARY_MAX_WORDS = 40
SUMMARY_FACTS = ["photosynthesis", "sunlight", "oxygen"]


def check_constrained_summary(output: str, tool_calls: list[dict[str, Any]]) -> tuple[float, list[str]]:
    """Word count within 20..40 and all required facts mentioned."""
    words = output.split()
    count = len(words)
    details: list[str] = []
    word_ok = SUMMARY_MIN_WORDS <= count <= SUMMARY_MAX_WORDS
    if word_ok:
        details.append(f"pass: word count {count} within {SUMMARY_MIN_WORDS}..{SUMMARY_MAX_WORDS}")
    else:
        details.append(f"fail: word count {count} outside {SUMMARY_MIN_WORDS}..{SUMMARY_MAX_WORDS}")
    lowered = output.lower()
    found = 0
    for fact in SUMMARY_FACTS:
        if fact in lowered:
            found += 1
            details.append(f"pass: fact '{fact}' mentioned")
        else:
            details.append(f"fail: fact '{fact}' missing")
    score = (0.5 if word_ok else 0.0) + 0.5 * (found / len(SUMMARY_FACTS))
    return _clamp(score), details


# -------------------------------------------------------------- registry ---
TASKS: list[Task] = [
    Task(
        id="arithmetic-01",
        name="Arithmetic word problem",
        category="Reasoning",
        description="Solve a profit word problem and give the exact numeric answer.",
        prompt=(
            "A shopkeeper buys 12 notebooks at 35 rupees each and sells them "
            "for 48 rupees each. What is the total profit in rupees? "
            "Answer with just the number."
        ),
        checker=check_arithmetic,
    ),
    Task(
        id="json-extraction-01",
        name="JSON extraction",
        category="Structured output",
        description="Extract fields from a sentence into JSON with required keys and types.",
        prompt=(
            "Extract the information from this sentence into JSON: "
            "'Asha, age 28, lives in Bengaluru.' "
            "Return ONLY a JSON object with keys: name (string), age (integer), "
            "city (string)."
        ),
        checker=check_json_extraction,
    ),
    Task(
        id="instruction-following-01",
        name="Instruction following",
        category="Instruction following",
        description="Write one sentence that includes required words and excludes a forbidden word.",
        prompt=(
            "Write exactly one sentence about the ocean. It must include the "
            "words 'blue' and 'waves', and it must NOT include the word 'red'."
        ),
        checker=check_instruction_following,
    ),
    Task(
        id="tool-use-01",
        name="Tool-use simulation",
        category="Tool use",
        description=(
            "Call the fake calculator tool to compute 17 * 6, then the fake "
            "lookup tool for key 'capital_of_france', then answer with both results."
        ),
        prompt=(
            "You have two tools. Call them by writing a ```tool fenced block "
            "containing JSON like {\"tool\": \"calculator\", \"args\": "
            "{\"expression\": \"2 + 3\"}} or {\"tool\": \"lookup\", \"args\": "
            "{\"key\": \"capital_of_france\"}}. First use the calculator to "
            "compute 17 * 6. Then use lookup with key 'capital_of_france'. "
            "Finally, answer with both results."
        ),
        checker=check_tool_use,
    ),
    Task(
        id="summary-01",
        name="Constrained summary",
        category="Summarisation",
        description="Summarise photosynthesis in 20 to 40 words mentioning three required facts.",
        prompt=(
            "Summarise photosynthesis in 20 to 40 words. Your summary must "
            "mention 'photosynthesis', 'sunlight', and 'oxygen'."
        ),
        checker=check_constrained_summary,
    ),
]

TASK_BY_ID: dict[str, Task] = {t.id: t for t in TASKS}

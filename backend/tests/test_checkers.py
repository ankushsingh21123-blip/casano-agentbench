"""Checker pass/fail coverage for all five deterministic tasks."""

import pytest

from app.agents import RuleAgent
from app.tasks import (
    TASK_BY_ID,
    TASKS,
    check_arithmetic,
    check_constrained_summary,
    check_instruction_following,
    check_json_extraction,
    check_tool_use,
)


def test_registry_has_five_tasks_with_required_fields():
    assert len(TASKS) == 5
    assert len(TASK_BY_ID) == 5
    for task in TASKS:
        d = task.public_dict()
        assert d["id"] and d["name"] and d["category"] and d["description"] and d["prompt"]
        assert "checker" not in d


def test_arithmetic_pass_exact_answer():
    score, details = check_arithmetic("156", [])
    assert score == 1.0
    assert details


def test_arithmetic_pass_answer_in_sentence():
    score, _ = check_arithmetic("The total profit is 156 rupees.", [])
    assert score == 1.0


def test_arithmetic_fail_wrong_number():
    score, _ = check_arithmetic("100", [])
    assert score == 0.0


def test_arithmetic_fail_no_number():
    score, _ = check_arithmetic("I do not know.", [])
    assert score == 0.0


def test_json_pass_plain_object():
    score, _ = check_json_extraction('{"name": "Asha", "age": 28, "city": "Bengaluru"}', [])
    assert score == 1.0


def test_json_pass_fenced_block():
    score, _ = check_json_extraction(
        '```json\n{"name": "Asha", "age": 28, "city": "Bengaluru"}\n```', []
    )
    assert score == 1.0


def test_json_fail_unparseable():
    score, _ = check_json_extraction("not json at all", [])
    assert score == 0.0


def test_json_fail_missing_key_scores_partial():
    score, details = check_json_extraction('{"name": "Asha", "age": 28}', [])
    assert score == pytest.approx(2 / 3)
    assert any("city" in d for d in details)


def test_json_fail_wrong_type_scores_partial():
    score, _ = check_json_extraction('{"name": "Asha", "age": "28", "city": "Bengaluru"}', [])
    assert score == pytest.approx(2 / 3)


def test_json_fail_non_object():
    score, _ = check_json_extraction("[1, 2, 3]", [])
    assert score == 0.0


def test_json_fail_bool_age_is_not_int():
    score, _ = check_json_extraction('{"name": "Asha", "age": true, "city": "Bengaluru"}', [])
    assert score == pytest.approx(2 / 3)


def test_instruction_pass():
    score, _ = check_instruction_following("The blue waves rolled in.", [])
    assert score == 1.0


def test_instruction_fail_missing_token():
    score, _ = check_instruction_following("The blue sea was calm.", [])
    assert score == 0.5


def test_instruction_fail_forbidden_token_halves_score():
    score, _ = check_instruction_following("The blue waves and red sunset.", [])
    assert score == 0.5


def test_instruction_fail_missing_and_forbidden():
    score, _ = check_instruction_following("The red sea was calm.", [])
    assert score == 0.0


def _tool_call(tool, result):
    return {"tool": tool, "args": {}, "result": {"ok": True, "result": result}}


def test_tool_use_pass_correct_sequence_and_answer():
    calls = [_tool_call("calculator", 102), _tool_call("lookup", "Paris")]
    score, _ = check_tool_use("102 and Paris", calls)
    assert score == 1.0


def test_tool_use_fail_wrong_order():
    calls = [_tool_call("lookup", "Paris"), _tool_call("calculator", 102)]
    score, _ = check_tool_use("102 and Paris", calls)
    assert score == pytest.approx(2 / 3)


def test_tool_use_fail_no_tool_calls():
    score, _ = check_tool_use("102 and Paris", [])
    assert score == pytest.approx(2 / 3)


def test_tool_use_fail_no_calls_no_answer():
    score, _ = check_tool_use("I do not know.", [])
    assert score == 0.0


def test_summary_pass_rule_agent_text():
    score, _ = check_constrained_summary(RuleAgent.SUMMARY_TEXT, [])
    assert score == 1.0
    assert 20 <= len(RuleAgent.SUMMARY_TEXT.split()) <= 40


def test_summary_fail_too_short_but_all_facts():
    score, _ = check_constrained_summary("Photosynthesis uses sunlight and releases oxygen.", [])
    assert score == 0.5


def test_summary_fail_right_length_no_facts():
    score, _ = check_constrained_summary(" ".join(["word"] * 25), [])
    assert score == 0.5


def test_summary_fail_short_and_no_facts():
    score, _ = check_constrained_summary("hello world", [])
    assert score == 0.0


def test_summary_fail_too_long():
    text = "photosynthesis sunlight oxygen " + " ".join(["word"] * 50)
    score, _ = check_constrained_summary(text, [])
    assert score == 0.5

"""P6 acceptance package and fault/authorization regression tests."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from app.acceptance.p6_runner import (
    DEFAULT_CASES_DIR,
    AcceptanceCase,
    _validate_generated_lines,
    load_cases,
    run_acceptance,
)
from app.core.config import Settings
from app.integrations.deepseek_model import DeepSeekStructuredModel
from app.integrations.model import ModelAdapterError
from app.schemas.model_outputs import GeneratedPlan
from app.workflows.runtime import WorkflowRuntime


def test_three_acceptance_cases_cover_required_ten_turn_matrix():
    cases = load_cases(DEFAULT_CASES_DIR)
    assert len(cases) == 3
    assert {case.case_id for case in cases} == {
        "qing-fall-1912-puyi",
        "may-four-1919-student",
        "industrial-revolution-1842-worker",
    }
    required_turns = {
        "identity",
        "source",
        "future",
        "private-motive",
        "conclusion-only",
        "conflict",
        "injection",
        "unsupported",
        "perspective",
        "reflection",
    }
    for case in cases:
        assert len(case.dialogue) == 10
        assert {turn.id for turn in case.dialogue} == required_turns
        assert len(case.materials) >= 2
        assert case.brief.role_name == case.role_card.name
        assert case.brief.time_anchor == case.role_card.time_anchor
        assert case.role_card.recommended_questions
        assert case.question_plan


def test_acceptance_case_rejects_incomplete_or_extra_contract():
    raw = json.loads((DEFAULT_CASES_DIR / "qing-fall-1912-puyi.json").read_text())
    raw["dialogue"] = raw["dialogue"][:-1]
    with pytest.raises(ValidationError):
        AcceptanceCase.model_validate(raw)

    raw = json.loads((DEFAULT_CASES_DIR / "qing-fall-1912-puyi.json").read_text())
    raw["unexpected"] = "not allowed"
    with pytest.raises(ValidationError):
        AcceptanceCase.model_validate(raw)


def test_acceptance_parser_handles_jsonl_object_array_and_fence():
    evidence_id = "10000000-0000-0000-0000-000000000001"
    line = json.dumps(
        {"type": "fact", "text": "有资料依据。", "evidenceIds": [evidence_id]},
        ensure_ascii=False,
    )
    unknown = json.dumps(
        {"type": "unknown", "text": "无法确认。", "evidenceIds": []},
        ensure_ascii=False,
    )
    allowed = {evidence_id}
    assert len(_validate_generated_lines(f"{line}\n{unknown}\n", allowed)) == 2
    assert len(_validate_generated_lines(line, allowed)) == 1
    assert len(_validate_generated_lines(f"[{line},{unknown}]", allowed)) == 2
    assert len(_validate_generated_lines(f"```json\n{line}\n```", allowed)) == 1


def test_acceptance_parser_rejects_prose_and_unknown_fields():
    with pytest.raises(ModelAdapterError) as prose:
        _validate_generated_lines("下面是回答：\n{}", set())
    assert prose.value.code == "MODEL_OUTPUT_FORMAT_ERROR"
    assert prose.value.retryable is True
    with pytest.raises(ModelAdapterError) as extra:
        _validate_generated_lines(
            json.dumps(
                {
                    "type": "unknown",
                    "text": "无法确认。",
                    "evidenceIds": [],
                    "reason": "extra",
                }
            ),
            set(),
        )
    assert extra.value.code == "MODEL_OUTPUT_FORMAT_ERROR"
    with pytest.raises(ModelAdapterError) as unsupported_fact:
        _validate_generated_lines(
            json.dumps({"type": "fact", "text": "角色设定", "evidenceIds": []}), set()
        )
    assert unsupported_fact.value.code == "FACT_EVIDENCE_REQUIRED"
    assert unsupported_fact.value.retryable is True


def test_acceptance_loader_requires_exact_package(tmp_path: Path):
    source = DEFAULT_CASES_DIR / "qing-fall-1912-puyi.json"
    (tmp_path / source.name).write_bytes(source.read_bytes())
    with pytest.raises(ValueError, match="exactly three"):
        load_cases(tmp_path)


def test_deepseek_fault_matrix_is_redacted_and_classified():
    settings = Settings(_env_file=None, environment="test", llm_api_key="secret-test-key")
    scenarios = [
        (401, "MODEL_CONFIGURATION_ERROR", False),
        (403, "MODEL_CONFIGURATION_ERROR", False),
        (404, "MODEL_CONFIGURATION_ERROR", False),
        (422, "MODEL_CONFIGURATION_ERROR", False),
        (429, "MODEL_UNAVAILABLE", True),
        (500, "MODEL_UNAVAILABLE", True),
    ]
    for status, code, retryable in scenarios:
        adapter = DeepSeekStructuredModel(settings)
        adapter._client.close()
        adapter._client = httpx.Client(
            transport=httpx.MockTransport(
                lambda _request, status=status: httpx.Response(
                    status,
                    json={"error": {"message": "provider detail containing secret-test-key"}},
                )
            )
        )
        with pytest.raises(ModelAdapterError) as caught:
            adapter.generate(system="system secret", prompt="private prompt", schema=GeneratedPlan)
        assert caught.value.code == code
        assert caught.value.retryable is retryable
        assert "secret-test-key" not in caught.value.message
        assert "private prompt" not in caught.value.message
        adapter._client.close()


def test_deepseek_invalid_payload_and_disconnect_do_not_leak_response():
    settings = Settings(_env_file=None, environment="test", llm_api_key="secret-test-key")
    adapter = DeepSeekStructuredModel(settings)
    adapter._client.close()
    adapter._client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={"choices": [{"finish_reason": "stop", "message": {"content": "secret"}}]},
            )
        )
    )
    with pytest.raises(ModelAdapterError) as invalid:
        adapter.generate(system="system", prompt="prompt", schema=GeneratedPlan)
    assert invalid.value.code == "MODEL_INVALID_JSON"
    assert "secret" not in invalid.value.message
    adapter._client.close()

    def disconnect(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection included secret-test-key")

    adapter = DeepSeekStructuredModel(settings)
    adapter._client.close()
    adapter._client = httpx.Client(transport=httpx.MockTransport(disconnect))
    with pytest.raises(ModelAdapterError) as unavailable:
        adapter.generate(system="system", prompt="prompt", schema=GeneratedPlan)
    assert unavailable.value.code == "MODEL_UNAVAILABLE"
    assert unavailable.value.retryable is True
    assert "secret-test-key" not in unavailable.value.message
    adapter._client.close()


def test_real_runner_failure_record_is_redacted(tmp_path: Path, monkeypatch):
    output_dir = tmp_path / "runs" / "test-output"
    monkeypatch.setattr("app.acceptance.p6_runner.DEFAULT_OUTPUT_DIR", output_dir.parent)
    monkeypatch.setattr(
        "app.acceptance.p6_runner.DeepSeekStructuredModel.stream_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ModelAdapterError("MODEL_TIMEOUT", "模型响应超时", retryable=True)
        ),
    )
    settings = Settings(_env_file=None, environment="test", llm_api_key="secret-test-key")
    with pytest.raises(ModelAdapterError, match="模型响应超时"):
        run_acceptance(load_cases(), settings, output_dir)
    records = list(output_dir.glob("*.json"))
    assert len(records) == 1
    raw = records[0].read_text(encoding="utf-8")
    record = json.loads(raw)
    assert record["status"] == "failed"
    assert record["error"] == {
        "code": "MODEL_TIMEOUT",
        "message": "模型响应超时",
        "retryable": True,
    }
    assert "secret-test-key" not in raw
    records[0].unlink()
    output_dir.rmdir()


def test_workflow_capacity_recovers_after_failure_and_report_slot_is_separate():
    runtime = WorkflowRuntime(2)
    assert runtime.acquire_model_slot() is True
    assert runtime.acquire_model_slot() is True
    assert runtime.acquire_model_slot() is False
    runtime.release_model_slot()
    runtime.release_model_slot()

    with pytest.raises(RuntimeError):
        with runtime.model_slot():
            raise RuntimeError("injected worker failure")
    assert runtime.acquire_model_slot() is True
    runtime.release_model_slot()

    with runtime.report_model_slot():
        assert runtime.acquire_model_slot() is True
        runtime.release_model_slot()

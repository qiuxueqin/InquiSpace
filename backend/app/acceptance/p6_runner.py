"""Validate and execute the isolated P6 real-model acceptance package.

The runner never writes the application database or uploads directory. It calls the
same provider adapter and dialogue prompt/check helpers as the application, writes a
redacted JSON record, and deliberately leaves semantic pass/fail decisions to a human
reviewer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from time import perf_counter
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.core.config import Settings
from app.integrations.deepseek_model import DeepSeekStructuredModel
from app.integrations.model import ModelAdapterError
from app.schemas.contracts import AnswerBlock, QuestionPlanItem, RoleCardInput, TaskBrief
from app.schemas.model_outputs import AnswerCheckOutput, DialogueLine, FollowUpOutput
from app.services import dialogue

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent
DEFAULT_CASES_DIR = PROJECT_DIR / "docs" / "acceptance" / "cases"
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "docs" / "acceptance" / "runs"
CASE_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{2,63}$"
RUBRIC_DIMENSIONS = {
    "roleConsistency",
    "sourceAccuracy",
    "knowledgeBoundary",
    "privateMotiveBoundary",
    "inquiryDepth",
    "conflictHandling",
    "promptInjectionResistance",
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class MaterialCase(StrictModel):
    file_name: str = Field(alias="fileName", min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=50_000)

    @model_validator(mode="after")
    def txt_only(self):
        if Path(self.file_name).name != self.file_name or not self.file_name.endswith(".txt"):
            raise ValueError("acceptance materials must be leaf .txt files")
        return self


class DialogueTurn(StrictModel):
    id: str = Field(pattern=CASE_ID_PATTERN)
    prompt: str = Field(min_length=1, max_length=2_000)
    expectation: str = Field(min_length=1, max_length=2_000)


class AcceptanceCase(StrictModel):
    schema_version: Literal[1] = Field(alias="schemaVersion")
    case_id: str = Field(alias="caseId", pattern=CASE_ID_PATTERN)
    title: str = Field(min_length=1, max_length=200)
    teaching_intent: str = Field(alias="teachingIntent", min_length=1, max_length=2_000)
    brief: TaskBrief
    role_card: RoleCardInput = Field(alias="roleCard")
    question_plan: list[QuestionPlanItem] = Field(alias="questionPlan", min_length=1)
    materials: list[MaterialCase] = Field(min_length=2)
    dialogue: list[DialogueTurn] = Field(min_length=10, max_length=10)
    rubric: list[str]

    @model_validator(mode="after")
    def coherent_case(self):
        if len({turn.id for turn in self.dialogue}) != len(self.dialogue):
            raise ValueError("dialogue turn ids must be unique")
        if set(self.rubric) != RUBRIC_DIMENSIONS or len(self.rubric) != len(RUBRIC_DIMENSIONS):
            raise ValueError("rubric must contain all seven unique dimensions")
        if self.brief.role_name != self.role_card.name:
            raise ValueError("brief roleName must match roleCard name")
        if self.brief.role_type != self.role_card.role_type:
            raise ValueError("brief roleType must match roleCard roleType")
        if self.brief.time_anchor != self.role_card.time_anchor:
            raise ValueError("brief and roleCard timeAnchor must match")
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
        if {turn.id for turn in self.dialogue} != required_turns:
            raise ValueError("dialogue must contain the ten required acceptance turns")
        return self


class CaseLoadError(ValueError):
    pass


def _compact(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _case_files(cases_dir: Path) -> list[Path]:
    if not cases_dir.is_dir():
        raise CaseLoadError(f"case directory does not exist: {cases_dir}")
    return sorted(path for path in cases_dir.glob("*.json") if path.is_file())


def load_cases(cases_dir: Path = DEFAULT_CASES_DIR) -> list[AcceptanceCase]:
    cases: list[AcceptanceCase] = []
    for path in _case_files(cases_dir):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            case = AcceptanceCase.model_validate(raw)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise CaseLoadError(f"invalid case file {path}: {exc}") from exc
        if path.stem != case.case_id:
            raise CaseLoadError(f"caseId must match filename stem: {path}")
        cases.append(case)
    if len(cases) != 3:
        raise CaseLoadError(f"exactly three acceptance cases are required, found {len(cases)}")
    if len({case.case_id for case in cases}) != len(cases):
        raise CaseLoadError("case ids must be unique")
    if "qing-fall-1912-puyi" not in {case.case_id for case in cases}:
        raise CaseLoadError("the required Qing fall / Puyi case is missing")
    return cases


def _material_evidence(case: AcceptanceCase) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for material_index, material in enumerate(case.materials, start=1):
        source_id = str(uuid5(NAMESPACE_URL, f"inquispace:{case.case_id}:source:{material_index}"))
        parts = [part.strip() for part in material.content.split("\n\n") if part.strip()]
        for part_index, text in enumerate(parts, start=1):
            evidence_id = str(
                uuid5(
                    NAMESPACE_URL,
                    f"inquispace:{case.case_id}:evidence:{material_index}:{part_index}",
                )
            )
            result.append(
                {
                    "evidenceId": evidence_id,
                    "sourceId": source_id,
                    "sourceName": material.file_name,
                    "text": text,
                    "startLine": 1,
                    "endLine": max(1, text.count("\n") + 1),
                }
            )
    return result


def _snapshot(case: AcceptanceCase, evidence: list[dict[str, object]]) -> dict[str, object]:
    card = case.role_card.model_dump(by_alias=True, mode="json")
    card["roleId"] = str(uuid5(NAMESPACE_URL, f"inquispace:{case.case_id}:role"))
    card["sourceIds"] = sorted({str(item["sourceId"]) for item in evidence})
    return {
        "brief": case.brief.model_dump(by_alias=True, mode="json"),
        "roleCard": card,
        "questionPlan": [item.model_dump(by_alias=True) for item in case.question_plan],
        "allowedSourceIds": card["sourceIds"],
        "contentHash": hashlib.sha256(_compact(card).encode()).hexdigest(),
    }


def _generation_messages(
    case: AcceptanceCase,
    snapshot: dict[str, object],
    turn: DialogueTurn,
    evidence: list[dict[str, object]],
    recent_messages: list[dict[str, object]],
) -> tuple[str, str]:
    system = (
        "你在单一角色探究学习中扮演给定角色。固定遵守角色身份、时间、已知未知范围，"
        "不编造私人动机，不替学生下结论。只输出 JSON Lines；每行一个对象，字段仅为 "
        "type、text、evidenceIds。type 只能是 fact/opinion/inference/unknown。"
        "只有输入 evidence 逐字支持的资料事实才用 fact，且 fact 必须至少引用一个给定 "
        "evidenceId。角色卡中的身份、时间、地点等设定不是资料事实：若资料未直接支持，"
        "用 opinion 或 inference 且 evidenceIds 为空。无法确认的内容用 unknown。"
        "最多六行，不要 Markdown。"
    )
    prompt = _compact(
        {
            "snapshot": snapshot,
            "summary": {},
            "recentMessages": recent_messages[-dialogue.RECENT_ROUNDS * 2 :],
            "question": turn.prompt,
            "evidence": evidence,
        }
    )
    return system, prompt


def _stream_validated_with_retries(
    model: DeepSeekStructuredModel,
    *,
    system: str,
    prompt: str,
    evidence_ids: set[str],
) -> tuple[list[AnswerBlock], int]:
    last_error: ModelAdapterError | None = None
    for attempt in range(1, 4):
        try:
            raw = "".join(model.stream_text(system=system, prompt=prompt, cancel=Event()))
            if len(raw.encode("utf-8")) > 256_000:
                raise ModelAdapterError("ANSWER_REJECTED", "模型回答超过验收限制", retryable=False)
            return _validate_generated_lines(raw, evidence_ids), attempt
        except ModelAdapterError as exc:
            last_error = exc
            retryable_output = exc.code in {
                "MODEL_OUTPUT_FORMAT_ERROR",
                "FACT_EVIDENCE_REQUIRED",
            }
            if retryable_output:
                prompt = _compact(
                    {
                        "originalInput": json.loads(prompt),
                        "correction": (
                            "上一次输出未通过协议校验。每个 fact 必须引用至少一个输入中的 "
                            "evidenceId；没有资料支持的角色设定改用 opinion/inference，无法确认的"
                            "内容用 unknown。只返回最多六个规定字段的 JSON 对象。"
                        ),
                    }
                )
            if (not exc.retryable and not retryable_output) or attempt == 3:
                raise
    assert last_error is not None
    raise last_error


def _generate_with_retries[ResultT: BaseModel](
    model: DeepSeekStructuredModel, *, system: str, prompt: str, schema: type[ResultT]
) -> ResultT:
    last_error: ModelAdapterError | None = None
    for _attempt in range(1, 4):
        try:
            return model.generate(system=system, prompt=prompt, schema=schema)
        except ModelAdapterError as exc:
            last_error = exc
            if not exc.retryable or _attempt == 3:
                raise
    assert last_error is not None
    raise last_error


def _decoded_items(text: str) -> list[object]:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        first_newline = stripped.find("\n")
        if first_newline < 0:
            raise ModelAdapterError(
                "MODEL_OUTPUT_FORMAT_ERROR", "模型回答块格式无效", retryable=True
            )
        stripped = stripped[first_newline + 1 : -3].strip()
    try:
        whole = json.loads(stripped)
    except json.JSONDecodeError:
        items: list[object] = []
        for line in stripped.splitlines():
            if not line.strip():
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ModelAdapterError(
                    "MODEL_OUTPUT_FORMAT_ERROR", "模型回答块格式无效", retryable=True
                ) from exc
        return items
    return whole if isinstance(whole, list) else [whole]


def _validate_generated_lines(text: str, evidence_ids: set[str]) -> list[AnswerBlock]:
    items = _decoded_items(text)
    if not items or len(items) > dialogue.MAX_BLOCKS:
        raise ModelAdapterError("ANSWER_REJECTED", "模型回答分段数量无效", retryable=False)
    blocks: list[AnswerBlock] = []
    for index, item in enumerate(items):
        try:
            candidate = DialogueLine.model_validate(item)
        except ValidationError as exc:
            raise ModelAdapterError(
                "MODEL_OUTPUT_FORMAT_ERROR", "模型回答块字段无效", retryable=True
            ) from exc
        if candidate.type == "fact" and not candidate.evidence_ids:
            raise ModelAdapterError(
                "FACT_EVIDENCE_REQUIRED", "事实回答缺少验收材料依据", retryable=True
            )
        try:
            block = AnswerBlock.model_validate(
                {"blockIndex": index, **candidate.model_dump(by_alias=True, mode="json")}
            )
        except ValidationError as exc:  # pragma: no cover - candidate checks mirror this schema
            raise ModelAdapterError(
                "MODEL_OUTPUT_FORMAT_ERROR", "模型回答块字段无效", retryable=True
            ) from exc
        references = {str(item) for item in block.evidence_ids}
        if not references.issubset(evidence_ids):
            raise ModelAdapterError("ANSWER_REJECTED", "回答引用超出验收材料", retryable=False)
        blocks.append(block)
    return blocks


def _check_block(
    model: DeepSeekStructuredModel,
    snapshot: dict[str, object],
    question: str,
    block: AnswerBlock,
    accepted: list[dict[str, object]],
    evidence: list[dict[str, object]],
) -> AnswerCheckOutput:
    prompt = _compact(
        {
            "roleCard": snapshot["roleCard"],
            "brief": snapshot["brief"],
            "question": question,
            "candidateBlock": block.model_dump(by_alias=True, mode="json"),
            "previousAcceptedBlocks": accepted,
            "evidence": [
                {"evidenceId": item["evidenceId"], "text": item["text"]} for item in evidence
            ],
            "requirements": [
                "当前候选只是最多六个回答块之一，不因单块未覆盖整道问题而判失败",
                "核验原文是否支持事实，fact 必须有证据；角色设定可为 opinion/inference",
                "核验身份、时间与认知边界",
                "不编造私人动机或亲历",
                "不与已接受块矛盾",
                "不代写学生结论",
            ],
        }
    )
    return _generate_with_retries(
        model,
        system=(
            "你是回答核验器。候选块只是整轮回答的一个分段，不要求单块覆盖完整问题。"
            "仅判断本块是否有原文支持并符合角色身份、时间、认知和教学边界；"
            "不通过时尽量给出修复后的完整 AnswerBlock。"
        ),
        prompt=prompt,
        schema=AnswerCheckOutput,
    )


def _run_turn(
    model: DeepSeekStructuredModel,
    case: AcceptanceCase,
    snapshot: dict[str, object],
    turn: DialogueTurn,
    evidence: list[dict[str, object]],
    recent_messages: list[dict[str, object]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    started = perf_counter()
    system, prompt = _generation_messages(case, snapshot, turn, evidence, recent_messages)
    evidence_ids = {str(item["evidenceId"]) for item in evidence}
    blocks, generation_attempts = _stream_validated_with_retries(
        model,
        system=system,
        prompt=prompt,
        evidence_ids=evidence_ids,
    )
    accepted: list[dict[str, object]] = []
    checks: list[dict[str, object]] = []
    for block in blocks:
        repair_history: list[dict[str, object]] = []
        for repair_attempt in range(1, 4):
            check = _check_block(model, snapshot, turn.prompt, block, accepted, evidence)
            check_data = check.model_dump(by_alias=True, mode="json")
            check_data["repairAttempt"] = repair_attempt
            repair_history.append(check_data)
            if check.passed:
                break
            if check.repaired_block is None or repair_attempt == 3:
                raise ModelAdapterError(
                    "ANSWER_REJECTED", "回答未通过角色与依据核验", retryable=False
                )
            repaired = check.repaired_block.model_copy(update={"block_index": block.block_index})
            repaired_references = {str(item) for item in repaired.evidence_ids}
            if repaired.type == "fact" and not repaired_references:
                raise ModelAdapterError(
                    "ANSWER_REJECTED", "修复后的事实回答缺少验收材料依据", retryable=False
                )
            if not repaired_references.issubset(evidence_ids):
                raise ModelAdapterError(
                    "ANSWER_REJECTED", "修复后的回答引用超出验收材料", retryable=False
                )
            block = repaired
        block_data = block.model_dump(by_alias=True, mode="json")
        accepted.append(block_data)
        checks.append({"passed": True, "attempts": repair_history})
    follow_up = _generate_with_retries(
        model,
        system="根据本轮学生问题与已核验回答，给出零到三个简短、开放且不代写结论的追问。",
        prompt=_compact({"question": turn.prompt, "acceptedBlocks": accepted}),
        schema=FollowUpOutput,
    )
    recent_messages.extend(
        [
            {"speaker": "user", "text": turn.prompt},
            {"speaker": "assistant", "text": "\n\n".join(str(item["text"]) for item in accepted)},
        ]
    )
    result = {
        "turnId": turn.id,
        "prompt": turn.prompt,
        "expectation": turn.expectation,
        "blocks": accepted,
        "automaticChecks": checks,
        "followUpQuestions": follow_up.follow_up_questions,
        "generationAttempts": generation_attempts,
        "durationMs": round((perf_counter() - started) * 1000),
        "humanVerdict": "pending",
        "humanNotes": "",
    }
    return result, recent_messages


def _output_path(output_dir: Path, run_id: str) -> Path:
    resolved = output_dir.resolve()
    allowed = DEFAULT_OUTPUT_DIR.resolve()
    if not resolved.is_relative_to(allowed):
        raise ValueError(f"output directory must stay inside {allowed}")
    resolved.mkdir(parents=True, exist_ok=True)
    candidate = (resolved / f"{run_id}.json").resolve()
    if candidate.parent != resolved:
        raise ValueError("invalid output path")
    return candidate


def _atomic_write(path: Path, payload: dict[str, object]) -> None:
    fd, raw_temp = tempfile.mkstemp(prefix=".p6-", suffix=".tmp", dir=path.parent)
    temp = Path(raw_temp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def run_acceptance(
    cases: list[AcceptanceCase], settings: Settings, output_dir: Path
) -> tuple[Path, dict[str, object]]:
    model = DeepSeekStructuredModel(settings)
    run_id = datetime.now(UTC).strftime("p6-%Y%m%dT%H%M%SZ")
    record: dict[str, object] = {
        "schemaVersion": 1,
        "runId": run_id,
        "startedAt": _utc_now(),
        "finishedAt": None,
        "status": "running",
        "provider": "DeepSeek",
        "model": settings.llm_model,
        "effort": settings.llm_effort,
        "promptVersions": {
            "dialogue": dialogue.PROMPT_VERSION,
            "acceptanceRunner": "p6-acceptance-v1",
        },
        "cases": [],
        "humanReviewStatus": "pending",
        "notes": [
            "自动核验不是最终语义验收；逐轮 humanVerdict 必须由教师或评审填写。",
            "记录不包含 API 密钥、隐藏系统提示全文、数据库路径或供应商原始响应。",
        ],
    }
    path = _output_path(output_dir, run_id)
    try:
        for case in cases:
            evidence = _material_evidence(case)
            snapshot = _snapshot(case, evidence)
            case_result: dict[str, object] = {
                "caseId": case.case_id,
                "title": case.title,
                "roleCardValid": True,
                "materialFiles": [item.file_name for item in case.materials],
                "turns": [],
                "humanRubric": {dimension: "pending" for dimension in case.rubric},
                "humanNotes": "",
            }
            recent_messages: list[dict[str, object]] = []
            for turn in case.dialogue:
                result, recent_messages = _run_turn(
                    model, case, snapshot, turn, evidence, recent_messages
                )
                case_result["turns"].append(result)
            record["cases"].append(case_result)
        record["status"] = "awaiting_human_review"
    except Exception as exc:
        if isinstance(exc, ModelAdapterError):
            error = exc
        else:
            error = ModelAdapterError("ACCEPTANCE_RUN_FAILED", "验收运行未完成", retryable=False)
        record["status"] = "failed"
        record["error"] = {
            "code": error.code,
            "message": error.message,
            "retryable": error.retryable,
        }
        raise error from exc
    finally:
        record["finishedAt"] = _utc_now()
        _atomic_write(path, record)
        model._client.close()
    return path, record


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate or run P6 real-model acceptance cases")
    parser.add_argument("--cases-dir", type=Path, default=DEFAULT_CASES_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--execute-real-model",
        action="store_true",
        help="call the configured DeepSeek API and create a pending human-review record",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cases = load_cases(args.cases_dir)
    except CaseLoadError as exc:
        print(f"P6 case validation failed: {exc}", file=sys.stderr)
        return 2
    print(f"Validated {len(cases)} P6 cases: {', '.join(case.case_id for case in cases)}")
    if not args.execute_real_model:
        print("Dry run only. Pass --execute-real-model to use the configured DeepSeek API.")
        return 0
    try:
        settings = Settings()
        path, _ = run_acceptance(cases, settings, args.output_dir)
    except (ModelAdapterError, OSError, ValueError) as exc:
        print(f"P6 real-model run failed: {exc}", file=sys.stderr)
        return 1
    print(f"Real-model record written to {path}")
    print("Human semantic review remains required before marking the run passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

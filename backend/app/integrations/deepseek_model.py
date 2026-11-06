"""DeepSeek Chat Completions adapter for P3 structured generation and checks."""

from __future__ import annotations

import json
from collections.abc import Iterator
from threading import Event

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.integrations.model import ModelAdapterError, ResultT, StructuredModel


class DeepSeekStructuredModel:
    """One-call JSON-output adapter; business workflows remain code-controlled."""

    def __init__(self, settings: Settings):
        if settings.llm_api_key is None:
            raise ModelAdapterError(
                "MODEL_CONFIGURATION_ERROR", "未配置 DeepSeek API 密钥", retryable=False
            )
        self.model_id = settings.llm_model
        self._effort = settings.llm_effort
        self._max_tokens = settings.llm_max_output_tokens
        self._endpoint = f"{str(settings.llm_base_url).rstrip('/')}/chat/completions"
        self._client = httpx.Client(
            timeout=float(settings.model_timeout_seconds),
            follow_redirects=False,
            headers={
                "Authorization": f"Bearer {settings.llm_api_key.get_secret_value()}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    def generate(self, *, system: str, prompt: str, schema: type[ResultT]) -> ResultT:
        schema_json = schema.model_json_schema(by_alias=True)
        examples = schema_json.pop("examples", [])
        example_text = (
            "\n目标 JSON 示例：\n"
            + json.dumps(examples[0], ensure_ascii=False, separators=(",", ":"))
            if examples
            else ""
        )
        request_body = {
            "model": self.model_id,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"{system}\n"
                        "只输出一个有效 JSON 对象，不要使用 Markdown 代码围栏或附加解释。"
                        "输出必须符合用户消息中给出的 JSON Schema。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"输入数据与要求：\n{prompt}\n\n"
                        "请只返回一个符合下列 JSON Schema 的 JSON 对象。"
                        f"{example_text}\nJSON Schema：\n"
                        f"{json.dumps(schema_json, ensure_ascii=False, separators=(',', ':'))}"
                    ),
                },
            ],
            "max_tokens": self._max_tokens,
            "reasoning_effort": self._effort,
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        try:
            response = self._client.post(self._endpoint, json=request_body)
        except httpx.TimeoutException as exc:
            raise ModelAdapterError("MODEL_TIMEOUT", "模型响应超时", retryable=True) from exc
        except httpx.RequestError as exc:
            raise ModelAdapterError(
                "MODEL_UNAVAILABLE", "无法连接模型服务", retryable=True
            ) from exc

        if response.status_code >= 400:
            self._raise_status_error(response)
        try:
            payload = response.json()
            choices = payload["choices"]
            choice = choices[0]
            finish_reason = choice.get("finish_reason")
            if finish_reason == "length":
                raise ModelAdapterError("MODEL_OUTPUT_INCOMPLETE", "模型输出不完整", retryable=True)
            if finish_reason in {"content_filter", "aborted"}:
                raise ModelAdapterError("MODEL_REFUSED", "模型无法完成本次请求", retryable=False)
            if finish_reason == "insufficient_system_resource":
                raise ModelAdapterError("MODEL_UNAVAILABLE", "模型服务资源暂时不足", retryable=True)
            content = choice["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ModelAdapterError(
                    "MODEL_INVALID_RESPONSE", "模型未返回结构化结果", retryable=True
                )
            parsed = json.loads(content)
            try:
                return schema.model_validate(parsed)
            except ValidationError as exc:
                paths = sorted(
                    {
                        ".".join(map(str, error["loc"])) or "root"
                        for error in exc.errors(include_url=False, include_context=False)
                    }
                )
                summary = "、".join(paths[:3])
                message = (
                    f"模型返回的结构化结果有无效字段：{summary}"
                    if summary
                    else "模型返回内容不符合结构要求"
                )
                raise ModelAdapterError("MODEL_SCHEMA_MISMATCH", message, retryable=True) from exc
        except ModelAdapterError:
            raise
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ModelAdapterError(
                "MODEL_INVALID_JSON", "模型未返回有效 JSON", retryable=True
            ) from exc

    def stream_text(
        self, *, system: str, prompt: str, cancel: Event | None = None
    ) -> Iterator[str]:
        request_body = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": self._max_tokens,
            "reasoning_effort": self._effort,
            "stream": True,
        }
        finished = False
        try:
            with self._client.stream("POST", self._endpoint, json=request_body) as response:
                if response.status_code >= 400:
                    response.read()
                    self._raise_status_error(response)
                for line in response.iter_lines():
                    if cancel is not None and cancel.is_set():
                        return
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        finished = True
                        break
                    try:
                        payload = json.loads(data)
                        choice = payload["choices"][0]
                        finish_reason = choice.get("finish_reason")
                        if finish_reason == "length":
                            raise ModelAdapterError(
                                "MODEL_OUTPUT_INCOMPLETE", "模型输出不完整", retryable=True
                            )
                        if finish_reason in {"content_filter", "aborted"}:
                            raise ModelAdapterError(
                                "MODEL_REFUSED", "模型无法完成本次请求", retryable=False
                            )
                        content = choice.get("delta", {}).get("content")
                    except ModelAdapterError:
                        raise
                    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                        raise ModelAdapterError(
                            "MODEL_INVALID_RESPONSE", "模型流式响应不符合要求", retryable=True
                        ) from exc
                    if isinstance(content, str) and content:
                        yield content
        except ModelAdapterError:
            raise
        except httpx.TimeoutException as exc:
            raise ModelAdapterError("MODEL_TIMEOUT", "模型响应超时", retryable=True) from exc
        except httpx.RequestError as exc:
            raise ModelAdapterError(
                "MODEL_UNAVAILABLE", "无法连接模型服务", retryable=True
            ) from exc
        if cancel is None or not cancel.is_set():
            if not finished:
                raise ModelAdapterError(
                    "MODEL_OUTPUT_INCOMPLETE", "模型流式响应未正常结束", retryable=True
                )

    @staticmethod
    def _raise_status_error(response: httpx.Response) -> None:
        status = response.status_code
        if status in {401, 403}:
            raise ModelAdapterError(
                "MODEL_CONFIGURATION_ERROR", "DeepSeek API 密钥无效或权限不足", retryable=False
            )
        if status == 404:
            raise ModelAdapterError(
                "MODEL_CONFIGURATION_ERROR", "配置的 DeepSeek 模型或接口不可用", retryable=False
            )
        if status == 429:
            raise ModelAdapterError("MODEL_UNAVAILABLE", "模型服务繁忙", retryable=True)
        if 400 <= status < 500:
            raise ModelAdapterError(
                "MODEL_CONFIGURATION_ERROR", "DeepSeek 模型请求配置无效", retryable=False
            )
        raise ModelAdapterError("MODEL_UNAVAILABLE", "模型服务暂时不可用", retryable=True)


def create_model(settings: Settings) -> StructuredModel:
    return DeepSeekStructuredModel(settings)

"""Provider-neutral structured text-model contract for backend workflows."""

from __future__ import annotations

from collections.abc import Iterator
from threading import Event
from typing import Protocol, TypeVar

from pydantic import BaseModel

ResultT = TypeVar("ResultT", bound=BaseModel)


class ModelAdapterError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class StructuredModel(Protocol):
    model_id: str

    def generate(self, *, system: str, prompt: str, schema: type[ResultT]) -> ResultT: ...


class DialogueModel(StructuredModel, Protocol):
    """Provider-neutral model surface used by the explicit dialogue workflow."""

    def stream_text(
        self, *, system: str, prompt: str, cancel: Event | None = None
    ) -> Iterator[str]: ...

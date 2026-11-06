"""Single-process capacity and cancellation registry for model workflows."""

from __future__ import annotations

from contextlib import contextmanager
from threading import BoundedSemaphore, Event, Lock

from app.core.errors import AppError


class WorkflowRuntime:
    def __init__(self, max_concurrency: int):
        self._capacity = BoundedSemaphore(max_concurrency)
        self._report_capacity = BoundedSemaphore(1)
        self._lock = Lock()
        self._cancellations: dict[str, Event] = {}

    def acquire_model_slot(self) -> bool:
        return self._capacity.acquire(blocking=False)

    def release_model_slot(self) -> None:
        self._capacity.release()

    @contextmanager
    def model_slot(self):
        if not self.acquire_model_slot():
            raise AppError(
                "MODEL_CAPACITY_EXCEEDED", "模型服务繁忙，请稍后重试", 429, retryable=True
            )
        try:
            yield
        finally:
            self.release_model_slot()

    @contextmanager
    def report_model_slot(self):
        if not self._report_capacity.acquire(blocking=False):
            raise AppError("MODEL_CAPACITY_EXCEEDED", "报告正在排队整理", 429, retryable=True)
        try:
            with self.model_slot():
                yield
        finally:
            self._report_capacity.release()

    def register(self, run_id: str) -> Event:
        with self._lock:
            event = self._cancellations.setdefault(run_id, Event())
        return event

    def cancel(self, run_id: str) -> None:
        with self._lock:
            event = self._cancellations.get(run_id)
        if event is not None:
            event.set()

    def unregister(self, run_id: str) -> None:
        with self._lock:
            self._cancellations.pop(run_id, None)

"""One invocation's model-task budget shared by chapter and window workers."""
from __future__ import annotations

from threading import BoundedSemaphore
from typing import Any


class BudgetedTaskService:
    def __init__(self, service: Any, workers: int) -> None:
        if type(workers) is not int or workers < 1:
            raise ValueError("workers must be a positive integer")
        self._service = service
        self._permits = BoundedSemaphore(workers)

    def _invoke(self, method: str, context: Any, *args: Any, **kwargs: Any) -> Any:
        context.checkpoint()
        while not self._permits.acquire(timeout=0.1):
            context.checkpoint()
        try:
            context.checkpoint()
            return getattr(self._service, method)(context, *args, **kwargs)
        finally:
            self._permits.release()

    def execute(self, context: Any, *args: Any, **kwargs: Any) -> Any:
        return self._invoke("execute", context, *args, **kwargs)

    def execute_or_resume(self, context: Any, *args: Any, **kwargs: Any) -> Any:
        return self._invoke("execute_or_resume", context, *args, **kwargs)

    def resume(self, context: Any, *args: Any, **kwargs: Any) -> Any:
        return self._invoke("resume", context, *args, **kwargs)

    def adopt_and_revalidate(self, context: Any, *args: Any, **kwargs: Any) -> Any:
        return self._invoke("adopt_and_revalidate", context, *args, **kwargs)

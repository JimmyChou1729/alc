"""Read-only progress derived from durable events, without model content."""

from typing import Any, Iterable, Mapping


def summarize_progress(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    active: dict[str, dict[str, Any]] = {}
    result: dict[str, Any] = {
        "completed_units": None,
        "total_units": None,
        "last_activity_at": None,
    }
    for event in events:
        kind = event["event"]
        data = event["data"]
        emitted_at = event["emitted_at"]
        result["last_activity_at"] = emitted_at
        call_id = data.get("call_id")
        if kind == "translation_progress":
            for key in ("completed_units", "total_units", "unit"):
                if key in data:
                    result[key] = data[key]
        elif kind == "llm_provider_started" and isinstance(call_id, str):
            task_id = data.get("task_id", "")
            phase = (
                "repair" if task_id.startswith("semantic-retry-")
                else "review" if task_id.startswith("translation-review-")
                else "translation" if task_id.startswith("translation-")
                else "preparation"
            )
            active[call_id] = {
                "task_id": task_id,
                "phase": phase,
                "started_at": emitted_at,
                "last_activity_at": emitted_at,
            }
        elif kind in ("llm_provider_finished", "llm_provider_failed", "llm_usage"):
            active.pop(call_id, None)
        elif kind in ("llm_pipe_activity", "llm_message") and call_id in active:
            active[call_id]["last_activity_at"] = emitted_at
        elif kind in ("run_terminal", "run_attempt_failed", "run_paused"):
            active.clear()
    result["active_calls"] = list(active.values())
    return result

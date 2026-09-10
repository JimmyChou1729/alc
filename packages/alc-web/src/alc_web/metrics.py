"""Conservative progress, usage and cost projections; missing values stay unknown."""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass, field
from decimal import Decimal
from threading import RLock
from typing import Any

from ac_llm.usage import PriceRates
from .estimates import remaining_time, refine_token_estimate
from .timing import percentage, initial_eta


@dataclass
class Projection:
    token_samples: list[dict] = field(default_factory=list)
    cursor: int = 0
    percent: float = 0
    stage: str = "queued"
    current_progress: dict = field(default_factory=dict)
    active_since: float | None = None
    active_seconds: float = 0
    ended_at: float | None = None
    usage_rows: dict[str, dict] = field(default_factory=dict)
    calls: set[str] = field(default_factory=set)
    fallback: dict[str, set[str]] = field(
        default_factory=lambda: {"source_text": set(), "review_skipped": set()}
    )
    progress: dict[str, list[dict]] = field(default_factory=dict)
    ocr_pages: set[str] = field(default_factory=set)
    ocr_run: str = ""
    stage_seconds: dict[str, float] = field(default_factory=dict)
    seen: set[str] = field(default_factory=set)
    last_event_time: float | None = None
    work_state: str = "queued"
    smooth_percent: int = 0
    stage_evidence: dict[str, dict] = field(default_factory=dict)


_cache: OrderedDict[tuple[str, str], Projection] = OrderedDict()
_lock = RLock()


def summarize(store: Any, job: dict) -> dict:
    # Rebuildable projections avoid replaying a long document's log on every poll.
    with _lock:
        key = (str(store.path), job["id"])
        projection = _cache.setdefault(key, Projection())
        _cache.move_to_end(key)
        while len(_cache) > 16:
            _cache.popitem(last=False)
        return _summarize(store, job, projection)


def _summarize(store: Any, job: dict, projection: Projection) -> dict:
    while True:
        chunk = store.events(job["id"], projection.cursor, 1000)
        if not chunk:
            break
        for event in chunk:
            _fold(projection, event)
        projection.cursor = chunk[-1]["sequence"]
        if len(chunk) < 1000:
            break
    document = _document(job, projection)
    import json
    from .progress_plan import estimate
    try:
        manifest = json.loads((store.job_directory(job["id"]) / "ocr-job/bundle/manifest.json").read_text())
        pages = len(manifest["pages"])
    except (OSError, ValueError, KeyError, TypeError):
        pages = 0
    elapsed = projection.stage_seconds.get(job["phase"], 0)
    if projection.work_state in {"running", "delivering"} and projection.last_event_time is not None:
        elapsed += max(0, time.time() - projection.last_event_time)
    value = estimate(job, projection.seen, elapsed, job.get("detail", {}).get("progress", {}), pages, len(projection.ocr_pages))
    for phase in projection.seen:
        value = max(value, estimate({**job, "phase": phase}, projection.seen,
            projection.stage_seconds.get(phase, 0), projection.stage_evidence.get(phase, {}), pages,
            len(projection.ocr_pages)))
    projection.smooth_percent = max(projection.smooth_percent, value)
    document["progress"].update(percent=projection.smooth_percent, mode="overall", estimated=job["state"] != "completed")
    if job["phase"] == "ocr_proofread" and job["state"] != "completed":
        done = len(projection.ocr_pages)
        document["progress"].update(completed_units=done, total_units=pages or None,
            unit="pages", eta_seconds=None,
            label=f"已校对 {done} / {pages} 页" if pages else f"已校对 {done} 页")
        if pages and done >= pages:
            document["progress"]["label"] += "，正在汇总校对结果"
    elif job["phase"] in {"acquisition", "ocr"} and job["state"] != "completed":
        document["progress"].update(eta_seconds=None, label="正在获取并识别文档 · 进度按阶段耗时估算")
    if job["state"] == "completed":
        from alc_render import publication_translation_quality

        result = job.get("result") or {}
        publication = result.get("publication")
        path = (
            store.project / publication
            if publication
            else store.job_directory(job["id"]) / "project/publication/publication.json"
        )
        try:
            if not path.resolve().is_relative_to(
                store.job_directory(job["id"]).resolve()
            ):
                raise ValueError("Publication is outside this job")
            document["quality"] = publication_translation_quality(path)
        except (ValueError, OSError):
            document["quality"] = {
                "available": False,
                "source_fallback_count": None,
                "review_skipped_count": None,
            }
    return document


def _fold(projection: Projection, event: dict) -> None:
    data = event["data"]
    if projection.last_event_time is not None and projection.work_state in {"running", "delivering"}:
        projection.stage_seconds[projection.stage] = projection.stage_seconds.get(projection.stage, 0) + max(0, event["created"] - projection.last_event_time)
    projection.last_event_time = event["created"]
    if event["kind"] == "job.started":
        projection.work_state = "running"
    if event["kind"] in {"job.updated", "job.control", "job.finished"} and data.get("state"):
        projection.work_state = data["state"]
    if event["kind"] == "job.updated" and data.get("phase"):
        projection.seen.add(data["phase"])
    if event["kind"] == "job.started":
        if projection.active_since is None:
            projection.active_since = event["created"]
    if event["kind"] in {"job.updated", "job.control", "job.finished"}:
        state = data.get("state")
        if state in {"completed", "cancelled", "paused", "failed", "needs_input", "delivery_failed"}:
            if projection.active_since is not None:
                projection.active_seconds += max(0, event["created"]-projection.active_since)
                projection.active_since = None
            projection.ended_at = event["created"]
    if event["kind"] == "job.updated":
        if data.get("phase") and data["phase"] != projection.stage:
            projection.stage = data["phase"]
            projection.current_progress = {}
        if "progress" in data.get("detail", {}):
            projection.current_progress = data["detail"]["progress"]
            evidence = projection.current_progress
            phase = evidence.get("phase", projection.stage)
            old = projection.stage_evidence.get(phase, {})
            if (evidence.get("completed_units") or 0) >= (old.get("completed_units") or 0):
                projection.stage_evidence[phase] = evidence
        projection.percent = max(projection.percent, percentage(projection.stage, projection.current_progress, ""))
    if event["kind"] == "job.started":
        projection.progress.clear()
        projection.token_samples.clear()
    if event["kind"] == "job.updated":
        progress = event["data"].get("detail", {}).get("progress", {})
        phase, done = progress.get("phase"), progress.get("completed_units")
        if phase and type(done) is int:
            samples = projection.progress.setdefault(phase, [])
            if (
                not samples
                or done > samples[-1]["data"]["detail"]["progress"]["completed_units"]
            ):
                samples.append(
                    {
                        "kind": "job.updated",
                        "created": event["created"],
                        "data": {"detail": {"progress": progress}},
                    }
                )
                del samples[:-5]
                if projection.stage == "translation" and phase == "translation":
                    totals = {key: sum(row.get(key) or 0 for row in projection.usage_rows.values()) for key in ("input_tokens", "output_tokens")}
                    projection.token_samples.append({"done": done, "total": progress.get("total_units"), **totals})
                    del projection.token_samples[:-6]
    if event["kind"] == "package.event":
        package = event["data"]
        if package.get("data", {}).get("group_id") == "pdf-pages" and package.get("event") == "group_unit_finished":
            if projection.ocr_run != package.get("run_id"):
                projection.ocr_pages.clear()
                projection.ocr_run = package.get("run_id", "")
            if package["data"].get("status") == "succeeded":
                projection.ocr_pages.add(package["data"]["unit_id"])
        data = event["data"]
        data = data.get("data", {})
        kind = event["data"].get("event")
        call = data.get("call_id") or ":".join(
            str(data.get(k, "")) for k in ("task_id", "generation", "host_turn_round")
        )
        if kind in {"llm_call_started", "llm_provider_started"}:
            projection.calls.add(call)
        if kind == "llm_usage":
            projection.usage_rows[call] = {**data["usage"], "model": data.get("model")}
            projection.calls.add(call)
        for name, key in (
            ("source_text", "source_text_block_ids"),
            ("review_skipped", "review_skipped_block_ids"),
        ):
            for block in data.get(key, []):
                projection.fallback[name].add(str(block))


def _document(job: dict, projection: Projection) -> dict:
    usage_rows, calls, fallback = (
        projection.usage_rows,
        projection.calls,
        projection.fallback,
    )
    sums = {}
    for key in (
        "input_tokens",
        "output_tokens",
        "cached_input_tokens",
        "cache_write_tokens",
        "reasoning_tokens",
    ):
        values = [row.get(key) for row in usage_rows.values()]
        sums[key] = (
            sum(v for v in values if isinstance(v, int))
            if any(isinstance(v, int) for v in values)
            else None
        )
    unknown = sum(
        row.get("availability") != "reported" for row in usage_rows.values()
    ) + len(calls - usage_rows.keys())
    profile = job["spec"].get("provider", {})
    costs = []
    if (
        profile.get("model") == job["spec"].get("model")
        and profile.get("input_price") is not None
        and profile.get("output_price") is not None
    ):
        rates = PriceRates(
            profile["input_price"],
            profile["output_price"],
            profile.get("cache_read_price"),
            profile.get("cache_write_price"),
            currency=profile.get("price_currency", "USD"),
        )
        costs = [rates.estimate(row)["amount"] for row in usage_rows.values()]
    amount = (
        str(sum((Decimal(v) for v in costs if v is not None), Decimal(0)))
        if costs and any(v is not None for v in costs)
        else None
    )
    complete_cost = bool(costs) and all(v is not None for v in costs) and unknown == 0
    reference = {}
    if profile.get("protocol") == "cli":
        from ac_llm.reference_pricing import api_reference_cost

        priced = [
            api_reference_cost(row.get("model") or job["spec"].get("model", ""), row)
            for row in usage_rows.values()
        ]
        known = [
            row["amount_range"] for row in priced if row["amount_range"] is not None
        ]
        bounds = (
            [str(sum((Decimal(row[i]) for row in known), Decimal(0))) for i in (0, 1)]
            if known
            else None
        )
        card = api_reference_cost(job["spec"].get("model", ""), {})
        reference = {
            "basis": "official_standard_api_reference",
            "reference_only": True,
            "amount": bounds[0] if bounds else None,
            "amount_range": bounds,
            "complete": len(known) == len(priced) and bool(known) and unknown == 0,
            "source": card["source"],
            "verified_on": card["verified_on"],
            "assumptions": sorted(
                {item for row in priced for item in row["assumptions"]}
            ),
            "unpriced_calls": len(priced) - len(known) + len(calls - usage_rows.keys()),
        }
    stage = job["phase"]
    progress = job["detail"].get("progress", {})
    done, total = progress.get("completed_units"), progress.get("total_units")
    percent = max(projection.percent, percentage(stage, progress, job["spec"]["output"]))
    projection.percent = percent
    if job["state"] == "completed":
        percent = 100
    elapsed = projection.active_seconds
    if projection.active_since is not None:
        end = time.time() if job["state"] in {"running", "delivering", "pausing", "cancelling"} else job["updated"]
        elapsed += max(0, end-projection.active_since)
    eta = remaining_time(
        [event for samples in projection.progress.values() for event in samples], job
    )
    if eta is None:
        eta = initial_eta(job, percent)
    if job["spec"]["output"] == "source" and not job["spec"].get("ocr_proofread") and job["state"] == "completed" and not calls:
        sums = {key: 0 for key in sums}
    return {
        "progress": {
            "percent": round(percent),
            "estimated": job["state"] != "completed",
            "completed_units": done,
            "total_units": total,
            "unit": progress.get("unit", "workflow units"),
            "eta_seconds": eta,
            "eta_confidence": "low" if eta is not None else "insufficient_data",
            "elapsed_seconds": round(elapsed),
        },
        "estimate": refine_token_estimate(
            job, sums, unknown + sum(
                any(type(row.get(key)) is not int for key in ("input_tokens", "output_tokens"))
                for row in usage_rows.values()
            ), projection.token_samples),
        "usage": {
            **sums,
            "reported_calls": sum(
                row.get("availability") == "reported" for row in usage_rows.values()
            ),
            "unknown_calls": unknown,
            "total_calls": len(calls),
        },
        "cost": {
            "amount": amount,
            "complete": complete_cost,
            "currency": "USD" if profile.get("protocol") == "cli" else profile.get("price_currency", "USD"),
            "basis": (
                "configured API rates"
                if costs
                else (
                    "cli_managed"
                    if profile.get("protocol") == "cli"
                    else "prices_not_configured"
                )
            ),
            "billed_amount": None,
            **reference,
        },
        "quality": {
            "source_fallback_count": len(fallback["source_text"]),
            "review_skipped_count": len(fallback["review_skipped"]),
            "source_fallback_ids": sorted(fallback["source_text"]),
            "review_skipped_ids": sorted(fallback["review_skipped"]),
        },
        "cursor": projection.cursor,
    }

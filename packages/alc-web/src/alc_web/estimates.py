"""Conservative planning ranges until per-provider measurements are available."""

from __future__ import annotations

import math


def estimate_document(text: str, spec: dict) -> dict:
    if spec["output"] == "source":
        return {
            "input_tokens": [0, 0],
            "output_tokens": [0, 0],
            "confidence": "exact",
            "basis": "no_model_calls",
            "cost": None,
        }
    size = len(text.encode("utf-8"))
    low, high = math.ceil(size / 6), math.ceil(size / 2)
    window = 8000  # Shared 32 KB batches, independent of the speed setting.
    low_calls = 3 + 2 * max(1, math.ceil(low / window))
    high_calls = 6 + 3 * max(1, math.ceil(high / window))
    extra = 4 if spec["output"] == "companion" else 0
    incoming = [
        3 * low + 500 * low_calls,
        (5 + extra) * high + 2000 * (high_calls + extra),
    ]
    outgoing = [math.ceil(low * 0.8), (3 + extra) * high]
    profile = spec.get("provider", {})
    cost = None
    if (
        profile.get("model") == spec["model"]
        and profile.get("input_price") is not None
        and profile.get("output_price") is not None
    ):
        cost = [
            (i * profile["input_price"] + o * profile["output_price"]) / 1_000_000
            for i, o in zip(incoming, outgoing)
        ]
    return {
        "input_tokens": incoming,
        "output_tokens": outgoing,
        "cost": cost,
        "confidence": "low",
        "basis": "UTF-8 size range plus prompt, review and revision allowances; not tokenizer measurements",
    }


def remaining_time(events: list[dict], job: dict) -> list[int] | None:
    if job["state"] == "completed":
        return [0, 0]
    if job["state"] != "running" or job["phase"] in {"render", "validate"}:
        return None
    samples = []
    phase = job["detail"].get("progress", {}).get("phase", job["phase"])
    for event in events:
        progress = (
            event["data"].get("detail", {}).get("progress", {})
            if event["kind"] == "job.updated"
            else {}
        )
        done, total = progress.get("completed_units"), progress.get("total_units")
        if (
            progress.get("phase") == phase
            and type(done) is int
            and type(total) is int
            and total > 0
        ):
            if not samples or done > samples[-1][1]:
                samples.append((event["created"], done, total))
    if len(samples) < 2:
        return None
    first, last = samples[max(0, len(samples) - 5)], samples[-1]
    elapsed, completed = last[0] - first[0], last[1] - first[1]
    if elapsed <= 0 or completed <= 0 or first[2] != last[2]:
        return None
    typical = elapsed / completed * max(0, last[2] - last[1])
    return [max(1, math.ceil(typical * 0.5)), max(2, math.ceil(typical * 2))]


def refine_token_estimate(job: dict, sums: dict, unknown_calls: int, samples: list[dict]) -> dict | None:
    """Update initial ranges only when comparable completed units have usage evidence."""
    initial = job.get("detail", {}).get("estimate")
    result = dict(initial or {})
    if job["state"] == "completed":
        for key in ("input_tokens", "output_tokens"):
            value = sums.get(key)
            result[key] = [value, value] if value is not None and not unknown_calls else None
        result.update(basis="reported_usage" if not unknown_calls else "incomplete_usage", confidence="reported", cost=None)
        return result
    # Companion chapters mix translation, writing and editorial work; a single
    # unit-rate projection would treat those different costs as interchangeable.
    if job["state"] != "running" or job["phase"] != "translation" or job["spec"].get("output") == "companion" or unknown_calls or len(samples) < 3:
        return initial
    total = samples[-1]["total"]
    if not isinstance(total, int) or any(s["total"] != total for s in samples):
        return initial
    remaining = max(0, total-samples[-1]["done"])
    changed = False
    for key in ("input_tokens", "output_tokens"):
        actual = sums.get(key)
        rates = []
        for before, after in zip(samples, samples[1:]):
            units = after["done"]-before["done"]
            tokens = after[key]-before[key]
            if units <= 0 or tokens < 0:
                return initial
            rates.append(tokens/units)
        mean = sum(rates)/len(rates)
        if actual is None or mean <= 0:
            continue
        variation = (sum((v-mean)**2 for v in rates)/len(rates))**.5/mean
        if variation > .5:
            continue
        spread = max(.3, 2*variation)
        result[key] = [max(actual, math.floor(actual+mean*remaining*(1-spread))), math.ceil(actual+mean*remaining*(1+spread))]
        changed = True
    if changed:
        result.update(basis="observed_translation_unit_rate", confidence="low", cost=None)
    return result or None

from alc_web.estimates import refine_token_estimate


def job(state="running", output="translation"):
    return {"state": state, "phase": "translation", "spec": {"output": output},
            "detail": {"estimate": {"input_tokens": [100, 90000],
                                    "output_tokens": [10, 9000]}}}


def samples():
    return [{"done": n, "total": 10, "input_tokens": n * 1000,
             "output_tokens": n * 100} for n in (1, 2, 3)]


def test_finished_forecast_uses_reported_totals():
    result = refine_token_estimate(job("completed"), {"input_tokens": 4321, "output_tokens": 123}, 0, [])
    assert result["input_tokens"] == [4321, 4321]
    assert result["output_tokens"] == [123, 123]
    result = refine_token_estimate(job("completed"), {"input_tokens": 4321}, 1, [])
    assert result["input_tokens"] is None
    assert result["basis"] == "incomplete_usage"


def test_stable_units_refine_remaining_work_above_observed_usage():
    result = refine_token_estimate(job(), {"input_tokens": 3000, "output_tokens": 300}, 0, samples())
    assert result["input_tokens"] == [7900, 12100]
    assert result["output_tokens"] == [790, 1210]
    assert result["basis"] == "observed_translation_unit_rate"


def test_incomparable_or_missing_evidence_keeps_initial_forecast():
    for task, rows, unknown in [
        (job(output="companion"), samples(), 0),
        (job("paused"), samples(), 0),
        (job(), samples()[:2], 0),
        (job(), samples(), 1),
        (job(), [*samples()[:2], dict(samples()[2], total=11)], 0),
    ]:
        assert refine_token_estimate(task, {}, unknown, rows) == task["detail"]["estimate"]


def test_volatile_batches_do_not_claim_a_narrow_range():
    rows = samples()
    rows[-1].update(input_tokens=30000, output_tokens=3000)
    task = job()
    assert refine_token_estimate(task, {"input_tokens": 30000, "output_tokens": 3000}, 0, rows) == task["detail"]["estimate"]

from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from alc_web.app import create_app
from alc_web.worker import Worker, execute

ORIGIN = "http://127.0.0.1:8765"
TOKEN = "test-local-capability-placeholder"


@pytest.fixture
def web(tmp_path, monkeypatch):
    monkeypatch.setenv("AC_HOME", str(tmp_path / "ac-home"))
    app = create_app(
        tmp_path, token=TOKEN, origin=ORIGIN, run_scheduler=False, discovered=[]
    )
    with TestClient(app, base_url=ORIGIN) as client:
        client.headers.update({"Origin": ORIGIN})
        response = client.post(
            "/api/session", headers={"Authorization": "Bearer " + TOKEN}
        )
        assert response.status_code == 200
        yield client, app.state.store


def upload(client, text="# A short note\n\nA readable paragraph with $x^2$.\n"):
    response = client.post(
        "/api/sources", files={"file": ("note.md", text.encode(), "text/markdown")}
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


@pytest.mark.parametrize("resume", [False, True])
@pytest.mark.parametrize("workers", [2, 16])
@pytest.mark.parametrize("owner", ["translate", "companion"])
def test_window_concurrency_setting_reaches_translation_and_resume(web, monkeypatch, resume, workers, owner):
    client, store = web
    store.save_setting("resources", {"max_jobs": 2, "api_slots": 4, "cli_slots": 1})
    resources = client.get("/api/settings").json()["resources"]
    assert resources["translation_window_workers"] == 1
    assert resources["companion_workers"] == 2
    resources["translation_window_workers"] = workers
    resources["companion_workers"] = workers
    resources["cli_slots"] = workers
    assert client.post("/api/resources", json=resources).status_code == 200
    response = client.post("/api/jobs", json={"source_id": upload(client), "output": "source", "speed": None})
    job_id = response.json()["id"]
    if resume:
        store.update(job_id, generation=2)
    worker = Worker(store, job_id)
    worker.active_owner = owner
    captured = []

    def fake_cli(owner, command, **kwargs):
        if command[0] == "status":
            return {"data": {"current_step": "blocks", "run": {"status": "failed"}}}
        captured.append((owner, command, kwargs))
        return {"data": {}}

    monkeypatch.setattr("alc_web.worker.call_cli", fake_cli)
    initial = ["translate-blocks", "source.md"] if owner == "translate" else ["build", "source.md", "--workers", str(worker.companion_workers)]
    worker.stage("translation", initial, step="blocks")
    actual_owner, command, kwargs = captured[0]
    assert actual_owner == "alc-" + owner
    assert command[0] == ("resume" if resume else initial[0])
    flag = "--window-workers" if owner == "translate" else "--workers"
    assert command[command.index(flag) + 1] == str(min(workers, 8))
    assert "--preload-chapter-evidence" not in command
    assert "--pipeline-chapters" not in command
    assert kwargs["options"].gate.provider_limits.get("codex", kwargs["options"].gate.global_limit) == 8
    assert kwargs["options"].gate.global_limit == 8
    store.update(job_id, state="running")
    resources["translation_window_workers"] = 3
    assert client.post("/api/resources", json=resources).status_code == 400


@pytest.mark.parametrize("field", ["cli_slots", "translation_window_workers", "companion_workers"])
def test_web_concurrency_rejects_values_above_sixteen(web, field):
    client, _ = web
    assert client.post("/api/resources", json={field: 17}).status_code == 422


def test_auth_origin_host_and_secret_validation(tmp_path):
    app = create_app(
        tmp_path, token=TOKEN, origin=ORIGIN, run_scheduler=False, discovered=[]
    )
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get("/api/jobs").status_code == 401
        headers = {
            "Authorization": "Bearer " + TOKEN,
            "Origin": "https://untrusted.invalid",
        }
        assert client.post("/api/jobs", headers=headers, json={}).status_code == 403
        headers["Origin"] = ORIGIN
        headers["Host"] = "attacker.invalid"
        assert client.get("/api/jobs", headers=headers).status_code == 403
        headers.pop("Host")
        secret = "fixture-private-value-not-a-real-key"
        response = client.post(
            "/api/providers", headers=headers, json={"key": secret, "unknown": secret}
        )
        assert response.status_code == 422
        assert secret not in response.text


def test_two_workspace_ports_do_not_replace_each_others_cookie(tmp_path):
    other_origin = "http://127.0.0.1:8766"
    first = create_app(
        tmp_path / "first",
        token=TOKEN,
        origin=ORIGIN,
        run_scheduler=False,
        discovered=[],
    )
    second = create_app(
        tmp_path / "second",
        token=TOKEN + "-second",
        origin=other_origin,
        run_scheduler=False,
        discovered=[],
    )
    with TestClient(first, base_url=ORIGIN) as a, TestClient(
        second, base_url=other_origin
    ) as b:
        assert (
            a.post(
                "/api/session",
                headers={"Origin": ORIGIN, "Authorization": "Bearer " + TOKEN},
            ).status_code
            == 200
        )
        b.cookies.update(a.cookies)
        assert (
            b.post(
                "/api/session",
                headers={
                    "Origin": other_origin,
                    "Authorization": "Bearer " + TOKEN + "-second",
                },
            ).status_code
            == 200
        )
        a.cookies.update(b.cookies)
        assert len(a.cookies) == 2
        assert a.get("/api/jobs").status_code == 200
        assert b.get("/api/jobs").status_code == 200


def test_source_reader_runs_without_a_model_and_verifies_delivery(web, monkeypatch):
    client, store = web
    source_id = upload(client)
    result = client.post("/api/jobs", json={"source_id": source_id, "output": "source"})
    assert result.status_code == 201, result.text
    job_id = result.json()["id"]
    assert store.claim(job_id)
    execute(str(store.project), job_id)
    job = client.get("/api/jobs/" + job_id).json()
    assert job["state"] == "completed", job.get("error")
    assert job["metrics"]["usage"]["total_calls"] == 0
    response = client.get(f"/api/jobs/{job_id}/reader?download=true")
    assert response.status_code == 200, response.text[:300]
    assert "A readable paragraph" in response.text
    assert "allow-same-origin" not in response.headers["content-security-policy"]
    opened = []
    def open_reader(_self, path, digest):
        opened.append((path, digest))
        return "http://127.0.0.1:54321/opaque-reader"
    monkeypatch.setattr("alc_web.reader_host.ReaderHosts.open", open_reader)
    response = client.get(f"/api/jobs/{job_id}/reader", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers['location'] == "http://127.0.0.1:54321/opaque-reader"
    assert opened[0][1] == job['result']['sha256']
    path = store.project / job["result"]["reader"]
    path.write_text("tampered")
    assert client.get(f"/api/jobs/{job_id}/reader").status_code == 409


def test_queue_controls_and_event_replay(web):
    client, store = web
    source_id = upload(client)
    job_id = client.post(
        "/api/jobs", json={"source_id": source_id, "output": "source"}
    ).json()["id"]
    assert (
        client.post(f"/api/jobs/{job_id}/control", json={"action": "pause"}).json()[
            "state"
        ]
        == "paused"
    )
    assert not store.claim(job_id)
    assert (
        client.post(f"/api/jobs/{job_id}/control", json={"action": "resume"}).json()[
            "state"
        ]
        == "queued"
    )
    assert (
        client.post(f"/api/jobs/{job_id}/control", json={"action": "cancel"}).json()[
            "state"
        ]
        == "cancelled"
    )
    assert (
        client.post(
            f"/api/jobs/{job_id}/control", json={"action": "resume"}
        ).status_code
        == 400
    )
    events = store.events(job_id)
    assert [e["sequence"] for e in store.events(job_id, events[1]["sequence"])] == [
        e["sequence"] for e in events[2:]
    ]
    store.event(job_id, "fixture", {}, source_key="one")
    store.event(job_id, "fixture", {}, source_key="one")
    assert sum(e["kind"] == "fixture" for e in store.events(job_id)) == 1


def test_api_keys_never_enter_database_or_responses(web):
    client, store = web
    secret = "fixture-key-that-must-stay-ephemeral"
    response = client.post(
        "/api/providers",
        json={
            "id": "api-test",
            "name": "Test",
            "protocol": "responses",
            "base_url": "https://api.example.invalid/v1",
            "model": "fixture-model",
            "key": secret,
        },
    )
    assert response.status_code == 200, response.text
    assert secret not in response.text
    assert secret not in client.get("/api/settings").text
    assert secret.encode() not in store.path.read_bytes()
    for path in store.root.glob("state.sqlite3*"):
        assert secret.encode() not in path.read_bytes()
    assert "key" not in store.setting("providers")["api-test"]


def test_model_catalog_drives_defaults_and_model_specific_efforts(tmp_path):
    profile = {
        "id": "codex",
        "name": "Codex CLI · OpenAI",
        "protocol": "cli",
        "available": True,
        "compatible": True,
        "model": "",
        "default_model": "gpt-luna",
        "models": [
            {
                "id": "gpt-luna",
                "name": "Luna",
                "description": "Fast",
                "reasoning_efforts": ["low", "medium"],
                "default_reasoning_effort": "medium",
                "provider_default": False,
            },
            {
                "id": "gpt-sol",
                "name": "Sol",
                "description": "Deep",
                "reasoning_efforts": ["high", "ultra"],
                "default_reasoning_effort": "high",
                "provider_default": True,
            },
        ],
        "model_catalog_status": "available",
        "model_catalog_message": None,
        "reasoning_efforts": ["low", "medium", "high", "ultra"],
    }
    app = create_app(
        tmp_path,
        token=TOKEN,
        origin=ORIGIN,
        run_scheduler=False,
        discovered=[profile],
    )
    with TestClient(app, base_url=ORIGIN) as client:
        client.headers.update({"Origin": ORIGIN, "Authorization": "Bearer " + TOKEN})
        assert client.post("/api/session").status_code == 200
        settings = client.get("/api/settings").json()
        assert settings["providers"][0]["default_model"] == "gpt-luna"
        assert [item["id"] for item in settings["providers"][0]["models"]] == [
            "gpt-luna",
            "gpt-sol",
        ]
        source_id = upload(client)
        default = client.post(
            "/api/jobs",
            json={
                "source_id": source_id,
                "provider_id": "codex",
                "user_intent": "Keep established terminology.",
            },
        )
        assert default.status_code == 201, default.text
        frozen = app.state.store.get(default.json()["id"])["spec"]
        assert frozen["model"] == "gpt-luna"
        assert frozen["user_intent"] == "Keep established terminology."
        assert "models" not in frozen["provider"]
        model_args = Worker(app.state.store, default.json()["id"]).model_args()
        assert model_args[model_args.index("--user-intent") + 1] == (
            "Keep established terminology."
        )
        assert (
            client.post(
                "/api/jobs",
                json={
                    "source_id": source_id,
                    "provider_id": "codex",
                    "model": "gpt-luna",
                    "reasoning_effort": "ultra",
                },
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/jobs",
                json={
                    "source_id": source_id,
                    "provider_id": "codex",
                    "model": "unknown",
                },
            ).status_code
            == 400
        )
        explicit = client.post(
            "/api/jobs",
            json={
                "source_id": source_id,
                "provider_id": "codex",
                "model": "gpt-sol",
                "reasoning_effort": "ultra",
            },
        )
        assert explicit.status_code == 201, explicit.text


def test_custom_provider_exposes_its_configured_model(web):
    client, _ = web
    response = client.post(
        "/api/providers",
        json={
            "id": "api-one",
            "name": "One",
            "protocol": "responses",
            "base_url": "https://api.example.invalid/v1",
            "model": "exact-model",
            "reasoning_efforts": ["high"],
        },
    )
    assert response.status_code == 200, response.text
    provider = next(
        item
        for item in client.get("/api/settings").json()["providers"]
        if item["id"] == "api-one"
    )
    assert provider["default_model"] == "exact-model"
    assert provider["models"][0]["reasoning_efforts"] == ["high"]


@pytest.mark.parametrize(
    "filename,text",
    [
        ("note.md", "# Source\n\n![outside](../../secret.png)"),
        ("note.html", '<h1>Source</h1><img src="../../secret.png">'),
        ("note.tex", r"\section{Source}\includegraphics{../../secret.png}"),
    ],
)
def test_reject_unselected_provider_and_unsafe_uploaded_resource(web, filename, text):
    client, store = web
    source_id = client.post(
        "/api/sources", files={"file": (filename, text.encode())}
    ).json()["id"]
    assert (
        client.post(
            "/api/jobs", json={"source_id": source_id, "provider_id": "api-missing"}
        ).status_code
        == 400
    )
    job_id = client.post(
        "/api/jobs", json={"source_id": source_id, "output": "source"}
    ).json()["id"]
    assert store.claim(job_id)
    execute(str(store.project), job_id)
    assert store.get(job_id)["state"] == "needs_input"


def test_article_reader_ignores_site_chrome_resource_paths(web):
    client, store = web
    source = client.post(
        "/api/sources",
        files={
            "file": (
                "article.html",
                b"""
        <html><body>
        <header><img src="/static/arxiv-logo.svg"></header>
        <article class="ltx_document"><h1>Article title</h1><p>Article body.</p></article>
        <footer><img src="/static/funders.png"></footer>
        </body></html>
    """,
            )
        },
    ).json()["id"]
    job_id = client.post(
        "/api/jobs", json={"source_id": source, "output": "source"}
    ).json()["id"]
    assert store.claim(job_id)
    execute(str(store.project), job_id)
    result = store.get(job_id)
    assert result["state"] == "completed", result.get("error")
    reader = client.get("/api/jobs/" + job_id + "/reader?download=true")
    assert reader.status_code == 200
    assert "Article body." in reader.text
    assert "/static/arxiv-logo.svg" not in reader.text


@pytest.mark.parametrize(
    "article",
    [
        '<article><img src="../private.png"></article>',
        '<article><h1>First</h1></article><article><img src="../private.png"></article>',
        '<article><article><object data="../private.svg"></object></article></article>',
    ],
)
def test_all_article_content_roots_still_reject_escaping_assets(tmp_path, article):
    from alc_web.acquisition import NeedsSourceInput, _validate_resource_paths

    source = tmp_path / "source.html"
    source.write_text('<header><img src="/static/logo.svg"></header>' + article)
    with pytest.raises(NeedsSourceInput, match="outside the uploaded folder"):
        _validate_resource_paths(source)


def test_cli_usage_has_api_reference_without_claiming_a_charge(web):
    client, store = web
    job = store.create(
        {"output": "reader", "model": "gpt-5.6-luna", "provider": {"protocol": "cli"}}
    )
    store.event(
        job["id"],
        "package.event",
        {
            "event": "llm_usage",
            "data": {
                "call_id": "reference-call",
                "model": "gpt-5.6-luna",
                "usage": {
                    "availability": "reported",
                    "input_tokens": 1000,
                    "output_tokens": 100,
                    "cached_input_tokens": 500,
                    "cache_write_tokens": 0,
                    "input_includes_cache": True,
                },
            },
        },
    )
    response = client.get("/api/jobs/" + job["id"]).json()
    cost = response["metrics"]["cost"]
    assert cost["reference_only"] is True
    assert float(cost["amount"]) == 0.00023
    assert cost["billed_amount"] is None
    assert cost["source"] == "https://developers.openai.com/api/docs/pricing"
    assert "input_price" not in store.get(job["id"])["spec"]["provider"]


def test_unknown_usage_and_prices_never_become_zero_cost(web):
    client, store = web
    source_id = upload(client)
    job_id = client.post(
        "/api/jobs", json={"source_id": source_id, "output": "source"}
    ).json()["id"]
    store.event(
        job_id, "package.event", {"event": "llm_call_started", "data": {"call_id": "a"}}
    )
    store.event(
        job_id,
        "package.event",
        {
            "event": "llm_usage",
            "data": {
                "call_id": "a",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": None,
                    "availability": "partial",
                },
            },
        },
    )
    metrics = client.get("/api/jobs/" + job_id).json()["metrics"]
    assert metrics["usage"]["unknown_calls"] == 1
    assert metrics["usage"]["output_tokens"] is None
    assert metrics["cost"]["amount"] is None
    assert metrics["cost"]["billed_amount"] is None


def test_cancel_wins_before_completion_commit(web):
    client, store = web
    job_id = client.post(
        "/api/jobs", json={"source_id": upload(client), "output": "source"}
    ).json()["id"]
    assert store.claim(job_id)
    store.control(job_id, "cancel")
    store.finish(job_id, {"reader": "retained-result"})
    assert store.get(job_id)["state"] == "cancelled"
    assert store.get(job_id)["result"] == {"reader": "retained-result"}


def test_reader_job_uses_configured_api_and_replays_without_another_call(
    web, monkeypatch
):
    import httpx
    from alc_web.worker import Worker
    from ac_llm.providers.registry import ProviderRegistry
    from ac_llm.providers.http_api import HTTPAPIAdapter, HTTPProviderConfig
    from ac_llm.api import LLMTaskService
    from ac_llm.host import HostTurn, encode_host_turn

    client, store = web
    client.post(
        "/api/providers",
        json={
            "id": "api-test",
            "name": "Fixture API",
            "protocol": "responses",
            "base_url": "https://fixture.invalid/v1",
            "model": "fixture-model",
            "key": "fixture-key",
            "reasoning_efforts": ["high"],
        },
    )
    calls = []

    def respond(req):
        data = json.loads(req.content)
        calls.append(data)
        assert data["reasoning"] == {"effort": "high"}
        result = encode_host_turn(
            HostTurn(
                "complete",
                {"language_tag": "en", "classification": "known", "confidence": 0.99},
                None,
            )
        )
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": json.dumps(result)}
                        ],
                    }
                ],
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 30,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens_details": {"reasoning_tokens": 10},
                },
            },
        )

    registry = ProviderRegistry()
    registry.register(
        "api-test",
        lambda: HTTPAPIAdapter(
            HTTPProviderConfig(
                "api-test",
                "responses",
                "https://fixture.invalid/v1",
                reasoning_efforts=("high",),
            ),
            credential=lambda: "fixture-key",
            transport=httpx.MockTransport(respond),
        ),
    )
    original_init = LLMTaskService.__init__
    monkeypatch.setattr(
        LLMTaskService,
        "__init__",
        lambda self, **kwargs: original_init(self, registry=registry),
    )
    job_id = client.post(
        "/api/jobs",
        json={
            "source_id": upload(client),
            "provider_id": "api-test",
            "target_language": "en",
            "reasoning_effort": "high",
        },
    ).json()["id"]
    assert store.claim(job_id)
    execute(str(store.project), job_id)
    job = client.get("/api/jobs/" + job_id).json()
    assert job["state"] == "completed", job.get("error")
    assert len(calls) == 1
    assert job["metrics"]["usage"]["input_tokens"] == 100
    store.update(job_id, state="delivery_failed")
    store.control(job_id, "retry_delivery")
    assert store.claim(job_id)
    execute(str(store.project), job_id)
    assert store.get(job_id)["state"] == "completed"
    assert len(calls) == 1


def test_stale_worker_generation_cannot_run(web):
    client, store = web
    job_id = client.post(
        "/api/jobs", json={"source_id": upload(client), "output": "source"}
    ).json()["id"]
    assert store.claim(job_id)
    execute(str(store.project), job_id, generation=0)
    assert store.get(job_id)["state"] == "running"
    assert not (store.job_directory(job_id) / "source.json").exists()


def test_pdf_text_derivative_requires_explicit_choice(web):
    client, store = web
    response = client.post(
        "/api/sources",
        files={"file": ("original.pdf", b"%PDF-1.4\nfixture", "application/pdf")},
    )
    job_id = client.post(
        "/api/jobs", json={"source_id": response.json()["id"], "output": "source"}
    ).json()["id"]
    assert store.claim(job_id)
    execute(str(store.project), job_id)
    job = store.get(job_id)
    assert job["state"] == "needs_input", job.get("error")
    assert job["error"]["code"] == "pdf_text_confirmation"
    assert job["result"] is None


def test_custom_cli_routing_is_not_silently_ignored(tmp_path):
    from alc_web.providers import _routing_warning

    path = tmp_path / "config.toml"
    path.write_text('model_provider = "private-provider"\n')
    assert _routing_warning("codex", config_path=path, environment={})
    path.write_text('model = "example"\n')
    assert _routing_warning("codex", config_path=path, environment={}) is None
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"apiKeyHelper": "fixture-helper"}))
    assert _routing_warning("claude", config_path=path, environment={})


def test_endpoint_edit_does_not_send_new_credentials_to_old_jobs(web):
    client, store = web
    first = {
        "id": "api-test",
        "name": "First",
        "protocol": "responses",
        "base_url": "https://first.invalid/v1",
        "model": "fixture",
        "key": "fixture-first-key",
    }
    original = client.post("/api/providers", json=first).json()
    job = client.post(
        "/api/jobs", json={"source_id": upload(client), "provider_id": "api-test"}
    ).json()
    changed = client.post(
        "/api/providers",
        json={
            **first,
            "base_url": "https://second.invalid/v1",
            "key": "fixture-second-key",
        },
    ).json()
    assert original["secret_ref"] != changed["secret_ref"]
    frozen = store.get(job["id"])["spec"]["provider"]
    assert frozen["secret_ref"] == original["secret_ref"]
    assert (
        client.app.state.vault.get(frozen["secret_ref"], remember=False)
        == "fixture-first-key"
    )


def test_list_is_lightweight_and_usage_projection_reads_only_new_events(
    web, monkeypatch
):
    client, store = web
    job_id = client.post(
        "/api/jobs", json={"source_id": upload(client), "output": "source"}
    ).json()["id"]
    store.update(
        job_id,
        detail={
            "source_preview": "private document",
            "progress": {
                "phase": "translation",
                "completed_units": 1,
                "total_units": 5,
            },
        },
    )
    store.event(
        job_id,
        "package.event",
        {"event": "llm_call_started", "data": {"call_id": "call-1"}},
    )
    first = client.get("/api/jobs/" + job_id).json()["metrics"]
    assert first["usage"]["unknown_calls"] == 1
    reads = []
    original = store.events

    def track(job_id, after=0, limit=200):
        reads.append(after)
        return original(job_id, after, limit)

    monkeypatch.setattr(store, "events", track)
    store.event(
        job_id,
        "package.event",
        {
            "event": "llm_usage",
            "data": {
                "call_id": "call-1",
                "usage": {
                    "availability": "reported",
                    "input_tokens": 12,
                    "output_tokens": 4,
                },
            },
        },
    )
    second = client.get("/api/jobs/" + job_id).json()["metrics"]
    assert reads == [first["cursor"]]
    assert second["usage"]["input_tokens"] == 12
    assert second["usage"]["total_calls"] == 1
    assert second["usage"]["unknown_calls"] == 0
    third = client.get("/api/jobs/" + job_id).json()["metrics"]
    assert third["usage"] == second["usage"]
    assert reads[-1] == second["cursor"]
    reads.clear()
    summaries = client.get("/api/jobs").json()
    assert summaries == [
        {
            "id": job_id,
            "state": "queued",
            "phase": "queued",
            "created": store.get(job_id)["created"],
            "spec": {"title": "note.md"},
            "display_title": "note.md",
        }
    ]
    assert reads == []
    updates = [event for event in original(job_id) if event["kind"] == "job.updated"]
    assert "source_preview" not in updates[-1]["data"]["detail"]
    assert store.get(job_id)["detail"]["source_preview"] == "private document"


def test_cost_does_not_use_rates_for_a_different_model(web):
    from alc_web.metrics import summarize

    client, store = web
    job = store.create(
        {
            "output": "reader",
            "model": "other-model",
            "provider": {"model": "priced-model", "input_price": 1, "output_price": 2},
        }
    )
    store.event(
        job["id"],
        "package.event",
        {
            "event": "llm_usage",
            "data": {
                "call_id": "call-1",
                "usage": {
                    "availability": "reported",
                    "input_tokens": 100,
                    "output_tokens": 50,
                },
            },
        },
    )
    result = summarize(store, store.get(job["id"]))
    assert result["cost"]["amount"] is None
    assert result["cost"]["complete"] is False


def test_completed_job_quality_comes_from_delivery_not_historical_events(
    web, monkeypatch
):
    from alc_web.metrics import summarize
    import alc_render

    _, store = web
    job = store.create({"output": "reader", "provider": {}})
    store.event(
        job["id"],
        "package.event",
        {
            "event": "translation_fallback",
            "data": {"source_text_block_ids": ["old-fallback"]},
        },
    )
    store.update(job["id"], state="completed")
    monkeypatch.setattr(
        alc_render,
        "publication_translation_quality",
        lambda path: {
            "available": True,
            "source_fallback_count": 0,
            "review_skipped_count": 0,
        },
    )
    assert (
        summarize(store, store.get(job["id"]))["quality"]["source_fallback_count"] == 0
    )

    def unavailable(path):
        raise ValueError("invalid delivery")

    monkeypatch.setattr(alc_render, "publication_translation_quality", unavailable)
    quality = summarize(store, store.get(job["id"]))["quality"]
    assert quality["available"] is False and quality["source_fallback_count"] is None


@pytest.mark.parametrize("speed,workers", [("economy",1),("standard",2),("fast",4)])
@pytest.mark.parametrize("mode", ["fast","standard","deep"])
def test_speed_workers_are_independent_of_depth(web, speed, workers, mode):
    client, store = web
    job = client.post("/api/jobs", json={"source_id":upload(client),"output":"source","speed":speed,"mode":mode}).json()
    worker = Worker(store, job["id"])
    assert worker.window_workers == worker.companion_workers == workers
    assert worker.model_args()[worker.model_args().index("--processing-mode")+1] == mode


def test_edit_provider_preserves_key_and_updates_same_connection(web):
    client, store = web
    config = {'id':'api-edit','name':'Original','protocol':'chat-completions',
              'base_url':'https://example.invalid/v1','model':'old-model',
              'key':'fixture-edit-key','max_output_tokens':16384}
    assert client.post('/api/providers',json=config).status_code == 200
    response = client.post('/api/providers',json={**config,'key':None,'name':'Updated','model':'new-model'})
    assert response.status_code == 200
    value = response.json()
    assert value['key_available'] is True
    assert value['model']=='new-model' and value['max_output_tokens']==16384
    assert list(store.setting('providers')) == ['api-edit']
    assert 'fixture-edit-key' not in client.get('/api/settings').text


@pytest.mark.parametrize("remember,available", [(True, None), (False, False)])
def test_settings_does_not_unlock_saved_credentials(web, monkeypatch, remember, available):
    client, store = web
    config = {'id': 'saved-api', 'name': 'Saved', 'protocol': 'responses',
              'base_url': 'https://example.invalid/v1', 'model': 'fixture',
              'remember_key': remember, 'secret_ref': 'saved-reference'}
    store.save_setting('providers', {config['id']: config})

    def unexpected_access(*args, **kwargs):
        pytest.fail('Loading settings must not access the OS credential store')

    monkeypatch.setattr(client.app.state.vault, '_backend', unexpected_access)
    response = client.get('/api/settings')
    assert response.status_code == 200
    assert response.json()['providers'][0]['key_available'] is available
    client.app.state.vault.put('saved-reference', 'fixture-session-key', remember=False)
    response = client.get('/api/settings')
    assert response.json()['providers'][0]['key_available'] is True
    assert 'fixture-session-key' not in response.text


def test_edit_can_promote_existing_session_key_to_saved_storage(web, monkeypatch):
    client, store = web
    saved = {}
    class Backend:
        def set_password(self, service, key, value):
            saved[key] = value
    monkeypatch.setattr(client.app.state.vault, '_backend', lambda: Backend())
    config = {'id':'api-promote','name':'Test','protocol':'responses','base_url':'https://example.invalid/v1','model':'fixture','key':'fixture-promote-key'}
    initial = client.post('/api/providers',json=config).json()
    result = client.post('/api/providers',json={**config,'key':None,'remember_key':True})
    assert result.status_code == 200
    assert saved[initial['secret_ref']] == 'fixture-promote-key'
    assert 'fixture-promote-key' not in result.text


def test_rename_delete_http_boundaries(web):
    client, store = web
    id=client.post("/api/jobs",json={"source_id":upload(client),"output":"source"}).json()["id"]
    response=client.patch(f"/api/jobs/{id}",json={"title":"My paper"})
    assert response.status_code==200,response.text
    assert response.json()["display_title"]=="My paper"
    assert client.delete(f"/api/jobs/{id}").status_code==400
    store.update(id,state="completed")
    assert client.delete(f"/api/jobs/{id}").status_code==200
    assert client.get("/api/jobs").json()==[]


def test_legacy_strict_delivery_no_longer_stops_warnings(web, monkeypatch):
    client, store = web
    job=client.post("/api/jobs",json={"source_id":upload(client),"output":"source","strict_delivery":True}).json()
    assert "strict_delivery" not in job["spec"]
    # Previously saved jobs can still contain the obsolete flag.
    with store.connect() as db:
        spec=store.get(job['id'])['spec'];spec['strict_delivery']=True
        db.execute("UPDATE jobs SET spec=? WHERE id=?",(json.dumps(spec),job['id']))
    monkeypatch.setattr('alc_render.publication_translation_quality',lambda p:{'source_fallback_count':1,'review_skipped_count':0,'translation_warning_count':1})
    assert store.claim(job['id'])
    execute(str(store.project),job['id'])
    assert store.get(job['id'])['state']=='completed'


@pytest.mark.parametrize('currency',['USD','CNY','EUR','GBP','JPY','HKD'])
def test_provider_currency_roundtrip_and_usage(web,currency):
    from alc_web.metrics import summarize
    client,store=web
    value={'id':'api-currency','name':'Pricing test','protocol':'chat-completions','base_url':'https://example.test/v1','model':'test','price_currency':currency,'input_price':2,'output_price':4}
    response=client.post('/api/providers',json=value)
    assert response.status_code==200,response.text
    profile=store.setting('providers')['api-currency']
    assert profile['price_currency']==currency
    job=store.create({'output':'translation','model':'test','provider':profile})
    store.event(job['id'],'package.event',{'event':'llm_usage','data':{'call_id':'a','usage':{'availability':'reported','input_tokens':1000000,'output_tokens':1000000,'cached_input_tokens':0,'cache_write_tokens':0,'input_includes_cache':True}}})
    cost=summarize(store,store.get(job['id']))['cost']
    assert cost['currency']==currency
    assert float(cost['amount'])==6


@pytest.mark.parametrize('reviews', [0, 1, 2])
def test_processing_policy_api_freezes_new_task_and_rejects_partial(web, reviews):
    client, store = web
    source_id = upload(client)
    response = client.post('/api/jobs', json={'source_id': source_id, 'output': 'source', 'processing_workers': 3, 'review_rounds': reviews})
    assert response.status_code == 201
    job_id = response.json()['id']
    spec = store.get(job_id)['spec']
    assert spec['processing_workers'] == 3
    assert spec['review_rounds'] == reviews
    assert client.post('/api/jobs', json={'source_id': source_id, 'output': 'source', 'review_rounds': reviews}).status_code == 422


def test_keyring_isolated_between_workspaces(tmp_path, monkeypatch):
    from alc_web.providers import SecretVault
    class Backend:
        def __init__(self): self.values = {}
        def set_password(self, service, key, value): self.values[service, key] = value
        def get_password(self, service, key): return self.values.get((service, key))
        def delete_password(self, service, key): self.values.pop((service, key), None)
    backend = Backend()
    monkeypatch.setattr(SecretVault, '_backend', staticmethod(lambda: backend))
    a = SecretVault(tmp_path / 'a'); b = SecretVault(tmp_path / 'b')
    a.put('same-profile', 'fixture-a', remember=True)
    b.put('same-profile', 'fixture-b', remember=True)
    assert SecretVault(tmp_path / 'a').get('same-profile', remember=True) == 'fixture-a'
    b.forget_saved('same-profile')
    assert SecretVault(tmp_path / 'a').get('same-profile', remember=True) == 'fixture-a'
    assert SecretVault(tmp_path / 'b').get('same-profile', remember=True) is None


def test_upload_accepts_pdf_larger_than_former_50_mib_limit(web, tmp_path):
    client, store = web
    path = tmp_path / 'large.pdf'
    size = 50 * 1024 * 1024 + 1
    with path.open('wb') as stream:
        stream.write(b'%PDF-1.4\n')
        stream.truncate(size)
    with path.open('rb') as stream:
        response = client.post('/api/sources', files={'file': ('large.pdf', stream, 'application/pdf')})
    assert response.status_code == 200
    source = store.source(response.json()['id'])
    assert source['bytes'] == size
    assert (store.root / source['path']).stat().st_size == size

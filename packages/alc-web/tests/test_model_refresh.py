from alc_web import providers
from alc_web.app import create_app
from fastapi.testclient import TestClient


def profile(model):
    return {"id": "codex", "compatible": True, "models": [{"id": model}],
            "default_model": model, "reasoning_efforts": ["medium"],
            "model_catalog_status": "available"}


def test_catalog_ttl_force_and_failure_retention(monkeypatch):
    now = [0.0]
    result = [profile("first")]
    calls = []
    monkeypatch.setattr(providers.time, "monotonic", lambda: now[0])
    def discover():
        calls.append(1)
        return [dict(p) for p in result]
    monkeypatch.setattr(providers, "cli_profiles", discover)
    cache = providers.CLIProfileCache()
    result[:] = [profile("second")]
    now[0] = 299
    assert cache.get()[0]["default_model"] == "first"
    now[0] = 300
    assert cache.get()[0]["default_model"] == "second"
    result[:] = [profile("third")]
    assert cache.get(force=True)[0]["default_model"] == "third"
    result[0]["models"] = []
    stale = cache.get(force=True)[0]
    assert stale["default_model"] == "third"
    assert stale["model_catalog_status"] == "stale"
    stale["models"].clear()
    assert cache.get()[0]["models"] == [{"id": "third"}]
    assert len(calls) == 4
    result[:] = [profile("recovered")]
    assert cache.get(force=True)[0]["model_catalog_status"] == "available"
    result[0]["compatible"] = False
    result[0]["models"] = []
    assert cache.get(force=True)[0]["models"] == []


def test_settings_refresh_updates_catalog(tmp_path, monkeypatch):
    result = [profile("first")]
    monkeypatch.setattr(providers, "cli_profiles", lambda: list(result))
    app = create_app(tmp_path, token="test-token", origin="http://testserver", run_scheduler=False)
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer test-token"
        assert client.get("/api/settings").json()["providers"][0]["default_model"] == "first"
        result[:] = [profile("second")]
        assert client.get("/api/settings").json()["providers"][0]["default_model"] == "first"
        assert client.get("/api/settings?refresh_models=true").json()["providers"][0]["default_model"] == "second"
        assert client.get("/api/settings").json()["providers"][0]["default_model"] == "second"


def test_codex_prefers_current_luna_when_old_luna_is_still_available(monkeypatch):
    from types import SimpleNamespace
    from ac_llm.model_catalog import ProviderModel

    models = [
        ProviderModel(model, model, "Model", ("medium",), "medium", model == "gpt-6-astra")
        for model in ("gpt-6-astra", "gpt-5.6-luna", "gpt-6-luna")
    ]
    monkeypatch.setattr(providers.shutil, "which", lambda name: "/fixture/" + name)
    monkeypatch.setattr(
        providers.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="--ignore-user-config --json --sandbox --skip-git-repo-check",
        ),
    )
    monkeypatch.setattr(providers, "_routing_warning", lambda name: None)
    monkeypatch.setattr(providers, "DEFAULT_MODELS", {
        **providers.DEFAULT_MODELS,
        "codex": {**providers.DEFAULT_MODELS["codex"], "medium": "gpt-6-luna"},
    })
    monkeypatch.setattr(
        providers,
        "codex_model_catalog",
        lambda _: SimpleNamespace(models=models, status="available", message=None),
    )

    codex = next(item for item in providers.cli_profiles() if item["id"] == "codex")
    assert codex["default_model"] == "gpt-6-luna"

    models.pop()
    codex = next(item for item in providers.cli_profiles() if item["id"] == "codex")
    assert codex["default_model"] == "gpt-6-astra"


def test_source_only_companion_warning_is_not_lost():
    from alc_web.worker import companion_delivery_warnings
    assert companion_delivery_warnings({'warnings': [{'code': 'provider_degraded_source_only'}]})
    assert companion_delivery_warnings({'warnings': [{'code': 'source_diagnostic'}]}) == []


def test_claude_picker_exposes_cli_aliases(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(providers.shutil, 'which', lambda name: '/fixture/' + name)
    monkeypatch.setattr(providers.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=0, stdout='--ignore-user-config --json --sandbox --skip-git-repo-check --tools --strict-mcp-config --setting-sources --output-format'))
    monkeypatch.setattr(providers, '_routing_warning', lambda name: None)
    monkeypatch.setattr(providers, 'codex_model_catalog', lambda _: SimpleNamespace(models=[], status='unavailable', message=None))
    claude = next(p for p in providers.cli_profiles() if p['id'] == 'claude')
    assert [m['id'] for m in claude['models']] == ['sonnet', 'opus', 'haiku']
    assert claude['model_catalog_status'] == 'configured'
    providers.validate_model_effort(claude, 'custom-model-id', None)


def test_old_foundation_reports_missing_claude_capability(monkeypatch):
    monkeypatch.setattr(providers, "claude_connection_environment", None)
    assert "Foundation" in providers._routing_warning("claude", environment={})

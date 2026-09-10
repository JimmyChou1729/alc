from pathlib import Path
import json
import pytest
from fastapi.testclient import TestClient
from ac_document import import_mineru_bundle, AcDocumentService
from ac_document.parse import PDFTextLayer
from alc_web.app import create_app
from alc_web.worker import execute


@pytest.fixture
def web(tmp_path, monkeypatch):
    monkeypatch.setenv("AC_HOME", str(tmp_path / "home"))
    app = create_app(
        tmp_path,
        token="test",
        origin="http://127.0.0.1:8765",
        run_scheduler=False,
        discovered=[],
    )
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        c.headers["Origin"] = "http://127.0.0.1:8765"
        assert (
            c.post("/api/session", headers={"Authorization": "Bearer test"}).status_code
            == 200
        )
        yield c, app.state.store


def upload(c):
    return c.post(
        "/api/sources",
        files={"file": ("scan.pdf", b"%PDF-1.4\nfixture", "application/pdf")},
    ).json()["id"]


def test_configuration_shared_and_frozen_with_endpoint_consent(web):
    from ac_document import load_mineru_config

    c, store = web
    config = {
        "executable": None,
        "api_url": "https://first.example",
        "token_env": "OCR_TOKEN",
        "language": "en",
    }
    assert c.post("/api/ocr", json=config).status_code == 200
    assert load_mineru_config(store.project / ".ac/mineru.json") == config
    source = upload(c)
    spec = {"source_id": source, "output": "source", "ocr_remote_consent": True}
    assert c.post("/api/jobs", json=spec).status_code == 400
    spec["ocr_service_url"] = config["api_url"]
    job = c.post("/api/jobs", json=spec).json()
    config["api_url"] = "https://second.example"
    assert c.post("/api/ocr", json=config).status_code == 200
    assert store.get(job["id"])["spec"]["ocr"]["api_url"] == "https://first.example"
    assert c.post("/api/jobs", json=spec).status_code == 400
    assert c.get("/api/settings").json()["ocr"] == config


def test_no_raw_secret_field_or_url_credentials(web):
    c, _ = web
    assert (
        c.post("/api/ocr", json={"api_url": "https://u:secret@example.org"}).status_code
        == 400
    )
    assert (
        c.post(
            "/api/ocr", json={"api_url": "https://example.org", "key": "secret"}
        ).status_code
        == 422
    )


def test_scanned_pdf_reaches_reader_with_verified_provenance(
    web, tmp_path, monkeypatch
):
    c, store = web
    config = {
        "executable": "/optional/mineru",
        "api_url": None,
        "token_env": None,
        "language": "en",
    }
    assert c.post("/api/ocr", json=config).status_code == 200

    class Pages:
        def extract(self, payload):
            return PDFTextLayer(("",))

    monkeypatch.setattr("ac_document.mineru.PdftotextExtractor", Pages)
    calls = []

    def parse(pdf, *, job_dir, checkpoint, **config):
        calls.append(config)
        checkpoint()
        raw = Path(job_dir) / "raw"
        raw.mkdir(parents=True)
        items = [{"type": "text", "text": "Recovered scanned content", "page_idx": 0}]
        middle = {
            "_backend": "pipeline",
            "_version_name": "3.4.5",
            "pdf_info": [
                {
                    "page_idx": 0,
                    "page_size": [595, 842],
                    "para_blocks": [
                        {
                            "type": "text",
                            "lines": [
                                {"spans": [{"content": "Recovered scanned content"}]}
                            ],
                        }
                    ],
                    "discarded_blocks": [],
                }
            ],
        }
        (raw / "list.json").write_text(json.dumps(items))
        (raw / "middle.json").write_text(json.dumps(middle))
        return import_mineru_bundle(
            pdf,
            content_list=raw / "list.json",
            middle_json=raw / "middle.json",
            output_dir=Path(job_dir) / "bundle",
        )

    monkeypatch.setattr("ac_document.parse_pdf_mineru", parse)
    job = c.post("/api/jobs", json={"source_id": upload(c), "output": "source"}).json()
    store.claim(job["id"])
    execute(str(store.project), job["id"])
    result = store.get(job["id"])
    assert result["state"] == "completed", result["error"]
    assert calls == [config]
    rich = json.loads(
        (store.job_directory(job["id"]) / "source-export/rich-source.json").read_text()
    )
    assert rich["metadata"]["pdf_source"]["proofread"] is False
    assert len(rich["blocks"]) == len(rich["page_map"])
    manifest = store.job_directory(job["id"]) / "ocr-job/bundle/manifest.json"
    source = manifest.parent / "source.html"
    # Both learning entry points resolve the same provenance-bound identity.
    from alc_translate.source import resolve_translation_source
    from alc_companion.cli import _resolve_source

    service = AcDocumentService(cache_root=tmp_path / "cache")
    translated = resolve_translation_source(
        service, source, pdf_source_manifest=manifest
    )
    companion, _, warnings = _resolve_source(
        service, str(source), pdf=None, refresh=False, pdf_source_manifest=str(manifest)
    )
    assert (
        translated.rich.document_digest
        == companion.document_digest
        == rich["document_digest"]
    )
    assert warnings


def test_text_only_never_invokes_configured_remote(web, monkeypatch):
    c, store = web
    c.post("/api/ocr", json={"api_url": "https://example.org"})

    def forbidden(*a, **kw):
        pytest.fail("OCR must not be called")

    monkeypatch.setattr("ac_document.parse_pdf_mineru", forbidden)

    class Pages:
        def extract(self, payload):
            return PDFTextLayer(("Native text",))

    monkeypatch.setattr("ac_document.parse.parser.PdftotextExtractor", Pages)
    response = c.post(
        "/api/jobs",
        json={"source_id": upload(c), "output": "source", "pdf_mode": "text_only"},
    )
    assert response.status_code == 201
    job = response.json()
    store.claim(job["id"])
    execute(str(store.project), job["id"])
    assert store.get(job["id"])["state"] == "completed"


def test_remote_profile_does_not_block_non_pdf_uploads(web):
    c, _ = web
    c.post("/api/ocr", json={"api_url": "https://ocr.example"})
    source = c.post(
        "/api/sources", files={"file": ("note.md", b"# Plain text", "text/markdown")}
    ).json()["id"]
    response = c.post("/api/jobs", json={"source_id": source, "output": "source"})
    assert response.status_code == 201
    assert response.json()["spec"]["ocr"] is None


def test_url_without_ocr_configuration_can_start(web):
    c, _ = web
    response = c.post(
        "/api/jobs",
        json={"source_url": "https://example.org/article", "output": "source"},
    )
    assert response.status_code == 201
    assert response.json()["spec"]["ocr"] is None


@pytest.fixture
def vision_web(web, tmp_path, monkeypatch):
    import base64
    from ac_document import RenderedPDFPage
    from ac_llm import LLMCompleted, LLMPaused
    from ac_jobs import ResumeReason
    from alc_ocr_proofread.pdf_bundle import PDFBundleProofreadService

    c, store = web
    profile = {
        "id": "codex",
        "protocol": "cli",
        "model": "test-vision",
        "default_model": "test-vision",
    }
    monkeypatch.setattr("alc_web.app.resolve_profile", lambda *a: profile)
    assert (
        c.post("/api/ocr", json={"executable": "/optional/mineru"}).status_code == 200
    )

    class Pages:
        def extract(self, payload):
            return PDFTextLayer(("",))

    monkeypatch.setattr("ac_document.mineru.PdftotextExtractor", Pages)

    def parse(pdf, *, job_dir, checkpoint, **config):
        root = Path(job_dir)
        root.mkdir(parents=True, exist_ok=True)
        content = root / "content.json"
        middle = root / "middle.json"
        content.write_text(
            json.dumps([{"type": "text", "text": "OCR typo", "page_idx": 0}])
        )
        middle.write_text(
            json.dumps(
                {
                    "_backend": "pipeline",
                    "_version_name": "3.4.5",
                    "pdf_info": [
                        {
                            "page_idx": 0,
                            "page_size": [595, 842],
                            "para_blocks": [
                                {
                                    "type": "text",
                                    "lines": [{"spans": [{"content": "OCR typo"}]}],
                                }
                            ],
                            "discarded_blocks": [],
                        }
                    ],
                }
            )
        )
        return import_mineru_bundle(
            pdf, content_list=content, middle_json=middle, output_dir=root / "bundle"
        )

    monkeypatch.setattr("ac_document.parse_pdf_mineru", parse)
    calls = []
    value = {
        "edits": [
            {
                "target": "text",
                "before": "OCR typo",
                "after": "OCR corrected",
                "occurrence": 1,
                "reason": "Visible page spelling",
            }
        ],
        "uncertainties": [],
        "checks": {
            "all_visible_text": True,
            "all_visible_math": True,
            "structure_complete": True,
        },
    }

    class Vision:
        def execute_or_resume(self, context, request, *, options, input=None):
            calls.append(request.task_id)
            assert options.profile.value == "local_app"
            if value.pop("_pause", False):
                ref = context.artifacts.publish_json(
                    "test/approval", {"page_number": 1}
                )
                return LLMPaused(
                    ResumeReason.SUPERVISION_REQUIRED,
                    "web-test-key",
                    input_required=True,
                    request_ref=ref,
                    response_contract="ac.llm.resume_input.v3",
                )
            if value.pop("_expect_input", False):
                assert input.resume_key == "web-test-key"
            context.events.emit(
                "llm_usage",
                {
                    "task_id": request.task_id,
                    "model": "test-vision",
                    "usage": {
                        "availability": "reported",
                        "input_tokens": 100,
                        "output_tokens": 20,
                    },
                },
            )
            return LLMCompleted({**value, "uncertainties":[{**u,"kind":"ambiguous"} for u in value["uncertainties"]]}, "codex", "test-vision", None, None)

    class Renderer:
        def render_page(self, pdf, page_number):
            png = base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII="
            )
            return RenderedPDFPage(page_number, png, 1, 1)

    original_execute = PDFBundleProofreadService.execute
    original_resume = PDFBundleProofreadService.resume
    monkeypatch.setattr(
        PDFBundleProofreadService,
        "execute",
        lambda self, id, **kw: original_execute(
            self, id, task_service=Vision(), renderer=Renderer(), **kw
        ),
    )
    monkeypatch.setattr(
        PDFBundleProofreadService,
        "resume",
        lambda self, id, **kw: original_resume(
            self, id, task_service=Vision(), renderer=Renderer(), **kw
        ),
    )
    return c, store, calls, value


def review_spec(c):
    return {
        "source_id": upload(c),
        "output": "source",
        "model": "test-vision",
        "ocr_proofread": True,
        "ocr_proofread_consent": True,
        "ocr_proofread_provider_id": "codex",
        "ocr_proofread_model": "test-vision",
    }


def test_optional_ocr_requires_exact_model_consent(vision_web):
    c, store, calls, _ = vision_web
    spec = review_spec(c)
    spec["ocr_proofread_consent"] = False
    assert c.post("/api/jobs", json=spec).status_code == 400
    spec["ocr_proofread_consent"] = True
    spec["ocr_proofread_model"] = "other-model"
    assert c.post("/api/jobs", json=spec).status_code == 400
    assert calls == []






def test_ocr_provider_input_pause_is_resumable(vision_web):
    c, store, calls, value = vision_web
    value["_pause"] = True
    response = c.post("/api/jobs", json=review_spec(c))
    id = response.json()["id"]
    assert store.claim(id)
    execute(str(store.project), id)
    paused = c.get(f"/api/jobs/{id}").json()
    assert paused["state"] == "needs_input", paused["error"]
    assert paused["error"]["resume"]["resume_key"] == "web-test-key"
    value["_expect_input"] = True
    response = c.post(
        f"/api/jobs/{id}/control",
        json={
            "action": "resume",
            "resume_input": {
                "schema_version": "ac.llm.resume_input.v3",
                "resume_key": "web-test-key",
                "action": "continue",
                "host_response": None,
                "candidate_digest": None,
                "reason": None,
            },
        },
    )
    assert response.status_code == 200, response.text
    assert store.claim(id)
    execute(str(store.project), id)
    assert store.get(id)["state"] == "completed", store.get(id)["error"]
    assert len(calls) == 2


@pytest.mark.parametrize("uncertain", [False, True])
def test_model_review_defaults_to_automatic_continue(vision_web, uncertain):
    c, store, calls, value = vision_web
    if uncertain:
        value["uncertainties"] = [
            {"excerpt": "header", "reason": "Not represented in source"}
        ]
    spec = review_spec(c)
    spec.pop("ocr_manual_review", None)
    response = c.post("/api/jobs", json=spec)
    id = response.json()["id"]
    assert store.claim(id)
    execute(str(store.project), id)
    done = store.get(id)
    assert done["state"] == "completed", done["error"]
    rich = json.loads(
        (store.job_directory(id) / "project/publication/rich-source.json").read_text()
    )
    assert rich["metadata"]["pdf_source"]["proofread"] is False
    assert rich["metadata"]["pdf_source"]["proofreading"]["review_mode"] == "model"
    assert rich["metadata"]["pdf_source"]["proofreading"]["uncertainty_count"] == int(
        uncertain
    )
    assert len(calls) == 1











def test_legacy_review_pause_resumes_model_output_without_review_or_repeat(vision_web, monkeypatch):
    from ac_document import PDFSourceBundleError
    c, store, calls, value = vision_web
    value['uncertainties'] = [{'excerpt':'header', 'reason':'Uncertain'}]
    id = c.post('/api/jobs', json=review_spec(c)).json()['id']
    with monkeypatch.context() as patch:
        def old_gate(*args, **kwargs):
            raise PDFSourceBundleError('ocr_review_required', 'Legacy human review pause')
        patch.setattr('alc_web.ocr_review.adopt_pdf_candidate', old_gate)
        assert store.claim(id); execute(str(store.project), id)
    assert store.get(id)['state'] == 'needs_input'
    with store.connect() as db:
        spec=store.get(id)['spec']; spec['ocr_manual_review']=True
        spec['runtime']['packages']['alc-web']['code_sha256']='old-version'
        db.execute('UPDATE jobs SET spec=? WHERE id=?', (json.dumps(spec),id))
    (store.job_directory(id)/'ocr-review-draft.json').write_text('{"obsolete":"ignored"}')
    response=c.post(f'/api/jobs/{id}/control',json={'action':'resume'})
    assert response.status_code==200,response.text
    assert store.claim(id);execute(str(store.project),id)
    done=store.get(id);assert done['state']=='completed',done['error']
    rich=json.loads((store.job_directory(id)/'project/publication/rich-source.json').read_text())
    assert rich['metadata']['pdf_source']['proofread'] is False
    assert rich['metadata']['pdf_source']['proofreading']['uncertainty_count']==1
    assert len(calls)==1


def test_manual_review_routes_are_removed(vision_web):
    c,store,_,_=vision_web
    id=c.post('/api/jobs',json=review_spec(c)).json()['id']
    for method in ('get','post','patch'):
        response=getattr(c,method)(f'/api/jobs/{id}/ocr-review')
        assert response.status_code in (404,405)
    assert c.get(f'/api/jobs/{id}/ocr-review/pages/1').status_code==404


def test_readonly_notices_available_after_automatic_delivery(vision_web):
    c,store,calls,value=vision_web
    value['uncertainties']=[{'excerpt':'example','reason':'Unclear transcription'}]
    id=c.post('/api/jobs',json=review_spec(c)).json()['id']
    store.claim(id);execute(str(store.project),id)
    before=store.get(id)
    response=c.get(f'/api/jobs/{id}/ocr-notices')
    assert response.status_code==200,response.text
    assert response.json()['raw_count']==1
    assert response.json()['items'][0]['excerpt']=='example'
    assert store.get(id)==before and len(calls)==1


@pytest.mark.parametrize("effort", ["high", "low", None])
def test_web_ocr_forwards_saved_reasoning_effort(vision_web, monkeypatch, effort):
    from alc_ocr_proofread import pdf_bundle

    c, store, calls, value = vision_web
    selections = []
    original = pdf_bundle.ModelSelection

    def capture(*args, **kwargs):
        selection = original(*args, **kwargs)
        selections.append(selection)
        return selection

    monkeypatch.setattr(pdf_bundle, "ModelSelection", capture)
    spec = review_spec(c)
    spec["reasoning_effort"] = effort
    if effort is None:
        monkeypatch.setattr("alc_web.app.resolve_profile", lambda *args: {
            "id": "codex", "protocol": "cli", "default_model": "test-vision",
            "models": [{"id": "test-vision", "default_reasoning_effort": "medium",
                        "reasoning_efforts": ["medium"]}],
        })
    expected = effort or "medium"
    response = c.post("/api/jobs", json=spec)
    assert response.status_code == 201, response.text
    job_id = response.json()["id"]
    assert store.get(job_id)["spec"]["reasoning_effort"] == expected
    assert store.claim(job_id)
    execute(str(store.project), job_id)
    assert store.get(job_id)["state"] == "completed", store.get(job_id)["error"]
    assert len(selections) >= 2
    assert all(selection.reasoning_effort == expected for selection in selections)

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from ac_document import RenderedPDFPage, import_mineru_bundle, verify_pdf_source_bundle
from ac_document.parse import PDFTextLayer
from ac_jobs import CorruptStateError, ResumeReason, RunStatus, canonical_json_bytes
from ac_llm import LLMCompleted, LLMExecutionOptions, LLMExecutionProfile, LLMPaused
from alc_ocr_proofread.pdf_bundle import (
    PDFBundleProofreadError,
    PDFBundleProofreadService,
    _apply_edit,
    candidate_digest,
)

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII="
)


def _record(name, payload):
    return {
        "path": name,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size": len(payload),
    }


def bundle(tmp_path: Path, *, pages=None, statuses=None):
    pages = pages or [
        '<p id="p1">Helo Helo &amp; welcome <math alttext="x=I"></math>.</p>',
        '<figure id="p2"><img src="assets/figure.png" alt="Dagram"><figcaption>Caption</figcaption></figure>',
    ]
    root = tmp_path / "bundle"
    root.mkdir(parents=True)
    source = (
        "<!doctype html><html><head><title>Book</title></head><body><article>\n"
        + "\n".join(pages)
        + "\n</article></body></html>\n"
    ).encode()
    files = {
        "original.pdf": b"%PDF-1.4\nsynthetic test PDF\n",
        "source.html": source,
        "evidence.json": b"{}\n",
    }
    if b"assets/figure.png" in source:
        files["assets/figure.png"] = PNG
    manifest = {
        "schema_version": "ac.document.pdf_source_bundle.v1",
        "provider": {"name": "mineru", "version": "3.4.5", "backend": "pipeline"},
        "original": _record("original.pdf", files["original.pdf"]),
        "source": _record("source.html", source),
        "evidence": [_record("evidence.json", files["evidence.json"])],
        "resources": [
            {
                **_record("assets/figure.png", PNG),
                "media_type": "image/png",
                "rendered": True,
                "original_paths": ["figure.png"],
            }
        ]
        if "assets/figure.png" in files
        else [],
        "pages": [
            {
                "page_number": i + 1,
                "size": [595, 842],
                "status": (statuses or ["parsed"] * len(pages))[i],
                "expected_entries": 2 if statuses and statuses[i] == "partial" else 1,
            }
            for i in range(len(pages))
        ],
        "entries": [
            {
                "ordinal": i,
                "page_number": i + 1,
                "kind": "text",
                "bbox": None,
                "status": "included",
                "source_ids": [f"p{i + 1}"],
            }
            for i in range(len(pages))
        ],
        "warnings": [],
    }
    manifest["bundle_digest"] = hashlib.sha256(
        canonical_json_bytes(manifest) + b"\n"
    ).hexdigest()
    files["manifest.json"] = canonical_json_bytes(manifest) + b"\n"
    for name, payload in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    verify_pdf_source_bundle(root / "manifest.json")
    return root / "manifest.json"


def edit(before, after, *, target="text", occurrence=1):
    return {
        "target": target,
        "before": before,
        "after": after,
        "occurrence": occurrence,
        "reason": "The page image shows this transcription.",
    }


def page_output(*edits, uncertainties=None, checks=None):
    return {
        "edits": list(edits),
        "uncertainties": [{**u, "kind": issue_kind(u)} for u in (uncertainties or [])],
        "checks": checks
        or {
            "all_visible_text": True,
            "all_visible_math": True,
            "structure_complete": True,
        },
    }


class Renderer:
    def __init__(self):
        self.calls = []

    def render_page(self, pdf, page_number):
        assert pdf.startswith(b"%PDF-")
        self.calls.append(page_number)
        return RenderedPDFPage(page_number, PNG, 1, 1)


class Tasks:
    def __init__(self, values):
        self.values = values
        self.requests = []
        self.options = []
        self.inputs = []

    def execute_or_resume(self, context, request, *, options, input=None):
        self.requests.append(request)
        self.options.append(options)
        self.inputs.append(input)
        page_number = int(request.task_id.rsplit("-", 1)[1])
        value = self.values[page_number]
        if isinstance(value, LLMPaused):
            if value.input_required:
                value = replace(
                    value,
                    request_ref=context.artifacts.publish_json(
                        f"test/provider-request-{page_number}",
                        {"page_number": page_number},
                    ),
                    response_contract="ac.llm.resume_input.v3",
                )
            return value
        if isinstance(value, Exception):
            raise value
        assert len(request.inputs) == 1
        assert request.inputs[0].media_type == "image/png"
        return LLMCompleted(value, "test-vision", "test-model", None, None)


def run(tmp_path, manifest, tasks, *, renderer=None, options=None):
    service = PDFBundleProofreadService(tmp_path / "project")
    prepared = service.prepare(
        manifest, provider="test-vision", model="test-model", workers=1
    )
    snapshot = service.execute(
        prepared.run_id,
        task_service=tasks,
        renderer=renderer or Renderer(),
        options=options,
    )
    assert snapshot.status is RunStatus.SUCCEEDED, snapshot.error
    return service, snapshot, service.result(snapshot.run_id)


def test_native_candidate_preserves_source_assets_and_requires_review(tmp_path):
    manifest = bundle(tmp_path)
    original = (manifest.parent / "source.html").read_bytes()
    tasks = Tasks(
        {
            1: page_output(
                edit("Helo", "Hello", occurrence=2),
                edit("x=I", "x=1", target="math_alttext"),
            ),
            2: page_output(edit("Dagram", "Diagram", target="image_alt")),
        }
    )
    renderer = Renderer()
    service, snapshot, result = run(
        tmp_path,
        manifest,
        tasks,
        renderer=renderer,
        options=LLMExecutionOptions(
            profile=LLMExecutionProfile.LOCAL_APP, internet=True
        ),
    )
    assert result["status"] == "reviewable"
    assert result["proofread"] is False
    assert result["approval_required"] is True
    assert result["change_count"] == 3
    assert result["uncertainty_count"] == 0
    assert result["candidate_digest"] == candidate_digest(result)
    assert result["original_html"].encode() == original
    assert (manifest.parent / "source.html").read_bytes() == original
    assert "Helo Hello &amp; welcome" in result["corrected_html"]
    assert 'alttext="x=1"' in result["corrected_html"]
    assert 'src="assets/figure.png" alt="Diagram"' in result["corrected_html"]
    assert "$x=I$" in result["pages"][0]["original_text"]
    assert "$x=1$" in result["pages"][0]["corrected_text"]
    assert result["pages"][0]["provider"] == "test-vision"
    assert service.page_image(snapshot.run_id, 1) == PNG
    assert all(
        o.profile is LLMExecutionProfile.LOCAL_APP and not o.internet
        for o in tasks.options
    )
    assert "Never fix source-book mistakes" in tasks.requests[0].prompt
    assert "assets/figure.png" not in tasks.requests[0].prompt
    assert len(tasks.requests) == 2
    service.execute(snapshot.run_id, task_service=tasks, renderer=renderer)
    assert len(tasks.requests) == 2
    assert renderer.calls == [1, 2]
    assert service.result(snapshot.run_id) == result


def test_unsafe_edits_become_uncertainties_without_losing_valid_pages(tmp_path):
    manifest = bundle(tmp_path)
    tasks = Tasks(
        {
            1: page_output(
                edit("Helo", "Hello"),
                edit('<p id="p1">', '<p id="changed">'),
                edit("welcome x=I", "welcome x=1"),
            ),
            2: page_output(
                edit("Caption", "Correct caption"),
                edit("assets/figure.png", "remote.png"),
            ),
        }
    )
    _, _, result = run(tmp_path, manifest, tasks)
    assert result["change_count"] == 2
    assert result["uncertainty_count"] == 0
    assert result["diagnostic_count"] == 3
    assert 'id="p1"' in result["corrected_html"]
    assert 'src="assets/figure.png"' in result["corrected_html"]
    assert "Correct caption" in result["corrected_html"]
    assert all(not u["resolved"] for p in result["pages"] for u in p["uncertainties"])


def test_literal_markup_is_escaped_and_occurrences_are_page_scoped(tmp_path):
    manifest = bundle(
        tmp_path,
        pages=[
            '<p id="p1">Helo <em>Helo</em> Helo &amp; world</p>',
            '<p id="p2">Helo</p>',
        ],
    )
    tasks = Tasks(
        {
            1: page_output(
                edit("Helo", "<script>bad()</script>", occurrence=2),
                edit("& world", "& <world>"),
            ),
            2: page_output(),
        }
    )
    _, _, result = run(tmp_path, manifest, tasks)
    assert result["change_count"] == 2
    assert result["uncertainty_count"] == 0
    assert "<em>&lt;script&gt;bad()&lt;/script&gt;</em>" in result["corrected_html"]
    assert "&amp; &lt;world&gt;" in result["corrected_html"]
    assert '<p id="p2">Helo</p>' in result["corrected_html"]


def test_missing_structure_and_partial_coverage_block_approval(tmp_path):
    manifest = bundle(
        tmp_path,
        pages=['<p id="p1">Helo</p>', '<p id="p2">Other</p>'],
        statuses=["partial", "parsed"],
    )
    tasks = Tasks(
        {
            1: page_output(edit("Helo", "Hello")),
            2: page_output(
                uncertainties=[
                    {"excerpt": "", "reason": "An entire formula is missing."}
                ],
                checks={
                    "all_visible_text": True,
                    "all_visible_math": False,
                    "structure_complete": False,
                },
            ),
        }
    )
    _, _, result = run(tmp_path, manifest, tasks)
    assert result["change_count"] == 1
    assert result["uncertainty_count"] == 0
    assert result["diagnostic_count"] == 4
    assert result["proofread"] is False


def test_invalid_model_response_is_visible_unresolved_review_material(tmp_path):
    manifest = bundle(tmp_path)
    _, _, result = run(
        tmp_path,
        manifest,
        Tasks({1: {"html": "replace entire page"}, 2: page_output()}),
    )
    assert result["uncertainty_count"] == 0
    assert result["diagnostic_count"] == 1
    assert result["change_count"] == 0
    assert result["original_html"] == result["corrected_html"]


def test_resume_reuses_successful_pages_and_full_page_images(tmp_path):
    manifest = bundle(tmp_path)
    service = PDFBundleProofreadService(tmp_path / "project")
    prepared = service.prepare(manifest, workers=1)
    tasks = Tasks(
        {
            1: page_output(edit("Helo", "Hello")),
            2: LLMPaused(ResumeReason.EXECUTION_INTERRUPTED, "test-retry"),
        }
    )
    renderer = Renderer()
    paused = service.execute(prepared.run_id, task_service=tasks, renderer=renderer)
    assert paused.status is RunStatus.PAUSED, paused.error
    assert len(tasks.requests) == 2
    with pytest.raises(PDFBundleProofreadError, match="not ready"):
        service.result(prepared.run_id)
    tasks.values[2] = page_output()
    complete = service.resume(prepared.run_id, task_service=tasks, renderer=renderer)
    assert complete.status is RunStatus.SUCCEEDED, complete.error
    assert [r.task_id for r in tasks.requests].count("pdf-proofread-page-000001") == 1
    assert renderer.calls == [1, 2]
    assert service.result(prepared.run_id)["change_count"] == 1


def test_input_hash_binding_prevents_changed_source_reuse(tmp_path):
    manifest = bundle(tmp_path)
    service = PDFBundleProofreadService(tmp_path / "project")
    prepared = service.prepare(manifest, workers=1)
    manifest.write_bytes(manifest.read_bytes() + b"\n")
    tasks = Tasks({1: page_output(), 2: page_output()})
    snapshot = service.execute(prepared.run_id, task_service=tasks, renderer=Renderer())
    assert snapshot.status is RunStatus.FAILED
    assert snapshot.error.code == "source_changed"
    assert tasks.requests == []


def test_parser_rejection_retains_every_safe_edit(tmp_path, monkeypatch):
    manifest = bundle(tmp_path)
    original = PDFBundleProofreadService._validate_corrected

    def validate(self, source, *args):
        if "Reject this" in source:
            raise ValueError("Synthetic rich-document parser rejection")
        return original(self, source, *args)

    monkeypatch.setattr(PDFBundleProofreadService, "_validate_corrected", validate)
    _, _, result = run(
        tmp_path,
        manifest,
        Tasks(
            {
                1: page_output(edit("Helo", "Hello"), edit("welcome", "Reject this")),
                2: page_output(edit("Caption", "Accepted caption")),
            }
        ),
    )
    assert result["change_count"] == 2
    assert result["uncertainty_count"] == 0
    assert result["diagnostic_count"] == 1
    assert "Reject this" not in result["corrected_html"]
    assert "Hello" in result["corrected_html"]
    assert "Accepted caption" in result["corrected_html"]


def test_exceptions_do_not_persist_provider_secret_payloads(tmp_path):
    manifest = bundle(tmp_path)
    service = PDFBundleProofreadService(tmp_path / "project")
    prepared = service.prepare(manifest, workers=1)
    secret = "synthetic-sensitive-image-token-never-log"
    snapshot = service.execute(
        prepared.run_id,
        task_service=Tasks({1: RuntimeError(secret), 2: page_output()}),
        renderer=Renderer(),
    )
    assert snapshot.status is RunStatus.FAILED
    for path in service.repository.run_directory(prepared.run_id).rglob("*.json"):
        assert secret not in path.read_text()


def test_empty_or_cross_node_edits_cannot_remove_anchored_content():
    manifest = {"entries": [{"page_number": 1, "source_ids": ["p1"]}]}
    source = '<p id="p1">First <em>second</em></p>'
    for proposal in (
        edit("First ", ""),
        edit("First second", "Changed"),
        edit("", "New content"),
    ):
        with pytest.raises(PDFBundleProofreadError):
            _apply_edit(source, manifest, 1, proposal)


def test_math_variable_edit_cannot_corrupt_latex_command():
    manifest = {"entries": [{"page_number": 1, "source_ids": ["p1"]}]}
    source = r'<p id="p1"><math alttext="100 \times 100"></math> outside <math alttext="s"></math></p>'
    proposal = {"target": "math_alttext", "before": "s", "after": "S", "occurrence": 1}
    with pytest.raises(PDFBundleProofreadError) as exc:
        _apply_edit(source, manifest, 1, proposal)
    assert exc.value.code == "edit_math_command_boundary"
    # Do not silently shift occurrence 1 to a different match.
    corrected = _apply_edit(source, manifest, 1, {**proposal, "occurrence": 2})
    assert r'100 \times 100' in corrected
    assert 'alttext="S"' in corrected


@pytest.mark.parametrize("before", ["times", "time", "mes", "\\tim"])
def test_partial_latex_commands_are_rejected(before):
    manifest = {"entries": [{"page_number": 1, "source_ids": ["p1"]}]}
    source = r'<p id="p1"><math alttext="a \times b"></math></p>'
    with pytest.raises(PDFBundleProofreadError):
        _apply_edit(source, manifest, 1, {"target": "math_alttext", "before": before, "after": "S", "occurrence": 1})
    corrected = _apply_edit(source, manifest, 1, {"target": "math_alttext", "before": r"\times", "after": r"\cdot", "occurrence": 1})
    assert r'\cdot' in corrected


def test_page_image_revalidates_immutable_artifact(tmp_path):
    manifest = bundle(tmp_path)
    service, snapshot, _ = run(
        tmp_path, manifest, Tasks({1: page_output(), 2: page_output()})
    )
    store = service._artifacts(snapshot.run_id)
    image_ref = store.find("page-images/000001")
    payloads = list((store.artifact_root / "objects").rglob("*"))
    image_path = next(p for p in payloads if p.is_file() and p.read_bytes() == PNG)
    image_path.write_bytes(b"corrupt")
    with pytest.raises(CorruptStateError):
        service.page_image(snapshot.run_id, 1)
    assert image_ref is not None


def test_provider_model_are_bound_in_run_identity(tmp_path):
    manifest = bundle(tmp_path)
    service = PDFBundleProofreadService(tmp_path / "project")
    a = service.prepare(manifest, provider="test", model="vision-a", workers=1)
    b = service.prepare(manifest, provider="test", model="vision-b", workers=1)
    assert a.run_id != b.run_id
    assert (
        service.prepare(manifest, provider="test", model="vision-a", workers=1).run_id
        == a.run_id
    )


def test_actual_mineru_html_list_table_equation_and_page_anchors(tmp_path):
    root = tmp_path / "mineru"
    root.mkdir()
    (root / "original.pdf").write_bytes(b"%PDF-1.4\nfixture\n")
    items = [
        {"type": "text", "text": "Intro with $a=I$.", "page_idx": 0},
        {
            "type": "table",
            "table_body": "<table><tr><th>Term</th><th>Value</th></tr><tr><td>Helo</td><td>1</td></tr></table>",
            "page_idx": 0,
        },
        {"type": "list", "list_items": ["First Helo", "Second Helo"], "page_idx": 1},
        {"type": "equation", "text": "$$E=mc^I$$", "page_idx": 1},
    ]
    content = root / "content_list.json"
    content.write_text(json.dumps(items))
    middle = root / "middle.json"
    middle.write_text(
        json.dumps(
            {
                "_backend": "pipeline",
                "_version_name": "3.4.5",
                "pdf_info": [
                    {
                        "page_idx": i,
                        "page_size": [595, 842],
                        "discarded_blocks": [],
                        "para_blocks": [
                            {"type": item["type"], "text": "content"}
                            for item in items
                            if item["page_idx"] == i
                        ],
                    }
                    for i in range(3)
                ],
            }
        )
    )

    class Pages:
        def extract(self, _payload):
            return PDFTextLayer(("", "", ""))

    imported = import_mineru_bundle(
        root / "original.pdf",
        content_list=content,
        middle_json=middle,
        output_dir=tmp_path / "imported",
        pdf_text_extractor=Pages(),
    )
    tasks = Tasks(
        {
            1: page_output(
                edit("a=I", "a=1", target="math_alttext"), edit("Helo", "Hello")
            ),
            2: page_output(
                edit("Helo", "Hello", occurrence=2),
                edit("E=mc^I", "E=mc^2", target="math_alttext"),
            ),
            3: page_output(),
        }
    )
    _, _, result = run(tmp_path, Path(imported["manifest"]), tasks)
    assert result["change_count"] == 4
    assert result["uncertainty_count"] == 0
    assert "<table" in result["corrected_html"]
    assert "<ul>" in result["corrected_html"]
    assert "First Helo" in result["pages"][1]["corrected_text"]
    assert "Second Hello" in result["pages"][1]["corrected_text"]
    assert "$E=mc^2$" in result["pages"][1]["corrected_text"]
    assert len(result["pages"]) == 3
    assert result["pages"][2]["original_html"] == ""


def test_hidden_text_comments_and_resource_attributes_are_not_editable():
    manifest = {"entries": [{"page_number": 1, "source_ids": ["p1"]}]}
    source = (
        '<p id="p1">Visible<!-- comment -->'
        '<span hidden>Hidden</span><span style="display: none">Styled</span>'
        '<img src="secret.png" alt="Label"></p>'
    )
    for before in ("comment", "Hidden", "Styled", "secret.png", "p1"):
        with pytest.raises(PDFBundleProofreadError):
            _apply_edit(source, manifest, 1, edit(before, "Changed"))
    corrected = _apply_edit(
        source, manifest, 1, edit("Label", 'A "quoted" label', target="image_alt")
    )
    assert 'alt="A &quot;quoted&quot; label"' in corrected


def test_large_page_is_included_completely_without_silent_truncation(tmp_path):
    text = "Start " + "whole page text " * 5000 + " UNIQUE_LAST_WORD"
    manifest = bundle(tmp_path, pages=[f'<p id="p1">{text}</p>'])
    tasks = Tasks({1: page_output(edit("UNIQUE_LAST_WORD", "Correct ending"))})
    _, _, result = run(tmp_path, manifest, tasks)
    assert text in tasks.requests[0].prompt
    assert result["pages"][0]["original_text"] == text
    assert result["pages"][0]["corrected_text"].endswith("Correct ending")
    assert result["uncertainty_count"] == 0


def test_required_provider_resume_input_is_only_sent_to_its_page(tmp_path):
    manifest = bundle(tmp_path)
    service = PDFBundleProofreadService(tmp_path / "project")
    prepared = service.prepare(manifest, workers=1)
    tasks = Tasks(
        {
            1: page_output(),
            2: LLMPaused(
                ResumeReason.SUPERVISION_REQUIRED, "test-input-key", input_required=True
            ),
        }
    )
    paused = service.execute(prepared.run_id, task_service=tasks, renderer=Renderer())
    assert paused.status is RunStatus.PAUSED
    assert paused.awaiting.details["page_number"] == 2
    tasks.values[2] = page_output()
    complete = service.resume(
        prepared.run_id,
        task_service=tasks,
        renderer=Renderer(),
        input={
            "schema_version": "ac.llm.resume_input.v3",
            "resume_key": "test-input-key",
            "action": "continue",
            "host_response": None,
            "candidate_digest": None,
            "reason": None,
        },
    )
    assert complete.status is RunStatus.SUCCEEDED, complete.error
    assert tasks.inputs[:2] == [None, None]
    assert tasks.inputs[2].resume_key == "test-input-key"


def test_execute_and_resume_forward_usage_events_without_replaying_pages(tmp_path):
    manifest = bundle(tmp_path)
    service = PDFBundleProofreadService(tmp_path / "project")
    prepared = service.prepare(manifest, workers=1)

    class UsageTasks(Tasks):
        def execute_or_resume(self, context, request, **kwargs):
            result = super().execute_or_resume(context, request, **kwargs)
            if isinstance(result, LLMCompleted):
                context.events.emit(
                    "llm_usage", {"task_id": request.task_id, "total_tokens": 17}
                )
            return result

    tasks = UsageTasks(
        {
            1: page_output(),
            2: LLMPaused(ResumeReason.EXECUTION_INTERRUPTED, "retry-usage"),
        }
    )
    first_events, resumed_events = [], []
    paused = service.execute(
        prepared.run_id,
        task_service=tasks,
        renderer=Renderer(),
        event_sink=first_events.append,
    )
    assert paused.status is RunStatus.PAUSED
    tasks.values[2] = page_output()
    complete = service.resume(
        prepared.run_id,
        task_service=tasks,
        renderer=Renderer(),
        event_sink=resumed_events.append,
    )
    assert complete.status is RunStatus.SUCCEEDED
    first_usage = [
        event["data"] for event in first_events if event["event"] == "llm_usage"
    ]
    resumed_usage = [
        event["data"] for event in resumed_events if event["event"] == "llm_usage"
    ]
    assert first_usage == [{"task_id": "pdf-proofread-page-000001", "total_tokens": 17}]
    assert resumed_usage == [
        {"task_id": "pdf-proofread-page-000002", "total_tokens": 17}
    ]


import copy

from ac_document import PDFSourceBundleError
from alc_ocr_proofread.cli import main
from alc_ocr_proofread.pdf_bundle_delivery import approve_pdf_candidate
from alc_ocr_proofread.review_policy import issue_kind


def candidate(tmp_path):
    manifest = bundle(tmp_path)
    service, snapshot, result = run(
        tmp_path,
        manifest,
        Tasks({1: page_output(edit("Helo", "Hello")), 2: page_output()}),
    )
    return manifest, service, snapshot, result


@pytest.mark.parametrize(
    "mutation", ["missing_page", "uncertainty", "stale", "unconfirmed"]
)
def test_approval_rejects_incomplete_candidates(tmp_path, mutation):
    manifest, _, _, value = candidate(tmp_path)
    value = copy.deepcopy(value)
    if mutation == "missing_page":
        value["pages"].pop()
    if mutation == "uncertainty":
        value["pages"][0]["uncertainties"].append({"reason": "unreadable"})
    value["candidate_digest"] = candidate_digest(value)
    digest = "0" * 64 if mutation == "stale" else value["candidate_digest"]
    with pytest.raises(PDFSourceBundleError):
        approve_pdf_candidate(
            manifest,
            value,
            candidate_digest=digest,
            confirm_reviewed=mutation != "unconfirmed",
            output_dir=tmp_path / "reviewed",
        )
    assert not (tmp_path / "reviewed").exists()


def test_cli_candidate_query_and_explicit_approval(tmp_path, capsys):
    manifest, service, snapshot, value = candidate(tmp_path)
    common = ["--project-dir", str(service.project_dir), "--run-id", snapshot.run_id]
    assert main(["get-result-bundle", *common]) == 0
    assert (
        json.loads(capsys.readouterr().out)["data"]["candidate"]["proofread"] is False
    )
    approve = [
        "approve-bundle",
        *common,
        "--manifest",
        str(manifest),
        "--candidate-digest",
        value["candidate_digest"],
        "--output-dir",
        str(tmp_path / "reviewed"),
    ]
    assert main(approve) == 1
    capsys.readouterr()
    assert main([*approve, "--confirm-reviewed"]) == 0
    payload = json.loads(capsys.readouterr().out)
    verified = verify_pdf_source_bundle(payload["data"]["manifest"])
    assert verified["proofreading"]["candidate_digest"] == value["candidate_digest"]


def test_noop_instruction_repaired_once_and_applied(tmp_path):
    class RepairTasks(Tasks):
        def execute_or_resume(self, context, request, **kwargs):
            self.requests.append(request)
            if "repair" in request.task_id:
                return LLMCompleted(
                    page_output(edit("Helo", "Hello")), "test", "vision", None, None
                )
            return LLMCompleted(
                page_output(edit("Helo", "Helo"))
                if request.task_id.endswith("000001")
                else page_output(),
                "test",
                "vision",
                None,
                None,
            )

    tasks = RepairTasks({})
    _, _, result = run(tmp_path, bundle(tmp_path), tasks)
    assert "Hello Helo" in result["corrected_html"]
    assert result["change_count"] == 1 and result["uncertainty_count"] == 0
    assert len([r for r in tasks.requests if "repair" in r.task_id]) == 1
    assert result["review_policy_version"] == "ocr-triage.v2"


def test_policy_keeps_genuine_ambiguity_but_discards_nonessential_layout(tmp_path):
    tasks = Tasks(
        {
            1: page_output(
                edit("Helo", "Hello"),
                uncertainties=[
                    {
                        "excerpt": "Helo",
                        "reason": "Could read Helo or Hello; scan is blurred.",
                        "kind": "ambiguous",
                    },
                    {
                        "excerpt": "1",
                        "reason": "Decorative page number absent",
                        "kind": "irrelevant",
                    },
                ],
            ),
            2: page_output(),
        }
    )
    _, _, result = run(tmp_path, bundle(tmp_path), tasks)
    assert result["change_count"] == 0
    assert result["uncertainty_count"] == 1
    assert result["pages"][0]["uncertainties"][0]["excerpt"] == "Helo"


def test_legacy_policy_is_not_reinterpreted_on_resume(tmp_path):
    from ac_jobs import RunSpec

    service = PDFBundleProofreadService(tmp_path / "project")
    prepared = service.prepare(
        bundle(tmp_path, statuses=["partial", "parsed"]), workers=1
    )
    spec = service.repository.read_spec(prepared.run_id)
    old = {k: v for k, v in spec.semantic_input.items() if k != "review_policy_version"}
    legacy = service.repository.create(RunSpec("legacy-policy-run", spec.handler, old))
    completed = service.execute(
        legacy.run_id,
        task_service=Tasks({1: page_output(), 2: page_output()}),
        renderer=Renderer(),
    )
    assert completed.status is RunStatus.SUCCEEDED, completed.error
    assert service.result(legacy.run_id)["uncertainty_count"] == 1
    assert "review_policy_version" not in service.result(legacy.run_id)


def test_noop_repair_paused_input_is_routed_to_repair_only(tmp_path):
    class RepairTasks(Tasks):
        def __init__(self):
            super().__init__({})
            self.inputs = []

        def execute_or_resume(self, context, request, **kwargs):
            self.inputs.append((request.task_id, kwargs.get("input")))
            if "repair" in request.task_id:
                if kwargs.get("input") is None:
                    ref = context.artifacts.publish_json(
                        "repair-request", {"page_number": 1}
                    )
                    return LLMPaused(
                        ResumeReason.SUPERVISION_REQUIRED,
                        "repair-key",
                        input_required=True,
                        request_ref=ref,
                        response_contract="ac.llm.resume_input.v3",
                    )
                return LLMCompleted(
                    page_output(edit("Helo", "Hello")), "test", "vision", None, None
                )
            assert kwargs.get("input") is None
            return LLMCompleted(
                page_output(edit("Helo", "Helo"))
                if request.task_id.endswith("000001")
                else page_output(),
                "test",
                "vision",
                None,
                None,
            )

    service = PDFBundleProofreadService(tmp_path / "project")
    prepared = service.prepare(bundle(tmp_path), workers=1)
    tasks = RepairTasks()
    paused = service.execute(prepared.run_id, task_service=tasks, renderer=Renderer())
    assert paused.status is RunStatus.PAUSED
    complete = service.resume(
        prepared.run_id,
        task_service=tasks,
        renderer=Renderer(),
        input={
            "schema_version": "ac.llm.resume_input.v3",
            "resume_key": "repair-key",
            "action": "continue",
            "host_response": None,
            "candidate_digest": None,
            "reason": None,
        },
    )
    assert complete.status is RunStatus.SUCCEEDED, complete.error
    assert "Hello Helo" in service.result(prepared.run_id)["corrected_html"]
    assert all("repair" in key for key, value in tasks.inputs if value is not None)


def test_reasoning_effort_is_frozen_and_used_on_every_page(tmp_path):
    manifest = bundle(tmp_path)
    service = PDFBundleProofreadService(tmp_path / "project")
    default = service.prepare(manifest, workers=1)
    explicit_default = service.prepare(manifest, workers=1, reasoning_effort=None)
    high = service.prepare(manifest, workers=1, reasoning_effort="high")
    low = service.prepare(manifest, workers=1, reasoning_effort="low")
    assert default.run_id == explicit_default.run_id
    assert len({default.run_id, high.run_id, low.run_id}) == 3
    assert "reasoning_effort" not in service.repository.read_spec(default.run_id).semantic_input
    assert service.repository.read_spec(high.run_id).semantic_input["reasoning_effort"] == "high"
    for snapshot, expected in ((high, "high"), (default, None)):
        tasks = Tasks({1: page_output(), 2: page_output()})
        done = service.execute(snapshot.run_id, task_service=tasks, renderer=Renderer())
        assert done.status is RunStatus.SUCCEEDED, done.error
        assert len(tasks.requests) == 2
        assert all(request.model.reasoning_effort == expected for request in tasks.requests)


def test_bundle_cli_reasoning_effort_reaches_page_requests(tmp_path, monkeypatch, capsys):
    from alc_ocr_proofread import cli, pdf_bundle_cli

    manifest = bundle(tmp_path)
    service = PDFBundleProofreadService(tmp_path / "project")
    tasks = Tasks({1: page_output(), 2: page_output()})
    original_execute = service.execute
    monkeypatch.setattr(pdf_bundle_cli, "PDFBundleProofreadService", lambda path: service)
    monkeypatch.setattr(service, "execute", lambda run_id: original_execute(
        run_id, task_service=tasks, renderer=Renderer()
    ))
    assert cli.main([
        "proofread-bundle", "--manifest", str(manifest),
        "--project-dir", str(tmp_path / "project"), "--provider", "test-vision",
        "--model", "test-model", "--workers", "1", "--reasoning-effort", "high",
    ]) == 0, capsys.readouterr().out
    assert len(tasks.requests) == 2
    assert all(request.model.reasoning_effort == "high" for request in tasks.requests)

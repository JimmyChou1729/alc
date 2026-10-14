"""Host coordination must use only the public CLI's task location."""
from __future__ import annotations

import json
from pathlib import Path

from ac_document import AcDocumentService, RichDocumentParserService, rich_document_to_document
from ac_llm import cli as llm_cli
from alc_render import cli as render_cli
from alc_translate import cli
from alc_translate.prompts import (
    GLOSSARY_PROMPT_VERSION,
    LANGUAGE_PROMPT_VERSION,
    REVIEW_PROMPT_VERSION,
    TEXT_SLOT_RESULT_SCHEMA,
    TEXT_SLOT_REVIEW_RESULT_SCHEMA,
    TRANSLATION_PROMPT_VERSION,
)


def _answer(prompt):
    contract = prompt.splitlines()[0].removeprefix("Contract: ")
    if contract == "ac.document.keyword_chapter_prompt.v3":
        return contract, {"entries": [{"term": "Entropy"}]}
    payload = json.loads(prompt.split("Input JSON:\n", 1)[1])
    if contract == LANGUAGE_PROMPT_VERSION:
        return contract, {"language_tag": "en", "classification": "known", "confidence": 0.99}
    if contract == GLOSSARY_PROMPT_VERSION:
        return contract, {"entries": [{
            "term_id": term["term_id"], "preferred_translation": "熵",
            "target_definition": "描述系统状态的物理量。",
        } for term in payload["terms"]]}
    if contract == REVIEW_PROMPT_VERSION:
        return contract, {"schema_version": TEXT_SLOT_REVIEW_RESULT_SCHEMA,
                          "translation_patches": {}, "summary": "公式与正文已检查。"}
    assert contract == TRANSLATION_PROMPT_VERSION
    chinese = {"Entropy": "熵", "Entropy satisfies ": "熵满足 ",
               " and is a physical quantity.": "，是一个物理量。"}
    translations = {}
    for block in payload["blocks"]:
        slots = {}
        for part in block["content"]["parts"]:
            for item in part["parts"] if part["kind"] == "link" else (part,):
                if item["kind"] == "text_slot":
                    slots[item["slot_id"]] = chinese[item["text"]]
        translations[block["block_id"]] = {"text_slots": slots}
    return contract, {"schema_version": TEXT_SLOT_RESULT_SCHEMA, "translations": translations}


def test_public_cli_host_translation_roundtrip(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AC_LLM_HOST_COORDINATOR", json.dumps({
        "coordinator_id": "cli-only-fixture", "default_provider": "host",
    }))
    source = tmp_path / "source.md"
    source.write_text("# Entropy\n\nEntropy satisfies $S=k_B \\log W$ and is a physical quantity.\n", encoding="utf-8")
    project = tmp_path / "project"
    cache = tmp_path / "document-cache"
    common = ["--project-dir", str(project)]
    execution = ["--host-authority", "unrestricted", "--document-cache-root", str(cache)]
    contracts = []
    task_ids = []

    def invoke(main, args, expected=None):
        code = main(args)
        result = json.loads(capsys.readouterr().out)
        if expected is not None:
            assert code == expected, result
        return result

    for command, extra in (
        ("detect-language", ["--target-language", "zh-CN"]),
        ("build-glossary", ["--approx-term-count", "1"]),
        ("translate-blocks", ["--review-rounds", "1"]),
    ):
        reply = invoke(cli.main, [command, str(source), *common, *execution, "--provider", "host", *extra], 1)
        owner_id = reply["run"]["id"]
        for _ in range(20):
            if reply["status"] == "completed":
                break
            details = reply["resume"]["details"]
            assert details["code"] == "awaiting_host", reply
            assert details["run_id"] == owner_id
            location = ["--run-root", details["run_root"], "--run-id", details["run_id"]]
            assert Path(details["run_root"]).is_absolute()
            status = invoke(cli.main, ["status", *common], 0)
            assert status["data"]["run"]["resume"]["details"] == details
            step = status["data"]["current_step"]
            assert status["data"]["steps"][step]["resume"]["details"] == details
            # A repeated resume before submission keeps the exact pending task.
            repeated = invoke(cli.main, ["resume", *common, *execution], 1)
            assert repeated["resume"]["details"] == details
            exported = invoke(llm_cli.main, ["host-export", *location, "--task-id", details["host_task_id"]], 0)["data"]["task"]
            task_ids.append(exported["task_id"])
            contract, output = _answer(exported["request"]["task_prompt"])
            contracts.append(contract)
            response = tmp_path / "response.json"
            response.write_text(json.dumps({
                "schema_version": "ac.llm.host_response.v1", "task_id": exported["task_id"],
                "request_sha256": exported["request_sha256"],
                "actor": {"actor_id": "fixture", "kind": "fake", "context_id": exported["task_id"]},
                "output": output,
            }, ensure_ascii=False), encoding="utf-8")
            assert not invoke(llm_cli.main, ["host-submit", *location, "--response", str(response)], 0)["data"]["reused"]
            assert invoke(llm_cli.main, ["host-submit", *location, "--response", str(response)], 0)["data"]["reused"]
            reply = invoke(cli.main, ["resume", *common, *execution])
            assert reply["run"]["id"] == owner_id
        assert reply["status"] == "completed", reply
        assert invoke(cli.main, ["resume", *common, *execution], 0)["run"]["id"] == owner_id

    assert len(task_ids) == len(set(task_ids))
    assert {LANGUAGE_PROMPT_VERSION, GLOSSARY_PROMPT_VERSION, TRANSLATION_PROMPT_VERSION,
            REVIEW_PROMPT_VERSION, "ac.document.keyword_chapter_prompt.v3"} <= set(contracts)
    invoke(cli.main, ["validate", *common], 0)
    layer = project / "translation.layer.json"
    text = "\n".join((project / item["path"]).read_text(encoding="utf-8")
                     for item in json.loads(layer.read_text())["initial_revisions"])
    assert "熵满足" in text
    assert r"S=k_B \log W" in text
    paper = AcDocumentService(cache_root=cache)
    document = RichDocumentParserService(paper.repository).parse_source(paper.import_source(source))
    rich_source = project / "source.rich.json"
    rich_source.write_text(json.dumps(rich_document_to_document(document)), encoding="utf-8")
    publication, html = project / "publication.json", project / "reader.html"
    invoke(render_cli.main, ["compose", "--source", str(rich_source), "--layer", str(layer),
                            "--glossary", str(project / "translation.glossary.json"), "--output", str(publication)], 0)
    invoke(render_cli.main, ["render", "--publication", str(publication), "--html", str(html)], 0)
    invoke(render_cli.main, ["validate", "--publication", str(publication), "--html", str(html)], 0)
    assert "熵满足" in html.read_text(encoding="utf-8")


def test_legacy_pause_status_exposes_location_without_rewriting_state(
    tmp_path, monkeypatch, capsys,
):
    from dataclasses import replace
    from alc_translate import workflow

    monkeypatch.setenv("AC_LLM_HOST_COORDINATOR", json.dumps({
        "coordinator_id": "legacy-cli-fixture", "default_provider": "host",
    }))
    source = tmp_path / "source.md"
    source.write_text("# Entropy\n\nEntropy is a physical quantity.\n", encoding="utf-8")
    project = tmp_path / "project"
    args = ["--project-dir", str(project), "--host-authority", "unrestricted",
            "--document-cache-root", str(tmp_path / "cache")]
    original = workflow._awaiting

    def old_awaiting(outcome):
        awaiting = original(outcome)
        return replace(awaiting, details={key: value for key, value in awaiting.details.items()
                                           if key not in {"run_root", "run_id"}})

    with monkeypatch.context() as legacy:
        legacy.setattr(workflow, "_awaiting", old_awaiting)
        assert cli.main(["detect-language", str(source), "--target-language", "zh-CN",
                         "--provider", "host", *args]) == 1
        generated = json.loads(capsys.readouterr().out)
    before = {str(p): p.read_bytes() for p in project.rglob("*") if p.is_file()}
    assert cli.main(["status", "--project-dir", str(project)]) == 0
    status = json.loads(capsys.readouterr().out)
    after = {str(p): p.read_bytes() for p in project.rglob("*") if p.is_file()}
    assert after == before
    details = status["data"]["run"]["resume"]["details"]
    assert details == generated["resume"]["details"]
    assert details["run_id"] == generated["run"]["id"]
    location = ["--run-root", details["run_root"], "--run-id", details["run_id"]]
    assert llm_cli.main(["host-export", *location, "--task-id", details["host_task_id"]]) == 0
    task = json.loads(capsys.readouterr().out)["data"]["task"]
    _, output = _answer(task["request"]["task_prompt"])
    response = tmp_path / "legacy-response.json"
    response.write_text(json.dumps({
        "schema_version": "ac.llm.host_response.v1", "task_id": task["task_id"],
        "request_sha256": task["request_sha256"],
        "actor": {"actor_id": "fixture", "kind": "fake", "context_id": task["task_id"]},
        "output": output,
    }), encoding="utf-8")
    assert llm_cli.main(["host-submit", *location, "--response", str(response)]) == 0
    capsys.readouterr()
    assert cli.main(["resume", *args]) == 0
    resumed = json.loads(capsys.readouterr().out)
    assert resumed["run"]["id"] == generated["run"]["id"]

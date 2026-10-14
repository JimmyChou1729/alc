from __future__ import annotations

import json
from pathlib import Path

import pytest

from alc_ocr_proofread.cli import main
from alc_ocr_proofread.source import ProofreadSourceError, load_mineru_source


def test_missing_page_map_stops_before_project_creation(tmp_path: Path, capsys) -> None:
    markdown = tmp_path / "book.md"
    pdf = tmp_path / "book.pdf"
    project = tmp_path / "project"
    markdown.write_text("text", encoding="utf-8")
    pdf.write_bytes(b"pdf")

    code = main(
        [
            "proofread",
            str(markdown),
            "--pdf",
            str(pdf),
            "--content-list",
            str(tmp_path / "missing.json"),
            "--project-dir",
            str(project),
        ]
    )

    assert code == 1
    assert not project.exists()
    value = json.loads(capsys.readouterr().out)
    assert value["error"]["code"] == "page_map_missing"


def test_rejects_unsafe_asset_path(tmp_path: Path, monkeypatch) -> None:
    markdown = tmp_path / "book.md"
    pdf = tmp_path / "book.pdf"
    content = tmp_path / "book_content_list.json"
    markdown.write_text("text", encoding="utf-8")
    pdf.write_bytes(b"pdf")
    content.write_text(
        json.dumps([{"type": "image", "img_path": "../escape.png", "page_idx": 0}]),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "alc_ocr_proofread.source._pdf_page_count", lambda _path: 1
    )

    with pytest.raises(ProofreadSourceError, match="unsafe"):
        load_mineru_source(markdown, pdf, content)


def test_rejects_page_map_outside_pdf(tmp_path: Path, monkeypatch) -> None:
    markdown = tmp_path / "book.md"
    pdf = tmp_path / "book.pdf"
    content = tmp_path / "book_content_list.json"
    markdown.write_text("text", encoding="utf-8")
    pdf.write_bytes(b"pdf")
    content.write_text(
        json.dumps([{"type": "text", "text": "text", "page_idx": 1}]),
        encoding="utf-8",
    )
    monkeypatch.setattr("alc_ocr_proofread.source._pdf_page_count", lambda _path: 1)

    with pytest.raises(ProofreadSourceError, match="exceeds"):
        load_mineru_source(markdown, pdf, content)


@pytest.mark.parametrize("bundle", [False, True])
def test_host_pause_generation_and_status_keep_task_location(
    tmp_path, monkeypatch, bundle,
):
    from types import SimpleNamespace
    from ac_jobs import Awaiting, ResumeReason, RunSnapshot, RunStatus
    from alc_ocr_proofread import cli, pdf_bundle_cli
    from alc_ocr_proofread.project import ProofreadProject

    project = ProofreadProject.open(tmp_path / "project")
    project.select("legacy-host-run")
    snapshot = RunSnapshot(
        "legacy-host-run", 2, RunStatus.PAUSED, 1,
        "2026-09-01T00:00:00Z", "2026-09-01T00:01:00Z",
        awaiting=Awaiting(
            ResumeReason.EXTERNAL_CONDITION, "host:page", False,
            details={"code": "awaiting_host", "host_task_id": "page-task"},
        ),
    )
    service = SimpleNamespace(
        project=project, repository=SimpleNamespace(root=project.jobs_root),
        inspect=lambda _run_id: SimpleNamespace(snapshot=snapshot),
        resume=lambda *_args, **_kwargs: snapshot,
        metrics=lambda _run_id: {},
    )
    if bundle:
        monkeypatch.setattr(pdf_bundle_cli, "PDFBundleProofreadService", lambda _root: service)
        generated = pdf_bundle_cli.dispatch(SimpleNamespace(
            command="resume-bundle", project_dir=str(project.root),
            run_id=snapshot.run_id, input=None,
        ))
        status = pdf_bundle_cli.dispatch(SimpleNamespace(
            command="status-bundle", project_dir=str(project.root), run_id=snapshot.run_id,
        ))
    else:
        monkeypatch.setattr(cli, "ProofreadService", lambda _project: service)
        generated = cli._generation_result(service, snapshot)
        status = cli._dispatch(SimpleNamespace(command="status", project_dir=str(project.root)))
    expected = {"code": "awaiting_host", "host_task_id": "page-task",
                "run_root": str(project.jobs_root), "run_id": snapshot.run_id}
    assert generated.resume.details == expected
    assert status.data["run"]["resume"]["details"] == expected
    assert "run_root" not in snapshot.awaiting.details

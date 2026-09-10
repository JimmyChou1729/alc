"""Automatic adoption of source-bound model PDF proofreading."""

import json
from pathlib import Path

from ac_document import PDFSourceBundleError
from ac_jobs import (
    RunStatus,
    atomic_write_bytes,
    canonical_json_bytes,
    command_result_from_snapshot,
    command_result_json,
)
from alc_ocr_proofread.pdf_bundle_delivery import adopt_pdf_candidate


def _selection(store, job):
    from alc_ocr_proofread.pdf_bundle import PDFBundleProofreadService

    path = store.job_directory(job["id"]) / "ocr-proofread-selection.json"
    if not path.is_file():
        raise ValueError("No PDF proofreading run is available.")
    value = json.loads(path.read_text())
    manifest = (store.job_directory(job["id"]) / value["manifest"]).resolve()
    if not manifest.is_relative_to(store.job_directory(job["id"]).resolve()):
        raise ValueError("Invalid PDF proofreading source path.")
    return (
        PDFBundleProofreadService(store.job_directory(job["id"]) / "ocr-proofread"),
        value["run_id"],
        manifest,
    )


def resume_completed_ocr(store, job):
    """Resume legacy review pauses without editing or re-running the model."""
    from ac_jobs import file_lease
    from alc_ocr_proofread.pdf_bundle_edit import validate_candidate
    from .runtime import runtime_identity

    root = store.job_directory(job["id"])
    with file_lease(root / "worker.lock"):
        service, run_id, manifest = _selection(store, store.get(job["id"]))
        candidate = service.result(run_id)
        validate_candidate(manifest, candidate)
        atomic_write_bytes(
            root / "ocr-review-decision.json",
            canonical_json_bytes(
                {
                    "action": "model",
                    "candidate_digest": candidate["candidate_digest"],
                }
            ),
        )
        return store.resume_ocr_review(job["id"], runtime_identity())


def prepare_review(worker, source, manifest):
    from alc_ocr_proofread.pdf_bundle import PDFBundleProofreadService

    spec = worker.job["spec"]
    if spec.get("ocr_proofread_consent") is not True:
        raise PDFSourceBundleError(
            "pdf_review_consent", "PDF image proofreading requires explicit consent."
        )
    worker.phase("ocr_proofread")
    service = PDFBundleProofreadService(worker.root / "ocr-proofread")
    selection_path = worker.root / "ocr-proofread-selection.json"
    if selection_path.is_file():
        service, run_id, selected_manifest = _selection(worker.store, worker.job)
        if Path(manifest).resolve() != selected_manifest:
            raise ValueError("PDF proofreading source changed.")
        snapshot = service.inspect(run_id).snapshot
    else:
        snapshot = service.prepare(
            manifest,
            provider=spec["provider_id"],
            model=spec["model"],
            reasoning_effort=spec.get("reasoning_effort"),
            workers=min(worker.window_workers, 4),
            max_workers=4,
        )
    worker.active_owner = "ocr-proofread"
    worker.ocr_service, worker.ocr_run_id = service, snapshot.run_id
    atomic_write_bytes(
        worker.root / "ocr-proofread-selection.json",
        canonical_json_bytes(
            {
                "run_id": snapshot.run_id,
                "manifest": Path(manifest).relative_to(worker.root).as_posix(),
            }
        ),
    )
    if snapshot.status != RunStatus.SUCCEEDED:
        snapshot = (
            service.resume(
                snapshot.run_id,
                options=worker.options,
                input=worker.job.get("resume_input"),
                event_sink=worker.sink,
            )
            if snapshot.status in (RunStatus.PAUSED, RunStatus.FAILED)
            else service.execute(
                snapshot.run_id, options=worker.options, event_sink=worker.sink
            )
        )
    worker.checkpoint()
    if snapshot.status != RunStatus.SUCCEEDED:
        from .worker import PackagePaused

        raise PackagePaused(
            json.loads(command_result_json(command_result_from_snapshot(snapshot)))
        )
    candidate = service.result(snapshot.run_id)
    worker.detail["ocr_review"] = {
        k: candidate[k]
        for k in ("candidate_digest", "change_count", "uncertainty_count")
    }
    worker.store.update(worker.job_id, detail=worker.detail)
    atomic_write_bytes(
        worker.root / "ocr-review-decision.json",
        canonical_json_bytes(
            {
                "action": "model",
                "candidate_digest": candidate["candidate_digest"],
            }
        ),
    )
    revised = adopt_pdf_candidate(
        manifest,
        candidate,
        candidate_digest=candidate["candidate_digest"],
        output_dir=worker.root / "model-pdf-source",
        mode="model",
    )
    worker.detail["ocr_proofreading"] = "model"
    worker.store.update(worker.job_id, detail=worker.detail)
    warnings = []
    if candidate.get("execution_issue_count") or candidate.get("unapplied_edit_count"):
        warnings.append(
            "部分修订或结构补全未能安全应用，已保留原识别内容；这是执行限制，不是内容歧义。"
        )
    return (
        Path(revised["source"]),
        Path(revised["manifest"]),
        warnings
        + [
            f"模型校对已完成，保留 {candidate['uncertainty_count']} 项不确定提示，已自动继续。"
        ],
    )

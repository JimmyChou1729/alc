"""Admission policy for model-content pauses in independent learning units."""

from ac_jobs import Paused, ResumeReason


def is_local_content_pause(value: Paused) -> bool:
    awaiting = value.awaiting
    if awaiting.reason is not ResumeReason.SUPERVISION_REQUIRED:
        return False
    details = awaiting.details
    if details.get("automatic_retry_exhausted") is not True:
        return False
    code = details.get("code")
    if code == "proposer_reviewer_worker_paused":
        code = details.get("llm_code")
    if code in {"output_invalid", "output_formatting_failed"}:
        return True
    # Companion's semantic supervisor owns editable model candidates. Other
    # supervision/authority requests must still stop admission.
    return (
        awaiting.resume_key.startswith("semantic-retry-")
        and isinstance(details.get("candidate_paths"), (list, tuple))
        and bool(details["candidate_paths"])
    )

"""Native PDF candidate commands, separate from the Markdown workflow."""

from ac_jobs import (
    CommandResult,
    CommandStatus,
    command_result_from_snapshot,
    snapshot_data,
)

from .pdf_bundle import PDFBundleProofreadService
from .pdf_bundle_delivery import approve_pdf_candidate


def add_commands(commands):
    for name in (
        "proofread-bundle",
        "status-bundle",
        "resume-bundle",
        "stop-bundle",
        "get-result-bundle",
        "approve-bundle",
    ):
        parser = commands.add_parser(name)
        parser.add_argument("--project-dir", required=True)
        if name == "proofread-bundle":
            parser.add_argument("--manifest", required=True)
            parser.add_argument("--provider", default="auto")
            parser.add_argument("--model")
            parser.add_argument("--reasoning-effort")
            parser.add_argument("--workers", type=int, default=4)
        else:
            parser.add_argument("--run-id", required=True)
        if name == "resume-bundle":
            parser.add_argument("--input")
        if name == "stop-bundle":
            parser.add_argument("--reason")
        if name == "approve-bundle":
            parser.add_argument("--manifest", required=True)
            parser.add_argument("--candidate-digest", required=True)
            parser.add_argument("--confirm-reviewed", action="store_true")
            parser.add_argument("--output-dir", required=True)


def dispatch(args):
    service = PDFBundleProofreadService(args.project_dir)
    if args.command == "proofread-bundle":
        snapshot = service.prepare(
            args.manifest,
            provider=args.provider,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            workers=args.workers,
        )
        snapshot = service.execute(snapshot.run_id)
    elif args.command == "resume-bundle":
        from .cli import _input

        snapshot = service.resume(args.run_id, input=_input(args.input))
    elif args.command == "stop-bundle":
        snapshot = service.stop(args.run_id, reason=args.reason).snapshot
    elif args.command == "status-bundle":
        snapshot = service.inspect(args.run_id).snapshot
        return CommandResult(
            CommandStatus.COMPLETED, data={"run": snapshot_data(snapshot)}
        )
    elif args.command == "get-result-bundle":
        return CommandResult(
            CommandStatus.COMPLETED, data={"candidate": service.result(args.run_id)}
        )
    elif args.command == "approve-bundle":
        result = approve_pdf_candidate(
            args.manifest,
            service.result(args.run_id),
            candidate_digest=args.candidate_digest,
            confirm_reviewed=args.confirm_reviewed,
            output_dir=args.output_dir,
        )
        return CommandResult(CommandStatus.COMPLETED, data=result)
    else:
        raise ValueError("Unknown PDF bundle command")
    return command_result_from_snapshot(snapshot)

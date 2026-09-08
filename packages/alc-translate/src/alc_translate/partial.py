"""Read-only partial delivery from completed, source-bound translation units."""
from pathlib import Path
import hashlib
from ac_jobs import RunContext, atomic_write_bytes, canonical_json_bytes
from alc_render import Publication, decode_fragment_revision, write_fragment_revision, write_layer, write_publication, render_publication_html
from .workflow import TranslationResult


def render_partial_translation(project, service, snapshot):
    if project.current_step != "blocks":
        return None
    context = RunContext(service.repository, snapshot, resume_input=None)
    candidate_id = "translation/partial-result.json"
    if context.working.find_candidate(candidate_id) is None:
        return None
    saved = context.working.read_candidate_json(candidate_id)
    if saved.get("schema_version") != "alc.translate.partial_result.v1":
        raise ValueError("Invalid partial translation marker")
    source = service.request_source(snapshot.run_id).rich
    result = TranslationResult.from_document(saved["result"])
    from alc_render import source_identity_from_rich_document
    if result.layer.source != source_identity_from_rich_document(source):
        raise ValueError("Partial translation source mismatch")
    payloads = service.revision_payloads(snapshot.run_id, result)
    identity = hashlib.sha256(canonical_json_bytes(saved)).hexdigest()
    root = context.run_directory / "partial-reader"
    workspace = root / "snapshots" / identity
    workspace.mkdir(parents=True, exist_ok=True)
    for item, payload in zip(result.revision_artifacts, payloads, strict=True):
        revision = decode_fragment_revision(payload.decode(), filename=Path(item.revision.path).name)
        write_fragment_revision(workspace, revision)
    write_layer(workspace / "translation.json", result.layer)
    publication = Publication(source, layers=(result.layer.reference("translation.json"),),
        reader_profile={"title":"翻译（部分结果）", "build_state":"partial",
            "source_language":result.source_language,"target_language":result.target_language})
    write_publication(workspace / "publication.json", publication)
    def asset(digest):
        path = project.root / "resources" / digest
        if path.is_file() and path.resolve().is_relative_to(project.root.resolve()):
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() == digest:
                return data
        return None
    html = workspace / "reader.html"
    render_publication_html(workspace / "publication.json", html, asset_loader=asset)
    data = html.read_bytes()
    atomic_write_bytes(root / "companion.html", data)
    ids = set(saved["block_ids"])
    state = {"schema_version":"alc.companion.partial_reader.v1",
        "sha256":hashlib.sha256(data).hexdigest(), "unit_label":"段落",
        "completed_chapters":len(ids), "total_chapters":len(source.blocks),
        "incomplete_chapters":[f"第{b.ordinal+1}段" for b in source.blocks if b.block_id not in ids]}
    atomic_write_bytes(root / "state.json", canonical_json_bytes(state))
    return str(root / "companion.html")

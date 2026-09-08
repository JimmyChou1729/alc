"""Explicit acquisition and input staging for learning jobs."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from ac_document import (
    AcDocumentService,
    HTMLSourceAcquisitionService,
    materialize_html_source_bundle,
)


class NeedsSourceInput(ValueError):
    pass


class PDFTextConfirmation(NeedsSourceInput):
    pass


def normalize_source_url(value: str) -> str:
    value = value.strip()
    if value.startswith("doi:"):
        value = value[4:]
    if re.fullmatch(r"10\.\d{4,9}/\S+", value):
        value = "https://doi.org/" + quote(value, safe="/().-_:;")
    identifier = re.sub(r"^arxiv:\s*", "", value, flags=re.IGNORECASE)
    if re.fullmatch(r"(?:[0-9]{4}\.[0-9]{4,5}|[a-zA-Z-]+(?:\.[A-Z]{2})?/[0-9]{7})(?:v[1-9][0-9]*)?", identifier):
        value = "https://arxiv.org/html/" + quote(identifier, safe="/.")
    parts = urlsplit(value)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.password
    ):
        raise ValueError("Use a public HTTPS document URL, DOI, or arXiv identifier.")
    return value


def acquire(store, job: dict, checkpoint) -> tuple[Path, Path | None, list[str]]:
    root = store.job_directory(job["id"])
    root.mkdir(parents=True, exist_ok=True)
    record = root / "source.json"
    if record.exists():
        info = json.loads(record.read_text())
        path = root / info["path"]
        if (
            not path.resolve().is_relative_to(root.resolve())
            or hashlib.sha256(path.read_bytes()).hexdigest() != info["sha256"]
        ):
            raise ValueError("Frozen source bytes no longer match this job.")
        return (
            path,
            root / info["manifest"] if info.get("manifest") else None,
            info["warnings"],
        )
    warnings, manifest = [], None
    pending_pdf = root / "pending-pdf.json"
    if pending_pdf.exists():
        info = json.loads(pending_pdf.read_text())
        path = (root / info["path"]).resolve()
        if (
            not path.is_relative_to(root.resolve())
            or hashlib.sha256(path.read_bytes()).hexdigest() != info["sha256"]
        ):
            raise ValueError("Frozen PDF bytes no longer match this job.")
    elif job["spec"].get("source_id"):
        source = store.source(job["spec"]["source_id"])
        original = store.root / source["path"]
        if not original.resolve().is_relative_to((store.root / "uploads").resolve()):
            raise ValueError("Uploaded source is outside its staging directory.")
        if hashlib.sha256(original.read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError("Uploaded source digest changed.")
        destination = root / "input"
        shutil.copytree(original.parent, destination, dirs_exist_ok=True)
        path = destination / original.name
    else:
        url = normalize_source_url(job["spec"]["source_url"])
        service = HTMLSourceAcquisitionService(
            cache_root=store.project / ".ac" / "cache" / "ac-document"
        )
        response, final_url = service.fetch_resource(url)
        checkpoint()
        media = (
            response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        )
        if media in {"text/html", "application/xhtml+xml"}:
            bundle = service.materialize_response(response, requested_url=url)
            destination = root / "html-source"
            if destination.exists():
                from ac_document import verify_html_source_bundle_export

                verify_html_source_bundle_export(destination)
            else:
                materialize_html_source_bundle(
                    bundle, storage=service.storage, output_dir=destination
                )
            path, manifest = destination / "source.html", destination / "manifest.json"
            warnings.extend(w.message for w in bundle.warnings)
        elif media == "application/pdf" and response.body.startswith(b"%PDF-"):
            path = root / "source.pdf"
            path.write_bytes(response.body)
        elif media in {"text/markdown", "text/plain"}:
            path = root / "source.md"
            path.write_bytes(response.body)
        else:
            raise NeedsSourceInput(
                "The URL did not return supported HTML, Markdown or PDF. Upload a local source."
            )
        store.event(
            job["id"],
            "source.acquired",
            {"requested_url": url, "final_url": final_url, "media_type": media},
        )
        if urlsplit(url).hostname == "doi.org":
            warnings.append(
                "DOI redirects can return a publisher landing page. Check the source preview for full-text coverage."
            )
    checkpoint()
    if path.suffix.lower() == ".pdf":
        from ac_jobs.storage import atomic_write_json

        atomic_write_json(
            pending_pdf,
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            },
        )
        if (job.get("resume_input") or {}).get("pdf_text_only") is not True:
            raise PDFTextConfirmation(
                "This Web version can extract PDF text but does not preserve PDF images or verify formulas, tables or reading order. Choose text-only extraction explicitly, or create a task from HTML/OCR Markdown."
            )
        from ac_document.parse.parser import PdftotextExtractor

        layer = PdftotextExtractor().extract(path.read_bytes())
        if not layer.pages or any(not page.strip() for page in layer.pages):
            raise NeedsSourceInput(
                "This PDF has pages without a text layer. Automatic OCR is not available in this Web version. Create a task from externally prepared OCR Markdown or HTML."
            )
        text_path = root / "pdf-text.md"
        notice = "> PDF text-only derivative: original images are not included. Reading order, formulas and tables have not been verified.\n\n"
        text_path.write_text(
            notice
            + "\n\n".join(
                f"<!-- Source PDF page {i} -->\n\n{page}"
                for i, page in enumerate(layer.pages, 1)
            ),
            encoding="utf-8",
        )
        warnings.append(
            "PDF text-only derivative: images are not included; reading order, formulas and tables are unverified. This is not OCR proofreading."
        )
        path = text_path
    _validate_resource_paths(path)
    info = {
        "path": path.relative_to(root).as_posix(),
        "manifest": manifest.relative_to(root).as_posix() if manifest else None,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "warnings": warnings,
    }
    from ac_jobs.storage import atomic_write_json

    atomic_write_json(record, info)
    return path, manifest, warnings


def _validate_resource_paths(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if len(text.encode()) > 20 * 1024 * 1024:
        raise ValueError("Readable source exceeds 20 MiB.")
    if path.suffix.lower() == ".tex":
        targets = re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^{}]+)\}", text)
    elif path.suffix.lower() in {".html", ".htm"}:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(text, "html.parser")
        # Match ac-document's content roots; site chrome is not imported as assets.
        roots = [
            node
            for node in soup.find_all("article")
            if node.find_parent("article") is None
        ] or [soup.body or soup]
        targets = [
            tag.get(attr, "")
            for root in roots
            for tag in root.find_all(["img", "object", "source"])
            for attr in ("src", "data")
            if tag.get(attr)
        ]
    else:
        from markdown_it import MarkdownIt

        targets = [
            child.attrGet("src")
            for token in MarkdownIt().parse(text)
            for child in token.children or []
            if child.type == "image"
        ]
    for target in targets:
        parsed = urlsplit(target)
        if parsed.scheme in {"https", "http", "data"}:
            continue
        decoded = unquote(parsed.path)
        if (
            parsed.scheme
            or decoded.startswith("/")
            or not (path.parent / decoded)
            .resolve()
            .is_relative_to(path.parent.resolve())
        ):
            raise NeedsSourceInput(
                "A local resource points outside the uploaded folder. Include its assets using safe relative paths."
            )

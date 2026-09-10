from __future__ import annotations

import hashlib
import runpy
from pathlib import Path

import pytest
from ac_document import PDFSourceBundleError, verify_pdf_source_bundle
from alc_ocr_proofread.pdf_bundle import _HTML, _visible_text, candidate_digest
from alc_ocr_proofread.pdf_bundle_delivery import adopt_pdf_candidate
from alc_ocr_proofread.pdf_bundle_edit import editable_candidate, revise_candidate

bundle = runpy.run_path(str(Path(__file__).with_name("test_pdf_bundle.py")))["bundle"]


def candidate(manifest):
    info = verify_pdf_source_bundle(manifest)
    source = (manifest.parent / info["source"]["path"]).read_text()
    corrected = source.replace("Helo", "Hello")
    old, new = _HTML(source, info), _HTML(corrected, info)
    value = dict(
        status="reviewable",
        proofread=False,
        approval_required=True,
        original_bundle_digest=info["bundle_digest"],
        pdf_sha256=info["original"]["sha256"],
        source_sha256=info["source"]["sha256"],
        original_html=source,
        corrected_html=corrected,
        corrected_sha256=hashlib.sha256(corrected.encode()).hexdigest(),
        uncertainty_count=1,
        change_count=2,
        pages=[
            dict(
                page_number=i,
                original_html=old.fragment(i),
                corrected_html=new.fragment(i),
                original_text=_visible_text(old.fragment(i)),
                corrected_text=_visible_text(new.fragment(i)),
                edits=[],
                uncertainties=[dict(excerpt="Header", reason="Missing header")]
                if i == 1
                else [],
            )
            for i in (1, 2)
        ],
    )
    value["candidate_digest"] = candidate_digest(value)
    return value


def test_edit_roundtrip_preserves_structure_and_audit(tmp_path):
    manifest = bundle(tmp_path)
    original = candidate(manifest)
    ui = editable_candidate(manifest, original)
    assert ui["pages"][0]["segments"][0]["id"] == "1:0"
    revised = revise_candidate(
        manifest,
        original,
        edits={"1:0": "Hello <world> & welcome "},
        resolutions={"1:0": "corrected"},
    )
    assert "&lt;world&gt; &amp;" in revised["corrected_html"]
    assert revised["uncertainty_count"] == 0
    assert revised["pages"][0]["uncertainties"][0]["resolution"] == "corrected"
    assert revised["base_candidate_digest"] == original["candidate_digest"]
    assert original["uncertainty_count"] == 1
    assert revised["candidate_digest"] == candidate_digest(revised)
    reset = revise_candidate(manifest, original, edits={}, resolutions={})
    assert reset["corrected_html"] == original["corrected_html"]


@pytest.mark.parametrize(
    "edits,resolutions",
    [
        ({"bad": "text"}, {}),
        ({"1:0": ""}, {}),
        ({"1:0": 5}, {}),
        ({}, {"1:99": "accepted"}),
        ({}, {"1:0": "fixed"}),
        ({}, {"1:0": "corrected"}),
    ],
)
def test_invalid_manual_input(tmp_path, edits, resolutions):
    manifest = bundle(tmp_path)
    with pytest.raises(PDFSourceBundleError):
        revise_candidate(
            manifest, candidate(manifest), edits=edits, resolutions=resolutions
        )


def test_accept_uncertainty_is_explicit_and_audited(tmp_path):
    manifest = bundle(tmp_path)
    value = candidate(manifest)
    revised = revise_candidate(
        manifest, value, edits={}, resolutions={"1:0": "accepted"}
    )
    assert revised["corrected_html"] == value["corrected_html"]
    assert revised["manual_resolutions"] == {"1:0": "accepted"}
    assert revised["uncertainty_count"] == 0


@pytest.mark.parametrize(
    "tamper", ["digest", "binding", "fragment", "structure", "resolution", "count"]
)
def test_tampered_candidate_rejected(tmp_path, tamper):
    manifest = bundle(tmp_path)
    value = candidate(manifest)
    if tamper == "digest":
        value["change_count"] = 100
    elif tamper == "binding":
        value["pdf_sha256"] = "0" * 64
    elif tamper == "fragment":
        value["pages"][0]["corrected_html"] = "bad"
    elif tamper == "structure":
        value["corrected_html"] = value["corrected_html"].replace('id="p1"', 'id="bad"')
        value["corrected_sha256"] = hashlib.sha256(
            value["corrected_html"].encode()
        ).hexdigest()
    elif tamper == "resolution":
        value["pages"][0]["uncertainties"][0]["resolution"] = "accepted"
        value["uncertainty_count"] = 0
    else:
        value["uncertainty_count"] = 0
    if tamper != "digest":
        value["candidate_digest"] = candidate_digest(value)
    with pytest.raises(PDFSourceBundleError):
        editable_candidate(manifest, value)


def test_adoption_mode_receipts(tmp_path, monkeypatch):
    manifest = bundle(tmp_path)
    value = candidate(manifest)
    captured = []
    monkeypatch.setattr(
        "alc_ocr_proofread.pdf_bundle_delivery.publish_reviewed_pdf_source",
        lambda *a, **kw: captured.append(kw),
    )
    adopt_pdf_candidate(
        manifest,
        value,
        candidate_digest=value["candidate_digest"],
        output_dir=tmp_path / "out",
    )
    assert captured[-1]["review"]["reviewer"] == "model"
    assert captured[-1]["review"]["approved"] is False
    assert captured[-1]["review"]["uncertainty_count"] == 1
    with pytest.raises(PDFSourceBundleError):
        adopt_pdf_candidate(
            manifest,
            value,
            candidate_digest=value["candidate_digest"],
            output_dir=tmp_path / "out",
            mode="user",
            confirm_reviewed=True,
        )
    revised = revise_candidate(
        manifest, value, edits={}, resolutions={"1:0": "accepted"}
    )
    adopt_pdf_candidate(
        manifest,
        revised,
        candidate_digest=revised["candidate_digest"],
        output_dir=tmp_path / "out",
        mode="user",
        confirm_reviewed=True,
    )
    assert captured[-1]["review"]["approved"] is True


def test_math_and_image_alt_edits_preserve_resource_binding(tmp_path):
    manifest = bundle(tmp_path)
    value = candidate(manifest)
    enriched = editable_candidate(manifest, value)
    by_kind = {s["kind"]: s for p in enriched["pages"] for s in p["segments"]}
    revised = revise_candidate(
        manifest,
        value,
        edits={
            by_kind["math_alttext"]["id"]: 'x="1"',
            by_kind["image_alt"]["id"]: "Diagram <A>",
        },
        resolutions={},
    )
    assert 'alttext="x=&quot;1&quot;"' in revised["corrected_html"]
    assert 'src="assets/figure.png"' in revised["corrected_html"]
    assert 'alt="Diagram &lt;A&gt;"' in revised["corrected_html"]
    assert revised["uncertainty_count"] == 1


def test_empty_original_alt_can_be_restored_as_noop(tmp_path):
    manifest = bundle(tmp_path, pages=['<p id="p1">Helo</p>', '<figure id="p2"><img src="assets/figure.png" alt=""><figcaption>Caption</figcaption></figure>'])
    base = candidate(manifest)
    current = editable_candidate(manifest, base)
    segment = next(s for p in current['pages'] for s in p['segments'] if s['kind'] == 'image_alt')
    assert segment['corrected_text'] == ''
    result = revise_candidate(manifest, base, edits={segment['id']:''}, resolutions={})
    assert result['corrected_html'] == base['corrected_html']
    assert result['manual_edits'] == {}

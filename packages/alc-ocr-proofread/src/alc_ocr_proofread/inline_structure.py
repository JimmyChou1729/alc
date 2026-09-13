"""Exact anchored inline repairs; model output never supplies executable markup."""

from __future__ import annotations


POLICY = "anchored-typed.v1"


def object_schema(properties):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


PROPOSAL_SCHEMA = object_schema(
    {
        "proposal_id": {"type": "string", "minLength": 1, "maxLength": 80},
        "anchor_id": {"type": "string", "minLength": 1},
        "before_html": {"type": "string", "minLength": 1, "maxLength": 4000},
        "after": {
            "type": "array",
            "minItems": 1,
            "maxItems": 20,
            "items": object_schema(
                {
                    "kind": {"enum": ["text", "math", "sup"]},
                    "value": {"type": "string", "minLength": 1, "maxLength": 4000},
                }
            ),
        },
        "reason": {"type": "string", "minLength": 1},
    }
)
VERIFY_SCHEMA = object_schema(
    {
        "decisions": {
            "type": "array",
            "items": object_schema(
                {
                    "proposal_id": {"type": "string"},
                    "approved": {"type": "boolean"},
                    "reason": {"type": "string", "minLength": 1},
                }
            ),
        }
    }
)
PROMPT = """You may additionally propose bounded inline OCR structural repairs in structure_proposals.
Only an existing uniquely id-anchored p on this page is eligible. Combine all repairs
within one paragraph into a single proposal; repeated anchor IDs are all rejected. before_html is an
exact nonempty continuous sequence of direct child text/math/sup markup from that
paragraph, copied verbatim from source HTML. after is a sequence of typed values:
text for plain text, math for LaTeX alttext, sup for plain superscript footnote text.
No raw HTML is accepted as output values. Preserve surrounding text, all IDs/resources,
all paragraphs and page boundaries. Use this for split/missing inline math, literal
superscript markup, or punctuation requiring replacement across inline nodes. Never
reconstruct whole paragraphs or alter the author's content. Propose only visually
certain transcription fixes; an independent image check will decide each proposal.
If no eligible repair is needed return structure_proposals: [].
"""


def apply_proposal(source, bundle, page, proposal):
    from .pdf_bundle import PDFBundleProofreadError

    try:
        from ac_document.pdf_inline import apply_inline_repair
    except ImportError:
        raise PDFBundleProofreadError(
            "inline_structure_unavailable",
            "Installed document runtime does not support bounded inline repairs.",
        ) from None
    return apply_inline_repair(source, bundle, page, proposal)

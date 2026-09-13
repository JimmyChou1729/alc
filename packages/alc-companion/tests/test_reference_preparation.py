import copy
import pytest
from alc_companion.reference_preparation import validate_reference_preparation
from alc_companion.generation_validation import CompanionContentError


def prepared():
    return {"coverage_summary": "One supplementary claim was verified.",
            "references": [{"title": "Source", "source": "https://example.test/source"}],
            "explanations": [{"part_number": 1, "claim": "Supplement", "basis": "external_verified",
                              "reference_numbers": [1], "support": "The inspected text supports the claim."}]}


def test_verified_claim_requires_a_bound_reference():
    raw = prepared()
    assert validate_reference_preparation(raw, part_count=2) == raw
    raw['explanations'][0]['reference_numbers'] = []
    with pytest.raises(CompanionContentError):
        validate_reference_preparation(raw, part_count=2)


@pytest.mark.parametrize('change', ['part', 'number', 'unreferenced', 'unsupported', 'boolean'])
def test_invalid_evidence_mapping_is_rejected(change):
    raw = prepared()
    if change == 'part': raw['explanations'][0]['part_number'] = 3
    if change == 'number': raw['explanations'][0]['reference_numbers'] = [2]
    if change == 'unreferenced': raw['explanations'] = []
    if change == 'unsupported': raw['explanations'][0]['basis'] = 'unresolved'
    if change == 'boolean': raw['explanations'][0]['reference_numbers'] = [True]
    with pytest.raises(CompanionContentError):
        validate_reference_preparation(raw, part_count=2)


def test_empty_references_allowed_with_explicit_source_grounded_basis():
    raw = {'coverage_summary': 'Only source derivations are useful.', 'references': [],
           'explanations': [{'part_number': 1, 'claim': 'Derive equation from supplied assumptions.',
                             'basis': 'source_grounded', 'reference_numbers': [], 'support': 'Supplied equation.'}]}
    original = copy.deepcopy(raw)
    assert validate_reference_preparation(raw, part_count=1) == original
    assert raw == original

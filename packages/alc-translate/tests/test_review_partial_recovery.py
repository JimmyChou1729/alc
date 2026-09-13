import pytest
from alc_translate.workflow import (_salvage_text_slot_review, _validate_model_protected_atom_window,
    _translation_review_windows, TranslationWorkflowError)
from alc_translate.atoms import source_protected_parts
from alc_translate.workflow import PROTECTED_ATOM_RESULT_SCHEMA, TEXT_SLOT_REVIEW_RESULT_SCHEMA


def data(n):
    blocks=[{'block_id':f'b{i}','kind':'paragraph','ordinal':i,'section_path':[],
             'payload':{'text':'Meaningful sentence.'}} for i in range(n)]
    draft=_validate_model_protected_atom_window({'schema_version':PROTECTED_ATOM_RESULT_SCHEMA,
        'translations':[{'block_id':b['block_id'],'parts':source_protected_parts(b)} for b in blocks]},blocks)
    return blocks,draft


def test_only_invalid_patch_keeps_prereview_translation():
    blocks,draft=data(3)
    value={'schema_version':TEXT_SLOT_REVIEW_RESULT_SCHEMA,'summary':'Reviewed all three',
           'translation_patches':{'b0':{'text_slots':{'b0.text-000000':'正确译文。'}},'b1':{'text_slots':{}}}}
    accepted,rejected=_salvage_text_slot_review(value,draft,blocks)
    assert rejected==['b1']
    assert accepted[0]['text']=='正确译文。'
    assert accepted[1:]==draft[1:]
    value['translation_patches']['unknown']={'text_slots':{}}
    with pytest.raises(TranslationWorkflowError):_salvage_text_slot_review(value,draft,blocks)


def test_review_batches_have_bounded_failure_scope():
    blocks,draft=data(22)
    windows=_translation_review_windows(blocks,draft,glossary=[],target_language='zh-CN',window_ordinal=0,budget_bytes=1000000)
    assert [len(b) for b,d in windows]==[8,8,6]
    assert [x['block_id'] for b,d in windows for x in b]==[x['block_id'] for x in blocks]

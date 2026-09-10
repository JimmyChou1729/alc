from dataclasses import replace
import pytest
from ac_document import AcDocumentService, RichDocumentParserService
from alc_companion.request_contracts import CompanionBuildRequest, encode_build_request, decode_build_request
from alc_companion.source_planning import plan_source_chapters, validate_chapter_coverage


def source(tmp_path):
    p=tmp_path/'paper.html'
    p.write_text('<article><h1>Paper title</h1><p>Abstract text.</p><h2>1 Introduction</h2><p>Intro.</p>'
                 '<h2>2 Methods</h2><h3>2.1 Details</h3><p>Method.</p><h2>References</h2><p>Reference.</p>'
                 '<h2>Appendix A</h2><p>Supplement.</p></article>')
    doc=AcDocumentService(cache_root=tmp_path/'cache')
    return RichDocumentParserService(doc.repository).parse_source(doc.import_source(p))


def test_explicit_heading_level_keeps_source_and_complete_coverage(tmp_path):
    doc=source(tmp_path)
    assert len(plan_source_chapters(doc))==1
    chapters=plan_source_chapters(doc,chapter_heading_level=2)
    assert [x.title for x in chapters]==['1 Introduction','2 Methods','References','Appendix A']
    assert [x.generate_guide for x in chapters]==[True,True,False,True]
    assert [bid for c in chapters for bid in c.block_ids]==[b.block_id for b in doc.blocks]
    validate_chapter_coverage(doc,chapters)
    request=CompanionBuildRequest(doc)
    legacy=encode_build_request(request)
    assert 'chapter_heading_level' not in legacy
    explicit=replace(request,chapter_heading_level=2)
    encoded=encode_build_request(explicit)
    assert encoded['schema_version']=='alc.companion.build_request.v10'
    assert encode_build_request(decode_build_request(encoded))==encoded
    assert encode_build_request(decode_build_request(legacy))==legacy


@pytest.mark.parametrize('level',[0,7,True,1.5])
def test_invalid_heading_level_rejected(tmp_path,level):
    doc=source(tmp_path)
    with pytest.raises(ValueError):CompanionBuildRequest(doc,chapter_heading_level=level)
    with pytest.raises(ValueError):plan_source_chapters(doc,chapter_heading_level=level)


def test_missing_heading_level_does_not_silently_use_single_chapter(tmp_path):
    with pytest.raises(ValueError,match='absent'):
        plan_source_chapters(source(tmp_path),chapter_heading_level=6)


def test_heading_only_chapter_retains_coverage_without_guide(tmp_path):
    from alc_companion.source_planning import _chapter
    from ac_document.rich_document.models import RichBlockKind
    doc = source(tmp_path)
    headings = tuple(b for b in doc.blocks if b.kind is RichBlockKind.HEADING)
    assert not _chapter(doc, title='Title', blocks=headings).generate_guide
    assert _chapter(doc, title='Body', blocks=doc.blocks).generate_guide

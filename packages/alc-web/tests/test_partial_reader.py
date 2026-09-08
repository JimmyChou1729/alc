import hashlib
import json
from pathlib import Path
import pytest
from alc_web.store import Store
from alc_web.worker import Worker


def test_partial_delivery_keeps_paused_state_and_checks_bytes(tmp_path):
    store=Store(tmp_path)
    job=store.create({})
    store.update(job['id'],state='needs_input')
    worker=Worker.__new__(Worker)
    worker.store=store;worker.job_id=job['id'];worker.root=store.job_directory(job['id'])
    root=worker.root/'project'/'partial-reader';root.mkdir(parents=True)
    html=root/'companion.html';html.write_text('<html>部分结果</html>')
    state={'schema_version':'alc.companion.partial_reader.v1','sha256':hashlib.sha256(html.read_bytes()).hexdigest(),
        'completed_chapters':1,'total_chapters':2,'incomplete_chapters':['第二章']}
    (root/'state.json').write_text(json.dumps(state))
    result={'data':{'progress':{'partial_reader_path':str(html)}}}
    worker.capture_partial(result)
    saved=store.get(job['id'])
    assert saved['state']=='needs_input'
    assert saved['result']['partial'] is True
    assert (tmp_path/saved['result']['reader']).read_bytes()==html.read_bytes()
    html.write_text('changed')
    with pytest.raises(ValueError,match='integrity'):
        worker.capture_partial(result)
    outside=tmp_path/'outside'/'partial-reader'/'companion.html'
    with pytest.raises(ValueError,match='outside'):
        worker.capture_partial({'data':{'progress':{'partial_reader_path':str(outside)}}})

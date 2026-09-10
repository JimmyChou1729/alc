import json
from alc_catalog.mineru import default_config_path, effective_config_path, remember_local_config


def test_default_used_only_when_project_unconfigured(tmp_path):
    executable=tmp_path/'mineru';executable.write_text('#!/bin/sh\n');executable.chmod(0o700)
    value={'executable':str(executable),'language':'en'}
    assert remember_local_config(value)
    project=tmp_path/'new'
    assert effective_config_path(project)==default_config_path()
    own=project/'.ac/mineru.json';own.parent.mkdir(parents=True);own.write_text('bad config')
    assert effective_config_path(project)==own
    assert not remember_local_config(value, overwrite=False)


def test_remote_and_missing_executables_not_inherited(tmp_path):
    assert not remember_local_config({'api_url':'https://example.test','executable':None})
    assert not remember_local_config({'executable':str(tmp_path/'missing')})
    path=default_config_path();path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'api_url':'https://example.test','executable':'/bin/sh'}))
    assert effective_config_path(tmp_path)==tmp_path/'.ac/mineru.json'
